"""Exception hierarchy for :mod:`msolveio`.

Every failure mode is a distinct type. Nothing here is a warning: msolveio
refuses ambiguous bytes rather than guessing at their meaning.
"""

from __future__ import annotations

__all__ = [
    "MsolveError",
    "MsolveInputError",
    "MsolveOutputError",
    "MsolveAmbiguous",
    "MsolveCharPParamUnsupported",
    "MsolveVersionUnsupported",
    "MsolveTimeout",
    "MsolveDied",
    "MsolveNotGeneric",
]


class MsolveError(Exception):
    """Base class for every error raised by msolveio."""


class MsolveInputError(MsolveError):
    """The caller asked us to emit something msolve would mis-parse.

    Raised by :func:`msolveio.emit_system`. msolveio never rewrites input to
    make it legal; it reports what is wrong and stops.
    """


class MsolveOutputError(MsolveError):
    """msolve output was malformed, truncated, or not Groebner-mode output."""


class MsolveAmbiguous(MsolveOutputError):
    """The bytes look like output from a *different* msolve mode.

    Most importantly, solver-mode output such as ``[-1]:`` is a valid-looking
    list that means "no solutions", not "the Groebner basis is ``[-1]``".
    Interpreting it as a basis would silently invert the answer, so this is a
    hard error.
    """


class MsolveCharPParamUnsupported(MsolveOutputError):
    """The bytes are a valid parametrization, but over a prime field.

    msolve's characteristic-p parametrization output uses a different grammar
    from the characteristic-0 one (numerator entries carry no scale constant,
    and the printed denominator need not be the derivative of the eliminating
    polynomial). Parsing it with the characteristic-0 conventions would produce
    wrong witness points that still pass casual arithmetic, so this release
    refuses it outright. Planned for a later msolveio release.
    """

    def __init__(self, message: str, *, characteristic: int) -> None:
        super().__init__(message)
        self.characteristic = characteristic


class MsolveVersionUnsupported(MsolveError):
    """The msolve binary is not a 0.10.x release (and the caller did not opt in)."""

    def __init__(self, message: str, *, version: str | None = None) -> None:
        super().__init__(message)
        self.version = version


class MsolveTimeout(MsolveError):
    """msolve exceeded the caller-supplied wall-clock timeout and was killed."""

    def __init__(self, message: str, *, timeout: float) -> None:
        super().__init__(message)
        self.timeout = timeout


class MsolveDied(MsolveError):
    """msolve exited nonzero, was killed by a signal, or produced no output."""

    def __init__(
        self,
        message: str,
        *,
        returncode: int | None = None,
        signal: int | None = None,
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.signal = signal
        self.stderr = stderr


class MsolveNotGeneric(MsolveDied):
    """msolve refused the system because the staircase is not generic enough.

    Raised only when the caller restricted msolve's genericity handling
    (``genericity=0`` or ``1``) and the restriction was not sufficient. Re-run
    with ``genericity=2`` (the default) to let msolve add a linear form with a
    new variable; the resulting chart change is surfaced on the parsed result.
    """
