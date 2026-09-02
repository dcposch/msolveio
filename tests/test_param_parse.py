"""Parametrization-parser tests against banked msolve 0.10.1 bytes.

Every fixture here is verbatim msolve 0.10.1 output captured from a known
system, so each assertion pins a printed convention: ascending coefficients,
the -v/(cst*w') sign and scale, the silent reorder, the added linear form, and
the two refusal classes (foreign modes, characteristic p).
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from msolveio import (
    EmptySolutionSet,
    Mode,
    MsolveAmbiguous,
    MsolveCharPParamUnsupported,
    MsolveOutputError,
    ParamNumerator,
    PositiveDimensional,
    RationalParametrization,
    parse_groebner,
    parse_param,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


# --- the worked example: 2x-1, 3y-1 -> the single point (1/2, 1/3) ---------


def test_frac_pins_every_convention() -> None:
    output = parse_param(fixture("param_frac.out"))
    assert isinstance(output, RationalParametrization)
    assert output.characteristic == 0
    assert output.quotient_degree == 1
    assert output.printed_variables == ("x", "y")
    assert output.linear_form_printed == (0, 1)
    # w keeps its integer content: 3t - 1, not the monic t - 1/3.
    assert output.w_ascending == (-1, 3)
    assert output.wprime_ascending == (3,)
    # x = 1/2 prints as v = -3 with scale 2: x = -(-3) / (2 * 3).
    assert output.numerators_printed == (
        ParamNumerator(v_ascending=(-3,), denominator_scale=2),
    )
    assert output.real_solutions_printed is None

    chart = output.coordinates(("x", "y"))
    assert chart.printed_index == (0, 1)
    assert chart.reordered is False
    assert chart.added_variable is None
    assert chart.linear_form_input is None
    assert chart.separating_input_index == 1
    assert chart.point_at(Fraction(1, 3)) == (Fraction(1, 2), Fraction(1, 3))


def test_point_at_refuses_non_roots() -> None:
    output = parse_param(fixture("param_frac.out"))
    assert isinstance(output, RationalParametrization)
    chart = output.coordinates(("x", "y"))
    with pytest.raises(ValueError):
        chart.point_at(Fraction(1, 2))


# --- univariate: the lone variable is the parameter itself -----------------


def test_univariate_has_no_numerators() -> None:
    output = parse_param(fixture("param_uni.out"))
    assert isinstance(output, RationalParametrization)
    assert output.printed_variables == ("x",)
    assert output.w_ascending == (-2, 0, 1)
    assert output.numerators_printed == ()

    chart = output.coordinates(("x",))
    assert chart.separating_input_index == 0
    # The parameter variable gets the synthesized numerator -t*w'(t).
    assert chart.numerators_input == (
        ParamNumerator(v_ascending=(0, 0, -2), denominator_scale=1),
    )


# --- silent reorder: input (x, y), printed (y, x) --------------------------


def test_reorder_is_surfaced_and_unmapped() -> None:
    output = parse_param(fixture("param_reorder.out"))
    assert isinstance(output, RationalParametrization)
    assert output.printed_variables == ("y", "x")

    chart = output.coordinates(("x", "y"))
    assert chart.printed_index == (1, 0)
    assert chart.reordered is True
    assert chart.added_variable is None
    assert chart.separating_input_index == 0  # input x is the parameter
    # The system was y = 0, x^2 - 3x + 2 = 0: witnesses (1, 0) and (2, 0).
    assert chart.point_at(Fraction(1)) == (Fraction(1), Fraction(0))
    assert chart.point_at(Fraction(2)) == (Fraction(2), Fraction(0))


# --- added linear form: three points, neither variable separating ----------


def test_added_variable_and_linear_form() -> None:
    output = parse_param(fixture("param_tri.out"))
    assert isinstance(output, RationalParametrization)
    assert output.printed_variables == ("x", "y", "A")
    assert output.linear_form_printed == (1, 1, 1)

    chart = output.coordinates(("x", "y"))
    assert chart.added_variable == "A"
    assert chart.separating_input_index is None
    assert chart.linear_form_input == (1, 1)  # t = -(x + y)

    # w = t^3 + 3t^2 + 2t with roots 0, -1, -2; the witnesses are the three
    # points {(0,0), (0,1), (1,1)}, and t = -(x + y) at each of them.
    points = {chart.point_at(Fraction(t)) for t in (0, -1, -2)}
    assert points == {
        (Fraction(0), Fraction(0)),
        (Fraction(0), Fraction(1)),
        (Fraction(1), Fraction(1)),
    }
    for t in (0, -1, -2):
        x, y = chart.point_at(Fraction(t))
        assert -(chart.linear_form_input[0] * x + chart.linear_form_input[1] * y) == t


def test_added_variable_name_collision_resolves_positionally() -> None:
    # msolve reuses the name 'A' for its added variable even when the input
    # already has one; identification must be positional, not by name.
    text = fixture("param_tri.out").replace("'x'", "'A'")
    output = parse_param(text)
    assert isinstance(output, RationalParametrization)
    assert output.printed_variables == ("A", "y", "A")

    chart = output.coordinates(("A", "y"))
    assert chart.printed_index == (0, 1)
    assert chart.added_variable == "A"
    assert chart.point_at(Fraction(-2)) == (Fraction(1), Fraction(1))


# --- non-radical input: msolve parametrizes the radical --------------------


def test_radical_degree_gap_is_allowed() -> None:
    output = parse_param(fixture("param_dbl.out"))
    assert isinstance(output, RationalParametrization)
    # x^2, y-1: quotient degree 2, but w = t has degree 1.
    assert output.quotient_degree == 2
    assert output.w_ascending == (0, 1)

    chart = output.coordinates(("x", "y"))
    assert chart.point_at(Fraction(0)) == (Fraction(0), Fraction(1))


# --- typed non-parametrization results -------------------------------------


def test_empty_solution_set() -> None:
    output = parse_param(fixture("param_empty.out"))
    assert isinstance(output, EmptySolutionSet)


def test_positive_dimensional() -> None:
    output = parse_param(fixture("param_posdim.out"))
    assert isinstance(output, PositiveDimensional)
    assert output.nvars == 2


# --- refusals: foreign modes and characteristic p --------------------------


def test_groebner_bytes_raise() -> None:
    with pytest.raises(MsolveAmbiguous):
        parse_param(fixture("ne_xy.out"))


def test_solver_bytes_raise() -> None:
    with pytest.raises(MsolveAmbiguous):
        parse_param(fixture("param_solver.out"))


def test_param_bytes_raise_in_groebner_parser() -> None:
    with pytest.raises(MsolveAmbiguous):
        parse_groebner(fixture("param_frac.out"))


def test_char_p_raises_typed() -> None:
    with pytest.raises(MsolveCharPParamUnsupported) as excinfo:
        parse_param(fixture("param_fp.out"))
    assert excinfo.value.characteristic == 1073741827
    assert isinstance(excinfo.value, MsolveOutputError)


# --- real-root boxes (-P 1) ------------------------------------------------


def test_boxes_are_exact_dyadic_fractions() -> None:
    output = parse_param(fixture("param_boxes_uni.out"))
    assert isinstance(output, RationalParametrization)
    boxes = output.real_solutions_printed
    assert boxes is not None and len(boxes) == 2
    (neg,), (pos,) = boxes
    assert isinstance(neg[0], Fraction) and isinstance(neg[1], Fraction)
    # The two roots of x^2 - 2, in increasing order, tightly enclosed.
    assert neg[0] <= neg[1] < 0 < pos[0] <= pos[1]
    assert (neg[1] - neg[0]) < Fraction(1, 2**100)
    assert neg[0] ** 2 <= 2 <= neg[1] ** 2 or neg[1] ** 2 <= 2 <= neg[0] ** 2


def test_boxes_follow_printed_order_and_chart_unmaps_them() -> None:
    output = parse_param(fixture("param_boxes_reorder.out"))
    assert isinstance(output, RationalParametrization)
    # Printed order is (y, x): y = 0 comes first in the raw boxes.
    assert output.real_solutions_printed == (
        ((Fraction(0), Fraction(0)), (Fraction(1), Fraction(1))),
        ((Fraction(0), Fraction(0)), (Fraction(2), Fraction(2))),
    )
    chart = output.coordinates(("x", "y"))
    assert chart.real_solutions_input == (
        ((Fraction(1), Fraction(1)), (Fraction(0), Fraction(0))),
        ((Fraction(2), Fraction(2)), (Fraction(0), Fraction(0))),
    )


def test_no_real_roots_is_an_empty_tuple() -> None:
    output = parse_param(fixture("param_boxes_noreal.out"))
    assert isinstance(output, RationalParametrization)
    assert output.real_solutions_printed == ()


# --- strictness: fabricated convention drift must raise --------------------


def test_wrong_multiplicity_slot_raises() -> None:
    text = fixture("param_frac.out").replace("[1,\n[[1, [-1, 3]]", "[2,\n[[1, [-1, 3]]")
    with pytest.raises(MsolveOutputError):
        parse_param(text)


def test_denominator_that_is_not_wprime_raises() -> None:
    text = fixture("param_frac.out").replace("[0, [3]]", "[0, [6]]")
    with pytest.raises(MsolveOutputError, match="derivative"):
        parse_param(text)


def test_nonpositive_scale_raises() -> None:
    for bad in ("0", "-2"):
        text = fixture("param_frac.out").replace("[[0, [-3]],\n2]", f"[[0, [-3]],\n{bad}]")
        with pytest.raises(MsolveOutputError, match="scale"):
            parse_param(text)


def test_coefficient_count_mismatch_raises() -> None:
    text = fixture("param_frac.out").replace("[1, [-1, 3]]", "[2, [-1, 3]]")
    with pytest.raises(MsolveOutputError):
        parse_param(text)


def test_truncated_output_raises() -> None:
    text = fixture("param_frac.out")
    with pytest.raises(MsolveOutputError):
        parse_param(text[: len(text) // 2])


def test_trailing_content_raises() -> None:
    with pytest.raises(MsolveOutputError):
        parse_param(fixture("param_frac.out").rstrip() + " [1]:")


def test_unit_form_tripwire_without_added_variable() -> None:
    output = parse_param(fixture("param_frac.out").replace("[0, 1]", "[1, 1]"))
    assert isinstance(output, RationalParametrization)
    with pytest.raises(MsolveOutputError, match="unit vector"):
        output.coordinates(("x", "y"))


def test_added_form_last_coefficient_tripwire() -> None:
    output = parse_param(fixture("param_tri.out").replace("[1,1,1]", "[1,1,2]"))
    assert isinstance(output, RationalParametrization)
    with pytest.raises(MsolveOutputError, match="coefficient is not 1"):
        output.coordinates(("x", "y"))


def test_chart_rejects_foreign_variables() -> None:
    output = parse_param(fixture("param_frac.out"))
    assert isinstance(output, RationalParametrization)
    with pytest.raises(MsolveOutputError):
        output.coordinates(("a", "b"))
    with pytest.raises(MsolveOutputError):
        output.coordinates(("x", "y", "z", "w"))


def test_mode_discipline() -> None:
    with pytest.raises(ValueError):
        parse_param(fixture("param_frac.out"), mode=Mode.GROEBNER)
    with pytest.raises(TypeError):
        parse_param(b"[-1]:")  # type: ignore[arg-type]
    with pytest.raises(MsolveOutputError):
        parse_param("")
