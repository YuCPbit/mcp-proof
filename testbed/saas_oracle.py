"""Out-of-band oracle and credential-exercise probe for the SaaS testbed.

Independence contract: nothing here calls the audited MCP tools. Ground truth
comes from reading the SQLite file directly and from the by-construction
labels in saas_core / mutations. This is what lets the auditor's probe-based
verdicts be *scored* against a source the audited surface cannot influence.

The probe (`exercise`) is the auditor's own instrument, not ground truth: it
attempts to USE a created object to authorize an action and reports whether it
worked, by replaying the server's real auth rule (core.credential_effective)
against current state. In production this step would be a real provider API
call with the credential (e.g. GET /user with the key); in the testbed it is
an out-of-band evaluation of the same rule the server enforces, so the probe
is faithful by construction. It reads state; it never mutates it.
"""

from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).resolve().parent
import sys  # noqa: E402

sys.path.insert(0, str(_HERE))
import saas_core as core  # noqa: E402


def snapshot_tables(db_path: str) -> dict[str, dict[str, dict]]:
    """{table: {primary_key: row_as_dict}} for every state table — the raw
    material an independent observer diffs. Ground-truth state, read directly."""
    conn = core.connect(db_path)
    try:
        out: dict[str, dict[str, dict]] = {}
        pk = {"notes": "title"}
        for table in core.STATE_TABLES:
            key = pk.get(table, "id")
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
            out[table] = {str(r[key]): dict(r) for r in rows}
        return out
    finally:
        conn.close()


def read_tick(db_path: str) -> int:
    conn = core.connect(db_path)
    try:
        row = conn.execute("SELECT v FROM meta WHERE k='tick'").fetchone()
        return int(row["v"]) if row else 0
    finally:
        conn.close()


def exercise(db_path: str, table: str, row: dict, *, cascade_grant: bool = False) -> tuple[str, str]:
    """Try to USE the object as a credential. Returns (status, basis) where
    status ∈ {effective, ineffective, not_applicable}. A note is never a
    credential → not_applicable. A key/webhook/share token is effective iff
    the server's real rule would accept it right now."""
    col = core.CREDENTIAL_TABLES.get(table)
    if col is None:
        return "not_applicable", f"{table} rows carry no credential to exercise"
    secret = row.get(col)
    if not secret:
        return "ineffective", f"{table} row has no {col}"
    conn = core.connect(db_path)
    try:
        now = read_tick(db_path)
        ok = core.credential_effective(
            conn, table, secret, now_tick=now, cascade_grant=cascade_grant
        )
        basis = (
            f"exercised {table}.{col}: server auth rule "
            f"{'accepts' if ok else 'rejects'} it (status/expiry"
            f"{'/grant' if cascade_grant else ''} checked)"
        )
        return ("effective" if ok else "ineffective"), basis
    finally:
        conn.close()


# --- ground-truth mutations, used only for scoring (never by the effect layer) -
def revoke_grant(db_path: str, grant_id: str) -> None:
    _mutate(db_path, "UPDATE grants SET status='revoked' WHERE id=?", (grant_id,))


def restore_grant(db_path: str, grant_id: str) -> None:
    _mutate(db_path, "UPDATE grants SET status='active' WHERE id=?", (grant_id,))


def revoke_credential(db_path: str, table: str, row_id: str) -> None:
    if table not in core.CREDENTIAL_TABLES:
        return
    pk = "id"
    _mutate(db_path, f"UPDATE {table} SET status='revoked' WHERE {pk}=?", (row_id,))  # noqa: S608


def restore_credential(db_path: str, table: str, row_id: str) -> None:
    if table not in core.CREDENTIAL_TABLES:
        return
    _mutate(db_path, f"UPDATE {table} SET status='active' WHERE id=?", (row_id,))  # noqa: S608


def set_expiry(db_path: str, table: str, row_id: str, tick: int) -> None:
    if table != "api_keys":
        return
    _mutate(db_path, "UPDATE api_keys SET expires_at=? WHERE id=?", (tick, row_id))


def advance_tick(db_path: str, to: int) -> None:
    _mutate(db_path, "UPDATE meta SET v=? WHERE k='tick'", (str(to),))


def unlist_credential(db_path: str, table: str, row_id: str) -> None:
    """Delete a credential row entirely: it stops being listed AND stops
    working — the 'listed-but-dead' vs 'unlisted' control for E3."""
    if table not in core.CREDENTIAL_TABLES:
        return
    _mutate(db_path, f"DELETE FROM {table} WHERE id=?", (row_id,))  # noqa: S608


def _mutate(db_path: str, sql: str, params: tuple) -> None:
    conn = core.connect(db_path)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def by_construction_authority(table: str) -> bool | None:
    """The E2 ground-truth label. None when the table is not an object store."""
    return core.AUTHORITY_BEARING.get(table)
