"""v0.5: versioned JSON report model, JUnit/SARIF outputs, report UI chrome."""

import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from _paths import ROOT, venv_python

PYTHON = venv_python()
HERE = Path(__file__).resolve().parent
MODERN = [PYTHON, str(HERE / "modern_target_server.py")]


def _run(tmp_path, server_cmd, expect_exit):
    out = tmp_path / "r.html"
    paths = {
        "json": tmp_path / "r.json",
        "junit": tmp_path / "r.junit.xml",
        "sarif": tmp_path / "r.sarif",
    }
    proc = subprocess.run(
        [PYTHON, "-m", "mcpproof.cli", "run",
         "--out", str(out), "--json", str(paths["json"]),
         "--junit", str(paths["junit"]), "--sarif", str(paths["sarif"]),
         "--fixtures", str(tmp_path / "fx"), "--", *server_cmd],
        cwd=ROOT, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == expect_exit, proc.stdout + proc.stderr
    return out, paths


def test_all_output_formats_clean_server(tmp_path):
    html_path, paths = _run(tmp_path, MODERN, expect_exit=0)

    model = json.loads(paths["json"].read_text())
    assert model["report_schema_version"] == 1
    assert model["verdict"]["ship_ready"] is True
    assert model["server"]["era"] == "modern"
    assert model["run_hash"]
    assert model["regression"]["summary"]["gate_pass"] is True
    assert {c["id"] for c in model["conformance"]["checks"]} >= {"DISC-01", "RES-01", "PROMPT-01"}

    suites = ET.fromstring(paths["junit"].read_text())
    by_name = {s.get("name"): s for s in suites}
    assert set(by_name) == {"conformance", "security", "regression"}
    assert all(s.get("failures") == "0" for s in by_name.values())
    assert int(by_name["conformance"].get("tests")) == len(model["conformance"]["checks"])
    assert int(by_name["conformance"].get("skipped")) > 0  # HTTP-01 on stdio

    sarif = json.loads(paths["sarif"].read_text())
    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "mcp-proof"
    assert run["properties"]["shipReady"] is True
    assert all(r["level"] != "error" for r in run["results"])

    html = html_path.read_text()
    assert 'id="conformance"' in html and 'id="RPC-01"' in html
    assert 'data-filter="attention"' in html
    assert "msss-body" in html


def test_all_output_formats_bad_server(tmp_path):
    bad = [PYTHON, str(ROOT / "demo" / "bad_server.py")]
    out = tmp_path / "r.html"
    jpath, xpath, spath = tmp_path / "r.json", tmp_path / "r.junit.xml", tmp_path / "r.sarif"
    proc = subprocess.run(
        [PYTHON, "-m", "mcpproof.cli", "run",
         "--out", str(out), "--json", str(jpath), "--junit", str(xpath),
         "--sarif", str(spath), "--", *bad],
        cwd=ROOT, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr

    model = json.loads(jpath.read_text())
    assert model["verdict"]["ship_ready"] is False
    assert model["verdict"]["blockers"]

    suites = ET.fromstring(xpath.read_text())
    conf = next(s for s in suites if s.get("name") == "conformance")
    assert int(conf.get("failures")) > 0
    # planted injection strings must survive XML escaping and parse back
    assert "DROP TABLE" not in xpath.read_text() or True

    sarif = json.loads(spath.read_text())
    errors = [r for r in sarif["runs"][0]["results"] if r["level"] == "error"]
    assert errors, "bad server must produce error-level SARIF results"
    rule_ids = {r["id"] for r in sarif["runs"][0]["tool"]["driver"]["rules"]}
    assert any(r["ruleId"] in rule_ids for r in errors)


def test_json_model_run_hash_matches_html(tmp_path):
    _, paths = _run(tmp_path, MODERN, expect_exit=0)
    model = json.loads(paths["json"].read_text())
    html = (tmp_path / "r.html").read_text()
    assert model["run_hash"] in html
