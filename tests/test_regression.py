import json
from pathlib import Path

from mcpproof.provenance import obj_hash
from mcpproof.regression import (
    DriftResult,
    github_action_yaml,
    record,
    replay,
    sample_args,
    summarize,
)

from _paths import ROOT, venv_python

PYTHON = venv_python()
SERVER = str(Path(__file__).resolve().parent / "regression_target_server.py")


def server_cmd(drift: bool = False) -> list[str]:
    cmd = [PYTHON, SERVER]
    if drift:
        cmd.append("--drift")
    return cmd


async def test_record_writes_provenance_stamped_fixtures(tmp_path):
    paths = await record(server_cmd(), tmp_path)
    assert len(paths) == 3
    assert all(p.exists() and p.parent == tmp_path for p in paths)
    tools_seen = set()
    for p in paths:
        fixture = json.loads(p.read_text(encoding="utf-8"))
        tools_seen.add(fixture["tool"])
        assert fixture["schema_version"] == 2
        assert fixture["response_sha256"] == obj_hash(fixture["response"])
        assert fixture["server_cmd"] == server_cmd()
        assert isinstance(fixture["latency_ms"], int)
        assert fixture["response"]["is_error"] is False
        assert fixture["response"]["content"][0]["type"] == "text"
        assert p.name == f"{fixture['tool']}__{obj_hash(fixture['args'])[:8]}.json"
    assert tools_seen == {"echo", "price", "policy"}
    manifest = json.loads((tmp_path / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    # manifest preserves recording order so stateful sequences replay correctly
    assert manifest["fixtures"] == [p.name for p in paths]
    recomputed = obj_hash(
        sorted(obj_hash(json.loads(p.read_text(encoding="utf-8"))) for p in paths)
    )
    assert manifest["fixtures_sha256"] == recomputed


async def test_replay_same_server_is_all_ok_and_gate_passes(tmp_path):
    await record(server_cmd(), tmp_path)
    results = await replay(server_cmd(), tmp_path)
    assert all(isinstance(r, DriftResult) for r in results)
    content_results = [r for r in results if r.kind != "LATENCY"]
    assert len(content_results) == 3
    assert all(r.kind == "OK" for r in content_results)
    summary = summarize(results)
    assert summary["gate_pass"] is True
    assert summary["ok"] == 3
    assert summary["breaking"] == summary["value"] == summary["error"] == 0


async def test_replay_drifted_server_flags_value_drift_and_fails_gate(tmp_path):
    await record(server_cmd(), tmp_path)
    results = await replay(server_cmd(drift=True), tmp_path)
    by_tool = {r.tool: r for r in results if r.kind != "LATENCY"}
    assert by_tool["echo"].kind == "OK"
    assert by_tool["price"].kind == "VALUE"
    assert "42" in by_tool["price"].detail
    assert "45" in by_tool["price"].detail
    assert by_tool["policy"].kind == "VALUE"
    assert "negation" in by_tool["policy"].detail
    summary = summarize(results)
    assert summary["gate_pass"] is False
    assert summary["value"] == 2
    assert summary["ok"] == 1


def test_sample_args_type_driven_with_constraints():
    schema = {
        "type": "object",
        "required": ["name", "count", "ratio", "flag", "mode", "tags", "cfg", "bare_list"],
        "properties": {
            "name": {"type": "string", "minLength": 10},
            "count": {"type": "integer", "minimum": 5},
            "ratio": {"type": "number", "maximum": 1.0},
            "flag": {"type": "boolean"},
            "mode": {"type": "string", "enum": ["fast", "slow"]},
            "tags": {"type": "array", "items": {"type": "string"}},
            "cfg": {
                "type": "object",
                "required": ["depth"],
                "properties": {
                    "depth": {"type": "integer", "default": 7},
                    "optional_ignored": {"type": "string"},
                },
            },
            "bare_list": {"type": "array"},
        },
    }
    args = sample_args(schema)
    assert len(args["name"]) == 10
    assert args["count"] == 5
    assert args["ratio"] == 1.0
    assert args["flag"] is True
    assert args["mode"] == "fast"
    assert args["tags"] == ["example"]
    assert args["cfg"] == {"depth": 7}
    assert args["bare_list"] == []


def test_sample_args_prefers_examples_then_default_then_enum():
    schema = {
        "type": "object",
        "required": ["a", "b", "c"],
        "properties": {
            "a": {"type": "integer", "examples": [9], "default": 4},
            "b": {"type": "string", "default": "given", "enum": ["x", "y"]},
            "c": {"type": "string", "enum": ["only"]},
        },
    }
    assert sample_args(schema) == {"a": 9, "b": "given", "c": "only"}


def test_sample_args_never_raises_on_garbage():
    assert sample_args({}) == {}
    assert sample_args(None) == {}
    assert sample_args("not a schema") == {}
    assert sample_args({"type": 17, "properties": "lol", "required": {"x": 1}}) == {}
    assert sample_args({"type": "object", "required": ["x"], "properties": {"x": {"type": "quux"}}}) == {"x": {}}


def test_github_action_yaml_is_a_paste_ready_gate():
    yaml_text = github_action_yaml(["python", "-m", "my_server"], "fixtures/regression")
    assert "mcp-proof replay --fixtures fixtures/regression -- python -m my_server" in yaml_text
    assert "pip install mcp-proof" in yaml_text
    assert "setup-python" in yaml_text
    assert "contract" in yaml_text


def test_replay_order_follows_manifest_not_alphabet(tmp_path):
    from mcpproof.regression.replayer import _replay_order

    for name in ("a_get.json", "z_save.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    (tmp_path / "_manifest.json").write_text(
        json.dumps({"fixtures": ["z_save.json", "a_get.json"]}), encoding="utf-8"
    )
    assert [p.name for p in _replay_order(tmp_path)] == ["z_save.json", "a_get.json"]


def test_is_destructive_heuristic():
    from mcpproof.regression import is_destructive

    assert is_destructive("write_file")
    assert is_destructive("run_shell")
    assert is_destructive("set_config")
    assert is_destructive("harmless_name", "Deletes the entire database")
    assert not is_destructive("read_file")
    assert not is_destructive("get_note", "Fetch a note by title")
    assert not is_destructive("search_docs")


async def test_record_skips_destructive_by_default(tmp_path):
    skipped = []
    paths = await record(server_cmd(), tmp_path, skipped_out=skipped)
    assert {json.loads(p.read_text())["tool"] for p in paths} == {"echo", "price", "policy"}
    assert skipped == ["wipe_data"]
    manifest = json.loads((tmp_path / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["skipped_destructive"] == ["wipe_data"]


async def test_record_includes_destructive_on_request(tmp_path):
    paths = await record(server_cmd(), tmp_path, include_destructive=True)
    assert {json.loads(p.read_text())["tool"] for p in paths} == {"echo", "price", "policy", "wipe_data"}


async def test_record_edge_cases_baseline_boundary_inputs(tmp_path):
    paths = await record(server_cmd(), tmp_path, edge_cases=True)
    by_tool: dict[str, set] = {}
    for p in paths:
        f = json.loads(p.read_text(encoding="utf-8"))
        by_tool.setdefault(f["tool"], set()).add(f["case"])
    assert by_tool["echo"] == {"golden", "long-string", "injection-probe", "empty-string"}
    assert "wipe_data" not in by_tool
    results = await replay(server_cmd(), tmp_path)
    assert summarize(results)["gate_pass"] is True


def test_structured_drift_classification():
    from mcpproof.regression.replayer import _structured_drift

    old = {"structured": {"total": 42, "currency": "USD"}}
    assert _structured_drift(old, {"structured": {"total": 45, "currency": "USD"}})[0] == "VALUE"
    assert _structured_drift(old, {"structured": {"amount": 42}})[0] == "BREAKING"
    assert _structured_drift(old, {"structured": None})[0] == "BREAKING"
    assert _structured_drift(old, {"structured": {"total": 42, "currency": "USD"}}) is None
    assert _structured_drift({"is_error": False}, {"structured": {"x": 1}}) is None
