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
    "MsolveVersionUnsupported",
    "MsolveTimeout",
    "MsolveDied",
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
