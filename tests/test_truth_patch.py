"""v0.2.1 truth patch: the README's load-bearing claims, pinned by tests.

- contract fingerprints depend on behaviour only (re-record → same hash)
- the report fingerprint ignores latency advisories
- v2-era fixtures still replay against current code
- capability honesty: a resources-only server is never failed for lacking tools
- a crashed server leaves its exit code and stderr in the evidence
"""

import json
import re
from pathlib import Path

from _paths import venv_python

from mcpproof.checks.base import FAIL, MUST, PASS, SKIP, CheckResult
from mcpproof.checks.conformance import run_conformance
from mcpproof.provenance import obj_hash
from mcpproof.regression import DriftResult, record, replay, summarize
from mcpproof.report.builder import build_report

PYTHON = venv_python()
HERE = Path(__file__).resolve().parent
REGRESSION_SERVER = [PYTHON, str(HERE / "regression_target_server.py")]

RUN_HASH_RE = re.compile(r"sha256:([0-9a-f]{64})")


async def test_contract_fingerprint_stable_across_recordings(tmp_path):
    """Same behaviour, same fingerprint — even though recorded_at differs."""
    a, b = tmp_path / "a", tmp_path / "b"
    await record(REGRESSION_SERVER, a)
    await record(REGRESSION_SERVER, b)
    ma = json.loads((a / "_manifest.json").read_text(encoding="utf-8"))
    mb = json.loads((b / "_manifest.json").read_text(encoding="utf-8"))
    assert ma["fixtures_sha256"] == mb["fixtures_sha256"]
    fa = json.loads((a / ma["fixtures"][0]).read_text(encoding="utf-8"))
    fb = json.loads((b / mb["fixtures"][0]).read_text(encoding="utf-8"))
    assert fa["observation"]["recorded_at"] != fb["observation"]["recorded_at"]
    assert fa["contract_sha256"] == fb["contract_sha256"]


def _reg(drifts: list[DriftResult]) -> dict:
    return {
        "summary": summarize(drifts),
        "drifts": drifts,
        "fixtures_sha256": "f" * 8,  # not 64-hex on purpose: keeps RUN_HASH_RE unambiguous
        "fixtures_dir": "fixtures",
        "action_yaml": "name: gate",
    }


def test_run_hash_ignores_latency_advisories(tmp_path):
    conf = [CheckResult("LIFE-01", "t", "MUST", "PASS", "ok")]
    quiet = [DriftResult("f1.json", "echo", "OK", "")]
    noisy = quiet + [
        DriftResult("f1.json", "echo", "LATENCY", "999ms vs recorded 3ms (threshold 503ms)")
    ]
    hashes = []
    for name, drifts in (("quiet.html", quiet), ("noisy.html", noisy)):
        out = build_report(
            server_name="x", server_cmd=["x"], negotiated_protocol="2025-11-25",
            conformance=conf, security=[], regression=_reg(drifts),
            out_path=tmp_path / name,
        )
        found = set(RUN_HASH_RE.findall(out.read_text(encoding="utf-8")))
        assert len(found) == 1
        hashes.append(found.pop())
    assert hashes[0] == hashes[1], "a latency advisory must not change the report fingerprint"
    noisy_html = (tmp_path / "noisy.html").read_text(encoding="utf-8")
    assert ">1/1<" in noisy_html, "tile denominator must count behaviour verdicts, not latency rows"
    assert "1 latency advisory" in noisy_html


async def test_v2_fixtures_still_replay(tmp_path):
    """Fixtures recorded before the contract/observation split keep replaying."""
    await record(REGRESSION_SERVER, tmp_path)
    for p in tmp_path.glob("*.json"):
        if p.name.startswith("_"):
            continue
        fixture = json.loads(p.read_text(encoding="utf-8"))
        observation = fixture.pop("observation")
        fixture.pop("contract_sha256")
        fixture["schema_version"] = 2
        fixture["response_sha256"] = obj_hash(fixture["response"])
        fixture["latency_ms"] = observation["latency_ms"]
        fixture["recorded_at"] = observation["recorded_at"]
        fixture["server_cmd"] = observation["server_cmd"]
        p.write_text(json.dumps(fixture), encoding="utf-8")
    results = await replay(REGRESSION_SERVER, tmp_path)
    summary = summarize(results)
    assert summary["gate_pass"] is True
    assert summary["ok"] == 3 and summary["content_total"] == 3


async def test_resources_only_server_is_not_failed():
    """A server whose capabilities hold no tools is spec-legal, not broken."""
    results = await run_conformance([PYTHON, str(HERE / "resources_only_server.py")])
    by_id = {r.id: r for r in results}
    must_fails = [(r.id, r.evidence) for r in results if r.level == MUST and r.status == FAIL]
    assert not must_fails, must_fails
    assert by_id["LIFE-01"].status == PASS
    assert by_id["LIFE-03"].status == SKIP
    assert by_id["TOOL-01"].status == SKIP
    assert by_id["LIST-01"].status == SKIP
    assert by_id["CAP-01"].status == PASS


async def test_crashed_server_reports_exit_code_and_stderr():
    results = await run_conformance([PYTHON, str(HERE / "crashing_server.py")])
    life01 = {r.id: r for r in results}["LIFE-01"]
    assert life01.status == FAIL
    assert "exited with code 1" in life01.evidence, life01.evidence
    assert "MISSING_API_KEY" in life01.evidence, life01.evidence
