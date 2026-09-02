"""Strict parsing of msolve 0.10.x rational-parametrization (``-P``) output.

The ``-P`` output language is where the mode confusion of :mod:`msolveio.parse`
returns in new clothing: the same bracketed-list surface syntax encodes a
parametrization, a solver run, an empty solution set, and a positive-dimensional
signal, and a misread sign or scale factor yields wrong witness points that
still pass casual arithmetic. So every convention this module relies on is
pinned as a named dataclass field with its exact meaning, and everything the
parser cannot certify is a hard error.

The conventions, verified against msolve 0.10.1 (all polynomials are ascending
integer coefficient tuples; the parameter ``t`` is the *last printed*
variable):

- ``w_ascending`` is the eliminating polynomial ``w(t)``. Its printed integer
  content is kept (it need not be monic), and its degree may be *smaller* than
  ``quotient_degree``: msolve parametrizes the radical, so multiplicity is not
  recoverable here.
- ``wprime_ascending`` is the printed common denominator, strictly checked to
  equal the derivative ``w'(t)``. If msolve ever prints anything else, parsing
  fails loudly rather than returning silently rescaled coordinates.
- Each printed variable before the last has a :class:`ParamNumerator`
  ``(v_ascending, denominator_scale)`` and satisfies, at every root ``t*`` of
  ``w``::

      variable = -v(t*) / (denominator_scale * w'(t*))

  The last printed variable *is* ``t``.
- When msolve's genericity fix added a variable, the printed
  ``linear_form_printed`` vector ``(c_1, .., c_n)`` states the added relation
  ``c_1*v_1 + .. + c_n*v_n = 0`` over the printed variables, with ``c_n = 1``
  on the added (last, parameter) variable; equivalently
  ``t = -(c_1*v_1 + .. + c_{n-1}*v_{n-1})``. Without an added variable the
  vector is the unit vector selecting the last printed variable, and both
  shapes are strictly checked.

Genericity fixes are *silent* in msolve (exit 0, empty stderr): a variable
reorder shows up only as a permuted echoed variable order, and the added
variable is always named ``A`` -- even when the input already uses that name,
producing a duplicate. :meth:`RationalParametrization.coordinates` therefore
resolves the chart positionally against the caller's input variables and hands
back every coordinate in input order, so callers never index printed order.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import NoReturn, Sequence, Union

from .errors import (
    MsolveAmbiguous,
    MsolveCharPParamUnsupported,
    MsolveOutputError,
)
from .mode import Mode

__all__ = [
    "EmptySolutionSet",
    "ParamChart",
    "ParamNumerator",
    "ParamOutput",
    "PositiveDimensional",
    "RationalParametrization",
    "parse_param",
]

_Box = tuple[Fraction, Fraction]
_Solution = tuple[_Box, ...]


@dataclass(frozen=True)
class EmptySolutionSet:
    """msolve reported ``[-1]:``, i.e. no solutions in the algebraic closure.

    This is a *result*, not an error: an EMPTY verdict is a legitimate and
    common answer. It deliberately has no useful boolean or iterable behaviour;
    match on the type.
    """


@dataclass(frozen=True)
class PositiveDimensional:
    """msolve reported ``[1, nvars, -1, []]:``, i.e. infinitely many solutions.

    No parametrization exists; the locus is not zero-dimensional. This is a
    result, never a silent empty list.

    :param nvars: the variable count msolve printed in the signal.
    """

    nvars: int


@dataclass(frozen=True)
class ParamNumerator:
    """One coordinate's RUR numerator.

    At every root ``t*`` of the eliminating polynomial the coordinate is
    recovered *exactly* as::

        coordinate = -v(t*) / (denominator_scale * w'(t*))

    The leading minus sign and the integer ``denominator_scale`` are msolve's
    printed conventions, not msolveio's; both are load-bearing. A scale other
    than 1 appears when clearing denominators (e.g. the point ``x = 1/2``
    prints as ``v = -3``, ``denominator_scale = 2`` against ``w = 3t - 1``).

    :param v_ascending: ascending integer coefficients of ``v(t)``; may carry
        trailing zeros, exactly as printed.
    :param denominator_scale: the positive integer ``cst`` msolve printed next
        to the numerator.
    """

    v_ascending: tuple[int, ...]
    denominator_scale: int


@dataclass(frozen=True)
class RationalParametrization:
    """A parsed msolve rational parametrization (RUR), in *printed* order.

    Everything here is exact; nothing is a float. Coefficients are Python
    integers as printed by msolve. The printed variable order is msolve's, not
    the caller's -- it may be a permutation of the input and may carry one
    appended auxiliary variable. Use :meth:`coordinates` to map back to the
    input chart; do not index these fields by input position.

    :param characteristic: the printed field characteristic. Always ``0`` in
        this release; characteristic-p bytes raise before construction.
    :param quotient_degree: the printed K-dimension of the quotient ring. May
        exceed ``len(w_ascending) - 1``: msolve parametrizes the radical.
    :param printed_variables: the variable names msolve echoed, in msolve's
        order, including any added variable (always last).
    :param linear_form_printed: msolve's printed linear-form vector over
        ``printed_variables``; see the module docstring for its two shapes.
    :param w_ascending: the eliminating polynomial ``w(t)``, ascending integer
        coefficients, exact degree (nonzero leading coefficient), not
        necessarily monic.
    :param wprime_ascending: the printed common denominator, strictly verified
        to equal ``w'(t)``.
    :param numerators_printed: one :class:`ParamNumerator` per printed variable
        *except the last*; the last printed variable equals the parameter.
    :param real_solutions_printed: real-root isolation boxes when the bytes
        came from ``-P 1``, else ``None``. Each solution is a tuple of exact
        ``(lo, hi)`` :class:`~fractions.Fraction` pairs **in printed variable
        order** with the added variable omitted -- after a reorder fix these
        are *not* in input order.
    """

    characteristic: int
    quotient_degree: int
    printed_variables: tuple[str, ...]
    linear_form_printed: tuple[int, ...]
    w_ascending: tuple[int, ...]
    wprime_ascending: tuple[int, ...]
    numerators_printed: tuple[ParamNumerator, ...]
    real_solutions_printed: tuple[_Solution, ...] | None

    def coordinates(self, input_variables: Sequence[str]) -> "ParamChart":
        """Resolve this parametrization against the caller's input chart.

        :param input_variables: the variable names of the *input* system, in
            input order (the first line of the ``.ms`` file).
        :raises MsolveOutputError: if the printed variables are not explainable
            as a permutation of the input plus at most one appended variable,
            or if any strictly checked convention fails.
        """
        return _build_chart(self, input_variables)


#: Everything :func:`parse_param` can return. Match on the type; none of the
#: members is a list, and none has a boolean truth value worth trusting.
ParamOutput = Union[RationalParametrization, EmptySolutionSet, PositiveDimensional]


@dataclass(frozen=True)
class ParamChart:
    """A parametrization mapped back onto the input chart.

    This is the object witness extraction should consume: every field is in
    *input* variable order, the permutation and any added linear form are
    surfaced explicitly, and the parameter-variable special case is already
    folded into a uniform numerator convention.

    :param parametrization: the printed-order parametrization this was built
        from.
    :param input_variables: the input variable names, as given.
    :param printed_index: for each input variable, its position in
        ``parametrization.printed_variables``. The identity tuple iff msolve
        did not reorder.
    :param added_variable: the printed name of msolve's appended auxiliary
        variable, or ``None``. The name is cosmetic (msolve reuses ``A`` even
        when it collides with an input variable); identification is positional.
    :param linear_form_input: when a variable was added, the coefficients
        ``c_j`` over the *input* variables such that the parameter satisfies
        ``t = -(sum_j c_j * x_j)``; else ``None``.
    :param separating_input_index: when no variable was added, the input index
        of the variable that equals the parameter ``t``; else ``None``.
    :param numerators_input: one :class:`ParamNumerator` per input variable, in
        input order, all under the single convention
        ``x_j = -v_j(t) / (scale_j * w'(t))``. For the separating variable the
        numerator is the synthesized ``-t * w'(t)``, so the convention holds
        uniformly.
    :param real_solutions_input: ``real_solutions_printed`` re-ordered to input
        variable order, or ``None`` when boxes were not requested.
    """

    parametrization: RationalParametrization
    input_variables: tuple[str, ...]
    printed_index: tuple[int, ...]
    added_variable: str | None
    linear_form_input: tuple[int, ...] | None
    separating_input_index: int | None
    numerators_input: tuple[ParamNumerator, ...]
    real_solutions_input: tuple[_Solution, ...] | None

    @property
    def reordered(self) -> bool:
        """``True`` iff msolve permuted the input variables."""
        return self.printed_index != tuple(range(len(self.printed_index)))

    def point_at(self, t: Fraction) -> tuple[Fraction, ...]:
        """Evaluate the witness point at a rational root ``t`` of ``w``.

        Exact :class:`~fractions.Fraction` arithmetic, coordinates in input
        order. Only rational roots can be evaluated here; number-field roots
        belong to the caller's algebra layer.

        :raises ValueError: if ``t`` is not a root of ``w`` -- evaluating the
            numerators anywhere else yields coordinates that look plausible
            and mean nothing.
        """
        t = Fraction(t)
        p = self.parametrization
        if _eval_ascending(p.w_ascending, t) != 0:
            raise ValueError(
                f"t = {t} is not a root of the eliminating polynomial; "
                f"coordinates are only defined at roots of w"
            )
        denominator = _eval_ascending(p.wprime_ascending, t)
        if denominator == 0:
            raise ValueError(
                f"w'({t}) = 0; the eliminating polynomial has a multiple root "
                f"there and the parametrization does not evaluate"
            )
        return tuple(
            -_eval_ascending(numerator.v_ascending, t)
            / (numerator.denominator_scale * denominator)
            for numerator in self.numerators_input
        )


def parse_param(text: str, *, mode: Mode = Mode.PARAM) -> ParamOutput:
    """Parse msolve 0.10.x rational-parametrization (``-P``) output.

    Accepts both the ``-P 2`` shape (parametrization only) and the ``-P 1``
    shape (parametrization plus real-root boxes).

    :param text: the contents of msolve's ``-o`` file, or its stdout.
    :param mode: must be :attr:`Mode.PARAM`. Present so callers state which
        output language they believe they have.
    :raises MsolveAmbiguous: if the bytes look like a different msolve mode
        (Groebner-shaped, or solver output without a parametrization).
    :raises MsolveCharPParamUnsupported: if the parametrization is over a
        prime field; that grammar differs and is refused, not half-parsed.
    :raises MsolveOutputError: if the bytes are not well-formed ``-P`` output
        or violate a pinned convention.
    """
    if mode is not Mode.PARAM:
        raise ValueError(f"unsupported mode {mode!r}; parse_param parses Mode.PARAM only")
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")

    stripped = text.strip()
    if not stripped:
        raise MsolveOutputError("empty msolve output")
    if stripped.startswith("#"):
        raise MsolveAmbiguous(
            f"refusing to parse Groebner-shaped output as a parametrization: "
            f"{stripped[:60]!r}. These bytes carry msolve's '#' Groebner "
            f"header; parse them with parse_groebner, or re-run msolve with -P."
        )

    top = _parse_top(stripped)

    if top == [-1]:
        return EmptySolutionSet()
    if _is_positive_dimensional(top):
        return PositiveDimensional(nvars=top[1])

    if not (isinstance(top, list) and len(top) in (2, 3) and top[0] == 0):
        raise MsolveOutputError(
            f"unrecognized msolve -P output shape: {stripped[:60]!r}"
        )
    inner = top[1]
    if not isinstance(inner, list):
        raise MsolveOutputError(
            f"unrecognized msolve -P output shape: {stripped[:60]!r}"
        )
    if len(inner) == 2 and isinstance(inner[1], list):
        raise MsolveAmbiguous(
            "refusing to parse solver-mode output as a parametrization: these "
            "bytes are real-root isolation output with no parametrization "
            "block. Re-run msolve with -P 1 or -P 2."
        )
    if len(inner) != 6:
        raise MsolveOutputError(
            f"malformed msolve parametrization: expected 6 fields "
            f"[char, nvars, degree, vars, form, param], got {len(inner)}"
        )

    parametrization = _interpret_parametrization(inner)

    real_solutions: tuple[_Solution, ...] | None = None
    if len(top) == 3:
        real_solutions = _interpret_real_block(
            top[2], nvars_printed=len(parametrization.printed_variables)
        )

    if real_solutions is None:
        return parametrization
    return dataclasses.replace(parametrization, real_solutions_printed=real_solutions)


# --------------------------------------------------------------------------
# Tokenizing and reading the bracketed-list surface syntax.

_TOKEN_RE = re.compile(r"\s+|-?\d+|'[^']*'|[\[\],:/^]")

_Value = Union[int, Fraction, str, list]


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    pos = 0
    for match in _TOKEN_RE.finditer(text):
        if match.start() != pos:
            raise MsolveOutputError(
                f"unexpected character {text[pos]!r} in msolve -P output"
            )
        pos = match.end()
        token = match.group()
        if not token.isspace():
            tokens.append(token)
    if pos != len(text):
        raise MsolveOutputError(
            f"unexpected character {text[pos]!r} in msolve -P output"
        )
    return tokens


class _Reader:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos = 0

    def peek(self) -> str | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise MsolveOutputError("truncated msolve -P output")
        self._pos += 1
        return token

    def expect(self, token: str) -> None:
        got = self.take()
        if got != token:
            raise MsolveOutputError(
                f"malformed msolve -P output: expected {token!r}, got {got[:20]!r}"
            )

    def at_end(self) -> bool:
        return self._pos == len(self._tokens)


def _parse_top(text: str) -> list:
    """Read the top level: one ``[...]`` list, then the closing ``:``."""
    reader = _Reader(_tokenize(text))
    top = _read_list(reader)
    reader.expect(":")
    if not reader.at_end():
        raise MsolveOutputError(
            "malformed msolve -P output: unexpected trailing content after ':'"
        )
    return top


def _read_list(reader: _Reader) -> list:
    reader.expect("[")
    items: list[_Value] = []
    if reader.peek() == "]":
        reader.take()
        return items
    while True:
        items.append(_read_value(reader))
        token = reader.take()
        if token == "]":
            return items
        if token != ",":
            raise MsolveOutputError(
                f"malformed msolve -P output: expected ',' or ']', got {token[:20]!r}"
            )


def _read_value(reader: _Reader) -> _Value:
    token = reader.peek()
    if token is None:
        raise MsolveOutputError("truncated msolve -P output")
    if token == "[":
        return _read_list(reader)
    if token.startswith("'"):
        reader.take()
        return token[1:-1]
    if _is_int(token):
        reader.take()
        if reader.peek() != "/":
            return int(token)
        # A dyadic box endpoint: <int> / <int> [^ <int>].
        reader.take()
        base = reader.take()
        if not _is_int(base):
            raise MsolveOutputError(
                f"malformed msolve -P output: expected an integer after '/', "
                f"got {base[:20]!r}"
            )
        denominator = int(base)
        if reader.peek() == "^":
            reader.take()
            exponent = reader.take()
            if not _is_int(exponent) or int(exponent) < 0:
                raise MsolveOutputError(
                    f"malformed msolve -P output: expected a non-negative "
                    f"integer exponent after '^', got {exponent[:20]!r}"
                )
            denominator **= int(exponent)
        if denominator == 0:
            raise MsolveOutputError("malformed msolve -P output: zero denominator")
        return Fraction(int(token), denominator)
    raise MsolveOutputError(
        f"malformed msolve -P output: unexpected token {token[:20]!r}"
    )


def _is_int(token: str) -> bool:
    return token.lstrip("-").isdigit()


# --------------------------------------------------------------------------
# Interpreting the read lists against the pinned -P grammar.


def _is_positive_dimensional(block: list) -> bool:
    return (
        isinstance(block, list)
        and len(block) == 4
        and block[0] == 1
        and isinstance(block[1], int)
        and block[2] == -1
        and block[3] == []
    )


def _interpret_parametrization(inner: list) -> RationalParametrization:
    characteristic, nvars, degree, variables, form, param = inner

    if not isinstance(characteristic, int) or characteristic < 0:
        raise MsolveOutputError(
            f"malformed msolve parametrization: bad field characteristic "
            f"{characteristic!r}"
        )
    if characteristic != 0:
        raise MsolveCharPParamUnsupported(
            f"parametrization over F_{characteristic} is not supported in this "
            f"msolveio release: msolve's characteristic-p -P grammar differs "
            f"from the characteristic-0 one (no per-numerator scale constant, "
            f"denominator not pinned to w'), and parsing it with "
            f"characteristic-0 conventions would yield wrong witness points. "
            f"Planned for a later release; witness extraction is a "
            f"characteristic-0 activity.",
            characteristic=characteristic,
        )
    if not isinstance(nvars, int) or nvars < 1:
        raise MsolveOutputError(
            f"malformed msolve parametrization: bad variable count {nvars!r}"
        )
    if not isinstance(degree, int) or degree < 1:
        raise MsolveOutputError(
            f"malformed msolve parametrization: bad quotient degree {degree!r}"
        )
    if not (
        isinstance(variables, list)
        and len(variables) == nvars
        and all(isinstance(name, str) and name for name in variables)
    ):
        raise MsolveOutputError(
            f"malformed msolve parametrization: expected {nvars} quoted "
            f"variable names, got {variables!r}"
        )
    if not (
        isinstance(form, list)
        and len(form) == nvars
        and all(isinstance(c, int) for c in form)
    ):
        raise MsolveOutputError(
            f"malformed msolve parametrization: expected a linear form with "
            f"{nvars} integer coefficients, got {form!r}"
        )
    if not (isinstance(param, list) and len(param) == 2 and param[0] == 1):
        raise MsolveOutputError(
            f"malformed msolve parametrization: expected the single-"
            f"parametrization block [1, [w, den, nums]], got "
            f"{str(param)[:60]!r}"
        )
    triple = param[1]
    if not (isinstance(triple, list) and len(triple) == 3):
        raise MsolveOutputError(
            "malformed msolve parametrization: expected [w, den, nums]"
        )
    w_raw, den_raw, nums_raw = triple

    w_ascending = _interpret_poly(w_raw, "eliminating polynomial")
    if len(w_ascending) < 2 or w_ascending[-1] == 0:
        raise MsolveOutputError(
            f"malformed eliminating polynomial: expected exact degree >= 1, "
            f"got coefficients {w_raw!r}"
        )
    wprime_ascending = _interpret_poly(den_raw, "denominator")
    expected_derivative = tuple(
        i * c for i, c in enumerate(w_ascending)
    )[1:]
    if wprime_ascending != expected_derivative:
        raise MsolveOutputError(
            f"msolve printed a denominator that is not the derivative of the "
            f"eliminating polynomial: got {wprime_ascending!r}, derivative is "
            f"{expected_derivative!r}. The 0.10.x convention has drifted; "
            f"refusing to guess what the printed denominator means."
        )

    if not isinstance(nums_raw, list):
        raise MsolveOutputError("malformed msolve parametrization: bad numerator list")
    if len(nums_raw) != nvars - 1:
        raise MsolveOutputError(
            f"malformed msolve parametrization: expected {nvars - 1} "
            f"numerators for {nvars} printed variables, got {len(nums_raw)}"
        )
    numerators = tuple(_interpret_numerator(entry) for entry in nums_raw)

    return RationalParametrization(
        characteristic=characteristic,
        quotient_degree=degree,
        printed_variables=tuple(variables),
        linear_form_printed=tuple(form),
        w_ascending=w_ascending,
        wprime_ascending=wprime_ascending,
        numerators_printed=numerators,
        real_solutions_printed=None,
    )


def _interpret_poly(raw: object, what: str) -> tuple[int, ...]:
    if not (
        isinstance(raw, list)
        and len(raw) == 2
        and isinstance(raw[0], int)
        and isinstance(raw[1], list)
        and all(isinstance(c, int) for c in raw[1])
    ):
        raise MsolveOutputError(
            f"malformed {what}: expected [degree, [coefficients]], got "
            f"{str(raw)[:60]!r}"
        )
    declared, coefficients = raw
    if len(coefficients) != declared + 1:
        raise MsolveOutputError(
            f"malformed {what}: declared degree {declared} but "
            f"{len(coefficients)} coefficients were printed"
        )
    return tuple(coefficients)


def _interpret_numerator(entry: object) -> ParamNumerator:
    if not (isinstance(entry, list) and len(entry) == 2):
        raise MsolveOutputError(
            f"malformed numerator entry: expected [poly, scale], got "
            f"{str(entry)[:60]!r}"
        )
    poly_raw, scale = entry
    coefficients = _interpret_poly(poly_raw, "numerator")
    if not isinstance(scale, int) or scale < 1:
        raise MsolveOutputError(
            f"malformed numerator entry: expected a positive integer scale, "
            f"got {scale!r}. A zero or negative scale would silently flip or "
            f"destroy the sign convention; refusing to guess."
        )
    return ParamNumerator(v_ascending=coefficients, denominator_scale=scale)


def _interpret_real_block(
    block: list, *, nvars_printed: int
) -> tuple[_Solution, ...]:
    if not (isinstance(block, list) and len(block) == 2 and block[0] == 1):
        raise MsolveOutputError(
            f"malformed real-solutions block: expected [1, [solutions]], got "
            f"{str(block)[:60]!r}"
        )
    solutions_raw = block[1]
    if not isinstance(solutions_raw, list):
        raise MsolveOutputError("malformed real-solutions block: bad solution list")

    solutions: list[_Solution] = []
    for sol_raw in solutions_raw:
        if not isinstance(sol_raw, list) or not sol_raw:
            raise MsolveOutputError(
                f"malformed real solution: expected a list of [lo, hi] boxes, "
                f"got {str(sol_raw)[:60]!r}"
            )
        # Boxes cover the original variables only (the added variable is
        # omitted), so a solution has nvars_printed or nvars_printed - 1
        # coordinates; the chart pins it against the true input count.
        if len(sol_raw) not in (nvars_printed, nvars_printed - 1):
            raise MsolveOutputError(
                f"malformed real solution: {len(sol_raw)} boxes for "
                f"{nvars_printed} printed variables"
            )
        boxes: list[_Box] = []
        for box_raw in sol_raw:
            if not (isinstance(box_raw, list) and len(box_raw) == 2):
                raise MsolveOutputError(
                    f"malformed real solution: expected [lo, hi], got "
                    f"{str(box_raw)[:60]!r}"
                )
            lo, hi = (_as_fraction(endpoint) for endpoint in box_raw)
            if lo > hi:
                raise MsolveOutputError(
                    f"malformed real solution: inverted box [{lo}, {hi}]"
                )
            boxes.append((lo, hi))
        solutions.append(tuple(boxes))

    lengths = {len(sol) for sol in solutions}
    if len(lengths) > 1:
        raise MsolveOutputError(
            "malformed real-solutions block: solutions disagree on coordinate count"
        )
    return tuple(solutions)


def _as_fraction(value: object) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, Fraction)):
        raise MsolveOutputError(
            f"malformed real solution: expected an exact number, got "
            f"{str(value)[:40]!r}"
        )
    return Fraction(value)


# --------------------------------------------------------------------------
# Mapping printed order back onto the input chart.


def _build_chart(
    parametrization: RationalParametrization, input_variables: Sequence[str]
) -> ParamChart:
    if isinstance(input_variables, str):
        raise TypeError("input_variables must be a sequence of strings, not a string")
    inputs = tuple(input_variables)
    if not inputs or not all(isinstance(name, str) and name for name in inputs):
        raise ValueError(f"malformed input variables: {inputs!r}")
    if len(set(inputs)) != len(inputs):
        raise ValueError(f"duplicate input variable names: {inputs!r}")

    printed = parametrization.printed_variables
    n = len(inputs)
    if len(printed) == n:
        added = False
    elif len(printed) == n + 1:
        added = True
    else:
        _reject_chart(printed, inputs, "the variable counts do not match")

    # The input variables occupy the first n printed slots (msolve appends its
    # auxiliary variable last), so identification is positional-first: match
    # printed[:n] against the input as a permutation, by name. The appended
    # variable's name is untrustworthy -- msolve reuses 'A' even when the
    # input already has one -- and is never used for identification.
    if sorted(printed[:n]) != sorted(inputs):
        _reject_chart(
            printed, inputs, "the printed variables are not a permutation of the input"
        )
    if len(set(printed[:n])) != n:
        _reject_chart(printed, inputs, "the printed variables repeat a name")
    position_of = {name: i for i, name in enumerate(printed[:n])}
    printed_index = tuple(position_of[name] for name in inputs)

    form = parametrization.linear_form_printed
    if added:
        if form[-1] != 1:
            raise MsolveOutputError(
                f"msolve added a variable but printed linear form {form!r} "
                f"whose added-variable coefficient is not 1; the added-relation "
                f"convention has drifted and t cannot be trusted"
            )
        added_variable = printed[-1]
        linear_form_input: tuple[int, ...] | None = tuple(
            form[printed_index[j]] for j in range(n)
        )
        separating_input_index: int | None = None
    else:
        expected_form = tuple(0 if i < n - 1 else 1 for i in range(n))
        if form != expected_form:
            raise MsolveOutputError(
                f"msolve printed linear form {form!r} without adding a "
                f"variable; expected the unit vector {expected_form!r} "
                f"selecting the last printed variable. The parameter's "
                f"identity cannot be trusted."
            )
        added_variable = None
        linear_form_input = None
        separating_input_index = inputs.index(printed[-1])

    numerators_input = tuple(
        parametrization.numerators_printed[printed_index[j]]
        if added or printed_index[j] < len(printed) - 1
        else _parameter_numerator(parametrization.wprime_ascending)
        for j in range(n)
    )

    real_solutions_input: tuple[_Solution, ...] | None = None
    if parametrization.real_solutions_printed is not None:
        for solution in parametrization.real_solutions_printed:
            if len(solution) != n:
                raise MsolveOutputError(
                    f"real solution carries {len(solution)} boxes for "
                    f"{n} input variables"
                )
        real_solutions_input = tuple(
            tuple(solution[printed_index[j]] for j in range(n))
            for solution in parametrization.real_solutions_printed
        )

    return ParamChart(
        parametrization=parametrization,
        input_variables=inputs,
        printed_index=printed_index,
        added_variable=added_variable,
        linear_form_input=linear_form_input,
        separating_input_index=separating_input_index,
        numerators_input=numerators_input,
        real_solutions_input=real_solutions_input,
    )


def _parameter_numerator(wprime_ascending: tuple[int, ...]) -> ParamNumerator:
    """The separating variable as a numerator: ``t == -(-t*w'(t)) / w'(t)``."""
    return ParamNumerator(
        v_ascending=(0, *(-c for c in wprime_ascending)),
        denominator_scale=1,
    )


def _reject_chart(
    printed: tuple[str, ...], inputs: tuple[str, ...], why: str
) -> NoReturn:
    raise MsolveOutputError(
        f"cannot map the parametrization onto the input chart: {why}. msolve "
        f"printed variables {printed!r} for input variables {inputs!r}; "
        f"expected a permutation of the input plus at most one appended "
        f"auxiliary variable."
    )


def _eval_ascending(coefficients: tuple[int, ...], t: Fraction) -> Fraction:
    result = Fraction(0)
    for coefficient in reversed(coefficients):
        result = result * t + coefficient
    return result
