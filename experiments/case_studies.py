"""Case studies: effect-aware audits of third-party MCP servers.

E1–E3 establish detection behaviour on a testbed we built; the obvious
external-validity question is whether the instrument works on servers we did
NOT build. Each case study here points the same effect audit (out-of-band
observer + declared annotations + EFF checks) at a published third-party
server, chosen by these criteria: source publicly accessible, safe to run
locally, state isolable to a throwaway store, and the effect boundary
observable out-of-band (SQLite file, directory tree, or a local data file).

Three targets, three store types, three annotation profiles:

  memory      @modelcontextprotocol/server-memory      JSONL file   fully annotated
  filesystem  @modelcontextprotocol/server-filesystem  jailed dir   fully annotated
  sqlite      @executeautomation/database-server       SQLite file  no annotations

What these runs establish — and what they do not:

* The OBSERVATION half of the lane is exercised for real: per-object effect
  attribution, EFF-01/02/03 against annotations the servers themselves ship,
  and the honest-degradation path (nothing declared → SKIP, never invented).
* The PROBE half is deliberately not exercised: none of these services mints
  credential-like objects with a local authorization rule to exercise, so the
  audits run with a NullProbe and authority/effectiveness stay `unknown`
  (EFF-06 SKIP). Probe-backed authority/effectiveness results remain
  testbed-validated (E2/E3); a real-provider exercise adapter is future work.
* An all-PASS outcome is the honest result, not a failure of the method: it
  means the annotations these servers declare match their observed effects
  under this plan. The instrument's job is evidence either way.

Unlike E1–E3 these runs need the servers on the machine (`npx`, network on
first download), so they are NOT part of run_all.py or the CI reproduction
gate. Committed outputs are a record of a real audit (they may embed real
responses); versions are pinned below and recorded in the evidence.

    python experiments/case_studies.py            # all three
    python experiments/case_studies.py memory     # one target
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from mcpproof.checks.base import FAIL, WARN  # noqa: E402
from mcpproof.checks.effects import run_effect_checks  # noqa: E402
from mcpproof.client import open_session  # noqa: E402
from mcpproof.effects.audit import run_effect_audit  # noqa: E402
from mcpproof.effects.model import EffectRecord, records_to_dicts  # noqa: E402
from mcpproof.effects.observe import (  # noqa: E402
    FilesystemObserver,
    SqliteObserver,
    TableStateObserver,
)
from mcpproof.effects.report import render_effect_report  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

# Pinned versions: the evidence must say exactly what was audited.
MEMORY_PKG = "@modelcontextprotocol/server-memory@2026.8.31"
FILESYSTEM_PKG = "@modelcontextprotocol/server-filesystem@2026.8.31"
SQLITE_PKG = "@executeautomation/database-server@1.1.0"

TARGET_ORDER = ("memory", "filesystem", "sqlite")


# ------------------------------------------------------------- observers ----


def jsonl_graph_snapshot(path: Path) -> dict[str, dict[str, dict]]:
    """Out-of-band snapshot of the memory server's knowledge-graph store: one
    JSONL line per entity/relation. Entities are keyed by name, relations by
    (from, type, to). Read directly from the file — never through the tools."""
    entities: dict[str, dict] = {}
    relations: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("type") == "entity":
                entities[str(row.get("name"))] = row
            elif row.get("type") == "relation":
                key = f"{row.get('from')}→{row.get('relationType')}→{row.get('to')}"
                relations[key] = row
    return {"entities": entities, "relations": relations}


# ---------------------------------------------------------------- helpers ----


def _annotations_dict(ann) -> dict:
    if ann is None:
        return {}
    if isinstance(ann, dict):
        return {k: v for k, v in ann.items() if v is not None}
    out = {}
    for key in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
        v = getattr(ann, key, None)
        if v is not None:
            out[key] = v
    return out


async def _list_declared(session) -> dict[str, dict]:
    listed = await session.list_tools()
    return {t.name: _annotations_dict(getattr(t, "annotations", None)) for t in listed.tools}


def _annotation_profile(declared: dict[str, dict]) -> dict:
    return {
        "tools": len(declared),
        "annotated": sum(1 for a in declared.values() if a),
        "readonly_true": sum(1 for a in declared.values() if a.get("readOnlyHint") is True),
        "destructive_true": sum(1 for a in declared.values() if a.get("destructiveHint") is True),
        "idempotent_true": sum(1 for a in declared.values() if a.get("idempotentHint") is True),
    }


def _expand_path_variants(replacements: dict[str, str]) -> dict[str, str]:
    """Each local path plus its resolved form (macOS tmpdirs are symlinks:
    /var/folders/… realpaths to /private/var/folders/…) — a server may echo
    either spelling back."""
    out: dict[str, str] = {}
    for real, placeholder in replacements.items():
        out[real] = placeholder
        try:
            resolved = str(Path(real).resolve())
        except OSError:
            resolved = real
        if resolved != real:
            out[resolved] = placeholder
    # longest first, so /x/jail is consumed before /x
    return dict(sorted(out.items(), key=lambda kv: -len(kv[0])))


def _sanitize(obj, replacements: dict[str, str]):
    """Replace machine-local paths in the evidence with stable placeholders, so
    committed JSON identifies objects, not this machine's tempdir layout."""
    s = json.dumps(obj)
    for real, placeholder in _expand_path_variants(replacements).items():
        s = s.replace(json.dumps(real)[1:-1], placeholder)  # JSON-escaped form
    return json.loads(s)


