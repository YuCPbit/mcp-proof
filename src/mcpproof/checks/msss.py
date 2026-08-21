"""MSSS (MCP Server Security Standard) control taxonomy and evaluation.

Control IDs, titles, domains and level assignments are reproduced verbatim
from the official control-level mapping (v2.0, 2026-01-20) of MSSS v0.1:
https://github.com/mcp-security-standard/mcp-server-security-standard
(v0.1/standard/control-level-mapping.md) — 24 controls across 8 domains,
compliance levels L1-L4 (cumulative). 23 controls have detail documents
under v0.1/controls/; MCP-DEPLOY-04 is defined in the mapping matrix only
("future control, implementation details TBD").

The taxonomy is licensed CC BY-SA 4.0 by the MCP Security Standard Working
Group (https://mcp-security-standard.org/); the delivery report renders the
required attribution.

Honesty contract: a control is only ever assessed automatically ("auto")
when mcp-proof's deterministic checks produce evidence for it from
tools/list metadata or probe behaviour. Everything else is "manual" and is
reported as not auto-assessable — never as passed. "met" is reserved for
full direct evidence: when mapped checks were skipped, produced warnings,
or the control's automated evidence is only *supporting* (it corroborates
but cannot prove the control), the verdict is capped at "partial".
"""

from dataclasses import dataclass

from .base import FAIL, PASS, SKIP, WARN, CheckResult

MSSS_VERSION = "v0.1"
MSSS_MAPPING_VERSION = "control-level mapping v2.0 (2026-01-20)"
MSSS_URL = "https://mcp-security-standard.org/"

AUTO = "auto"
MANUAL = "manual"

MET = "met"
PARTIAL = "partial"
GAP = "gap"
MANUAL_REVIEW = "manual"

DIRECT = "direct"
SUPPORTING = "supporting"

_LEVELS = ("L1", "L2", "L3", "L4")


@dataclass(frozen=True)
class Control:
    """One MSSS control as published in the official control matrix.

    min_level is the compliance level that first requires the control
    (levels are cumulative: L2 includes all L1 controls, and so on).
    checks lists the mcp-proof check IDs whose outcomes evidence the
    control when assessment == "auto". evidence_strength says how far that
    evidence reaches: "direct" evidence can prove the control met;
    "supporting" evidence can only corroborate it (a clean scan caps the
    verdict at "partial") — though a failing check still proves a gap
    either way. note is a static scope caveat rendered alongside the
    verdict so the evidence boundary is always visible.
    """

    id: str
    domain: str
    title: str
    min_level: str
    assessment: str
    checks: tuple[str, ...] = ()
    note: str = ""
    evidence_strength: str = DIRECT


