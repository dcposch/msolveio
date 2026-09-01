"""Subprocess wrapper around the msolve CLI.

Runs msolve with stdin closed, a mandatory timeout, and a version gate, then
hands the output to :func:`msolveio.parse_groebner`. Nothing here interprets
msolve's bytes itself.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import MsolveDied, MsolveTimeout, MsolveVersionUnsupported
from .mode import Mode
from .parse import GroebnerOutput, parse_groebner

__all__ = ["RunResult", "run_groebner", "SUPPORTED_VERSION_PREFIX"]

#: The only msolve series v0.1 claims to understand.
SUPPORTED_VERSION_PREFIX = "0.10."

_VERSION_RE = re.compile(r"\b(\d+\.\d+(?:\.\d+)?)\b")
_VERSION_PROBE_TIMEOUT = 20.0


@dataclass(frozen=True)
class RunResult:
    """Everything one msolve invocation produced, plus how it was produced.

    :param output: the parsed Groebner basis.
    :param argv: the exact command line, with the temp paths msolve saw.
    :param msolve_version: the version string reported by ``msolve --version``,
        or ``"unknown"`` when the probe failed under ``allow_unknown_version``.
    :param wall_seconds: wall-clock time for the solve, excluding the probe.
    :param returncode: msolve's exit status.
    :param stderr: msolve's captured stderr.
    :param input_sha256: SHA-256 of the ``.ms`` bytes written to disk.
    :param output_sha256: SHA-256 of the output-file bytes read back.
    """

    output: GroebnerOutput
    argv: tuple[str, ...]
    msolve_version: str
    wall_seconds: float
    returncode: int
    stderr: str
    input_sha256: str
    output_sha256: str


def run_groebner(
    source: str,
    *,
    gb: Literal[1, 2] = 2,
    timeout: float,
    threads: int = 1,
    binary: str | Path | None = None,
    allow_unknown_version: bool = False,
    mode: Mode = Mode.GROEBNER,
) -> RunResult:
    """Run msolve in Groebner mode on ``source`` and parse the result.

    :param source: msolve input text, normally from :func:`msolveio.emit_system`.
    :param gb: ``2`` for the reduced Groebner basis, ``1`` for the leading ideal.
    :param timeout: wall-clock limit in seconds. Required; there is no default,
        because an unbounded Groebner computation is not a thing to opt into by
        accident.
    :param threads: value for msolve's ``-t``.
    :param binary: path to the msolve executable. Defaults to
        ``shutil.which("msolve")``.
    :param allow_unknown_version: run anyway if the binary is not 0.10.x. The
        parser is written against 0.10.x output and may reject or misread others.
    :param mode: must be :attr:`Mode.GROEBNER`.
    :raises MsolveVersionUnsupported: if the version gate fails.
    :raises MsolveTimeout: if msolve exceeded ``timeout``.
    :raises MsolveDied: if msolve exited nonzero, took a signal, or wrote nothing.
    :raises MsolveOutputError: if msolve's output is not well-formed.
    """
    if mode is not Mode.GROEBNER:
        raise ValueError(f"unsupported mode {mode!r}; v0.1 runs Mode.GROEBNER only")
    if gb not in (1, 2):
        raise ValueError(f"gb must be 1 or 2, got {gb!r}")
    if not isinstance(threads, int) or isinstance(threads, bool) or threads < 1:
        raise ValueError(f"threads must be a positive int, got {threads!r}")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise TypeError(f"timeout must be a number, got {type(timeout).__name__}")
    if timeout <= 0:
        raise ValueError(f"timeout must be positive, got {timeout!r}")
    if not isinstance(source, str):
        raise TypeError(f"source must be str, got {type(source).__name__}")

    executable = _resolve_binary(binary)
    version = _check_version(executable, allow_unknown_version)

    payload = source.encode("utf-8")
    with tempfile.TemporaryDirectory(prefix="msolveio-") as tmp:
        in_path = Path(tmp) / "system.ms"
        out_path = Path(tmp) / "basis.out"
        in_path.write_bytes(payload)

        argv = (
            executable,
            "-g",
            str(gb),
            "-f",
            str(in_path),
            "-o",
            str(out_path),
            "-t",
            str(threads),
        )

        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MsolveTimeout(
                f"msolve exceeded the {timeout}s timeout and was killed",
                timeout=float(timeout),
            ) from exc
        except OSError as exc:
            raise MsolveDied(f"could not execute {executable!r}: {exc}") from exc
        wall_seconds = time.monotonic() - started

        stderr = completed.stderr.decode("utf-8", errors="replace")
        _check_exit(completed.returncode, argv, stderr)

        raw = out_path.read_bytes() if out_path.exists() else b""
        if not raw.strip():
            # Fall back to stdout: some builds print the basis rather than
            # writing it when the output file cannot be produced.
            raw = completed.stdout

    if not raw.strip():
        raise MsolveDied(
            "msolve exited 0 but produced no output",
            returncode=completed.returncode,
            stderr=stderr,
        )

    text = raw.decode("utf-8", errors="replace")
    output = parse_groebner(text, mode=mode)

    return RunResult(
        output=output,
        argv=argv,
        msolve_version=version,
        wall_seconds=wall_seconds,
        returncode=completed.returncode,
        stderr=stderr,
        input_sha256=hashlib.sha256(payload).hexdigest(),
        output_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _resolve_binary(binary: str | Path | None) -> str:
    if binary is None:
        found = shutil.which("msolve")
        if found is None:
            raise MsolveDied(
                "no msolve binary found on PATH; install msolve 0.10.x or pass "
                "binary=..."
            )
        return found
    return str(binary)


def _check_exit(returncode: int, argv: tuple[str, ...], stderr: str) -> None:
    if returncode == 0:
        return
    if returncode < 0:
        raise MsolveDied(
            f"msolve was killed by signal {-returncode}"
            + (f": {stderr.strip()[:200]}" if stderr.strip() else ""),
            returncode=returncode,
            signal=-returncode,
            stderr=stderr,
        )
    raise MsolveDied(
        f"msolve exited with status {returncode}"
        + (f": {stderr.strip()[:200]}" if stderr.strip() else ""),
        returncode=returncode,
        stderr=stderr,
    )


def _check_version(executable: str, allow_unknown_version: bool) -> str:
    """Probe ``msolve --version``. Returns the version string it reported."""
    try:
        probe = subprocess.run(
            [executable, "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=_VERSION_PROBE_TIMEOUT,
            check=False,
        )
        blob = (probe.stdout + b"\n" + probe.stderr).decode("utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        if allow_unknown_version:
            return "unknown"
        raise MsolveVersionUnsupported(
            f"could not determine the version of {executable!r}: {exc}. Pass "
            f"allow_unknown_version=True to run anyway."
        ) from exc

    match = _VERSION_RE.search(blob)
    if match is None:
        if allow_unknown_version:
            return "unknown"
        raise MsolveVersionUnsupported(
            f"{executable!r} did not report a recognizable version. Pass "
            f"allow_unknown_version=True to run anyway."
        )

    version = match.group(1)
    if not version.startswith(SUPPORTED_VERSION_PREFIX) and not allow_unknown_version:
        raise MsolveVersionUnsupported(
            f"msolve {version} is not supported; msolveio v0.1 targets "
            f"{SUPPORTED_VERSION_PREFIX}x output. Pass "
            f"allow_unknown_version=True to run anyway.",
            version=version,
        )
    return version
