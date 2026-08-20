"""The starter template ships audit-clean: this test is that guarantee."""

from _paths import ROOT, venv_python

from mcpproof.checks.base import FAIL, MUST, PASS, SKIP, WARN
from mcpproof.checks.conformance import run_conformance
from mcpproof.checks.security import fetch_tools, run_security

STARTER_CMD = [venv_python(), str(ROOT / "templates" / "server-starter" / "server.py")]


async def test_starter_template_is_audit_clean():
    conformance = await run_conformance(STARTER_CMD)
    by_id = {r.id: r for r in conformance}

    must_bad = [
        (r.id, r.status, r.evidence)
        for r in conformance
        if r.level == MUST and r.status not in (PASS, SKIP)
    ]
    assert not must_bad, must_bad

    # the fastmcp stack negotiates 2025-11-25 — the newest revision the
    # initialize handshake carries, so the template is fully current
    assert by_id["LIFE-02"].status == PASS, (by_id["LIFE-02"].status, by_id["LIFE-02"].evidence)

    tools = await fetch_tools(STARTER_CMD)
    assert len(tools) == 3, [t.get("name") for t in tools]
    security_bad = [
        (r.id, r.status, r.evidence)
        for r in run_security(tools)
        if r.status in (FAIL, WARN)
    ]
    assert not security_bad, security_bad
