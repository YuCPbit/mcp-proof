"""Aggregate lane results into the client-facing delivery report.

The run hash covers inputs and behavioural outcomes — never timestamps,
never latency measurements — so two runs that observe identical behaviour
produce the identical fingerprint.
"""

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import KNOWN_SPECS, LATEST_LEGACY_SPEC, __version__
from ..checks.base import FAIL, MUST, PASS, SHOULD, SKIP, WARN, CheckResult
from ..checks.msss import evaluate_msss
from ..provenance import obj_hash

_TEMPLATE_DIR = Path(__file__).parent


def _as_dicts(results: list) -> list[dict]:
    return [asdict(r) if is_dataclass(r) else dict(r) for r in results]


def _level_score(results: list[dict], level: str) -> tuple[int, int]:
    scoped = [r for r in results if r["level"] == level and r["status"] != SKIP]
    ok = [r for r in scoped if r["status"] in (PASS, WARN)]
    return len(ok), len(scoped)


def _next_steps(conf: list[dict], sec: list[dict], reg: dict | None) -> list[dict]:
    """The remediation queue, priority-ordered: P0 blocks shipping, P1 is advisory.
    A clean report gets maintenance guidance instead of an empty section."""
    steps: list[dict] = []
    for r in conf:
        if r["level"] == MUST and r["status"] == FAIL:
            steps.append({"p": "P0", "text": f"{r['id']} — {r['fix_hint'] or r['title']}"})
    for r in sec:
        if r["status"] == FAIL:
            steps.append({"p": "P0", "text": f"{r['id']} — {r['fix_hint'] or r['title']}"})
    if reg:
        for d in reg.get("drifts", []):
            if d["kind"] in ("BREAKING", "ERROR"):
                steps.append({
                    "p": "P0",
                    "text": f"{d['tool']} — {d['kind'].lower()} drift: {d['detail'][:90]}",
                })
        value_n = sum(1 for d in reg.get("drifts", []) if d["kind"] == "VALUE")
        if value_n:
            steps.append({
                "p": "P1",
                "text": f"Review {value_n} value drift(s): if the change is intended, re-record the baseline; "
                        "if not, it reached production unannounced.",
            })
    for r in conf:
        if r["status"] == WARN or (r["level"] == SHOULD and r["status"] == FAIL):
            steps.append({"p": "P1", "text": f"{r['id']} — {r['fix_hint'] or r['title']}"})
    for r in sec:
        if r["status"] == WARN:
            steps.append({"p": "P1", "text": f"{r['id']} — {r['fix_hint'] or r['title']}"})
    if not steps:
        return [
            {"p": "KEEP", "text": "Commit the fixtures directory and the CI workflow above — "
                                  "behavioural drift will then fail the build before users see it."},
            {"p": "KEEP", "text": "Re-audit after the next MCP spec revision or any SDK upgrade; "
                                  "identical behaviour reproduces the same fingerprint, so before/after is provable."},
        ]
    return steps[:8]


def build_report(
    *,
    server_name: str,
    server_cmd: list[str],
    negotiated_protocol: str | None,
    conformance: list[CheckResult],
    security: list[CheckResult],
    regression: dict | None,
    out_path: str | Path,
    msss: dict | None = None,
    protocol_era: str = "legacy",
    discovery: str | None = None,
) -> Path:
    """regression: None when the lane didn't run, else
    {"summary": dict from replayer.summarize, "drifts": [DriftResult-like],
     "fixtures_sha256": str, "action_yaml": str, "fixtures_dir": str}

    msss: pre-computed evaluate_msss() dict; when None (the default) it is
    derived here from the conformance + security results.
    """
    conf = _as_dicts(conformance)
    sec = _as_dicts(security)
    if msss is None:
        msss = evaluate_msss(conf + sec)
    reg = None
    if regression is not None:
        reg = dict(regression)
        reg["drifts"] = _as_dicts(regression.get("drifts", []))

    must_ok, must_total = _level_score(conf, MUST)
    should_ok, should_total = _level_score(conf, SHOULD)
    sec_fails = sum(1 for r in sec if r["status"] == FAIL)
    sec_warns = sum(1 for r in sec if r["status"] == WARN)

    blockers: list[str] = []
    if must_ok < must_total:
        blockers.append(f"{must_total - must_ok} MUST conformance check(s) failing")
    if sec_fails:
        blockers.append(f"{sec_fails} security finding(s)")
    if reg and not reg.get("summary", {}).get("gate_pass", True):
        s = reg["summary"]
        drifting = s.get("breaking", 0) + s.get("value", 0) + s.get("error", 0)
        blockers.append(f"{drifting} behavioural drift(s)")

    # LATENCY rows carry live measurements and the summary is derived data —
    # both stay out of the fingerprint so it depends on behaviour only.
    run_hash = obj_hash(
        {
            "tool": {"name": "mcp-proof", "version": __version__},
            "server_cmd": server_cmd,
            "negotiated_protocol": negotiated_protocol,
            "protocol_era": protocol_era,
            "conformance": conf,
            "security": sec,
            "regression": reg and {
                "drifts": [d for d in reg.get("drifts", []) if d.get("kind") != "LATENCY"],
                "fixtures_sha256": reg.get("fixtures_sha256"),
            },
        }
    )

    if protocol_era == "modern":
        era_label = f"modern era ({discovery or 'server/discover'})"
        protocol_note = ""
        spec_reference = negotiated_protocol or LATEST_LEGACY_SPEC
        protocol_verb = "selected"
    else:
        era_label = "initialize-handshake era"
        spec_reference = LATEST_LEGACY_SPEC
        protocol_verb = "negotiated"
        if negotiated_protocol == LATEST_LEGACY_SPEC:
            protocol_note = "newest initialize-handshake revision"
        elif negotiated_protocol in KNOWN_SPECS:
            protocol_note = f"newer revision available: {LATEST_LEGACY_SPEC}"
        else:
            protocol_note = ""

    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(default=True, default_for_string=True),
    )
    html = env.get_template("template.html").render(
        server_name=server_name,
        server_cmd=" ".join(server_cmd),
        generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        tool_version=__version__,
        negotiated_protocol=negotiated_protocol or "unknown",
        protocol_note=protocol_note,
        protocol_verb=protocol_verb,
        era_label=era_label,
        spec_reference=spec_reference,
        run_hash=run_hash,
        conformance=conf,
        must_ok=must_ok,
        must_total=must_total,
        should_ok=should_ok,
        should_total=should_total,
        security=sec,
        sec_fails=sec_fails,
        sec_warns=sec_warns,
        msss=msss,
        regression=reg,
        verdict_pass=not blockers,
        blockers=blockers,
        next_steps=_next_steps(conf, sec, reg),
    )
    out = Path(out_path)
    out.write_text(html, encoding="utf-8")
    return out
