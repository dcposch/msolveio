"""Strict parsing of msolve 0.10.x Groebner-mode (``-g 1`` / ``-g 2``) output.

msolve prints different languages in different modes, and they overlap
syntactically. Solver mode prints ``[-1]:`` to mean "no solutions"; Groebner
mode prints ``[1]:`` to mean "the unit ideal". Both are bracketed lists, and
mistaking one for the other inverts the answer. So the ``#`` comment header is
load-bearing here: it is the only thing that says which language the bytes are
in, and this module refuses to proceed without it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NoReturn

from .errors import MsolveAmbiguous, MsolveOutputError
from .mode import Mode

__all__ = ["GroebnerOutput", "parse_groebner"]

_GB_HEADER = "#Reduced Groebner basis data"
_LEADING_HEADER = "#Leading ideal data"
_SEPARATOR = "#---"

# `[1, <nvars>, -1, []]:` -- solver mode reporting an inconsistent system.
_SOLVER_EMPTY_RE = re.compile(r"\[\s*1\s*,\s*\d+\s*,\s*-1\s*,\s*\[\s*\]\s*\]\s*:")
_LENGTH_RE = re.compile(r"(\d+)\s+element")


@dataclass(frozen=True)
class GroebnerOutput:
    """A parsed msolve Groebner basis.

    :param unit_ideal: ``True`` iff the basis is exactly ``["1"]``, i.e. the
        ideal is the whole ring and the system has no solutions.
    :param basis: the basis polynomials as msolve printed them, stripped, with
        separating commas removed. ``("1",)`` for the unit ideal.
    :param leading_only: ``True`` iff this was ``-g 1`` output, so the entries
        are leading monomials rather than full basis elements.
    :param characteristic: the characteristic msolve printed. Note that msolve
        0.10.1 labels some unlifted rational bases as characteristic 0 whether
        or not a lift happened; this field reports what was printed, and nothing
        more.
    :param variables: the variable order msolve echoed back.
    :param monomial_order: the monomial order msolve printed, verbatim.
    """

    unit_ideal: bool
    basis: tuple[str, ...]
    leading_only: bool
    characteristic: int
    variables: tuple[str, ...]
    monomial_order: str


def parse_groebner(text: str, *, mode: Mode = Mode.GROEBNER) -> GroebnerOutput:
    """Parse msolve 0.10.x Groebner-mode output.

    :param text: the contents of msolve's ``-o`` file, or its stdout.
    :param mode: must be :attr:`Mode.GROEBNER`. Present so callers can state
        which output language they believe they have; v0.1 parses no other.
    :raises MsolveAmbiguous: if the bytes look like a different msolve mode.
    :raises MsolveOutputError: if the bytes are not well-formed Groebner output.
    """
    if mode is not Mode.GROEBNER:
        raise ValueError(f"unsupported mode {mode!r}; v0.1 parses Mode.GROEBNER only")
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    start = _first_content_line(lines)
    if start is None:
        raise MsolveOutputError("empty msolve output")

    header = lines[start].strip()
    if header.startswith(_GB_HEADER):
        leading_only = False
    elif header.startswith(_LEADING_HEADER):
        leading_only = True
    else:
        _reject_headerless(header)

    fields, body_start = _parse_header_block(lines, start)
    basis = _parse_basis(lines, body_start)

    characteristic = _require_int(fields, "field characteristic")
    variables = _require_variables(fields)
    monomial_order = _require_field(fields, "monomial order")
    _check_length(fields, basis)

    return GroebnerOutput(
        unit_ideal=basis == ("1",),
        basis=basis,
        leading_only=leading_only,
        characteristic=characteristic,
        variables=variables,
        monomial_order=monomial_order,
    )


def _first_content_line(lines: list[str]) -> int | None:
    for i, line in enumerate(lines):
        if line.strip():
            return i
    return None


def _reject_headerless(header: str) -> NoReturn:
    """Raise. Ambiguous if the bytes look like solver mode, malformed otherwise."""
    if (
        header.startswith("[-1")
        or header.startswith("[0,")
        or _SOLVER_EMPTY_RE.match(header)
    ):
        raise MsolveAmbiguous(
            f"refusing to parse solver-mode output as a Groebner basis: "
            f"{header[:60]!r}. In solver mode '[-1]:' means the system has no "
            f"solutions; in Groebner mode the unit ideal prints as '[1]:'. "
            f"Re-run msolve with -g 1 or -g 2."
        )
    raise MsolveOutputError(
        f"missing msolve Groebner header: expected a line starting with "
        f"{_GB_HEADER!r} or {_LEADING_HEADER!r}, got {header[:60]!r}"
    )


def _parse_header_block(lines: list[str], start: int) -> tuple[dict[str, str], int]:
    """Parse ``#---`` / fields / ``#---``. Returns the fields and the body index."""
    pos = start + 1
    if pos >= len(lines) or lines[pos].strip() != _SEPARATOR:
        got = lines[pos].strip() if pos < len(lines) else "<end of output>"
        raise MsolveOutputError(
            f"malformed msolve header: expected {_SEPARATOR!r} after the header "
            f"line, got {got[:60]!r}"
        )
    pos += 1

    fields: dict[str, str] = {}
    while pos < len(lines):
        line = lines[pos].strip()
        if line == _SEPARATOR:
            return fields, pos + 1
        if not line.startswith("#"):
            raise MsolveOutputError(
                f"malformed msolve header: expected a '#' field line or "
                f"{_SEPARATOR!r}, got {line[:60]!r}"
            )
        key, sep, value = line[1:].partition(":")
        if not sep:
            raise MsolveOutputError(
                f"malformed msolve header field: {line[:60]!r}"
            )
        fields[key.strip().lower()] = value.strip()
        pos += 1

    raise MsolveOutputError(
        f"truncated msolve output: header block was never closed with {_SEPARATOR!r}"
    )


