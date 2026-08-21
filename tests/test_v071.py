"""v0.7.1 release hardening: the auditor knows when it cannot conclude.

Three trust-model properties, pinned:
- an exception in mcp-proof's own check logic is INCONCLUSIVE (exit 2),
  never a verdict against the target;
- `run --fixtures` never invents the baseline it then verifies — missing
  baselines fail closed unless --record-if-missing opts in, and a baseline
  recorded in the same run presents itself as exactly that;
- a written JSON report can be re-proven offline: `verify` recomputes both
  fingerprints from the report's own fields and fails on any edit.
"""

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

import pytest
from _paths import ROOT, venv_python

import mcpproof.checks.conformance as conformance_mod
from mcpproof.checks.conformance import _safe, run_conformance

PYTHON = venv_python()
HERE = Path(__file__).resolve().parent
MODERN = [PYTHON, str(HERE / "modern_target_server.py")]


def run_cli(*argv: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "mcpproof.cli", *argv],
        cwd=ROOT, capture_output=True, text=True, timeout=timeout,
    )


# ------------------------------------------------------ failure taxonomy ----


async def test_safe_swallows_transport_but_propagates_auditor_bugs():
    async def transport_dies():
        raise ValueError("I/O operation on closed pipe")

    assert await _safe(transport_dies()) is None

    async def auditor_bug():
        raise TypeError("'NoneType' object is not subscriptable")

    with pytest.raises(TypeError):
        await _safe(auditor_bug())


async def test_auditor_bug_is_inconclusive_not_target_failure(monkeypatch):
    async def broken_check(*args, **kwargs):
        raise TypeError("planted auditor bug")

    monkeypatch.setattr(conformance_mod, "_rpc_checks", broken_check)
    outcome = await run_conformance(MODERN)
    assert outcome.audit_error and "TypeError" in outcome.audit_error
    assert "planted auditor bug" in outcome.audit_error
    # the one verdict this must never produce: evidence against the target
    assert outcome.results == []
    assert outcome.era == "modern"


async def test_dead_server_is_still_target_evidence_not_inconclusive():
    # taxonomy sanity from the other side: a command that cannot start is
    # target-side evidence and keeps its LIFE-01/handshake failure verdict
    outcome = await run_conformance([PYTHON, str(HERE / "crashing_server.py")])
    assert outcome.audit_error is None
    by_id = {r.id: r for r in outcome.results}
    assert by_id["LIFE-01"].status == "FAIL"


