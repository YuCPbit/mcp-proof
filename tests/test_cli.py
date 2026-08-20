"""End-to-end CLI tests: the full `mcp-proof run` pipeline against both demo
targets, plus the reproducibility promise the README makes."""

import re
import subprocess
from pathlib import Path

from _paths import ROOT, venv_python

PYTHON = venv_python()

FINGERPRINT_RE = re.compile(r"sha256:([0-9a-f]{64})")


def run_cli(*argv: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "mcpproof.cli", *argv],
        cwd=ROOT, capture_output=True, text=True, timeout=timeout,
    )


def test_run_good_server_ships_ready_and_exits_zero(tmp_path):
    out = tmp_path / "report.html"
    proc = run_cli(
        "run", PYTHON, str(ROOT / "demo" / "good_server.py"),
        "--fixtures", str(tmp_path / "fixtures"), "--out", str(out),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    html = out.read_text(encoding="utf-8")
    assert "SHIP-READY" in html and "NOT SHIP-READY" not in html
    assert "gate PASS" in html
    assert "Recommended next steps" in html and ">P1<" in html


def test_run_bad_server_fails_gate_and_exits_one(tmp_path):
    out = tmp_path / "report.html"
    proc = run_cli("run", PYTHON, str(ROOT / "demo" / "bad_server.py"), "--out", str(out))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    html = out.read_text(encoding="utf-8")
    assert "NOT SHIP-READY" in html
    assert "MUST conformance check(s) failing" in html
    assert "security finding(s)" in html
    assert "Recommended next steps" in html and ">P0<" in html


def test_run_fingerprint_is_reproducible_across_runs(tmp_path):
    """README promise: identical server behaviour -> identical report hash.
    Deterministic lanes only (no fixtures), two separate processes."""
    hashes = []
    for name in ("a.html", "b.html"):
        out = tmp_path / name
        proc = run_cli("run", PYTHON, str(ROOT / "demo" / "good_server.py"), "--out", str(out))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        found = FINGERPRINT_RE.findall(out.read_text(encoding="utf-8"))
        assert found, "no fingerprint in report"
        assert len(set(found)) == 1, "meta and footer fingerprints disagree"
        hashes.append(found[0])
    assert hashes[0] == hashes[1], f"non-reproducible: {hashes}"


def test_next_steps_maintenance_branch_on_perfect_results(tmp_path):
    from mcpproof.checks.base import CheckResult
    from mcpproof.report.builder import build_report

    conf = [CheckResult("LIFE-01", "t", "MUST", "PASS", "ok")]
    sec = [CheckResult("SEC-01", "t", "MUST", "PASS", "0 matches")]
    out = build_report(server_name="x", server_cmd=["x"], negotiated_protocol="2026-07-28",
                       conformance=conf, security=sec, regression=None,
                       out_path=tmp_path / "r.html")
    html = out.read_text(encoding="utf-8")
    assert "KEEP" in html and "Re-audit after the next MCP spec revision" in html
