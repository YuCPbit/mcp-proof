"""v0.7 integrity hardening: the audit must fail closed.

Adversarial coverage for the v0.6 review findings: violations hidden on page
2 of any surface, fixture sets tampered with after recording, non-text and
structured value drift that used to pass the gate as COSMETIC, synthesized
arguments that were never proven valid, and MSSS verdicts that outran their
evidence.
"""

import json
import shutil
from pathlib import Path

import pytest
from _paths import venv_python

from mcpproof.checks.base import FAIL, PASS, SKIP, WARN
from mcpproof.checks.conformance import run_conformance
from mcpproof.checks.security import run_security
from mcpproof.pagination import collect_paginated
from mcpproof.provenance import obj_hash
from mcpproof.regression import record, replay, summarize
from mcpproof.regression.negative import negative_variants
from mcpproof.regression.replayer import _classify, _value_drift, verify_fixture_set
from mcpproof.regression.sampler import synthesize_valid_args
from mcpproof.schemas import iter_properties

PYTHON = venv_python()
HERE = Path(__file__).resolve().parent
PAGINATED = [PYTHON, str(HERE / "paginated_surfaces_server.py")]
REGRESSION_SERVER = [PYTHON, str(HERE / "regression_target_server.py")]
MODERN = [PYTHON, str(HERE / "modern_target_server.py")]


# ---------------------------------------------- page 2 is part of the audit ----


@pytest.fixture(scope="module")
def paginated_outcome():
    import asyncio

    return asyncio.run(run_conformance(PAGINATED))


def test_page2_tools_reach_conformance_and_pagination_passes(paginated_outcome):
    outcome = paginated_outcome
    assert [t["name"] for t in outcome.tools] == ["lookup", "evil_helper", "shell_helper"]
    by_id = {r.id: r for r in outcome.results}
    assert by_id["LIST-01"].status == PASS
    assert "2 page(s)" in by_id["LIST-01"].evidence
    # the TOOL-01 violation lives on page 2 — before v0.7 it was invisible
    assert by_id["TOOL-01"].status == FAIL
    assert "evil_helper" in by_id["TOOL-01"].evidence


def test_page2_security_violations_are_flagged(paginated_outcome):
    by_id = {r.id: r for r in run_security(paginated_outcome.tools)}
    assert by_id["SEC-01"].status == FAIL, "page-2 prompt injection must be seen"
    assert "evil_helper" in by_id["SEC-01"].evidence
    # the injection surface is nested one object deep — needs the schema walker
    assert by_id["SEC-04"].status == WARN
    assert "shell_helper.config.command" in by_id["SEC-04"].evidence
    assert by_id["SEC-06"].status == WARN
    assert "shell_helper(config.command)" in by_id["SEC-06"].evidence


def test_page2_resource_violation_and_prompt_pagination(paginated_outcome):
    by_id = {r.id: r for r in paginated_outcome.results}
    assert by_id["RES-02"].status == FAIL, "the nameless resource lives on page 2"
    assert by_id["RES-04"].status == PASS and "2 page(s)" in by_id["RES-04"].evidence
    # prompts finally have the pagination check LIST-01/RES-04 always had
    assert by_id["PROMPT-04"].status == PASS
    assert "2 page(s)" in by_id["PROMPT-04"].evidence


async def test_prompt_cursor_loop_fails_prompt04():
    outcome = await run_conformance(PAGINATED + ["--prompt-loop"])
    p04 = {r.id: r for r in outcome.results}["PROMPT-04"]
    assert p04.status == FAIL
    assert "repeats" in p04.evidence


async def test_broken_page2_fails_pagination_loudly():
    outcome = await run_conformance(PAGINATED + ["--break-tools-page2"])
    by_id = {r.id: r for r in outcome.results}
    assert by_id["LIST-01"].status == FAIL
    assert "page 2 failed" in by_id["LIST-01"].evidence


async def test_inspect_refuses_partial_contract():
    from mcpproof.contract import capture_manifest

    with pytest.raises(RuntimeError, match="partial contract"):
        await capture_manifest(PAGINATED + ["--break-tools-page2"])


async def test_inspect_captures_every_page_and_absent_surfaces():
    from mcpproof.contract import capture_manifest

    manifest = await capture_manifest(PAGINATED)
    assert [t["name"] for t in manifest["tools"]] == ["lookup", "evil_helper", "shell_helper"]
    assert manifest["unserved"] == []  # absent ≠ empty is now recorded
    assert manifest["manifest_version"] == 2


