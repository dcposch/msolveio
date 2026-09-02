"""run_param tests. Tests that need the real binary skip when msolve is absent."""

from __future__ import annotations

import shutil
from fractions import Fraction

import pytest

from msolveio import (
    EmptySolutionSet,
    Mode,
    MsolveCharPParamUnsupported,
    MsolveNotGeneric,
    PositiveDimensional,
    RationalParametrization,
    emit_system,
    run_param,
)

MSOLVE = shutil.which("msolve")
needs_msolve = pytest.mark.skipif(MSOLVE is None, reason="msolve binary not on PATH")


@needs_msolve
def test_witness_point_round_trip() -> None:
    source = emit_system(["2*x-1", "3*y-1"], variables=["x", "y"])
    result = run_param(source, timeout=60)
    assert isinstance(result.output, RationalParametrization)
    assert result.chart is not None
    assert result.chart.point_at(Fraction(1, 3)) == (Fraction(1, 2), Fraction(1, 3))
    assert result.output.real_solutions_printed is None

    assert result.msolve_version.startswith("0.10.")
    assert result.returncode == 0
    assert result.wall_seconds >= 0
    assert len(result.input_sha256) == 64
    assert len(result.output_sha256) == 64
    assert "-P" in result.argv and "2" in result.argv
    assert "-c" in result.argv


@needs_msolve
def test_empty_solution_set() -> None:
    source = emit_system(["x", "y", "x+1"], variables=["x", "y"])
    result = run_param(source, timeout=60)
    assert isinstance(result.output, EmptySolutionSet)
    assert result.chart is None


@needs_msolve
def test_positive_dimensional() -> None:
    source = emit_system(["x-1"], variables=["x", "y"])
    result = run_param(source, timeout=60)
    assert isinstance(result.output, PositiveDimensional)
    assert result.output.nvars == 2
    assert result.chart is None


@needs_msolve
def test_precision_requests_exact_boxes_in_input_order() -> None:
    source = emit_system(["x-2", "y^2-3"], variables=["x", "y"])
    result = run_param(source, timeout=60, precision=64)
    assert isinstance(result.output, RationalParametrization)
    assert "-P" in result.argv and "1" in result.argv and "-p" in result.argv
    assert result.chart is not None
    boxes = result.chart.real_solutions_input
    assert boxes is not None and len(boxes) == 2
    for solution in boxes:
        (x_lo, x_hi), (y_lo, y_hi) = solution
        assert isinstance(x_lo, Fraction)
        assert x_lo == x_hi == 2  # x is exactly 2 in every real solution
        assert y_lo <= y_hi
        assert y_lo**2 <= 3 <= y_hi**2 or y_hi**2 <= 3 <= y_lo**2


@needs_msolve
def test_forced_linear_form_yields_usable_chart() -> None:
    source = emit_system(
        ["x^2-x", "y^2-y", "x*y-x"], variables=["x", "y"]
    )
    result = run_param(source, timeout=60)
    assert isinstance(result.output, RationalParametrization)
    assert result.chart is not None
    assert result.chart.added_variable is not None
    assert result.chart.linear_form_input is not None
    # Recover all three witnesses through the chart, whatever form msolve chose.
    w = result.output.w_ascending
    roots = [
        Fraction(t)
        for t in range(-10, 11)
        if sum(c * t**i for i, c in enumerate(w)) == 0
    ]
    assert len(roots) == 3
    assert {result.chart.point_at(t) for t in roots} == {
        (Fraction(0), Fraction(0)),
        (Fraction(0), Fraction(1)),
        (Fraction(1), Fraction(1)),
    }


@needs_msolve
def test_restricted_genericity_raises_typed() -> None:
    source = emit_system(["x^2-1", "y^2-1"], variables=["x", "y"])
    with pytest.raises(MsolveNotGeneric):
        run_param(source, timeout=60, genericity=0)


@needs_msolve
def test_char_p_raises_typed() -> None:
    source = emit_system(
        ["x^2+y^2-1", "x-y"], variables=["x", "y"], characteristic=65537
    )
    with pytest.raises(MsolveCharPParamUnsupported):
        run_param(source, timeout=60)


def test_argument_validation() -> None:
    source = "x,y\n0\nx-1,\ny-1\n"
    with pytest.raises(ValueError):
        run_param(source, timeout=60, mode=Mode.GROEBNER)
    with pytest.raises(ValueError):
        run_param(source, timeout=0)
    with pytest.raises(ValueError):
        run_param(source, timeout=60, threads=0)
    with pytest.raises(ValueError):
        run_param(source, timeout=60, precision=0)
    with pytest.raises(ValueError):
        run_param(source, timeout=60, genericity=3)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        run_param(source, timeout=60, precision=1.5)  # type: ignore[arg-type]