# Official matrix order (control-level-mapping.md, "Complete Control Matrix").
CONTROLS: list[Control] = [
    # ---- Level 1 ----
    Control(
        "MCP-EXEC-01", "Execution", "Prohibition of Shell Execution", "L1", MANUAL,
        note="SEC-06 flags advertised arbitrary-exec tools, but proving the "
             "absence of shell invocation requires source review.",
    ),
    Control("MCP-FS-01", "Filesystem", "Path Allowlisting and Canonical Resolution", "L1", MANUAL),
    Control("MCP-FS-02", "Filesystem", "Symlink Resolution Validation", "L1", MANUAL),
    Control("MCP-NET-01", "Network", "URL Validation and SSRF Mitigation", "L1", MANUAL),
    Control(
        "MCP-INPUT-01", "Input Validation", "JSON Schema Validation", "L1", AUTO,
        checks=("TOOL-01", "TOOL-03", "RPC-03", "TOOL-05", "SEC-01", "SEC-02", "SEC-05"),
        note="Auto-assessed from advertised schemas (present and valid), live "
             "rejection probes, and the tool-metadata poisoning scan.",
    ),
    Control(
        "MCP-LOG-02", "Logging", "Secret Redaction in Logs", "L1", AUTO,
        checks=("SEC-03",),
        note="Supporting evidence only: SEC-03 scans advertised tool metadata "
             "for secret-like strings; server log output is not inspected, so a "
             "clean scan cannot prove log redaction (a leak still proves a gap).",
        evidence_strength=SUPPORTING,
    ),
    # ---- Level 2 ----
    Control("MCP-SUPPLY-02", "Supply Chain", "Trusted Package Sources", "L2", MANUAL),
    Control(
        "MCP-INPUT-02", "Input Validation", "Input Bounds Enforcement", "L2", AUTO,
        checks=("SEC-04",),
        note="Auto-assessed from advertised schema constraints "
             "(enum/pattern/maxLength); runtime payload limits are not probed.",
    ),
    Control("MCP-INPUT-03", "Input Validation", "Timeout Enforcement", "L2", MANUAL),
    Control(
        "MCP-NET-03", "Network", "TLS Enforcement", "L2", MANUAL,
        note="MSSS marks this N/A for stdio-only deployments with no network access.",
    ),
    Control(
        "MCP-EXEC-02", "Execution", "Command Allowlisting", "L2", MANUAL,
        note="See the SEC-06 advisory for advertised command tools; allowlist "
             "verification requires source review.",
    ),
    Control("MCP-EXEC-03", "Execution", "Argument Separator Usage", "L2", MANUAL),
    # ---- Level 3 ----
    Control(
        "MCP-AUTHZ-01", "Authorization", "OAuth Token Delegation", "L3", MANUAL,
        note="MSSS marks this N/A for stdio transport with OS-level user isolation.",
    ),
    Control("MCP-AUTHZ-02", "Authorization", "Per-Tool Scope Definition", "L3", MANUAL),
    Control("MCP-AUTHZ-03", "Authorization", "Least Privilege Tool Design", "L3", MANUAL),
    Control("MCP-AUTHZ-04", "Authorization", "Resource-Based Access Control", "L3", MANUAL),
    Control("MCP-LOG-01", "Logging", "Comprehensive Audit Logging", "L3", MANUAL),
    Control("MCP-DEPLOY-01", "Deployment", "Container Hardening", "L3", MANUAL),
    # ---- Level 4 ----
    Control("MCP-FS-03", "Filesystem", "Filesystem Sandboxing", "L4", MANUAL),
    Control("MCP-SUPPLY-01", "Supply Chain", "Package Integrity Verification", "L4", MANUAL),
    Control("MCP-DEPLOY-03", "Deployment", "Resource Limits and Rate Limiting", "L4", MANUAL),
    Control("MCP-NET-02", "Network", "Egress Traffic Filtering", "L4", MANUAL),
    Control("MCP-DEPLOY-02", "Deployment", "System Call Filtering (seccomp/AppArmor)", "L4", MANUAL),
    Control(
        "MCP-DEPLOY-04", "Deployment", "Runtime Integrity Monitoring", "L4", MANUAL,
        note="Future control in MSSS v0.1 — implementation details TBD upstream.",
    ),
]


def _id_status_evidence(result) -> tuple[str, str, str]:
    if isinstance(result, dict):
        return result.get("id", ""), result.get("status", ""), result.get("evidence", "")
    return result.id, result.status, result.evidence