def _check_dicts(checks) -> list[dict]:
    return [{"id": c.id, "level": c.level, "status": c.status, "evidence": c.evidence}
            for c in checks]


def _summary(records, checks) -> dict:
    by_status: dict[str, int] = {}
    for c in checks:
        by_status[c.status] = by_status.get(c.status, 0) + 1
    return {
        "calls": len(records),
        "effects_observed": {
            kind: sum(1 for r in records if r.effect_type.value == kind)
            for kind in ("create", "update", "delete", "none")
        },
        "checks": {c.id: c.status for c in checks},
        "failures": by_status.get(FAIL, 0),
        "warnings": by_status.get(WARN, 0),
    }


# ----------------------------------------------------------------- cases ----


async def run_memory_case() -> dict:
    """Official knowledge-graph memory server. Fully annotated tool surface
    over a JSONL file; the observer parses that file into per-entity /
    per-relation objects, so effects are attributed at object granularity."""
    state = Path(tempfile.mkdtemp(prefix="mcp_case_memory_"))
    store = state / "memory.jsonl"
    cmd = ["npx", "-y", MEMORY_PKG]
    observer = TableStateObserver(lambda: jsonl_graph_snapshot(store))
    plan = [
        ("create_entities", {"entities": [
            {"name": "ada", "entityType": "person",
             "observations": ["studies delegated authority"]},
            {"name": "mcp-proof", "entityType": "project",
             "observations": ["audits MCP servers"]},
        ]}),
        ("create_relations", {"relations": [
            {"from": "ada", "to": "mcp-proof", "relationType": "maintains"},
        ]}),
        ("add_observations", {"observations": [
            {"entityName": "ada", "contents": ["probes tool-created authority"]},
        ]}),
        # the three readOnlyHint=true tools — EFF-01's scope
        ("read_graph", {}),
        ("search_nodes", {"query": "delegated"}),
        ("open_nodes", {"names": ["ada"]}),
        # destructiveHint=true tools; deleting an observation/relation/entity
        ("delete_observations", {"deletions": [
            {"entityName": "ada", "observations": ["probes tool-created authority"]},
        ]}),
        ("delete_relations", {"relations": [
            {"from": "ada", "to": "mcp-proof", "relationType": "maintains"},
        ]}),
        ("delete_entities", {"entityNames": ["mcp-proof"]}),
        # repeated identical call of an idempotentHint=true tool — EFF-03's scope
        ("delete_entities", {"entityNames": ["mcp-proof"]}),
    ]
    async with open_session(cmd, env={"MEMORY_FILE_PATH": str(store)}) as session:
        declared = await _list_declared(session)
        records = await run_effect_audit(session, plan, observer, declared=declared)
    result = _assemble(
        declared=declared,
        target="memory",
        server={
            "package": MEMORY_PKG,
            "maintainer": "modelcontextprotocol (official reference server)",
            "command": f"npx -y {MEMORY_PKG}",
            "store": "knowledge-graph JSONL file (MEMORY_FILE_PATH)",
        },
        observer_desc="an out-of-band parse of the JSONL store into per-entity/"
                      "per-relation objects (TableStateObserver adapter, ~20 lines)",
        records=records, plan=plan,
        replacements={str(store): "<memory-file>", str(state): "<state>"},
        notes=[
            "All nine tools ship full annotations; the three readOnlyHint=true tools "
            "(read_graph, search_nodes, open_nodes) caused no observed change — EFF-01 "
            "verified against the server's own declarations.",
            "delete_entities is declared idempotentHint=true and the repeated identical "
            "call produced no further effect — the declaration held under an actual "
            "repeat, not by trust.",
            "Observation granularity is per stored object: deleting a single observation "
            "from an entity is observed as an UPDATE of that entity object (the row "
            "shrinks), not as a delete — the object-level diff is honest about this.",
        ],
    )
    shutil.rmtree(state, ignore_errors=True)
    return result


async def run_filesystem_case() -> dict:
    """Official filesystem server on a jailed directory, observed with the
    stock FilesystemObserver — no target-specific adapter at all."""
    state = Path(tempfile.mkdtemp(prefix="mcp_case_fs_"))
    jail = state / "jail"
    jail.mkdir()
    cmd = ["npx", "-y", FILESYSTEM_PKG, str(jail)]
    observer = FilesystemObserver(jail)
    ws = str(jail / "workspace")
    a_txt = str(jail / "workspace" / "a.txt")
    b_txt = str(jail / "workspace" / "b.txt")
    plan = [
        ("create_directory", {"path": ws}),
        ("create_directory", {"path": ws}),                       # idempotent repeat
        ("write_file", {"path": a_txt, "content": "alpha v1\n"}),
        ("write_file", {"path": a_txt, "content": "alpha v1\n"}),  # idempotent repeat
        # the ten readOnlyHint=true tools — EFF-01's scope
        ("read_file", {"path": a_txt}),
        ("read_text_file", {"path": a_txt}),
        ("read_media_file", {"path": a_txt}),
        ("read_multiple_files", {"paths": [a_txt]}),
        ("get_file_info", {"path": a_txt}),
        ("list_directory", {"path": str(jail)}),
        ("list_directory_with_sizes", {"path": str(jail)}),
        ("directory_tree", {"path": str(jail)}),
        ("search_files", {"path": str(jail), "pattern": "a.txt"}),
        ("list_allowed_directories", {}),
        ("edit_file", {"path": a_txt, "edits": [
            {"oldText": "alpha v1", "newText": "alpha v2"},
        ]}),
        # move = observed create (dest) + delete (source); destructiveHint=true
        ("move_file", {"source": a_txt, "destination": b_txt}),
    ]
    async with open_session(cmd) as session:
        declared = await _list_declared(session)
        records = await run_effect_audit(session, plan, observer, declared=declared)
    result = _assemble(
        declared=declared,
        target="filesystem",
        server={
            "package": FILESYSTEM_PKG,
            "maintainer": "modelcontextprotocol (official reference server)",
            "command": f"npx -y {FILESYSTEM_PKG} <jail>",
            "store": "jailed directory tree",
        },
        observer_desc="the stock FilesystemObserver over the jail root — files by "
                      "content hash, directories as objects; zero target-specific code",
        records=records, plan=plan,
        replacements={str(jail): "<jail>", str(state): "<state>"},
        notes=[
            "All ten readOnlyHint=true tools caused no observed filesystem change — "
            "EFF-01 verified against the server's own declarations.",
            "move_file is observed as create(destination) + delete(source); its "
            "destructiveHint=true declaration covers the observed delete (EFF-02).",
            "This call improved the instrument: EFF-02's first implementation read only "
            "the record's headline effect, where create outranks delete — so move_file's "
            "delete was invisible to it (a lying tool could mask a delete by also creating "
            "something). EFF-02 now reads per-target ops; the gap was found by this case "
            "study, not by the testbed.",
            "write_file and create_directory declare idempotentHint=true; the repeated "
            "identical calls left the tree byte-identical, so the claim held under an "
            "actual repeat.",
        ],
    )
    shutil.rmtree(state, ignore_errors=True)
    return result


