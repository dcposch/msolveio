"""Output-language selector.

msolve prints a different language in each mode and does not always make the
mode obvious from the bytes. Callers name the mode they expect. There is
deliberately no ``Mode.SOLVER`` member: an enum value the library cannot
honour would be a promise it does not keep.
"""

from __future__ import annotations

import enum

__all__ = ["Mode"]


class Mode(enum.Enum):
    """The msolve output language a caller expects."""

    #: Groebner basis output, i.e. msolve invoked with ``-g 1`` or ``-g 2``.
    GROEBNER = "groebner"

    #: Rational-parametrization output, i.e. msolve invoked with ``-P 1`` or
    #: ``-P 2``.
    PARAM = "param"
