"""Strict Python I/O for msolve: canonical input, mode-required output.

Groebner mode (``-g``) and characteristic-0 rational-parametrization mode
(``-P``). Bytes from any other msolve mode are rejected, not interpreted.

msolveio is not a computer algebra system and not a Groebner engine. It writes
``.ms`` files msolve will parse the way you meant, and reads back only the
output languages it can identify with certainty.
"""

from __future__ import annotations

from .emit import emit_system
from .errors import (
    MsolveAmbiguous,
    MsolveCharPParamUnsupported,
    MsolveDied,
    MsolveError,
    MsolveInputError,
    MsolveNotGeneric,
    MsolveOutputError,
    MsolveTimeout,
    MsolveVersionUnsupported,
)
from .mode import Mode
from .param import (
    EmptySolutionSet,
    ParamChart,
    ParamNumerator,
    ParamOutput,
    PositiveDimensional,
    RationalParametrization,
    parse_param,
)
from .parse import GroebnerOutput, parse_groebner
from .run import ParamResult, RunResult, run_groebner, run_param

__version__ = "0.2.1"

__all__ = [
    "Mode",
    "emit_system",
    "parse_groebner",
    "parse_param",
    "run_groebner",
    "run_param",
    "GroebnerOutput",
    "RunResult",
    "ParamResult",
    "ParamOutput",
    "RationalParametrization",
    "EmptySolutionSet",
    "PositiveDimensional",
    "ParamNumerator",
    "ParamChart",
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
