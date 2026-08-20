"""MSSS control mapping: taxonomy integrity, evaluation semantics, report rendering."""

import re
from collections import Counter

from mcpproof.checks.base import CheckResult, FAIL, MUST, PASS, SKIP, WARN
from mcpproof.checks.conformance import _CHECKS as CONFORMANCE_CHECKS, run_conformance
from mcpproof.checks.msss import CONTROLS, evaluate_msss
from mcpproof.checks.security import _META as SECURITY_CHECKS, fetch_tools, run_security
from mcpproof.report.builder import build_report

_CONTROL_ID = re.compile(r"MCP-(FS|EXEC|NET|AUTHZ|INPUT|LOG|SUPPLY|DEPLOY)-\d{2}")


def _r(check_id: str, status: str, evidence: str = "") -> CheckResult:
    return CheckResult(id=check_id, title=check_id, level=MUST, status=status, evidence=evidence)


# The bad demo server's known outcomes (mirrors tests/test_checks.py expectations).
BAD_SERVER_STATUSES = {
    "LIFE-01": FAIL, "LIFE-02": WARN, "LIFE-03": PASS, "LIST-01": PASS,
    "RPC-01": PASS, "RPC-02": FAIL, "RPC-03": FAIL,
    "TOOL-01": PASS, "TOOL-02": WARN, "TOOL-03": FAIL, "TOOL-04": PASS, "TOOL-05": FAIL,
    "HYG-01": FAIL, "CAP-01": PASS,
    "SEC-01": FAIL, "SEC-02": FAIL, "SEC-03": FAIL,
    "SEC-04": WARN, "SEC-05": PASS, "SEC-06": WARN,
}
BAD_SERVER_EVIDENCE = {
    "SEC-04": "unconstrained injection-surface params: run_shell.cmd, fetch_url.url",
    "SEC-06": "exec-style tools with free-form string params: run_shell(cmd)",
}


def _bad_server_results() -> list[CheckResult]:
    return [
        _r(cid, status, BAD_SERVER_EVIDENCE.get(cid, ""))
        for cid, status in BAD_SERVER_STATUSES.items()
    ]


def test_controls_match_official_matrix():
    """24 controls, 8 domains, 6 per level — verbatim from MSSS control-level mapping v2.0."""
    assert len(CONTROLS) == 24
    ids = [c.id for c in CONTROLS]
    assert len(set(ids)) == 24
    assert all(_CONTROL_ID.fullmatch(i) for i in ids)
    assert len({c.domain for c in CONTROLS}) == 8
    assert Counter(c.min_level for c in CONTROLS) == {"L1": 6, "L2": 6, "L3": 6, "L4": 6}

    known_checks = set(SECURITY_CHECKS) | set(CONFORMANCE_CHECKS)
    for c in CONTROLS:
        assert c.assessment in ("auto", "manual"), c.id
        if c.assessment == "auto":
            assert c.checks, f"{c.id} is auto but maps no checks"
            unknown = set(c.checks) - known_checks
            assert not unknown, f"{c.id} maps nonexistent checks: {unknown}"
        else:
            assert not c.checks, f"{c.id} is manual but maps checks"


def test_security_msss_refs_are_canonical_control_ids():
    control_ids = {c.id for c in CONTROLS}
    for check_id, meta in SECURITY_CHECKS.items():
        refs = [ref.strip() for ref in meta[3].split(",")]
        assert refs, check_id
        for ref in refs:
            assert _CONTROL_ID.fullmatch(ref), f"{check_id}: non-canonical msss_ref {ref!r}"
            assert ref in control_ids, f"{check_id}: msss_ref {ref!r} not in CONTROLS"


def test_sec06_flags_advertised_exec_tools():
    tools = [
        {
            "name": "run_shell",
            "description": "Run any shell command",
            "inputSchema": {"type": "object", "properties": {"cmd": {"type": "string"}}},
        },
        {
            "name": "calc_sum",
            "description": "Add two numbers.",
            "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}}},
        },
    ]
    by_id = {r.id: r for r in run_security(tools)}
    assert by_id["SEC-06"].status == WARN
    assert "run_shell(cmd)" in by_id["SEC-06"].evidence
    assert by_id["SEC-06"].msss_ref == "MCP-EXEC-01,MCP-EXEC-02"

    benign = {r.id: r for r in run_security(tools[1:])}
    assert benign["SEC-06"].status == PASS