async def run_sqlite_case() -> dict:
    """Community SQLite server (ExecuteAutomation database-server). Declares no
    annotations at all — the ecosystem's common case — so this run demonstrates
    the honest-degradation path: observed effects are still attributed
    per-row, but checks with nothing declared to verify SKIP rather than
    inventing a verdict, and an observed delete under an UNSET hint is covered
    by the spec's pessimistic default (destructiveHint ⇒ true), not flagged."""
    state = Path(tempfile.mkdtemp(prefix="mcp_case_sqlite_"))
    db = state / "case.db"
    cmd = ["npx", "-y", SQLITE_PKG, str(db)]
    observer = SqliteObserver(str(db))
    plan = [
        ("create_table", {"query":
            "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, qty INTEGER)"}),
        ("write_query", {"query": "INSERT INTO items (name, qty) VALUES ('anvil', 3)"}),
        ("write_query", {"query": "INSERT INTO items (name, qty) VALUES ('rope', 10)"}),
        ("read_query", {"query": "SELECT * FROM items ORDER BY id"}),
        ("list_tables", {}),
        ("describe_table", {"table_name": "items"}),
        ("write_query", {"query": "UPDATE items SET qty = 4 WHERE name = 'anvil'"}),
        ("write_query", {"query": "DELETE FROM items WHERE name = 'rope'"}),
        # persisted by the server into a table of its own (mcp_insights) — the
        # generic sqlite_master walk sees stores the audit never created
        ("append_insight", {"insight": "rope stock was removed"}),
        ("list_insights", {}),
    ]
    async with open_session(cmd) as session:
        declared = await _list_declared(session)
        records = await run_effect_audit(session, plan, observer, declared=declared)
    result = _assemble(
        declared=declared,
        target="sqlite",
        server={
            "package": SQLITE_PKG,
            "maintainer": "ExecuteAutomation (community)",
            "command": f"npx -y {SQLITE_PKG} <db>",
            "store": "SQLite database file",
        },
        observer_desc="the stock SqliteObserver (generic sqlite_master introspection) "
                      "over the DB file — the same channel `mcp-proof effects --sqlite` "
                      "ships; zero target-specific code",
        records=records, plan=plan,
        replacements={str(db): "<db>", str(state): "<state>"},
        notes=[
            "No tool declares any annotation — the ecosystem's common case. EFF-01/03 "
            "SKIP (nothing declared to verify); the observed DELETE from write_query is "
            "covered by the spec's pessimistic default for an unset destructiveHint and "
            "is therefore consistent, not a contradiction.",
            "Effects are still attributed per row (create/update/delete of items/<id>) "
            "even with nothing declared — observation does not depend on annotations.",
            "append_insight turned out to persist into a table the audit never created "
            "(mcp_insights) — caught because the observer introspects sqlite_master "
            "rather than diffing a hand-listed table set. (Its archived Python "
            "predecessor kept insights in process memory; verifying before writing "
            "this note corrected our own assumption.)",
            "Observation granularity, honestly: create_table of an EMPTY table is a "
            "schema-level change below the row-level diff (no rows → no per-object "
            "delta); the table becomes visible the moment it holds a row. The record "
            "for create_table therefore shows no observed per-object change.",
        ],
    )
    shutil.rmtree(state, ignore_errors=True)
    return result


