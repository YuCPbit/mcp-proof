"""Effect-aware conformance lane: unit + adversarial tests.

Pins the properties the research turns on:
- effects are read out-of-band, so a hidden write with an innocent response is
  seen (silent-keymint) while a response-only view is blind to it;
- authority is probed, not guessed — persistence ≠ authority;
- effectiveness is probed, not inferred from existence — a key outliving its
  grant is caught (residual authority);
- evidence discipline holds: with no probe, authority/effectiveness degrade to
  unknown and their checks SKIP, never a silent pass;
- the v0.8 trust inversion: a readOnly claim no longer rescues a tool into
  auto-call.
"""

import sys

from _paths import ROOT

sys.path.insert(0, str(ROOT / "testbed"))
sys.path.insert(0, str(ROOT / "experiments"))

from mcpproof.checks.base import FAIL, PASS, SKIP, WARN
from mcpproof.checks.effects import run_effect_checks
from mcpproof.effects.audit import run_effect_audit
from mcpproof.effects.model import (
    A_YES,
    E_CREATE,
    HOW_PROBED,
    HOW_UNKNOWN,
    EffectRecord,
    Evidenced,
    TargetRef,
)
from mcpproof.effects.observe import diff_snapshots, sqlite_snapshot
from mcpproof.effects.probes import NullProbe
from mcpproof.regression.recorder import classify_tool

# ------------------------------------------------------------------ units ----


def test_diff_snapshots_create_update_delete():
    before = {"t": {"a": {"v": 1}, "b": {"v": 2}}}
    after = {"t": {"a": {"v": 1}, "b": {"v": 9}, "c": {"v": 3}}}
    ops = {(d.op, d.key) for d in diff_snapshots(before, after)}
    assert ops == {("update", "b"), ("create", "c")}
    # a whole new store reads as creates
    d2 = diff_snapshots({}, {"s": {"x": {"v": 1}}})
    assert [(d.op, d.store, d.key) for d in d2] == [("create", "s", "x")]


def test_effect_record_round_trips():
    rec = EffectRecord("call#1:t", "t", {"a": 1}, {"readOnlyHint": True},
                       response_text="ok")
    rec.effect_type = Evidenced(E_CREATE, "observed", "created s/x")
    rec.targets = [TargetRef("s", "x")]
    rec.authority_bearing = Evidenced(A_YES, HOW_PROBED, "probe: exercised")
    back = EffectRecord.from_dict(rec.to_dict())
    assert back.tool == "t" and back.effect_type.value == E_CREATE
    assert back.authority_bearing.how == HOW_PROBED
    assert back.targets[0].store == "s"


def test_classify_tool_trust_inversion():
    # readOnly claim does NOT rescue a heuristically-mutating tool (v0.8)
    d, reason = classify_tool("run_query", "read-only query", {"readOnlyHint": True})
    assert d == "skip" and "unverified" in reason
    # annotations may still ADD caution
    assert classify_tool("fetch", "fetch data", {"destructiveHint": True})[0] == "skip"
    # a read-only claim on a safe-looking tool is simply not needed
    assert classify_tool("price", "quote", {"readOnlyHint": True})[0] == "auto"


def test_eff_checks_over_handbuilt_records():
    # a readOnly tool observed writing → EFF-01 FAIL
    r = EffectRecord("c1", "get_x", {}, {"readOnlyHint": True})
    r.effect_type = Evidenced("create", "observed", "created s/x")
    checks = {c.id: c for c in run_effect_checks([r])}
    assert checks["EFF-01"].status == FAIL
    # a delete with destructiveHint → EFF-02 PASS
    r2 = EffectRecord("c2", "del_x", {}, {"destructiveHint": True})
    r2.effect_type = Evidenced("delete", "observed", "deleted s/x")
    assert {c.id: c.status for c in run_effect_checks([r2])}["EFF-02"] == PASS


def test_eff02_follows_spec_default_semantics():
    """The spec's default for an UNSET destructiveHint is true (pessimistic),
    so absence is never a contradiction; only an explicit false is."""
    def delete_rec(declared):
        r = EffectRecord("c", "rotate_logs", {}, declared)
        r.effect_type = Evidenced("delete", "observed", "deleted logs/old")
        r.targets = [TargetRef("logs", "old", "delete")]
        return r

    # explicit destructiveHint=false + observed delete → the contradiction
    fail = {c.id: c for c in run_effect_checks([delete_rec({"destructiveHint": False})])}
    assert fail["EFF-02"].status == FAIL
    assert "destructiveHint=false" in fail["EFF-02"].evidence
    # unset hint + observed delete → covered by the spec default, PASS
    ok = {c.id: c for c in run_effect_checks([delete_rec({})])}
    assert ok["EFF-02"].status == PASS
    assert "default" in ok["EFF-02"].evidence
    # readOnly-declared tool that deletes: EFF-01's contradiction alone —
    # destructiveHint is meaningless under readOnly=true, so EFF-02 SKIPs
    ro = {c.id: c for c in run_effect_checks([delete_rec({"readOnlyHint": True})])}
    assert ro["EFF-01"].status == FAIL
    assert ro["EFF-02"].status == SKIP


