"""Effect-aware conformance: the declared-vs-observed methodology, extended
from response payloads to external state changes.

The existing lanes ask whether a server's *responses* honour its declared
input/output schemas. This layer asks the third question — whether a tool's
*effects on the world* honour its declared effect semantics (the MCP
annotations), whether a created object is authority-bearing, and whether it
stays effective across lifecycle events — using an observer that reads
external state out-of-band and probes that exercise created objects, never
the tool's own response, as evidence.
"""

from .model import (
    HOW_DECLARED,
    HOW_OBSERVED,
    HOW_PROBED,
    HOW_UNKNOWN,
    EffectRecord,
    Evidenced,
)

__all__ = [
    "EffectRecord",
    "Evidenced",
    "HOW_DECLARED",
    "HOW_OBSERVED",
    "HOW_PROBED",
    "HOW_UNKNOWN",
]
