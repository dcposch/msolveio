"""Canonical emission of msolve ``.ms`` input files.

The msolve 0.10.x parser is permissive in ways that silently change meaning:
it accepts text it will not evaluate the way a CAS user expects, and it
truncates oversized coefficients instead of complaining. This module refuses
anything in that grey zone.
"""

from __future__ import annotations

import re
from typing import Sequence

from .errors import MsolveInputError

__all__ = ["emit_system", "MAX_TERM_VAR_PRODUCT", "MAX_CHARACTERISTIC"]

#: msolve 0.10.1 indexes the exponent matrix with a 32-bit signed counter.
#: ``total_terms * nvars`` above this bound segfaults an unpatched build, so we
#: refuse to write such a file. Exposed as a constant so it can be lowered in
#: tests without constructing a two-billion-term system.
MAX_TERM_VAR_PRODUCT = 2**31 - 1

#: msolve's documented prime-field range is ``2 .. 2**31 - 1``.
MAX_CHARACTERISTIC = 2**31 - 1

#: Coefficient magnitudes are read into signed 64-bit words before reduction.
_MAX_COEFF_MAGNITUDE = 2**63 - 1

_VARIABLE_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*\Z")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*|[0-9]+|[+\-*/^]|\s+")

_Monomial = tuple[tuple[str, int], ...]


def emit_system(
    polynomials: Sequence[str],
    *,
    variables: Sequence[str],
    characteristic: int = 0,
) -> str:
    """Render a polynomial system as msolve input text.

    The result is the three-part msolve file format::

        x,y
        0
        x^2+y,
        x*y-1

    Each polynomial must already be an expanded sum of monomials. Whitespace in
    the input strings is insignificant and is removed; nothing else about a
    polynomial is rewritten. Any construct msolve would mis-parse -- parentheses,
    post-monomial division, unknown identifiers, repeated monomials -- raises
    :class:`~msolveio.MsolveInputError`.

    :param polynomials: the generators, as expanded monomial sums.
    :param variables: the variable order, which msolve echoes back in its output.
    :param characteristic: ``0`` for Q, or a prime in ``2 .. 2**31 - 1``.
    :raises MsolveInputError: if anything about the system is unsafe to write.
    """
    var_tuple = _check_variables(variables)
    _check_characteristic(characteristic)

    if isinstance(polynomials, str):
        raise MsolveInputError(
            "polynomials must be a sequence of strings, not a single string"
        )
    polys = list(polynomials)
    if not polys:
        raise MsolveInputError("at least one polynomial is required")

    varset = set(var_tuple)
    rendered: list[str] = []
    total_terms = 0
    for index, poly in enumerate(polys):
        if not isinstance(poly, str):
            raise MsolveInputError(
                f"polynomial {index}: expected a string, got {type(poly).__name__}"
            )
        text, nterms = _check_polynomial(poly, index, varset, characteristic)
        rendered.append(text)
        total_terms += nterms

    # Read the bound through the module global so tests can lower it.
    bound = MAX_TERM_VAR_PRODUCT
    product = total_terms * len(var_tuple)
    if product > bound:
        raise MsolveInputError(
            f"system is too large for msolve 0.10.1: total_terms * nvars = "
            f"{total_terms} * {len(var_tuple)} = {product} exceeds {bound}"
        )

    header = ",".join(var_tuple)
    body = ",\n".join(rendered)
    return f"{header}\n{characteristic}\n{body}\n"