def test_eff02_reads_per_target_ops_not_headline():
    """Regression pin for the filesystem case study: a call that creates one
    object AND deletes another headlines `create` (precedence), and the first
    EFF-02 implementation was blind to its delete. Per-target ops close that."""
    r = EffectRecord("c1", "move_thing", {}, {"destructiveHint": False})
    r.effect_type = Evidenced(E_CREATE, "observed",
                              "observed 2 change(s): create fs/b, delete fs/a")
    r.targets = [TargetRef("fs", "b", "create"), TargetRef("fs", "a", "delete")]
    checks = {c.id: c for c in run_effect_checks([r])}
    assert checks["EFF-02"].status == FAIL
    assert "fs/a" in checks["EFF-02"].evidence
    # with destructiveHint=true the same call is declared → PASS
    r.declared = {"destructiveHint": True}
    assert {c.id: c.status for c in run_effect_checks([r])}["EFF-02"] == PASS


def test_eff03_scoped_to_non_readonly_tools():
    """idempotentHint is meaningful only when readOnlyHint is false (spec): a
    repeated readOnly+idempotent read contributes nothing to EFF-03 — its
    writes, if any, are EFF-01's finding."""
    def read_rec():
        r = EffectRecord("c", "read_graph", {}, {"readOnlyHint": True, "idempotentHint": True})
        r.effect_type = Evidenced("none", "observed", "no change")
        return r

    checks = {c.id: c for c in run_effect_checks([read_rec(), read_rec()])}
    assert checks["EFF-03"].status == SKIP
    # a non-readOnly idempotent tool repeated with no effect → PASS
    def write_rec(effect):
        r = EffectRecord("c", "upsert", {"k": 1}, {"idempotentHint": True})
        r.effect_type = Evidenced(effect, "observed", f"{effect} s/k")
        return r

    ok = {c.id: c for c in run_effect_checks([write_rec("create"), write_rec("none")])}
    assert ok["EFF-03"].status == PASS
    bad = {c.id: c for c in run_effect_checks([write_rec("create"), write_rec("update")])}
    assert bad["EFF-03"].status == FAIL


def test_eff06_skips_without_probe():
    # a created authority object with UNKNOWN depends_on (no probe) → EFF-06 SKIP,
    # never a silent pass
    r = EffectRecord("c1", "mint", {}, {})
    r.effect_type = Evidenced(E_CREATE, "observed", "created keys/k1")
    r.authority_bearing = Evidenced(A_YES, HOW_PROBED, "probe: effective")
    r.depends_on = Evidenced(None, HOW_UNKNOWN, "")
    assert {c.id: c.status for c in run_effect_checks([r])}["EFF-06"] == SKIP


def test_sqlite_observer_introspects_arbitrary_tables(tmp_path):
    import sqlite3

    db = str(tmp_path / "x.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE widgets (id TEXT PRIMARY KEY, v INTEGER)")
    conn.execute("INSERT INTO widgets VALUES ('w1', 5)")
    conn.commit()
    conn.close()
    snap = sqlite_snapshot(db)
    assert snap["widgets"]["w1"]["v"] == 5


def test_filesystem_observer_sees_files_and_directories(tmp_path):
    """Files by content hash, directories as objects — so creating an empty
    directory is an observable effect, and a move reads as create+delete."""
    from mcpproof.effects.observe import FilesystemObserver

    obs = FilesystemObserver(tmp_path)
    before = obs.snapshot()
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.txt").write_text("alpha", encoding="utf-8")
    mid = obs.snapshot()
    ops = {(d.op, d.key) for d in obs.diff(before, mid)}
    assert ops == {("create", "sub"), ("create", "sub/a.txt")}
    # move = create at destination + delete at source
    (tmp_path / "sub" / "a.txt").rename(tmp_path / "sub" / "b.txt")
    after = obs.snapshot()
    ops2 = {(d.op, d.key) for d in obs.diff(mid, after)}
    assert ops2 == {("create", "sub/b.txt"), ("delete", "sub/a.txt")}
    # identical rewrite is a no-op (content hash, not mtime)
    (tmp_path / "sub" / "b.txt").write_text("alpha", encoding="utf-8")
    assert obs.diff(after, obs.snapshot()) == []


