"""Probe interfaces: how the auditor gathers authority and effectiveness
evidence by *exercising* objects, not by trusting names or persistence.

Two abstractions, both implemented by whatever environment is under audit:

* ``Probe.exercise`` attempts to USE a created object to authorize an action
  and reports effective / ineffective / not_applicable. Authority-bearing is
  then an operational verdict — the object let us do something security-
  relevant — rather than a guess from a field name.

* ``LifecycleController`` performs the out-of-band state changes that
  differential probing and lifecycle experiments need (revoke a grant, revoke
  the object itself, advance a clock), each paired with a restore so the audit
  can probe counterfactuals without leaving damage.

Both are deliberately thin. The effect layer never assumes a specific backend;
the testbed supplies concrete adapters. A ``NullProbe`` lets the audit run
with no probe at all — every authority/effectiveness verdict then honestly
degrades to ``unknown`` rather than being invented.
"""

from __future__ import annotations

# exercise outcomes
EFFECTIVE = "effective"
INEFFECTIVE = "ineffective"
NOT_APPLICABLE = "not_applicable"   # a probe RAN and the object is not a credential
UNKNOWN = "unknown"                 # no probe could run — absence of evidence, not a 'no'


class Probe:
    """Exercises a created object as a credential."""

    def exercise(self, store: str, key: str, after_row: dict | None) -> tuple[str, str]:
        """Return (status, basis). status ∈ effective | ineffective |
        not_applicable. ``basis`` explains what was exercised, for evidence."""
        raise NotImplementedError


class NullProbe(Probe):
    """No exercise channel. Returns UNKNOWN (not NOT_APPLICABLE): the object was
    never exercised, so authority/effectiveness stay unknown and their checks
    SKIP — absence of evidence is never a definitive 'not authority-bearing'."""

    def exercise(self, store: str, key: str, after_row: dict | None) -> tuple[str, str]:
        return UNKNOWN, "no probe configured for this environment"


class LifecycleController:
    """Out-of-band lifecycle operations for differential probing and E3.

    Each ``revoke_*`` should be reversible via the matching ``restore_*`` so a
    differential probe can test 'does effectiveness survive revoking X?' and
    put the world back. Implementations act on ground-truth state directly,
    never through the audited MCP tools.
    """

    def candidate_dependencies(self, store: str, key: str, after_row: dict | None) -> list[str]:
        """Named candidates whose revocation might disable the object, e.g.
        ['grant:grant_root', 'self']. Differential probing tests each."""
        return []

    def revoke(self, dependency: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def restore(self, dependency: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError
