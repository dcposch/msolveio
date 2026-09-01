"""Strict Python I/O for msolve: canonical input, mode-required output.

Groebner-mode (``-g``) only in v0.1. Solver-mode bytes are rejected, not
interpreted.

msolveio is not a computer algebra system and not a Groebner engine. It writes
``.ms`` files msolve will parse the way you meant, and reads back only the one
output language it can identify with certainty.
"""

from __future__ import annotations

from .emit import emit_system
from .errors import (
    MsolveAmbiguous,
    MsolveDied,
    MsolveError,
    MsolveInputError,
    MsolveOutputError,
    MsolveTimeout,
    MsolveVersionUnsupported,
)
from .mode import Mode
from .parse import GroebnerOutput, parse_groebner
from .run import RunResult, run_groebner

__version__ = "0.1.0"

__all__ = [
    "Mode",
    "emit_system",
    "parse_groebner",
    "run_groebner",
    "GroebnerOutput",
    "RunResult",
    "MsolveError",
    "MsolveInputError",
    "MsolveOutputError",
    "MsolveAmbiguous",
    "MsolveVersionUnsupported",
    "MsolveTimeout",
    "MsolveDied",
]
