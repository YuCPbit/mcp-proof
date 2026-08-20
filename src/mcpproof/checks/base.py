from dataclasses import dataclass, field

MUST = "MUST"
SHOULD = "SHOULD"

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
SKIP = "SKIP"


@dataclass
class CheckResult:
    """One conformance or security check outcome.

    id follows the family-number convention (LIFE-01, RPC-01, TOOL-03,
    HYG-01, CAP-01, SEC-02). evidence must contain the observed vs expected
    facts so the report can stand alone as a client deliverable.
    """

    id: str
    title: str
    level: str  # MUST | SHOULD
    status: str  # PASS | FAIL | WARN | SKIP
    evidence: str = ""
    fix_hint: str = ""
    msss_ref: str = ""  # security checks: canonical MSSS control ID(s), comma-separated, e.g. "MCP-INPUT-01"


def must_score(results: list[CheckResult]) -> tuple[int, int]:
    """(passed, total) over MUST-level checks; WARN counts as passed, SKIP excluded."""
    must = [r for r in results if r.level == MUST and r.status != SKIP]
    ok = [r for r in must if r.status in (PASS, WARN)]
    return len(ok), len(must)