def _run_args(tmp_path, **overrides) -> argparse.Namespace:
    base = dict(
        server_cmd=MODERN, url=None, era="auto", server_name=None,
        fixtures=None, out=str(tmp_path / "r.html"), json=str(tmp_path / "r.json"),
        junit=None, sarif=None, pdf=False, semantic=False,
        include_destructive=False, edge_cases=False, record_if_missing=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_inconclusive_run_exits_2_and_report_blames_nobody(tmp_path, monkeypatch):
    from mcpproof.checks.conformance import ConformanceOutcome
    from mcpproof.runner import _cmd_run

    async def fake_conformance(cmd, url=None, era="auto"):
        return ConformanceOutcome([], "modern", audit_error="TypeError: planted")

    monkeypatch.setattr("mcpproof.checks.conformance.run_conformance", fake_conformance)
    code = asyncio.run(_cmd_run(_run_args(tmp_path, fixtures=str(tmp_path / "fx"))))
    assert code == 2
    html = (tmp_path / "r.html").read_text(encoding="utf-8")
    assert "AUDIT INCONCLUSIVE" in html
    assert "NOT SHIP-READY" not in html, "an auditor bug must not read as a target failure"
    model = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert model["audit"] == {"status": "inconclusive", "error": "TypeError: planted"}
    assert not (tmp_path / "fx").exists(), "a broken audit must not touch fixtures"


# --------------------------------------------------- baselines fail closed ----


def test_missing_baseline_fails_closed_with_exit_2(tmp_path):
    proc = run_cli(
        "run", *MODERN, "--fixtures", str(tmp_path / "fx"), "--out", str(tmp_path / "r.html"),
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "no baseline" in proc.stdout
    assert "--record-if-missing" in proc.stdout
    assert not (tmp_path / "fx").exists(), "fail closed means nothing was recorded"


@pytest.fixture(scope="module")
def recorded_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("run071")
    proc = run_cli(
        "run", *MODERN, "--fixtures", str(tmp / "fx"), "--record-if-missing",
        "--out", str(tmp / "r.html"), "--json", str(tmp / "r.json"),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return tmp, proc


def test_record_if_missing_labels_the_fresh_baseline(recorded_run):
    tmp, proc = recorded_run
    assert "baseline recorded this run — no historical comparison" in proc.stdout
    html = (tmp / "r.html").read_text(encoding="utf-8")
    assert "self-replay PASS — no historical comparison" in html
    model = json.loads((tmp / "r.json").read_text(encoding="utf-8"))
    assert model["regression"]["baseline_created"] is True
    assert model["audit"]["status"] == "complete"


def test_existing_baseline_replays_without_flag_and_without_label(recorded_run, tmp_path):
    tmp, _ = recorded_run
    proc = run_cli(
        "run", *MODERN, "--fixtures", str(tmp / "fx"), "--out", str(tmp_path / "r2.html"),
        "--json", str(tmp_path / "r2.json"),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    model = json.loads((tmp_path / "r2.json").read_text(encoding="utf-8"))
    assert model["regression"]["baseline_created"] is False
    assert "no historical comparison" not in (tmp_path / "r2.html").read_text(encoding="utf-8")


# ------------------------------------------------------------ verify command ----


def test_verify_confirms_an_intact_report(recorded_run):
    tmp, _ = recorded_run
    proc = run_cli("verify", str(tmp / "r.json"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "report intact" in proc.stdout


def test_verify_catches_a_flipped_verdict(recorded_run, tmp_path):
    tmp, _ = recorded_run
    model = json.loads((tmp / "r.json").read_text(encoding="utf-8"))
    model["conformance"]["checks"][0]["status"] = "FAIL"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(model), encoding="utf-8")
    proc = run_cli("verify", str(tampered))
    assert proc.returncode == 1
    assert "MISMATCH" in proc.stdout


def test_verify_catches_edited_evidence_even_when_verdicts_stand(recorded_run, tmp_path):
    tmp, _ = recorded_run
    model = json.loads((tmp / "r.json").read_text(encoding="utf-8"))
    model["conformance"]["checks"][0]["evidence"] = "evidence rewritten after the audit"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(model), encoding="utf-8")
    proc = run_cli("verify", str(tampered))
    assert proc.returncode == 1
    # verdicts untouched → behaviour fingerprint still verifies; the audit-run
    # fingerprint covers the evidence text and catches the edit. Assert on the
    # words, not the ✓/✗ glyphs — Windows consoles replace them with '?'
    lines = proc.stdout.splitlines()
    behaviour_line = next(line for line in lines if line.startswith("behaviour fingerprint"))
    run_line = next(line for line in lines if line.startswith("audit-run fingerprint"))
    assert "verified" in behaviour_line and "MISMATCH" not in behaviour_line
    assert "MISMATCH" in run_line


def test_verify_rejects_non_reports(tmp_path):
    garbage = tmp_path / "not-a-report.json"
    garbage.write_text('{"hello": "world"}', encoding="utf-8")
    assert run_cli("verify", str(garbage)).returncode == 2
    assert run_cli("verify", str(tmp_path / "missing.json")).returncode == 2


# ------------------------------------------------------------------- misc ----


def test_version_flag():
    proc = run_cli("--version")
    assert proc.returncode == 0
    assert "mcp-proof 0.7" in proc.stdout
