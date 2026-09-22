"""End-to-end CLI tests: the full `mcp-proof run` pipeline against both demo
targets, plus the reproducibility promise the README makes."""

import re
import subprocess

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
        "--fixtures", str(tmp_path / "fixtures"), "--record-if-missing", "--out", str(out),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    html = out.read_text(encoding="utf-8")
    assert "SHIP-READY" in html and "NOT SHIP-READY" not in html
    # a baseline created in the same run must present itself as exactly that,
    # not as a historical regression verdict
    assert "self-replay PASS — no historical comparison" in html
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


# --------------------------------------------------- effects command (v0.8) ----


def test_effects_cli_sqlite_channel_catches_response_invisible_lie(tmp_path):
    """`mcp-proof effects --sqlite` end to end against the SaaS testbed with the
    phantom-write mutation: ping is readOnly-annotated, answers "ok", and
    writes a note — only the out-of-band channel can see it. Exit 1 + EFF-01."""
    db = str(tmp_path / "state.db")
    out = tmp_path / "effects.html"
    proc = run_cli(
        "effects", "--sqlite", db, "--out", str(out), "--",
        PYTHON, str(ROOT / "testbed" / "saas_server.py"),
        "--db", db, "--mutate", "phantom-write",
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "EFF-01" in proc.stdout
    html = out.read_text(encoding="utf-8")
    assert "ping" in html and "out-of-band" in html


def test_effects_cli_fs_root_channel(tmp_path):
    """The --fs-root observation channel end to end: honest file server passes;
    the --lie variant (readOnly read_file drops a shadow file) fails EFF-01."""
    root = tmp_path / "jail"
    out = tmp_path / "effects.html"
    server = str(ROOT / "tests" / "file_target_server.py")
    ok = run_cli(
        "effects", "--fs-root", str(root), "--include-destructive",
        "--out", str(out), "--json", str(tmp_path / "ok.json"), "--",
        PYTHON, server, "--root", str(root),
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    import json as _json

    records = _json.loads((tmp_path / "ok.json").read_text(encoding="utf-8"))["records"]
    save = next(r for r in records if r["tool"] == "save_file")
    assert save["effect_type"]["value"] == "create"          # observed, out-of-band
    assert save["targets"][0]["op"] == "create"

    root2 = tmp_path / "jail2"
    bad = run_cli(
        "effects", "--fs-root", str(root2), "--out", str(tmp_path / "bad.html"), "--",
        PYTHON, server, "--root", str(root2), "--lie",
    )
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert "EFF-01" in bad.stdout and "read_file" in bad.stdout


def test_effects_cli_requires_exactly_one_channel(tmp_path):
    neither = run_cli("effects", PYTHON, str(ROOT / "demo" / "good_server.py"))
    assert neither.returncode == 2
    assert "exactly one observation channel" in neither.stderr
    both = run_cli(
        "effects", "--sqlite", str(tmp_path / "x.db"), "--fs-root", str(tmp_path),
        PYTHON, str(ROOT / "demo" / "good_server.py"),
    )
    assert both.returncode == 2
    assert "exactly one observation channel" in both.stderr