# ------------------------------------------------------- collector semantics ----


async def test_collector_detects_repeating_cursor_and_midwalk_failure():
    async def looping(cursor):
        return {"tools": [{"name": "x"}], "nextCursor": "same"}

    result = await collect_paginated(looping, "tools")
    assert not result.complete and "repeats" in result.error

    async def breaks_on_page2(cursor):
        if cursor is None:
            return {"tools": [{"name": "a"}], "nextCursor": "2"}
        return None

    result = await collect_paginated(breaks_on_page2, "tools")
    assert not result.complete and "page 2 failed" in result.error
    assert [t["name"] for t in result.items] == ["a"], "partial items kept for evidence only"

    async def unbounded(cursor):
        nxt = str(int(cursor or 0) + 1)
        return {"tools": [], "nextCursor": nxt}

    result = await collect_paginated(unbounded, "tools", max_pages=5)
    assert not result.complete and "more than 5 page(s)" in result.error


# --------------------------------------------------- fixture-set integrity ----


@pytest.fixture(scope="module")
def recorded_baseline(tmp_path_factory):
    import asyncio

    base = tmp_path_factory.mktemp("baseline")
    asyncio.run(record(REGRESSION_SERVER, base))
    return base


def _copy(baseline: Path, tmp_path: Path) -> Path:
    target = tmp_path / "fixtures"
    shutil.copytree(baseline, target)
    return target


def _gate(problems) -> bool:
    return summarize(problems)["gate_pass"]


def test_missing_fixture_fails_gate(recorded_baseline, tmp_path):
    fdir = _copy(recorded_baseline, tmp_path)
    manifest = json.loads((fdir / "_manifest.json").read_text())
    victim = manifest["fixtures"][1]
    (fdir / victim).unlink()
    paths, problems = verify_fixture_set(fdir)
    assert any(p.kind == "ERROR" and "missing on disk" in p.detail for p in problems)
    assert victim not in {p.name for p in paths}
    assert not _gate(problems)


def test_tampered_fixture_content_fails_gate_and_is_not_replayed(recorded_baseline, tmp_path):
    fdir = _copy(recorded_baseline, tmp_path)
    manifest = json.loads((fdir / "_manifest.json").read_text())
    victim = fdir / manifest["fixtures"][0]
    fixture = json.loads(victim.read_text())
    fixture["response"]["content"][0]["text"] = "silently rewritten baseline"
    victim.write_text(json.dumps(fixture), encoding="utf-8")
    paths, problems = verify_fixture_set(fdir)
    assert any("contract_sha256 mismatch" in p.detail for p in problems)
    assert victim.name not in {p.name for p in paths}, "a tampered baseline is not truth"
    assert not _gate(problems)


def test_tampered_manifest_fingerprint_fails_gate(recorded_baseline, tmp_path):
    fdir = _copy(recorded_baseline, tmp_path)
    mpath = fdir / "_manifest.json"
    manifest = json.loads(mpath.read_text())
    manifest["fixtures_sha256"] = "0" * 64
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    _, problems = verify_fixture_set(fdir)
    assert any("manifest was modified" in p.detail for p in problems)
    assert not _gate(problems)


def test_duplicate_manifest_entry_is_an_error(recorded_baseline, tmp_path):
    fdir = _copy(recorded_baseline, tmp_path)
    mpath = fdir / "_manifest.json"
    manifest = json.loads(mpath.read_text())
    manifest["fixtures"].append(manifest["fixtures"][0])
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    paths, problems = verify_fixture_set(fdir)
    assert any("more than once" in p.detail for p in problems)
    assert len(paths) == len(set(p.name for p in paths)), "each fixture replays once"
    assert not _gate(problems)


def test_stale_extra_fixture_is_flagged_and_not_replayed(recorded_baseline, tmp_path):
    fdir = _copy(recorded_baseline, tmp_path)
    stale = {"tool": "echo", "args": {"text": "stale"},
             "response": {"is_error": False, "content": []}}
    (fdir / "zzz_stale.json").write_text(json.dumps(stale), encoding="utf-8")
    paths, problems = verify_fixture_set(fdir)
    assert any("not in the manifest" in p.detail for p in problems)
    assert "zzz_stale.json" not in {p.name for p in paths}, (
        "an unlisted fixture must not run inside the recorded call order"
    )
    assert not _gate(problems)


