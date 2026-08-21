"""Dual-era conformance: the 2026-07-28 modern lane and era auto-detection.

The modern target is hand-rolled from the spec (tests/modern_target_server.py)
and cross-validated against the official v2 SDK client by
scripts/crosscheck_modern_server.py.
"""

import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from _paths import ROOT, venv_python

from mcpproof.checks.base import FAIL, MUST, PASS, SKIP
from mcpproof.checks.conformance import run_conformance

PYTHON = venv_python()
SERVER = str(Path(__file__).resolve().parent / "modern_target_server.py")


def modern_cmd(*flags: str) -> list[str]:
    return [PYTHON, SERVER, *flags]


async def test_auto_detects_modern_and_all_checks_pass():
    outcome = await run_conformance(modern_cmd())
    assert outcome.era == "modern"
    assert outcome.revision == "2026-07-28"
    assert outcome.discovery == "server/discover"
    assert outcome.server_name == "modern-target"
    assert [t["name"] for t in outcome.tools] == ["echo", "price"]

    by_id = {r.id: r for r in outcome.results}
    assert "LIFE-01" not in by_id, "legacy checks must not appear in a modern-era audit"
    bad = [(r.id, r.status, r.evidence) for r in outcome.results if r.status == FAIL]
    assert not bad, bad
    for cid in ("DISC-01", "ENV-01", "VER-01", "RTYPE-01", "CACHE-01",
                "META-01", "ORD-01", "CAP-01", "TOOL-06", "RPC-02"):
        assert by_id[cid].status == PASS, (cid, by_id[cid].status, by_id[cid].evidence)
    assert by_id["HTTP-01"].status == SKIP  # routing headers are an HTTP concern
    assert by_id["HYG-01"].status == PASS


async def test_auto_falls_back_to_legacy(good_server_cmd):
    outcome = await run_conformance(good_server_cmd)
    assert outcome.era == "legacy"
    assert outcome.discovery == "initialize"
    by_id = {r.id: r for r in outcome.results}
    assert by_id["LIFE-01"].status == PASS
    assert "DISC-01" not in by_id


async def test_era_modern_against_legacy_server_fails_discover(good_server_cmd):
    outcome = await run_conformance(good_server_cmd, era="modern")
    assert outcome.era == "modern"
    by_id = {r.id: r for r in outcome.results}
    assert by_id["DISC-01"].status == FAIL
    skipped = [r for r in outcome.results if r.id != "DISC-01"]
    assert all(r.status == SKIP for r in skipped)


async def test_era_legacy_against_modern_server_reports_rejection():
    outcome = await run_conformance(modern_cmd(), era="legacy")
    assert outcome.era == "legacy"
    life01 = {r.id: r for r in outcome.results}["LIFE-01"]
    assert life01.status == FAIL
    assert "-32022" in life01.evidence, life01.evidence


async def test_omitted_cache_fields_fail_cache01():
    outcome = await run_conformance(modern_cmd("--omit-cache"))
    by_id = {r.id: r for r in outcome.results}
    assert by_id["CACHE-01"].status == FAIL
    assert "ttlMs" in by_id["CACHE-01"].evidence
    must_fails = {r.id for r in outcome.results if r.level == MUST and r.status == FAIL}
    assert must_fails == {"CACHE-01"}


async def test_omitted_result_type_fails_rtype01():
    outcome = await run_conformance(modern_cmd("--omit-result-type"))
    by_id = {r.id: r for r in outcome.results}
    assert by_id["RTYPE-01"].status == FAIL
    must_fails = {r.id for r in outcome.results if r.level == MUST and r.status == FAIL}
    assert must_fails == {"RTYPE-01"}


# ------------------------------------------------------- modern over HTTP ----


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def modern_http_url():
    import os

    port = _free_port()
    url = f"http://127.0.0.1:{port}/mcp"
    proc = subprocess.Popen(
        [PYTHON, SERVER, "--http", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15.0
        ready = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            try:
                httpx.get(url, timeout=1.0)
                ready = True
                break
            except httpx.TransportError:
                time.sleep(0.15)
        if not ready:
            if os.environ.get("CI"):
                pytest.fail("modern HTTP target server must boot in CI")
            pytest.skip("modern HTTP target server failed to boot")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


async def test_modern_over_http_including_header_enforcement(modern_http_url):
    outcome = await run_conformance(None, url=modern_http_url)
    assert outcome.era == "modern"
    by_id = {r.id: r for r in outcome.results}
    bad = [(r.id, r.status, r.evidence) for r in outcome.results if r.status == FAIL]
    assert not bad, bad
    assert by_id["HTTP-01"].status == PASS, by_id["HTTP-01"].evidence
    assert by_id["HYG-01"].status == SKIP
    assert by_id["ENV-01"].status == PASS
    assert by_id["VER-01"].status == PASS


# ------------------------------------------- regression lane, modern era ----


async def test_record_and_replay_against_modern_server(tmp_path):
    from mcpproof.regression.recorder import record
    from mcpproof.regression.replayer import replay, summarize

    paths = await record(modern_cmd(), tmp_path)
    # v4 fixture names: 0001__tool__args-hash.json — order prefix, then identity
    assert {p.name.split("__")[1] for p in paths} == {"echo", "price"}
    import json

    price_fixture = json.loads(
        next(p for p in paths if "__price__" in p.name).read_text()
    )
    assert price_fixture["response"]["structured"] == {"total": 42.0, "currency": "USD"}
    assert price_fixture["contract_sha256"]

    summary = summarize(await replay(modern_cmd(), tmp_path))
    assert summary["gate_pass"], summary
    assert summary["ok"] == len(paths)


async def test_modern_value_drift_detected(tmp_path):
    from mcpproof.regression.recorder import record
    from mcpproof.regression.replayer import replay

    await record(modern_cmd(), tmp_path)
    drifts = await replay(modern_cmd("--price-total", "43"), tmp_path)
    by_tool = {d.tool: d for d in drifts if d.kind != "OK"}
    assert "price" in by_tool, drifts
    assert by_tool["price"].kind == "VALUE"
    assert "42" in by_tool["price"].detail and "43" in by_tool["price"].detail


async def test_record_and_replay_modern_over_http(modern_http_url, tmp_path):
    from mcpproof.regression.recorder import record
    from mcpproof.regression.replayer import replay, summarize

    paths = await record(None, tmp_path, url=modern_http_url)
    assert len(paths) == 2
    summary = summarize(await replay(None, tmp_path, url=modern_http_url))
    assert summary["gate_pass"], summary


async def test_explicit_legacy_era_still_rides_the_sdk(good_server_cmd, tmp_path):
    from mcpproof.regression.recorder import record

    paths = await record(good_server_cmd, tmp_path, era="legacy")
    assert paths, "legacy-era recording must keep working through the SDK session"


# ------------------------------------------------------------- CLI e2e ----


def test_cli_run_modern_server_full_three_lanes(tmp_path):
    out = tmp_path / "report.html"
    proc = subprocess.run(
        [PYTHON, "-m", "mcpproof.cli", "run", PYTHON, SERVER,
         "--fixtures", str(tmp_path / "fx"), "--out", str(out)],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "modern era" in proc.stdout
    assert "replaying fixtures" in proc.stdout, proc.stdout
    assert "drift gate: PASS" in proc.stdout, proc.stdout
    html = out.read_text(encoding="utf-8")
    assert "SHIP-READY" in html and "NOT SHIP-READY" not in html
    assert "modern era (server/discover)" in html
    assert "selected" in html and "2026-07-28" in html
    assert (tmp_path / "fx" / "_manifest.json").exists()
