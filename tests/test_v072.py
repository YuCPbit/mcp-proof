"""v0.7.2 truthfulness patch: what the fingerprints cover is what a reader reads.

Pinned properties:
- the schema-v3 run fingerprint covers the WHOLE document — verdict banner,
  audit status, summary counters, MSSS table, next steps — so editing any
  derived field breaks `verify`, not just editing a check row;
- stored schema-v2 reports still verify under their frozen original recipe,
  with an explicit coverage note, and flipping the version field defeats
  itself because it just selects a recipe that disagrees with the stored hash;
- the fixture integrity gate cannot be disarmed by deleting a fixture's own
  contract_sha256 (the downgrade bypass this release exists to close), and
  pre-hash legacy sets fail closed unless --allow-legacy-fixtures opts in;
- every command answers failure the same way: exit 2 and one stable line,
  never a traceback (MCP_PROOF_DEBUG=1 brings it back), and never exit 1 for
  anything that is not target behaviour.
"""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from _paths import ROOT, venv_python

from mcpproof.regression import record

PYTHON = venv_python()
HERE = Path(__file__).resolve().parent
MODERN = [PYTHON, str(HERE / "modern_target_server.py")]
REGRESSION_SERVER = [PYTHON, str(HERE / "regression_target_server.py")]


def run_cli(*argv: str, timeout: int = 120,
            env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        [PYTHON, "-m", "mcpproof.cli", *argv],
        cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env,
    )