async def test_missing_manifest_fails_gate_but_still_replays(recorded_baseline, tmp_path):
    fdir = _copy(recorded_baseline, tmp_path)
    (fdir / "_manifest.json").unlink()
    results = await replay(REGRESSION_SERVER, fdir)
    summary = summarize(results)
    assert summary["error"] == 1 and not summary["gate_pass"]
    assert summary["ok"] == 3, "best-effort replay still shows what drifted"


def test_intact_baseline_verifies_clean(recorded_baseline):
    paths, problems = verify_fixture_set(recorded_baseline)
    assert problems == []
    assert len(paths) == 3


async def test_same_tool_same_args_twice_records_two_ordered_fixtures(tmp_path):
    paths = await record(REGRESSION_SERVER, tmp_path,
                         calls=[("echo", {"text": "hi"}), ("echo", {"text": "hi"})])
    assert len(paths) == 2 and paths[0].name != paths[1].name
    manifest = json.loads((tmp_path / "_manifest.json").read_text())
    assert manifest["fixtures"] == [p.name for p in paths]
    results = await replay(REGRESSION_SERVER, tmp_path)
    assert summarize(results)["ok"] == 2


async def test_aggregate_fingerprint_is_order_sensitive(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    calls = [("echo", {"text": "hi"}), ("price", {"item": "x"})]
    await record(REGRESSION_SERVER, a, calls=calls)
    await record(REGRESSION_SERVER, b, calls=list(reversed(calls)))
    ma = json.loads((a / "_manifest.json").read_text())
    mb = json.loads((b / "_manifest.json").read_text())
    assert ma["fixtures_sha256"] != mb["fixtures_sha256"], (
        "save→get and get→save are different contracts"
    )


# ------------------------------------------------- drift classification v4 ----


def _resp(parts, structured=None):
    return {"is_error": False, "content": parts, "structured": structured}


def test_image_payload_change_is_value_drift():
    old = _resp([{"type": "image", "mimeType": "image/png",
                  "data": {"sha256": "a" * 64, "bytes": 10}}])
    new = _resp([{"type": "image", "mimeType": "image/png",
                  "data": {"sha256": "b" * 64, "bytes": 12}}])
    verdict = _classify("f.json", "shot", old, new, version=4)
    assert verdict.kind == "VALUE"
    assert "data changed" in verdict.detail


def test_v3_fixture_with_bare_nontext_part_stays_compatible():
    # v≤3 recorded only {"type": ...}; comparing fields it never stored would
    # invent drift, so only shared fields are compared for old fixtures
    old = _resp([{"type": "image"}])
    new = _resp([{"type": "image", "mimeType": "image/png",
                  "data": {"sha256": "b" * 64, "bytes": 12}}])
    assert _classify("f.json", "shot", old, new, version=3).kind == "OK"


def test_structured_string_flip_fails_gate():
    old = _resp([{"type": "text", "text": "done"}], structured={"status": "approved"})
    new = _resp([{"type": "text", "text": "done"}], structured={"status": "denied"})
    verdict = _classify("f.json", "review", old, new, version=4)
    assert verdict.kind == "VALUE"
    assert not summarize([verdict])["gate_pass"]


def test_json_text_value_change_is_value_not_cosmetic():
    old = _resp([{"type": "text", "text": json.dumps({"role": "admin"})}])
    new = _resp([{"type": "text", "text": json.dumps({"role": "guest"})}])
    verdict = _classify("f.json", "whoami", old, new, version=4)
    assert verdict.kind == "VALUE"
    assert "role" in verdict.detail

    old = _resp([{"type": "text", "text": json.dumps(["a", "b"])}])
    new = _resp([{"type": "text", "text": json.dumps(["a"])}])
    verdict = _classify("f.json", "tags", old, new, version=4)
    assert verdict.kind == "VALUE"
    assert "length" in verdict.detail


def test_huge_integer_drift_is_not_folded_by_float():
    # 9007199254740993 == 9007199254740992 under float; Decimal must not fold
    assert _value_drift("id 9007199254740993", "id 9007199254740992") is not None


# ------------------------------------------------- synthesis is fail-closed ----

_IMPOSSIBLE_PATTERN = {
    "type": "object",
    "properties": {"code": {"type": "string", "pattern": r"^ZZZ\d{9}$"}},
    "required": ["code"],
}


def test_synthesize_valid_args_reports_pattern_miss():
    args, reason = synthesize_valid_args(_IMPOSSIBLE_PATTERN)
    assert args is None
    assert "do not satisfy the schema" in reason


def test_negative_variants_require_a_valid_baseline():
    # the sampler cannot satisfy this pattern, so no baseline is provably
    # valid — and without one, "exactly one field mutated" proves nothing
    assert negative_variants(_IMPOSSIBLE_PATTERN, limit=3) == []


def test_iter_properties_walks_refs_allof_nesting_and_items():
    schema = {
        "type": "object",
        "properties": {
            "config": {"$ref": "#/$defs/cfg"},
            "entries": {"type": "array", "items": {
                "type": "object", "properties": {"url": {"type": "string"}},
            }},
        },
        "$defs": {
            "cfg": {
                "allOf": [
                    {"type": "object",
                     "properties": {"shell": {
                         "type": "object",
                         "properties": {"command": {"type": "string"}},
                     }}},
                ],
            },
        },
    }
    paths = {path for path, _ in iter_properties(schema)}
    assert "config.shell.command" in paths
    assert "entries[].url" in paths


# ------------------------------------------------ TOOL-06/08 split, TOOL-08 ----


async def test_tool06_static_and_tool08_dynamic_verdicts_are_separate():
    outcome = await run_conformance(MODERN)
    by_id = {r.id: r for r in outcome.results}
    assert by_id["TOOL-06"].status == PASS
    assert "compile" in by_id["TOOL-06"].evidence
    assert by_id["TOOL-08"].status == PASS
    assert "validates" in by_id["TOOL-08"].evidence


async def test_tool08_skips_as_unobserved_when_nothing_safe_to_call(paginated_outcome):
    by_id = {r.id: r for r in paginated_outcome.results}
    # no tool on this server declares an outputSchema → both halves SKIP
    assert by_id["TOOL-06"].status == SKIP
    assert by_id["TOOL-08"].status == SKIP


# -------------------------------------------------- contract strip by location ----


def test_strip_preserves_user_schema_fields_named_like_wire_fields():
    from mcpproof.contract import _strip_item, diff_manifests

    tool = {
        "name": "pager",
        "_meta": {"volatile": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "nextCursor": {"type": "string"},
                "ttlMs": {"type": "integer", "maximum": 100},
            },
            "required": ["nextCursor"],
        },
    }
    stripped = _strip_item(tool)
    assert "_meta" not in stripped
    assert set(stripped["inputSchema"]["properties"]) == {"nextCursor", "ttlMs"}, (
        "a user's schema property named like a wire field is contract, not noise"
    )

    # and a change inside such a property must be diffable, not invisible
    base = {"capabilities": {}, "tools": [stripped], "resources": [], "prompts": []}
    import copy

    cur = copy.deepcopy(base)
    cur["tools"][0]["inputSchema"]["properties"]["ttlMs"]["maximum"] = 50
    changes = diff_manifests(base, cur)
    assert any(c["level"] == "BREAKING" and "ttlMs" in c["ref"] for c in changes)