# ------------------------------------------------------------- assembly ----


def _assemble(*, target: str, server: dict, observer_desc: str, records,
              declared: dict[str, dict], plan, replacements: dict[str, str],
              notes: list[str]) -> dict:
    probe_desc = ("none — this service mints no credential-like object with a local "
                  "authorization rule to exercise, so authority/effectiveness stay "
                  "unknown and EFF-06 SKIPs (probe-backed classification remains "
                  "validated on the controlled testbed, E2/E3)")
    # sanitize the records FIRST, then derive checks/report from the sanitized
    # view — so no downstream truncation can cut a placeholder-substitution
    # target in half. The checks are pure functions of the records; statuses
    # are identical either way.
    san_records = [
        EffectRecord.from_dict(d)
        for d in _sanitize(records_to_dicts(records), replacements)
    ]
    checks = run_effect_checks(san_records)
    result = {
        "case": "third_party_effect_audit",
        "target": target,
        "server": server,
        "observer": observer_desc,
        "probe": probe_desc,
        # profile of the SERVED tool surface (tools/list), not just the
        # tools the plan happened to call
        "annotations_profile": _annotation_profile(declared),
        "plan": _sanitize([[tool, args] for tool, args in plan], replacements),
        "checks": _check_dicts(checks),
        "summary": _summary(san_records, checks),
        "notes": notes,
        "records": records_to_dicts(san_records),
    }

    html = render_effect_report(
        f"{server['package']} (case study)", san_records, checks,
        observer_desc=observer_desc, probe_desc=probe_desc,
    )
    (RESULTS / f"effect-report-case-{target}.html").write_text(html, encoding="utf-8")
    return result


def _render_md(result: dict) -> str:
    s = result["summary"]
    prof = result["annotations_profile"]
    lines = [f"# Case study — {result['server']['package']}\n"]
    lines.append(
        f"Third-party server ({result['server']['maintainer']}); store: "
        f"{result['server']['store']}. {s['calls']} calls; observed effects: "
        f"{s['effects_observed']['create']} create / {s['effects_observed']['update']} "
        f"update / {s['effects_observed']['delete']} delete. Annotation profile: "
        f"{prof['annotated']}/{prof['tools']} tools annotated "
        f"({prof['readonly_true']} readOnly, {prof['destructive_true']} destructive, "
        f"{prof['idempotent_true']} idempotent).\n")
    lines.append("| check | level | status | evidence |")
    lines.append("|---|---|---|---|")
    for c in result["checks"]:
        ev = c["evidence"].replace("|", "\\|")
        lines.append(f"| {c['id']} | {c['level']} | {c['status']} | {ev} |")
    lines.append("")
    for n in result["notes"]:
        lines.append(f"- {n}")
    return "\n".join(lines) + "\n"


CASES = {
    "memory": run_memory_case,
    "filesystem": run_filesystem_case,
    "sqlite": run_sqlite_case,
}


def load_committed_case_results() -> list[dict]:
    """The committed case JSONs, in stable order — what run_all.py renders.
    Missing files are simply absent (the page section renders what exists)."""
    out = []
    for target in TARGET_ORDER:
        p = RESULTS / f"case_{target}.json"
        if p.exists():
            out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def main(targets: list[str] | None = None) -> None:
    RESULTS.mkdir(exist_ok=True)
    for target in targets or list(TARGET_ORDER):
        print(f"→ case study: {target}")
        result = asyncio.run(CASES[target]())
        (RESULTS / f"case_{target}.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (RESULTS / f"case_{target}.md").write_text(_render_md(result), encoding="utf-8")
        verdict = ", ".join(f"{c['id']}={c['status']}" for c in result["checks"])
        fails = result["summary"]["failures"]
        print(f"  {verdict}")
        print(f"  {'✗' if fails else '✓'} {result['server']['package']}: "
              f"{fails} effect-conformance failure(s)")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