def test_evaluate_msss_bad_server_known_results():
    msss = evaluate_msss(_bad_server_results())
    by_id = {c["id"]: c for c in msss["controls"]}

    # tool-metadata integrity (poisoning) and secrets controls must be gaps
    assert by_id["MCP-INPUT-01"]["status"] == "gap"
    assert "SEC-01" in by_id["MCP-INPUT-01"]["notes"]
    assert by_id["MCP-LOG-02"]["status"] == "gap"

    # SEC-04 WARN => met with the warning carried as a note
    assert by_id["MCP-INPUT-02"]["status"] == "met"
    assert "unconstrained injection-surface params" in by_id["MCP-INPUT-02"]["notes"]

    # manual controls are never assessed
    assert by_id["MCP-AUTHZ-01"]["status"] == "manual"
    assert by_id["MCP-DEPLOY-04"]["status"] == "manual"

    assert msss["level_summary"]["L1"] == {"auto_met": 0, "auto_gap": 2, "manual_count": 4}
    assert msss["level_summary"]["L2"] == {"auto_met": 1, "auto_gap": 0, "manual_count": 5}
    assert msss["level_summary"]["L3"] == {"auto_met": 0, "auto_gap": 0, "manual_count": 6}
    assert msss["overall"] == {"total": 24, "auto_met": 1, "auto_gap": 2, "manual": 21}
    assert msss["headline"] == "L1: 0/2 auto-assessable controls met · 4 require manual review"


def test_evaluate_msss_all_pass_yields_met():
    results = [_r(cid, PASS) for cid in (*CONFORMANCE_CHECKS, *SECURITY_CHECKS)]
    msss = evaluate_msss(results)
    statuses = {c["id"]: c["status"] for c in msss["controls"]}
    for c in CONTROLS:
        assert statuses[c.id] == ("met" if c.assessment == "auto" else "manual")
    assert msss["headline"] == "L1: 2/2 auto-assessable controls met · 4 require manual review"


def test_evaluate_msss_skipped_checks_degrade_to_manual():
    results = [_r(cid, SKIP, "handshake failed") for cid in (*CONFORMANCE_CHECKS, *SECURITY_CHECKS)]
    msss = evaluate_msss(results)
    for c in msss["controls"]:
        assert c["status"] == "manual"
        if c["assessment"] == "auto":
            assert "did not run" in c["notes"]


async def test_bad_server_live_msss_gaps(bad_server_cmd):
    conformance = await run_conformance(bad_server_cmd)
    tools = await fetch_tools(bad_server_cmd)
    msss = evaluate_msss(conformance + run_security(tools))
    by_id = {c["id"]: c for c in msss["controls"]}

    assert by_id["MCP-INPUT-01"]["status"] == "gap"
    assert by_id["MCP-LOG-02"]["status"] == "gap"
    assert by_id["MCP-INPUT-02"]["status"] == "met"
    assert "run_shell.cmd" in by_id["MCP-INPUT-02"]["notes"]
    assert msss["headline"] == "L1: 0/2 auto-assessable controls met · 4 require manual review"


def test_report_contains_msss_section_and_attribution(tmp_path):
    security = [
        _r(cid, status, BAD_SERVER_EVIDENCE.get(cid, ""))
        for cid, status in BAD_SERVER_STATUSES.items() if cid.startswith("SEC-")
    ]
    conformance = [
        _r(cid, status)
        for cid, status in BAD_SERVER_STATUSES.items() if not cid.startswith("SEC-")
    ]
    out = build_report(
        server_name="bad-demo",
        server_cmd=["python", "demo/bad_server.py"],
        negotiated_protocol="2025-03-26",
        conformance=conformance,
        security=security,
        regression=None,
        out_path=tmp_path / "report.html",
    )
    html = out.read_text(encoding="utf-8")

    assert "MSSS compliance" in html
    assert (
        "Control taxonomy from the MCP Server Security Standard (MSSS), "
        "CC BY-SA 4.0, mcp-security-standard.org." in html
    )
    # all 24 controls rendered
    for control in CONTROLS:
        assert control.id in html
    # the three verdict badges all appear, and manual is visibly distinct
    assert "✗ gap" in html
    assert "✓ met" in html
    assert "– manual review" in html
    assert "L1: 0/2 auto-assessable controls met · 4 require manual review" in html
