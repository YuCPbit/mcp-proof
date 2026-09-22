"""Independent observation of external state.

An Observer takes point-in-time snapshots of external state and diffs two of
them into per-object deltas (create / update / delete). Crucially it observes
the state *directly* — a database file, a directory tree — never through the
audited MCP tools, so the effect evidence cannot be shaped by a tool's
response. This is the source of independence the whole layer rests on.

The snapshot shape is generic: ``{store: {object_key: fingerprint_dict}}``.
Two adapters ship: ``TableStateObserver`` (any callable returning that shape,
e.g. an out-of-band SQLite read) and ``FilesystemObserver`` (a jailed
directory). Adding a real provider would mean one more adapter, not a change
here — but doing so is out of scope for this measurement instrument.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CREATE, UPDATE, DELETE = "create", "update", "delete"

# A snapshot: store name -> {object key -> fingerprint dict (row / file meta)}
Snapshot = dict[str, dict[str, dict]]


@dataclass
class ObjectDelta:
    op: str            # create | update | delete
    store: str
    key: str
    after: dict | None  # the object's fingerprint after the call (None on delete)


def _fingerprint(obj: dict) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


def diff_snapshots(before: Snapshot, after: Snapshot) -> list[ObjectDelta]:
    """Per-object deltas between two snapshots. A store present in one and
    absent in the other is treated as empty on the missing side, so a whole
    new store's rows read as creates."""
    deltas: list[ObjectDelta] = []
    stores = sorted(set(before) | set(after))
    for store in stores:
        b = before.get(store, {})
        a = after.get(store, {})
        for key in sorted(set(a) - set(b)):
            deltas.append(ObjectDelta(CREATE, store, key, a[key]))
        for key in sorted(set(b) - set(a)):
            deltas.append(ObjectDelta(DELETE, store, key, None))
        for key in sorted(set(a) & set(b)):
            if _fingerprint(a[key]) != _fingerprint(b[key]):
                deltas.append(ObjectDelta(UPDATE, store, key, a[key]))
    return deltas


class Observer:
    """Base observer. Subclasses implement ``snapshot()``; ``diff`` is shared."""

    def snapshot(self) -> Snapshot:  # pragma: no cover - interface
        raise NotImplementedError

    def diff(self, before: Snapshot, after: Snapshot) -> list[ObjectDelta]:
        return diff_snapshots(before, after)


class TableStateObserver(Observer):
    """Wraps any callable that returns a ``{store: {key: row}}`` snapshot —
    e.g. an out-of-band SQLite read. The callable is the independence
    boundary: it must not go through the audited MCP surface."""

    def __init__(self, snapshot_fn: Callable[[], Snapshot]):
        self._fn = snapshot_fn

    def snapshot(self) -> Snapshot:
        return self._fn()


def sqlite_snapshot(db_path: str) -> Snapshot:
    """Generic out-of-band snapshot of every user table in a SQLite file.

    Introspects ``sqlite_master`` and keys each row by its primary key (or
    rowid when none is declared). Works on any SQLite-backed MCP server the
    operator can point at — the effect observer is not testbed-specific.
    """
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        tables = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        snap: Snapshot = {}
        for table in tables:
            info = conn.execute(f"PRAGMA table_info({table})").fetchall()  # noqa: S608
            pks = [c["name"] for c in info if c["pk"]]
            key_expr = pks[0] if len(pks) == 1 else "rowid"
            try:
                rows = conn.execute(f"SELECT rowid, * FROM {table}").fetchall()  # noqa: S608
            except sqlite3.OperationalError:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
            store: dict[str, dict] = {}
            for r in rows:
                d = {k: r[k] for k in r.keys() if k != "rowid"}
                key = str(r[key_expr]) if key_expr in r.keys() else str(r["rowid"])
                store[key] = d
            snap[table] = store
        return snap
    finally:
        conn.close()


class SqliteObserver(Observer):
    """Observes a SQLite-backed server out-of-band by reading its DB file. The
    file path is the independence boundary — the audit never asks the MCP tools
    what changed, it reads the store directly."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def snapshot(self) -> Snapshot:
        return sqlite_snapshot(self.db_path)


class FilesystemObserver(Observer):
    """Snapshots a jailed directory: each file becomes an object keyed by its
    path relative to the root, fingerprinted by size + content hash. Proves
    the observer abstraction is not SQLite-specific."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def snapshot(self) -> Snapshot:
        files: dict[str, dict] = {}
        if self.root.exists():
            for p in sorted(self.root.rglob("*")):
                if p.is_file():
                    data = p.read_bytes()
                    rel = str(p.relative_to(self.root))
                    files[rel] = {
                        "size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
        return {"files": files}
