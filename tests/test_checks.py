from mcpproof.checks.base import FAIL, MUST, PASS, WARN
from mcpproof.checks.conformance import run_conformance
from mcpproof.checks.security import fetch_tools, run_security

BAD_SERVER_EXPECTED_FAILS = {
    "LIFE-01",
    "RPC-02",
    "RPC-03",
    "TOOL-03",
    "TOOL-05",
    "HYG-01",
    "SEC-01",
    "SEC-02",
    "SEC-03",
}


async def test_good_server_conformance(good_server_cmd):
    results = await run_conformance(good_server_cmd)
    by_id = {r.id: r for r in results}

    must_not_pass = [
        (r.id, r.status, r.evidence) for r in results if r.level == MUST and r.status != PASS
    ]
    assert not must_not_pass, must_not_pass
    assert by_id["LIFE-02"].status == WARN
    assert by_id["HYG-01"].status == PASS


async def test_good_server_security(good_server_cmd):
    tools = await fetch_tools(good_server_cmd)
    assert len(tools) == 4

    not_pass = [
        (r.id, r.status, r.evidence) for r in run_security(tools) if r.status != PASS
    ]
    assert not not_pass, not_pass


async def test_bad_server_expected_failures(bad_server_cmd):
    conformance = await run_conformance(bad_server_cmd)
    tools = await fetch_tools(bad_server_cmd)
    results = conformance + run_security(tools)

    failed = {r.id for r in results if r.status == FAIL}
    assert failed == BAD_SERVER_EXPECTED_FAILS

    by_id = {r.id: r for r in results}
    assert by_id["SEC-04"].status == WARN
    assert "run_shell.cmd" in by_id["SEC-04"].evidence
    assert "fetch_url.url" in by_id["SEC-04"].evidence


async def test_list01_catches_cursor_loop():
    from pathlib import Path

    from _paths import venv_python

    cmd = [venv_python(), str(Path(__file__).resolve().parent / "cursor_loop_server.py")]
    results = {r.id: r for r in await run_conformance(cmd)}
    assert results["LIST-01"].status == "FAIL"
    assert "loop" in results["LIST-01"].evidence.lower() or "repeats" in results["LIST-01"].evidence
