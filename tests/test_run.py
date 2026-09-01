"""Subprocess-wrapper tests. Every test that needs the real binary is skipped
when msolve is not installed."""

from __future__ import annotations

import shutil

import pytest

from msolveio import (
    MsolveDied,
    MsolveTimeout,
    MsolveVersionUnsupported,
    emit_system,
    run_groebner,
)
from msolveio import run as run_module

MSOLVE = shutil.which("msolve")
needs_msolve = pytest.mark.skipif(MSOLVE is None, reason="msolve binary not on PATH")


@needs_msolve
def test_unit_ideal_over_q() -> None:
    source = emit_system(["x-1", "x"], variables=["x", "y"])
    result = run_groebner(source, timeout=60)
    assert result.output.unit_ideal is True
    assert result.output.basis == ("1",)
    assert result.returncode == 0
    assert result.msolve_version.startswith("0.10.")
    assert result.wall_seconds >= 0
    assert len(result.input_sha256) == 64
    assert len(result.output_sha256) == 64
    assert "-g" in result.argv and "2" in result.argv


@needs_msolve
def test_nonempty_ideal_is_not_unit() -> None:
    source = emit_system(["x^2-1"], variables=["x"])
    result = run_groebner(source, timeout=60)
    assert result.output.unit_ideal is False
    assert result.output.basis == ("x^2-1",)


@needs_msolve
def test_leading_ideal_mode() -> None:
    source = emit_system(["x-1", "y^2-x"], variables=["x", "y"])
    result = run_groebner(source, gb=1, timeout=60)
    assert result.output.leading_only is True
    assert result.output.unit_ideal is False


@needs_msolve
def test_prime_field() -> None:
    source = emit_system(["x^2-1"], variables=["x"], characteristic=65521)
    result = run_groebner(source, timeout=60)
    assert result.output.characteristic == 65521


@needs_msolve
def test_bad_input_makes_msolve_die_not_lie() -> None:
    with pytest.raises((MsolveDied, MsolveTimeout)):
        run_groebner("this is not an msolve file\n", timeout=60)


def test_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_module.shutil, "which", lambda _name: None)
    with pytest.raises(MsolveDied, match="no msolve binary"):
        run_groebner("x\n0\nx-1\n", timeout=10)


def test_version_gate_rejects_non_010(tmp_path) -> None:
    fake = tmp_path / "fake-msolve"
    fake.write_text("#!/bin/sh\necho 0.9.9\n")
    fake.chmod(0o755)
    with pytest.raises(MsolveVersionUnsupported) as excinfo:
        run_groebner("x\n0\nx-1\n", timeout=10, binary=fake)
    assert excinfo.value.version == "0.9.9"


def test_unparseable_version_rejected(tmp_path) -> None:
    fake = tmp_path / "fake-msolve"
    fake.write_text("#!/bin/sh\necho no version here\n")
    fake.chmod(0o755)
    with pytest.raises(MsolveVersionUnsupported):
        run_groebner("x\n0\nx-1\n", timeout=10, binary=fake)


def test_allow_unknown_version_bypasses_gate(tmp_path) -> None:
    """Version gate off: the run proceeds and fails later, on the real problem."""
    fake = tmp_path / "fake-msolve"
    fake.write_text("#!/bin/sh\nexit 3\n")
    fake.chmod(0o755)
    with pytest.raises(MsolveDied) as excinfo:
        run_groebner(
            "x\n0\nx-1\n", timeout=10, binary=fake, allow_unknown_version=True
        )
    assert excinfo.value.returncode == 3


def test_nonzero_exit_reported(tmp_path) -> None:
    fake = tmp_path / "fake-msolve"
    fake.write_text("#!/bin/sh\nif [ \"$1\" = --version ]; then echo 0.10.1; exit 0; fi\necho boom >&2\nexit 7\n")
    fake.chmod(0o755)
    with pytest.raises(MsolveDied) as excinfo:
        run_groebner("x\n0\nx-1\n", timeout=10, binary=fake)
    assert excinfo.value.returncode == 7
    assert "boom" in excinfo.value.stderr


def test_signal_reported(tmp_path) -> None:
    fake = tmp_path / "fake-msolve"
    fake.write_text(
        "#!/bin/sh\nif [ \"$1\" = --version ]; then echo 0.10.1; exit 0; fi\nkill -SEGV $$\n"
    )
    fake.chmod(0o755)
    with pytest.raises(MsolveDied) as excinfo:
        run_groebner("x\n0\nx-1\n", timeout=10, binary=fake)
    assert excinfo.value.signal == 11


def test_empty_output_file_is_death_not_a_unit_ideal(tmp_path) -> None:
    fake = tmp_path / "fake-msolve"
    fake.write_text("#!/bin/sh\nif [ \"$1\" = --version ]; then echo 0.10.1; exit 0; fi\nexit 0\n")
    fake.chmod(0o755)
    with pytest.raises(MsolveDied, match="no output"):
        run_groebner("x\n0\nx-1\n", timeout=10, binary=fake)


def test_timeout(tmp_path) -> None:
    fake = tmp_path / "fake-msolve"
    fake.write_text(
        "#!/bin/sh\nif [ \"$1\" = --version ]; then echo 0.10.1; exit 0; fi\nsleep 30\n"
    )
    fake.chmod(0o755)
    with pytest.raises(MsolveTimeout) as excinfo:
        run_groebner("x\n0\nx-1\n", timeout=1.0, binary=fake)
    assert excinfo.value.timeout == 1.0


@pytest.mark.parametrize("gb", [0, 3, "2", None])
def test_invalid_gb(gb) -> None:
    with pytest.raises(ValueError):
        run_groebner("x\n0\nx-1\n", gb=gb, timeout=10, binary="/bin/false")


@pytest.mark.parametrize("timeout", [0, -1])
def test_invalid_timeout(timeout) -> None:
    with pytest.raises(ValueError):
        run_groebner("x\n0\nx-1\n", timeout=timeout, binary="/bin/false")


def test_invalid_threads() -> None:
    with pytest.raises(ValueError):
        run_groebner("x\n0\nx-1\n", timeout=10, threads=0, binary="/bin/false")