def evaluate_msss(check_results: list[CheckResult]) -> dict:
    """Map mcp-proof check outcomes onto the 24 MSSS controls.

    Per-control status:
      "met"     — every mapped check ran and PASSed, and the control's
                  automated evidence is direct,
      "partial" — evidence ran and nothing FAILed, but it cannot carry a full
                  "met": some mapped checks were skipped, some WARNed, or the
                  control's evidence is only supporting (e.g. MCP-LOG-02:
                  a clean metadata scan cannot prove log redaction),
      "gap"     — at least one mapped check FAILed,
      "manual"  — the control is not auto-assessable (or its mapped checks
                  could not run), so it needs human/process evidence.

    Accepts CheckResult dataclasses or equivalent dicts. Returns a dict with
    "controls" (matrix order), "level_summary" per L1-L4
    ({auto_met, auto_partial, auto_gap, manual_count}), "overall" totals and
    an honest one-line "headline" for L1.
    """
    outcomes: dict[str, tuple[str, str]] = {}
    for r in check_results:
        rid, status, evidence = _id_status_evidence(r)
        if rid:
            outcomes[rid] = (status, evidence)

    controls: list[dict] = []
    for c in CONTROLS:
        entry = {
            "id": c.id,
            "domain": c.domain,
            "title": c.title,
            "min_level": c.min_level,
            "assessment": c.assessment,
            "evidence_strength": c.evidence_strength if c.assessment == AUTO else "",
            "checks": list(c.checks),
            "status": MANUAL_REVIEW,
            "notes": "",
            "scope": c.note,
        }
        if c.assessment == AUTO:
            seen = {cid: outcomes[cid] for cid in c.checks if cid in outcomes}
            ran = {cid: (s, ev) for cid, (s, ev) in seen.items() if s != SKIP}
            failing = sorted(cid for cid, (s, _) in ran.items() if s == FAIL)
            warning = sorted(cid for cid, (s, _) in ran.items() if s == WARN)
            not_run = sorted(set(c.checks) - set(ran))
            if failing:
                entry["status"] = GAP
                entry["notes"] = "failing checks: " + ", ".join(failing)
            elif not ran:
                entry["status"] = MANUAL_REVIEW
                entry["notes"] = "mapped checks did not run — automated evidence unavailable"
            else:
                notes = [
                    f"{cid}: {ev}" for cid, (s, ev) in sorted(ran.items())
                    if s not in (PASS, FAIL)  # carry WARN evidence into the row
                ]
                capped = []
                if c.evidence_strength == SUPPORTING:
                    capped.append("supporting evidence only")
                if warning:
                    capped.append("warnings: " + ", ".join(warning))
                if not_run:
                    capped.append("not run: " + ", ".join(not_run))
                    notes.append("not run: " + ", ".join(not_run))
                entry["status"] = PARTIAL if capped else MET
                entry["notes"] = "; ".join(notes)
        controls.append(entry)

    level_summary: dict[str, dict[str, int]] = {}
    for lvl in _LEVELS:
        scoped = [e for e in controls if e["min_level"] == lvl]
        level_summary[lvl] = {
            "auto_met": sum(1 for e in scoped if e["status"] == MET),
            "auto_partial": sum(1 for e in scoped if e["status"] == PARTIAL),
            "auto_gap": sum(1 for e in scoped if e["status"] == GAP),
            "manual_count": sum(1 for e in scoped if e["status"] == MANUAL_REVIEW),
        }

    overall = {
        "total": len(controls),
        "auto_met": sum(1 for e in controls if e["status"] == MET),
        "auto_partial": sum(1 for e in controls if e["status"] == PARTIAL),
        "auto_gap": sum(1 for e in controls if e["status"] == GAP),
        "manual": sum(1 for e in controls if e["status"] == MANUAL_REVIEW),
    }

    l1 = level_summary["L1"]
    l1_auto = l1["auto_met"] + l1["auto_partial"] + l1["auto_gap"]
    if l1_auto:
        partial_bit = f" · {l1['auto_partial']} partial" if l1["auto_partial"] else ""
        headline = (
            f"L1: {l1['auto_met']}/{l1_auto} auto-assessable controls met{partial_bit} · "
            f"{l1['manual_count']} require manual review"
        )
    else:
        headline = f"L1: no auto-assessable controls · {l1['manual_count']} require manual review"

    return {
        "standard": f"MSSS {MSSS_VERSION}",
        "mapping": MSSS_MAPPING_VERSION,
        "url": MSSS_URL,
        "controls": controls,
        "level_summary": level_summary,
        "overall": overall,
        "headline": headline,
    }