def test_jsonl_graph_snapshot_parses_entities_and_relations(tmp_path):
    from case_studies import jsonl_graph_snapshot

    store = tmp_path / "memory.jsonl"
    store.write_text(
        '{"type":"entity","name":"ada","entityType":"person","observations":["x"]}\n'
        '{"type":"relation","from":"ada","to":"proj","relationType":"maintains"}\n',
        encoding="utf-8")
    snap = jsonl_graph_snapshot(store)
    assert snap["entities"]["ada"]["entityType"] == "person"
    assert "ada→maintains→proj" in snap["relations"]
    assert jsonl_graph_snapshot(tmp_path / "absent.jsonl") == {"entities": {}, "relations": {}}


# ---------------------------------------------------- adversarial / e2e ----


async def _audit(mutations, differential=True):
    import os

    from harness import run_audit  # imported lazily so unit tests need no server
    records, db = await run_audit(mutations, differential=differential)
    if os.path.exists(db):
        os.unlink(db)
    return records


async def test_response_invisible_lie_caught_only_out_of_band():
    """silent-keymint: get_note is readOnly and returns the note body, but
    secretly mints an API key. The effect observer catches it; a response-only
    view cannot. This is the property response-level mcp-proof lacks."""
    from harness import detect_effect_aware, detect_response_level

    records = await _audit(["silent-keymint"])
    assert "get_note" in detect_effect_aware(records)
    assert "get_note" not in detect_response_level(records)
    # and it surfaces as an EFF-01 failure
    checks = {c.id: c for c in run_effect_checks(records)}
    assert checks["EFF-01"].status == FAIL
    assert "get_note" in checks["EFF-01"].evidence


async def test_explicit_nondestructive_lie_fails_eff02():
    """hide-destructive plants the spec-correct lie: delete_note explicitly
    declares destructiveHint=false ('additive updates only') while deleting.
    Merely dropping the hint would NOT be a lie — the spec default is true."""
    records = await _audit(["hide-destructive"], differential=False)
    rec = next(r for r in records if r.tool == "delete_note")
    assert rec.declared.get("destructiveHint") is False  # the explicit claim
    checks = {c.id: c for c in run_effect_checks(records)}
    assert checks["EFF-02"].status == FAIL
    assert "delete_note" in checks["EFF-02"].evidence


async def test_honest_server_no_effect_failures_but_flags_residual_authority():
    records = await _audit([])
    checks = {c.id: c for c in run_effect_checks(records)}
    assert checks["EFF-01"].status == PASS
    assert checks["EFF-02"].status == PASS
    # created api_key depends only on itself, not the grant that authorized it
    assert checks["EFF-06"].status == WARN
    key_recs = [r for r in records if r.tool == "create_api_key"]
    assert key_recs and key_recs[0].authority_bearing.value == A_YES
    dep = key_recs[0].depends_on
    assert dep.how == HOW_PROBED
    assert not any("grant" in str(d) for d in (dep.value or []))  # residual authority


async def test_persistence_not_equal_authority():
    """A persistent note is not authority-bearing; the probe says so even when
    its name looks like a credential."""
    records = await _audit([])
    notes = [r for r in records if r.tool == "save_note"]
    keys = [r for r in records if r.tool == "create_api_key"]
    assert notes and notes[0].authority_bearing.value != A_YES  # persistent, not authority
    assert keys and keys[0].authority_bearing.value == A_YES     # authority


async def test_null_probe_keeps_authority_unknown():
    """With no probe, authority is never invented — it stays unknown and the
    downstream check SKIPs rather than passing."""
    from mcpproof.effects.observe import TableStateObserver

    sys.path.insert(0, str(ROOT / "testbed"))
    import os
    import tempfile

    import saas_oracle as oracle
    from harness import PYTHON, SERVER, default_plan

    from mcpproof.client import open_session

    db = tempfile.mktemp(suffix=".db")
    cmd = [PYTHON, SERVER, "--db", db, "--grant", "grant_root"]
    async with open_session(cmd) as session:
        records = await run_effect_audit(
            session, default_plan(),
            TableStateObserver(lambda: oracle.snapshot_tables(db)),
            probe=NullProbe(),
        )
    if os.path.exists(db):
        os.unlink(db)
    key = [r for r in records if r.tool == "create_api_key"][0]
    assert key.authority_bearing.how == HOW_UNKNOWN
    assert {c.id: c.status for c in run_effect_checks(records)}["EFF-06"] == SKIP


async def test_effect_audit_is_deterministic():
    a = await _audit(["silent-keymint"], differential=False)
    b = await _audit(["silent-keymint"], differential=False)
    types_a = [(r.tool, r.effect_type.value, r.authority_bearing.value) for r in a]
    types_b = [(r.tool, r.effect_type.value, r.authority_bearing.value) for r in b]
    assert types_a == types_b