def _parse_basis(lines: list[str], body_start: int) -> tuple[str, ...]:
    body = "\n".join(lines[body_start:]).strip()
    if not body:
        raise MsolveOutputError(
            "truncated msolve output: header present but no basis body"
        )
    if not body.startswith("["):
        raise MsolveOutputError(
            f"malformed msolve basis: expected '[', got {body[:60]!r}"
        )
    if not body.endswith("]:"):
        if "]:" in body:
            raise MsolveOutputError(
                "malformed msolve output: unexpected trailing content after ']:'"
            )
        raise MsolveOutputError(
            "truncated msolve output: basis list is not closed with ']:'"
        )

    inner = body[1:-2]
    if not inner.strip():
        raise MsolveOutputError("malformed msolve basis: empty list")

    entries = []
    for raw in inner.split(","):
        entry = raw.strip()
        if not entry:
            raise MsolveOutputError(
                "malformed msolve basis: empty entry (stray comma)"
            )
        entries.append(entry)
    return tuple(entries)


def _require_field(fields: dict[str, str], key: str) -> str:
    if key not in fields:
        raise MsolveOutputError(f"missing '#{key}' in msolve header")
    value = fields[key]
    if not value:
        raise MsolveOutputError(f"empty '#{key}' in msolve header")
    return value


def _require_int(fields: dict[str, str], key: str) -> int:
    value = _require_field(fields, key)
    try:
        return int(value)
    except ValueError:
        raise MsolveOutputError(
            f"'#{key}' is not an integer: {value[:60]!r}"
        ) from None


def _require_variables(fields: dict[str, str]) -> tuple[str, ...]:
    value = _require_field(fields, "variable order")
    variables = tuple(part.strip() for part in value.split(","))
    if any(not name for name in variables):
        raise MsolveOutputError(f"malformed '#variable order': {value[:60]!r}")
    return variables


def _check_length(fields: dict[str, str], basis: tuple[str, ...]) -> None:
    """Cross-check the printed basis length against what we actually read."""
    value = _require_field(fields, "length of basis")
    match = _LENGTH_RE.search(value)
    if match is None:
        raise MsolveOutputError(f"malformed '#length of basis': {value[:60]!r}")
    declared = int(match.group(1))
    if declared != len(basis):
        raise MsolveOutputError(
            f"msolve declared {declared} basis element(s) but {len(basis)} were "
            f"parsed; the output is truncated or corrupt"
        )
