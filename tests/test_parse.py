"""Parser tests. These run against checked-in msolve 0.10.1 output only --
nothing here invokes msolve."""

from __future__ import annotations

from pathlib import Path

import pytest

from msolveio import (
    GroebnerOutput,
    Mode,
    MsolveAmbiguous,
    MsolveOutputError,
    parse_groebner,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_unit_ideal_over_q() -> None:
    out = parse_groebner(fixture("unit_qq.out"))
    assert out.unit_ideal is True
    assert out.basis == ("1",)
    assert out.leading_only is False
    assert out.characteristic == 0
    assert out.variables == ("x", "y")


def test_unit_ideal_over_prime_field() -> None:
    out = parse_groebner(fixture("unit_fp.out"))
    assert out.unit_ideal is True
    assert out.characteristic == 65521


def test_nonempty_univariate() -> None:
    out = parse_groebner(fixture("ne_univariate.out"))
    assert out.unit_ideal is False
    assert out.basis == ("x^2-1",)
    assert out.variables == ("x",)


def test_positive_dimensional_basis_still_parses() -> None:
    out = parse_groebner(fixture("posdim.out"))
    assert out.unit_ideal is False
    assert out.basis == ("x-1",)


def test_leading_ideal() -> None:
    out = parse_groebner(fixture("leading.out"))
    assert out.leading_only is True
    assert out.basis == ("x", "y^2")
    assert out.unit_ideal is False


def test_multiline_basis_three_generators() -> None:
    out = parse_groebner(fixture("ne_xy.out"))
    assert out.basis == ("y^2+x", "x*y-1", "x^2+y")
    assert len(out.basis) == 3
    assert out.monomial_order == "graded reverse lexicographical"


def test_rational_coefficients_round_trip() -> None:
    out = parse_groebner(fixture("good_rat.out"))
    assert out.basis == ("x-2",)
    assert out.characteristic == 0


def test_solver_output_is_ambiguous_not_a_basis() -> None:
    """The inversion guard. Solver '[-1]:' means NO solutions; Groebner '[1]:'
    means the unit ideal. Reading one as the other flips the answer."""
    with pytest.raises(MsolveAmbiguous):
        parse_groebner(fixture("solver_unit.out"))


@pytest.mark.parametrize(
    "text",
    [
        "[-1]:\n",
        "[1, 2, -1, []]:\n",
        "[0, [1, 2]]:\n",
    ],
)
def test_solver_shapes_rejected(text: str) -> None:
    with pytest.raises(MsolveAmbiguous):
        parse_groebner(text)


def test_truncated_body_is_an_error_not_a_unit_ideal() -> None:
    with pytest.raises(MsolveOutputError) as excinfo:
        parse_groebner("#Reduced Groebner basis data\n[1")
    assert not isinstance(excinfo.value, GroebnerOutput)


def test_truncated_after_valid_header() -> None:
    text = fixture("unit_qq.out").replace("[1]:\n", "[1\n")
    with pytest.raises(MsolveOutputError):
        parse_groebner(text)


def test_junk_after_closing_bracket() -> None:
    with pytest.raises(MsolveOutputError):
        parse_groebner(fixture("unit_qq.out") + "surprise\n")


def test_empty_output() -> None:
    with pytest.raises(MsolveOutputError):
        parse_groebner("")
    with pytest.raises(MsolveOutputError):
        parse_groebner("   \n\n")


def test_missing_header() -> None:
    body = fixture("unit_qq.out").split("\n", 1)[1]
    with pytest.raises(MsolveOutputError):
        parse_groebner(body)


def test_missing_characteristic() -> None:
    text = "\n".join(
        line
        for line in fixture("ne_xy.out").splitlines()
        if not line.startswith("#field characteristic")
    )
    with pytest.raises(MsolveOutputError):
        parse_groebner(text)


def test_declared_length_must_match() -> None:
    text = fixture("ne_xy.out").replace("3 elements", "4 elements")
    with pytest.raises(MsolveOutputError):
        parse_groebner(text)


def test_output_is_frozen() -> None:
    out = parse_groebner(fixture("unit_qq.out"))
    with pytest.raises(Exception):
        out.unit_ideal = False  # type: ignore[misc]


def test_mode_must_be_groebner() -> None:
    assert list(Mode) == [Mode.GROEBNER]
    assert not hasattr(Mode, "SOLVER")
    with pytest.raises(ValueError):
        parse_groebner(fixture("unit_qq.out"), mode="solver")  # type: ignore[arg-type]
