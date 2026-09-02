# msolveio

Strict Python I/O for msolve: canonical input, mode-required output.
Gröbner mode (`-g`) and characteristic-0 rational-parametrization mode (`-P`).
Bytes from any other msolve mode are rejected, not interpreted.

msolveio writes `.ms` files that msolve 0.10.x will parse the way you meant, and reads back
only the one output language it can identify with certainty. It is not a CAS and not a
Gröbner engine.

## Install

```
pip install msolveio
```

You also need a system `msolve` 0.10.x binary on `PATH` (or pass `binary=`). msolveio has no
runtime dependencies.

## Usage

```python
from msolveio import emit_system, parse_groebner, run_groebner, MsolveAmbiguous

source = emit_system(
    ["x^2+y", "x*y-1"],
    variables=["x", "y"],
    characteristic=0,
)

result = run_groebner(source, gb=2, timeout=60)

print(result.output.unit_ideal)  # False
print(result.output.basis)       # ('y^2+x', 'x*y-1', 'x^2+y')
print(result.msolve_version)     # '0.10.1'
```

`emit_system` raises `MsolveInputError` rather than rewriting input: parentheses,
post-monomial division (`x/2`), repeated monomials, unknown identifiers, and coefficients
that would overflow msolve's 64-bit read are all refused. Leading rationals (`1/2*x`) are
allowed over Q only.

`parse_groebner` requires msolve's `#` comment header. That header is the only thing in the
bytes that says which mode produced them, so it is load-bearing. Feeding it solver output
raises `MsolveAmbiguous` instead of returning a basis:

```python
parse_groebner("[-1]:")  # MsolveAmbiguous
```

This matters because the two languages invert each other. In solver mode `[-1]:` means *no
solutions*; in Gröbner mode the unit ideal — the same fact — prints as `[1]:`. A parser that
guesses gets the answer exactly backwards.

## Rational parametrization (`-P`)

`run_param` runs `msolve -P 2` and parses the rational univariate representation exactly.
Every returned coefficient is a Python integer; nothing is a float, and nothing is `eval`'d.
The result is one of three types — match on it, none is ever a silent empty list:

```python
from fractions import Fraction
from msolveio import emit_system, run_param
from msolveio import RationalParametrization, EmptySolutionSet, PositiveDimensional

source = emit_system(["2*x-1", "3*y-1"], variables=["x", "y"], characteristic=0)
result = run_param(source, timeout=60)

assert isinstance(result.output, RationalParametrization)
result.output.w_ascending           # (-1, 3)      w(t) = 3t - 1, ascending, content kept
result.output.wprime_ascending      # (3,)         the denominator; checked to equal w'(t)
result.output.numerators_printed    # (ParamNumerator(v_ascending=(-3,), denominator_scale=2),)

result.chart.point_at(Fraction(1, 3))   # (Fraction(1, 2), Fraction(1, 3))
```

Read that worked example closely, because the conventions are load-bearing. The parameter
`t` is the **last printed** variable (here `y`, so `t = 1/3` at the point). Every earlier
printed variable is recovered as

```
variable = -v(t) / (denominator_scale * w'(t))
```

so `x = -(-3) / (2 * 3) = 1/2`. The leading minus sign, the integer scale, the ascending
coefficient order, and the kept integer content of `w` are all msolve's printed conventions,
pinned as named dataclass fields and verified by the parser; a misread scale or sign would
yield wrong witness points that still pass casual arithmetic, which is exactly the class of
silent inversion this library exists to refuse.

msolve fixes non-generic systems *silently*: it may permute your variables, and may append
an auxiliary variable tied to a linear form (always printed as `A`, even when that collides
with one of yours). `result.chart` resolves all of that back onto your input chart —
`printed_index`, `added_variable`, `linear_form_input` (`t = -(c_1*x_1 + ...)`), and one
numerator per *input* variable under the uniform convention above. Consume the chart, not
the printed order.

`[-1]:` parses to `EmptySolutionSet` and `[1, nvars, -1, []]:` to `PositiveDimensional` —
typed results, not errors and not lists. Gröbner-shaped or solver-shaped bytes raise
`MsolveAmbiguous`. A parametrization over a prime field raises
`MsolveCharPParamUnsupported`: msolve's characteristic-p `-P` grammar differs, and
half-parsing it with characteristic-0 conventions is the footgun, not the feature.

Passing `precision=<bits>` switches to `msolve -P 1 -p <bits>` and additionally returns
real-root isolation boxes as exact `Fraction` pairs (msolve prints dyadic rationals, not
floats), un-permuted to input order on the chart. Note that msolve parametrizes the
*radical*: `quotient_degree` may exceed `deg w`, and multiplicity is not recoverable here.

`ParamResult` carries the same custody fields as `RunResult`: `msolve_version`, `argv`,
`wall_seconds`, `returncode`, `stderr`, `input_sha256`, `output_sha256`.

## Not supported in v0.2

- Solver mode (real-root isolation without `-P`) — raises, and is never interpreted as a
  basis or a parametrization.
- Parametrizations over prime fields — a typed raise, see above.
- JSON output, Macaulay2 format, or any other msolve serialization.
- sympy / flint / numpy interop. Gröbner basis elements are strings exactly as msolve
  printed them; parametrization coefficients are plain Python integers. One canonical
  representation, zero dependencies; convert downstream where your algebra lives.

## A note on characteristic

msolve 0.10.1 labels some unlifted rational Gröbner bases as characteristic 0 regardless of
whether a lift to Q actually happened. `GroebnerOutput.characteristic` reports what msolve
printed and nothing more; msolveio does not pretend to know better.

## License

MIT © 2026 DC Posch — <https://github.com/dcposch/msolveio>