def test_behavior_hash_is_stable_across_environment_noise():
    from mcpproof.checks.base import CheckResult
    from mcpproof.report.model import build_model

    def model(evidence, server_cmd):
        return build_model(
            server_name="x", server_cmd=server_cmd, negotiated_protocol="2025-11-25",
            conformance=[CheckResult("LIFE-01", "t", "MUST", "PASS", evidence)],
            security=[], regression=None,
        )

    a = model("ok (stderr tail: pid 4242)", ["/usr/bin/python3", "s.py"])
    b = model("ok (stderr tail: pid 9999)", ["/opt/other/python3.12", "s.py"])
    assert a["behavior_sha256"] == b["behavior_sha256"], (
        "identical verdicts must fingerprint identically across machines"
    )
    assert a["run_hash"] != b["run_hash"], "the audit-run hash still records its inputs"


def test_manifest_hash_recomputation_matches_recorded(recorded_baseline):
    manifest = json.loads((recorded_baseline / "_manifest.json").read_text())
    hashes = []
    for name in manifest["fixtures"]:
        fixture = json.loads((recorded_baseline / name).read_text())
        hashes.append(obj_hash(
            {"tool": fixture["tool"], "args": fixture["args"], "response": fixture["response"]}
        ))
    assert manifest["fixtures_sha256"] == obj_hash(hashes)
