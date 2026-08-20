"""v0.4: capability-aware resources/prompts lanes, annotations-first call
plan, and the contract manifest engine (inspect / diff / breaking gate)."""

import json
import subprocess
from pathlib import Path

from _paths import ROOT, venv_python

from mcpproof.checks.base import FAIL, MUST, PASS, SKIP
from mcpproof.checks.conformance import run_conformance
from mcpproof.contract import (
    ADDITIVE,
    BREAKING,
    METADATA,
    capture_manifest,
    diff_manifests,
    has_breaking,
)
from mcpproof.regression.recorder import classify_tool

PYTHON = venv_python()
HERE = Path(__file__).resolve().parent
MODERN = [PYTHON, str(HERE / "modern_target_server.py")]
FULL_SURFACE = [PYTHON, str(HERE / "full_surface_server.py")]


# ------------------------------------------------ resources/prompts lanes ----


async def test_modern_server_surface_checks_pass():
    outcome = await run_conformance(MODERN)
    by_id = {r.id: r for r in outcome.results}
    for cid in ("RES-01", "RES-02", "RES-03", "RES-04",
                "PROMPT-01", "PROMPT-02", "PROMPT-03", "CAP-02", "CAP-03"):
        assert by_id[cid].status == PASS, (cid, by_id[cid].status, by_id[cid].evidence)
    # CACHE-01 must now cover every cacheable surface, not just tools/list
    assert "resources/read" in by_id["CACHE-01"].evidence
    assert "prompts/list" in by_id["CACHE-01"].evidence


async def test_legacy_full_surface_server_passes_surface_checks():
    outcome = await run_conformance(FULL_SURFACE)
    assert outcome.era == "legacy"
    by_id = {r.id: r for r in outcome.results}
    for cid in ("RES-01", "RES-02", "RES-03", "PROMPT-01", "PROMPT-02", "PROMPT-03"):
        assert by_id[cid].status == PASS, (cid, by_id[cid].status, by_id[cid].evidence)
    must_fails = {r.id for r in outcome.results if r.level == MUST and r.status == FAIL}
    assert not must_fails, must_fails


async def test_tools_only_server_skips_surface_checks(good_server_cmd):
    outcome = await run_conformance(good_server_cmd)
    by_id = {r.id: r for r in outcome.results}
    # fastmcp declares all capabilities, so lists are served (empty) — a
    # server that declares nothing must land on SKIP instead of FAIL
    assert by_id["RES-03"].status == SKIP
    assert by_id["PROMPT-03"].status == SKIP
    must_fails = {r.id for r in outcome.results if r.level == MUST and r.status == FAIL}
    assert not must_fails, must_fails


# --------------------------------------------------- annotations-first plan ----


def test_classify_tool_annotations_outrank_heuristic():
    # regex would block this read-only tool; the annotation rescues it
    assert classify_tool("run_query", "Runs a read-only query.",
                         {"readOnlyHint": True}) == ("auto", "annotation: readOnlyHint=true")
    # regex would miss this mutator; the annotation catches it
    assert classify_tool("charge_customer", "Charge a card.",
                         {"destructiveHint": True})[0] == "skip"
    # unannotated falls back to the heuristic, both ways
    assert classify_tool("charge_customer", "Charge a card.")[0] == "auto"  # known regex gap
    assert classify_tool("delete_file", "Delete a file.")[0] == "skip"
    assert classify_tool("search_docs", "Search documentation.")[0] == "auto"


