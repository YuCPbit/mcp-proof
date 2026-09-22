"""Wire the SaaS testbed's out-of-band oracle into the effect layer's Probe
and LifecycleController interfaces.

Dependency direction is testbed → library: the effect layer knows nothing
about SQLite or this testbed; here we adapt ``saas_oracle`` to the abstract
interfaces so the same ``run_effect_audit`` works against any environment that
provides an observer + probe.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import saas_oracle as oracle  # noqa: E402

from mcpproof.effects.observe import TableStateObserver  # noqa: E402
from mcpproof.effects.probes import LifecycleController, Probe  # noqa: E402


def make_observer(db_path: str) -> TableStateObserver:
    """An observer that reads ground-truth state directly from the DB file —
    never through the audited MCP surface."""
    return TableStateObserver(lambda: oracle.snapshot_tables(db_path))


class SaasProbe(Probe):
    def __init__(self, db_path: str, cascade_grant: bool = False):
        self.db_path = db_path
        self.cascade_grant = cascade_grant

    def exercise(self, store: str, key: str, after_row: dict | None) -> tuple[str, str]:
        if after_row is None:
            return "not_applicable", "no object row to exercise"
        return oracle.exercise(self.db_path, store, after_row, cascade_grant=self.cascade_grant)


class SaasLifecycle(LifecycleController):
    """Revokes/restores the two candidate dependencies of a created credential:
    the grant that authorized it, and the object's own record."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def candidate_dependencies(self, store: str, key: str, after_row: dict | None) -> list[str]:
        if after_row is None or store not in ("api_keys", "webhooks", "share_links"):
            return []
        cands = [f"self:{store}:{key}"]
        grant = after_row.get("grant_id")
        if grant:
            cands.insert(0, f"grant:{grant}")
        return cands

    def revoke(self, dependency: str) -> None:
        kind, _, rest = dependency.partition(":")
        if kind == "grant":
            oracle.revoke_grant(self.db_path, rest)
        elif kind == "self":
            store, _, key = rest.partition(":")
            oracle.revoke_credential(self.db_path, store, key)

    def restore(self, dependency: str) -> None:
        kind, _, rest = dependency.partition(":")
        if kind == "grant":
            oracle.restore_grant(self.db_path, rest)
        elif kind == "self":
            store, _, key = rest.partition(":")
            oracle.restore_credential(self.db_path, store, key)
