# msolveio

Strict Python I/O for msolve: canonical input, mode-required output.
Gröbner-mode (`-g`) only in v0.1. Solver-mode bytes are rejected, not interpreted.

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

## Not supported in v0.1

- Solver mode, real-root isolation, and `-P` parametrization output — these raise, and are
  never interpreted as a basis.
- JSON output, Macaulay2 format, or any other msolve serialization.
- sympy / flint / numpy interop. Basis elements are returned as strings, exactly as msolve
  printed them. Nothing is `eval`'d.

## A note on characteristic

msolve 0.10.1 labels some unlifted rational Gröbner bases as characteristic 0 regardless of
whether a lift to Q actually happened. `GroebnerOutput.characteristic` reports what msolve
printed and nothing more; msolveio does not pretend to know better.

## License

MIT © 2026 DC Posch — <https://github.com/dcposch/msolveio>
