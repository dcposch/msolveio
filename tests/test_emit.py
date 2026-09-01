"""Emitter tests: what msolveio will and will not write to a .ms file."""

from __future__ import annotations

from pathlib import Path

import pytest

from msolveio import MsolveInputError, emit_system
from msolveio import emit as emit_module

FIXTURES = Path(__file__).parent / "fixtures"


def test_basic_system() -> None:
    text = emit_system(["x^2+y", "x*y-1"], variables=["x", "y"])
    assert text == "x,y\n0\nx^2+y,\nx*y-1\n"


def test_matches_checked_in_fixture() -> None:
    assert emit_system(["x^2+y", "x*y-1"], variables=["x", "y"]) == (
        FIXTURES / "ne_xy.ms"
    ).read_text()


def test_no_trailing_comma_on_last_polynomial() -> None:
    text = emit_system(["x-1", "y-2", "x*y"], variables=["x", "y"])
    body = text.splitlines()[2:]
    assert body == ["x-1,", "y-2,", "x*y"]
    assert not text.rstrip("\n").endswith(",")


def test_prime_characteristic() -> None:
    text = emit_system(["x-1", "x"], variables=["x", "y"], characteristic=65521)
    assert text == (FIXTURES / "unit_fp.ms").read_text()


def test_whitespace_is_insignificant() -> None:
    assert emit_system([" x^2 + y "], variables=["x", "y"]) == "x,y\n0\nx^2+y\n"


def test_leading_rational_allowed_over_q_and_round_trips() -> None:
    text = emit_system(["1/2*x-1"], variables=["x"])
    assert text == "x\n0\n1/2*x-1\n"
    assert text == (FIXTURES / "good_rat.ms").read_text()


def test_negative_rational_allowed_over_q() -> None:
    assert emit_system(["-2/3*x*y+1"], variables=["x", "y"]) == (
        "x,y\n0\n-2/3*x*y+1\n"
    )


def test_leading_rational_rejected_over_prime_field() -> None:
    with pytest.raises(MsolveInputError, match="prime field"):
        emit_system(["1/2*x"], variables=["x"], characteristic=7)


@pytest.mark.parametrize(
    "poly, match",
    [
        ("x-(3+1)", "parenthes"),
        ("(x+1)", "parenthes"),
        ("x/2-1", "division"),
        ("x*y/2", "division"),
        ("*x", r"begins with"),
        ("x+z", "unknown identifier"),
        ("x+foo", "unknown identifier"),
        ("", "empty polynomial"),
        ("   ", "empty polynomial"),
        ("x^0", "positive integer"),
        ("x^y", "positive integer"),
        ("x^-1", "positive integer"),
        ("x+", "trailing"),
        ("x*", "trailing"),
        ("x_1", "identifier character"),
        ("2x", r"expected '\*'"),
        ("x+x", "more than once"),
        ("x*y+2*y*x", "more than once"),
        ("1/0*x", "zero denominator"),
    ],
)
def test_rejected_polynomials(poly: str, match: str) -> None:
    with pytest.raises(MsolveInputError, match=match):
        emit_system([poly], variables=["x", "y"])


@pytest.mark.parametrize(
    "name",
    ["", "x y", "x,y", "x^2", "x*y", "x/y", "x_1", "1x", "_x"],
)
def test_rejected_variable_names(name: str) -> None:
    with pytest.raises(MsolveInputError):
        emit_system(["1"], variables=[name])


def test_duplicate_variables_rejected() -> None:
    with pytest.raises(MsolveInputError, match="duplicate"):
        emit_system(["x"], variables=["x", "x"])


def test_no_variables_rejected() -> None:
    with pytest.raises(MsolveInputError):
        emit_system(["1"], variables=[])


def test_no_polynomials_rejected() -> None:
    with pytest.raises(MsolveInputError):
        emit_system([], variables=["x"])


def test_bare_strings_rejected() -> None:
    with pytest.raises(MsolveInputError):
        emit_system("x-1", variables=["x"])  # type: ignore[arg-type]
    with pytest.raises(MsolveInputError):
        emit_system(["x-1"], variables="x")  # type: ignore[arg-type]


@pytest.mark.parametrize("characteristic", [-1, -7, 1, 4, 9, 2**31, 2**31 + 1, 2**64])
def test_rejected_characteristics(characteristic: int) -> None:
    with pytest.raises(MsolveInputError):
        emit_system(["x"], variables=["x"], characteristic=characteristic)


@pytest.mark.parametrize("characteristic", [0, 2, 3, 65521, 2**31 - 1])
def test_accepted_characteristics(characteristic: int) -> None:
    emit_system(["x-1"], variables=["x"], characteristic=characteristic)


def test_coefficient_overflow_over_prime_field() -> None:
    with pytest.raises(MsolveInputError, match="64-bit"):
        emit_system([f"{2**63}*x"], variables=["x"], characteristic=65521)


def test_large_coefficient_allowed_over_q() -> None:
    emit_system([f"{2**200}*x-1"], variables=["x"])


def test_term_count_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real bound is 2**31 - 1; lower it so the test stays small."""
    monkeypatch.setattr(emit_module, "MAX_TERM_VAR_PRODUCT", 5)
    # 3 terms * 2 vars = 6 > 5
    with pytest.raises(MsolveInputError, match="too large"):
        emit_system(["x+y", "x*y"], variables=["x", "y"])
    # 2 terms * 2 vars = 4 <= 5
    emit_system(["x+y"], variables=["x", "y"])


def test_real_bound_is_the_32_bit_one() -> None:
    assert emit_module.MAX_TERM_VAR_PRODUCT == 2**31 - 1