@pytest.fixture(scope="module")
def recorded_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("run072")
    proc = run_cli(
        "run", *MODERN, "--fixtures", str(tmp / "fx"), "--record-if-missing",
        "--out", str(tmp / "r.html"), "--json", str(tmp / "r.json"),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return tmp


def _model(recorded_run) -> dict:
    return json.loads((recorded_run / "r.json").read_text(encoding="utf-8"))


def _write(tmp_path: Path, model: dict) -> Path:
    out = tmp_path / "tampered.json"
    out.write_text(json.dumps(model), encoding="utf-8")
    return out


# ------------------------------------------- verify covers derived fields ----


@pytest.mark.parametrize("path,value", [
    (("verdict", "ship_ready"), False),
    (("verdict", "blockers"), ["fabricated blocker"]),
    (("audit", "status"), "inconclusive"),
    (("audit", "error"), "fabricated auditor error"),
    (("conformance", "must_ok"), 99),
    (("conformance", "must_total"), 99),
    (("security", "fails"), 7),
    (("msss",), {"headline": "FABRICATED MSSS HEADLINE"}),
    (("next_steps",), [{"p": "KEEP", "text": "fabricated next step"}]),
    (("server", "name"), "renamed-after-the-audit"),
])
def test_verify_catches_every_derived_field_edit(recorded_run, tmp_path, path, value):
    model = _model(recorded_run)
    node = model
    for key in path[:-1]:
        node = node[key]
    assert node[path[-1]] != value, "tamper value must differ from the real report"
    node[path[-1]] = value
    proc = run_cli("verify", str(_write(tmp_path, model)))
    assert proc.returncode == 1, proc.stdout
    assert "MISMATCH" in proc.stdout


def test_derived_edit_breaks_run_hash_but_not_behaviour(recorded_run, tmp_path):
    """The behaviour fingerprint deliberately covers only what the server did;
    the document fingerprint is the one that pins what the report SAYS."""
    model = _model(recorded_run)
    model["verdict"] = {"ship_ready": False, "blockers": ["fabricated"]}
    proc = run_cli("verify", str(_write(tmp_path, model)))
    assert proc.returncode == 1
    lines = proc.stdout.splitlines()
    behaviour = next(line for line in lines if line.startswith("behaviour fingerprint"))
    run_line = next(line for line in lines if line.startswith("audit-run fingerprint"))
    assert "verified" in behaviour and "MISMATCH" not in behaviour
    assert "MISMATCH" in run_line


# --------------------------------------------------- schema-version rules ----


def test_verify_still_accepts_schema_v2_reports(recorded_run, tmp_path):
    """Reports written by mcp-proof ≤ 0.7.1 verify under their frozen recipe,
    and the reduced coverage is stated instead of implied away."""
    from mcpproof.provenance import obj_hash
    from mcpproof.report.model import _behavior_hash_input, _run_hash_input

    model = _model(recorded_run)
    model["report_schema_version"] = 2
    server = model["server"]
    conf = model["conformance"]["checks"]
    sec = model["security"]["checks"]
    reg = model.get("regression")
    model["behavior_sha256"] = obj_hash(
        _behavior_hash_input(server["revision"], server["era"], conf, sec, reg))
    model["run_hash"] = obj_hash(_run_hash_input(
        model["tool"]["version"], server["cmd"], server["revision"], server["era"],
        conf, sec, reg))
    proc = run_cli("verify", str(_write(tmp_path, model)))
    assert proc.returncode == 0, proc.stdout
    assert "schema v2" in proc.stdout, "reduced coverage must be stated"


def test_flipping_the_schema_version_defeats_itself(recorded_run, tmp_path):
    model = _model(recorded_run)
    model["report_schema_version"] = 2  # claim the weaker recipe on a v3 report
    proc = run_cli("verify", str(_write(tmp_path, model)))
    assert proc.returncode == 1
    assert "MISMATCH" in proc.stdout


def test_verify_refuses_reports_from_a_newer_schema(recorded_run, tmp_path):
    model = _model(recorded_run)
    model["report_schema_version"] = 99
    proc = run_cli("verify", str(_write(tmp_path, model)))
    assert proc.returncode == 2, "unknown semantics is inconclusive, not a verdict"
    assert "newer" in proc.stdout


# ------------------------------------- fixture-integrity downgrade attack ----


@pytest.fixture(scope="module")
def recorded_baseline(tmp_path_factory):
    base = tmp_path_factory.mktemp("baseline072")
    asyncio.run(record(REGRESSION_SERVER, base))
    return base


def test_stripping_contract_hash_is_itself_an_integrity_error(recorded_baseline, tmp_path):
    """Deleting a fixture's contract_sha256 must not disarm the very check
    that would have caught the edit (this was a live bypass in 0.7.0/0.7.1)."""
    from mcpproof.regression.replayer import verify_fixture_set

    fdir = tmp_path / "fixtures"
    shutil.copytree(recorded_baseline, fdir)
    manifest = json.loads((fdir / "_manifest.json").read_text(encoding="utf-8"))
    victim = fdir / manifest["fixtures"][0]
    fixture = json.loads(victim.read_text(encoding="utf-8"))
    fixture["response"]["content"][0]["text"] = "ATTACKER-REWRITTEN BASELINE"
    del fixture["contract_sha256"]
    victim.write_text(json.dumps(fixture), encoding="utf-8")

    paths, problems = verify_fixture_set(fdir)
    assert any("integrity-stripped" in p.detail for p in problems), problems
    assert victim.name not in {p.name for p in paths}, (
        "an unverifiable fixture inside a hashed set must not replay as truth"
    )


def test_replay_tampered_baseline_exits_2_with_integrity_detail(recorded_baseline, tmp_path):
    """End to end: a failed integrity gate is 'audit did not complete' (2),
    never drift evidence against the target (1)."""
    fdir = tmp_path / "fixtures"
    shutil.copytree(recorded_baseline, fdir)
    manifest = json.loads((fdir / "_manifest.json").read_text(encoding="utf-8"))
    victim = fdir / manifest["fixtures"][0]
    fixture = json.loads(victim.read_text(encoding="utf-8"))
    fixture["response"]["content"][0]["text"] = "silently rewritten baseline"
    victim.write_text(json.dumps(fixture), encoding="utf-8")

    proc = run_cli("replay", *REGRESSION_SERVER, "--fixtures", str(fdir))
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "contract_sha256 mismatch" in proc.stdout
    assert "Traceback" not in proc.stdout + proc.stderr


# ------------------------------------------------ exit taxonomy, CLI-wide ----


def test_replay_missing_baseline_is_exit_2_not_target_failure(tmp_path):
    """`run` already said 2 for a missing baseline; `replay` used to say 1
    for the same fact. One fact, one exit code."""
    proc = run_cli("replay", *REGRESSION_SERVER, "--fixtures", str(tmp_path / "nope"))
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "did not complete" in proc.stdout
    assert "Traceback" not in proc.stdout + proc.stderr


@pytest.mark.parametrize("argv", [
    ("record", "./nonexistent-server-xyz", "--fixtures", "{tmp}/fx"),
    ("inspect", "./nonexistent-server-xyz", "--out", "{tmp}/contract.json"),
])
def test_dead_command_is_one_stable_line_and_exit_2(tmp_path, argv):
    argv = [a.format(tmp=tmp_path) for a in argv]
    proc = run_cli(*argv)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "did not complete" in proc.stdout
    assert "Traceback" not in proc.stdout + proc.stderr


def test_debug_env_brings_the_traceback_back(tmp_path):
    proc = run_cli("record", "./nonexistent-server-xyz", "--fixtures", str(tmp_path / "fx"),
                   env_extra={"MCP_PROOF_DEBUG": "1"})
    assert proc.returncode != 2
    assert "Traceback" in proc.stderr


# ----------------------------------------------------------- determinism ----


def test_document_hash_excludes_observation_and_stays_deterministic():
    from mcpproof.checks.base import CheckResult
    from mcpproof.report.model import build_model, recompute_hashes

    kw = dict(server_name="x", server_cmd=["x"], negotiated_protocol="2025-11-25",
              conformance=[CheckResult("LIFE-01", "t", "MUST", "PASS", "ok")],
              security=[], regression=None)
    a, b = build_model(**kw), build_model(**kw)
    assert a["run_hash"] == b["run_hash"]
    a["observation"]["generated_at"] = "1999-01-01 00:00 UTC"
    behavior, run = recompute_hashes(a)
    assert (behavior, run) == (a["behavior_sha256"], a["run_hash"]), (
        "observation is context, never fingerprinted"
    )