def _check_variables(variables: Sequence[str]) -> tuple[str, ...]:
    if isinstance(variables, str):
        raise MsolveInputError(
            "variables must be a sequence of strings, not a single string"
        )
    var_tuple = tuple(variables)
    if not var_tuple:
        raise MsolveInputError("at least one variable is required")

    seen: set[str] = set()
    for name in var_tuple:
        if not isinstance(name, str):
            raise MsolveInputError(
                f"variable names must be strings, got {type(name).__name__}"
            )
        if not name:
            raise MsolveInputError("empty variable name")
        if not _VARIABLE_RE.match(name):
            raise MsolveInputError(
                f"invalid variable name {name!r}: names must match "
                f"[A-Za-z][A-Za-z0-9]* (no underscores, spaces, commas, or operators)"
            )
        if name in seen:
            raise MsolveInputError(f"duplicate variable name {name!r}")
        seen.add(name)
    return var_tuple


def _check_characteristic(characteristic: int) -> None:
    if isinstance(characteristic, bool) or not isinstance(characteristic, int):
        raise MsolveInputError(
            f"characteristic must be an int, got {type(characteristic).__name__}"
        )
    if characteristic == 0:
        return
    if characteristic < 0:
        raise MsolveInputError("characteristic must be 0 or a positive prime")
    if characteristic == 1:
        raise MsolveInputError("characteristic 1 is not a field")
    if characteristic > MAX_CHARACTERISTIC:
        raise MsolveInputError(
            f"characteristic {characteristic} is outside msolve's prime-field "
            f"range 2 .. {MAX_CHARACTERISTIC}"
        )
    if not _is_prime(characteristic):
        raise MsolveInputError(f"characteristic {characteristic} is not prime")


def _is_prime(n: int) -> bool:
    """Deterministic Miller-Rabin. Exact for every n we accept (n < 2**31)."""
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _tokenize(poly: str, index: int) -> list[str]:
    tokens: list[str] = []
    pos = 0
    for match in _TOKEN_RE.finditer(poly):
        if match.start() != pos:
            bad = poly[pos : match.start()]
            raise MsolveInputError(_bad_char_message(index, bad))
        pos = match.end()
        token = match.group()
        if not token.isspace():
            tokens.append(token)
    if pos != len(poly):
        raise MsolveInputError(_bad_char_message(index, poly[pos:]))
    return tokens


def _bad_char_message(index: int, bad: str) -> str:
    char = bad[0]
    if char in "()":
        return (
            f"polynomial {index}: parentheses are not allowed; msolve input must "
            f"be an expanded sum of monomials"
        )
    if char == "_":
        return (
            f"polynomial {index}: '_' is not a legal msolve identifier character"
        )
    return f"polynomial {index}: unexpected character {char!r}"


def _check_polynomial(
    poly: str,
    index: int,
    varset: set[str],
    characteristic: int,
) -> tuple[str, int]:
    """Validate one polynomial. Returns its canonical text and its term count."""
    tokens = _tokenize(poly, index)
    if not tokens:
        raise MsolveInputError(f"polynomial {index}: empty polynomial")

    seen: set[_Monomial] = set()
    pos = 0
    ntokens = len(tokens)
    first = True
    while pos < ntokens:
        if tokens[pos] in ("+", "-"):
            pos += 1
            if pos >= ntokens:
                raise MsolveInputError(
                    f"polynomial {index}: trailing '{tokens[pos - 1]}'"
                )
        elif not first:  # unreachable: _parse_term stops only at end or a sign
            raise MsolveInputError(
                f"polynomial {index}: expected '+' or '-' before {tokens[pos]!r}"
            )
        if tokens[pos] == "*":
            raise MsolveInputError(
                f"polynomial {index}: term begins with '*'"
            )
        pos, monomial = _parse_term(tokens, pos, index, varset, characteristic)
        if monomial in seen:
            raise MsolveInputError(
                f"polynomial {index}: monomial {_show_monomial(monomial)} appears "
                f"more than once; msolve's parser is undefined on repeated "
                f"monomials, so collect terms first"
            )
        seen.add(monomial)
        first = False

    return "".join(tokens), len(seen)