def test_cli_plan_shows_basis(tmp_path):
    proc = subprocess.run(
        [PYTHON, "-m", "mcpproof.cli", "plan", *MODERN],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "AUTO-CALL (2)" in proc.stdout
    assert "annotation: readOnlyHint=true" in proc.stdout  # price
    assert "heuristic: no mutation signal" in proc.stdout  # echo
    assert "SKIPPED (0)" in proc.stdout


# ------------------------------------------------------- contract engine ----


async def test_manifest_capture_and_hash_stability(tmp_path):
    m1 = await capture_manifest(MODERN)
    m2 = await capture_manifest(MODERN)
    assert m1["server"]["era"] == "modern"
    assert [t["name"] for t in m1["tools"]] == ["echo", "price"]
    assert [r["uri"] for r in m1["resources"]] == ["demo://readme"]
    assert [p["name"] for p in m1["prompts"]] == ["summarize"]
    # volatile fields stay out of both the manifest surface and the hash
    assert "ttlMs" not in json.dumps(m1["tools"]) and "_meta" not in json.dumps(m1["tools"])
    assert m1["contract_sha256"] == m2["contract_sha256"]
    assert m1["observation"]["captured_at"] != ""


async def test_manifest_capture_legacy_era():
    m = await capture_manifest(FULL_SURFACE)
    assert m["server"]["era"] == "legacy"
    assert [t["name"] for t in m["tools"]] == ["lookup"]
    assert [p["name"] for p in m["prompts"]] == ["summarize"]


async def test_diff_detects_removed_tool_end_to_end():
    base = await capture_manifest(MODERN)
    cur = await capture_manifest(MODERN + ["--drop-tool", "price"])
    changes = diff_manifests(base, cur)
    assert has_breaking(changes)
    assert any(c["level"] == BREAKING and c["ref"] == "tool price" for c in changes)


def test_diff_classification_rules():
    tool = {
        "name": "search",
        "description": "Search things.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": 100},
                "limit": {"type": "integer"},
                "lang": {"type": "string", "enum": ["en", "zh"]},
            },
            "required": ["query"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {"results": {"type": "array", "items": {"type": "object",
                           "properties": {"url": {"type": "string"}}}}},
        },
        "annotations": {"readOnlyHint": True},
    }
    base = {"capabilities": {"tools": {}}, "tools": [tool], "resources": [], "prompts": []}

    import copy

    cur = copy.deepcopy(base)
    t = cur["tools"][0]
    t["inputSchema"]["required"].append("limit")           # optional → required: BREAKING
    t["inputSchema"]["properties"]["lang"]["enum"] = ["en"]  # enum narrowed: BREAKING
    t["inputSchema"]["properties"]["query"]["maxLength"] = 50  # tightened: BREAKING
    t["inputSchema"]["properties"]["verbose"] = {"type": "boolean"}  # optional add: ADDITIVE
    del t["outputSchema"]["properties"]["results"]["items"]["properties"]["url"]  # BREAKING
    t["description"] = "Search things, faster."            # METADATA
    t["annotations"] = {"readOnlyHint": False}             # safety weakened: BREAKING

    changes = diff_manifests(base, cur)
    by = {(c["level"], c["ref"]): c["detail"] for c in changes}
    assert ("BREAKING", "tool search.inputSchema.limit") in by
    assert any(k[0] == "BREAKING" and "lang" in k[1] for k in by)
    assert any(k[0] == "BREAKING" and "query" in k[1] and "maxLength" in by[k] for k in by)
    assert ("ADDITIVE", "tool search.inputSchema.verbose") in by
    assert any(k[0] == "BREAKING" and "outputSchema" in k[1] and "url" in k[1] for k in by)
    assert ("METADATA", "tool search") in by
    assert any(k[0] == "BREAKING" and "annotations" in k[1] for k in by)


def test_diff_capability_and_prompt_rules():
    base = {
        "capabilities": {"tools": {}, "resources": {}},
        "tools": [], "resources": [],
        "prompts": [{"name": "sum", "arguments": [{"name": "topic", "required": True}]}],
    }
    cur = {
        "capabilities": {"tools": {}, "prompts": {}},
        "tools": [], "resources": [],
        "prompts": [{"name": "sum", "arguments": [
            {"name": "topic", "required": True},
            {"name": "style", "required": True},
        ]}],
    }
    changes = diff_manifests(base, cur)
    levels = {(c["level"], c["ref"]) for c in changes}
    assert (BREAKING, "capabilities.resources") in levels
    assert (ADDITIVE, "capabilities.prompts") in levels
    assert (BREAKING, "prompt sum.style") in levels
    assert not any(level == METADATA for level, _ in levels)


def test_cli_inspect_and_diff_gate(tmp_path):
    base_path = tmp_path / "base.json"
    cur_path = tmp_path / "cur.json"
    for path, extra in ((base_path, []), (cur_path, ["--drop-tool", "price"])):
        # server flags go after the `--` separator, per the replay convention
        proc = subprocess.run(
            [PYTHON, "-m", "mcpproof.cli", "inspect", "--out", str(path),
             "--", *MODERN, *extra],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "contract manifest written" in proc.stdout

    same = subprocess.run(
        [PYTHON, "-m", "mcpproof.cli", "diff", str(base_path), str(base_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert same.returncode == 0 and "contract unchanged" in same.stdout

    gate = subprocess.run(
        [PYTHON, "-m", "mcpproof.cli", "diff", str(base_path), str(cur_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert gate.returncode == 1, gate.stdout
    assert "BREAKING" in gate.stdout and "tool price" in gate.stdout

    tolerant = subprocess.run(
        [PYTHON, "-m", "mcpproof.cli", "diff", str(base_path), str(cur_path),
         "--fail-on", "never"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert tolerant.returncode == 0