def _parse_term(
    tokens: list[str],
    pos: int,
    index: int,
    varset: set[str],
    characteristic: int,
) -> tuple[int, _Monomial]:
    """Parse one monomial starting at ``pos``. Returns (next position, monomial)."""
    ntokens = len(tokens)
    exponents: dict[str, int] = {}
    factor = 0

    while True:
        token = tokens[pos]
        if token.isdigit():
            if factor != 0:
                raise MsolveInputError(
                    f"polynomial {index}: numeric coefficient {token} must come "
                    f"first in its term"
                )
            pos = _parse_coefficient(tokens, pos, index, characteristic)
        elif token[0].isalpha():
            if token not in varset:
                raise MsolveInputError(
                    f"polynomial {index}: unknown identifier {token!r}; only "
                    f"declared variables and integer/rational literals are allowed"
                )
            pos += 1
            exponent = 1
            if pos < ntokens and tokens[pos] == "^":
                pos += 1
                if pos >= ntokens or not tokens[pos].isdigit():
                    raise MsolveInputError(
                        f"polynomial {index}: exponent of {token!r} must be a "
                        f"positive integer"
                    )
                exponent = int(tokens[pos])
                if exponent < 1:
                    raise MsolveInputError(
                        f"polynomial {index}: exponent of {token!r} must be a "
                        f"positive integer, got {exponent}"
                    )
                pos += 1
            if token in exponents:
                raise MsolveInputError(
                    f"polynomial {index}: variable {token!r} appears twice in one "
                    f"monomial; write it as a single power instead"
                )
            exponents[token] = exponent
        elif token == "/":
            raise MsolveInputError(
                f"polynomial {index}: division is only allowed in a leading "
                f"rational coefficient such as '1/2*x'"
            )
        else:
            raise MsolveInputError(
                f"polynomial {index}: unexpected {token!r}"
            )

        factor += 1
        if pos >= ntokens or tokens[pos] in ("+", "-"):
            break
        if tokens[pos] == "/":
            raise MsolveInputError(
                f"polynomial {index}: division is only allowed in a leading "
                f"rational coefficient such as '1/2*x'"
            )
        if tokens[pos] != "*":
            raise MsolveInputError(
                f"polynomial {index}: expected '*' between factors, got "
                f"{tokens[pos]!r}"
            )
        pos += 1
        if pos >= ntokens:
            raise MsolveInputError(f"polynomial {index}: trailing '*'")
        if not (tokens[pos].isdigit() or tokens[pos][0].isalpha()):
            raise MsolveInputError(
                f"polynomial {index}: expected a factor after '*', got "
                f"{tokens[pos]!r}"
            )

    return pos, tuple(sorted(exponents.items()))


def _parse_coefficient(
    tokens: list[str],
    pos: int,
    index: int,
    characteristic: int,
) -> int:
    ntokens = len(tokens)
    numerator = int(tokens[pos])
    pos += 1
    parts = [numerator]

    if pos < ntokens and tokens[pos] == "/":
        if characteristic != 0:
            raise MsolveInputError(
                f"polynomial {index}: rational coefficients are not allowed over "
                f"a prime field; reduce the coefficient modulo {characteristic} first"
            )
        pos += 1
        if pos >= ntokens or not tokens[pos].isdigit():
            raise MsolveInputError(
                f"polynomial {index}: expected an integer denominator after '/'"
            )
        denominator = int(tokens[pos])
        if denominator == 0:
            raise MsolveInputError(f"polynomial {index}: zero denominator")
        parts.append(denominator)
        pos += 1

    if characteristic != 0:
        for value in parts:
            if value > _MAX_COEFF_MAGNITUDE:
                raise MsolveInputError(
                    f"polynomial {index}: coefficient {value} does not fit in a "
                    f"signed 64-bit word; msolve would truncate it instead of "
                    f"reducing it modulo {characteristic}"
                )
    return pos


def _show_monomial(monomial: _Monomial) -> str:
    if not monomial:
        return "1"
    return "*".join(
        name if exponent == 1 else f"{name}^{exponent}" for name, exponent in monomial
    )
