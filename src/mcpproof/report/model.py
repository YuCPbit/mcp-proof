"""The versioned, machine-readable report model.

Single source of truth for every output format: the HTML template, the JSON
artifact, JUnit and SARIF are all rendered from this dict.

Two fingerprints, two questions (schema v3):

* ``behavior_sha256`` — *what did the server do?* Check verdicts
  (id/level/status), non-latency drift verdicts, protocol facts. Evidence
  strings stay out (failure evidence embeds stderr tails and other
  environment noise), as do the auditor's version and the launch command —
  identical server behaviour fingerprints identically across machines.
* ``run_hash`` — *what does this report say?* The whole document minus the
  two fingerprints themselves and the volatile ``observation`` block: checks
  with their evidence, the verdict banner, audit status, summary counters,
  the MSSS table, next steps. Schema v2 hashed a curated field list instead,
  which left every derived field editable without breaking verification —
  v3 exists to close that.

Neither fingerprint ever includes timestamps or latency measurements;
volatile context lives under ``observation``, and latency advisory rows
(plus their summary counter) are filtered before hashing.
"""

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime

from .. import KNOWN_SPECS, LATEST_LEGACY_SPEC, __version__
from ..checks.base import FAIL, MUST, PASS, SHOULD, SKIP, WARN
from ..checks.msss import evaluate_msss
from ..errors import UnsupportedReportSchema
from ..provenance import obj_hash

REPORT_SCHEMA_VERSION = 3


def _as_dicts(results: list) -> list[dict]:
    return [asdict(r) if is_dataclass(r) else dict(r) for r in results]


def _non_latency_drifts(reg: dict | None) -> list[dict]:
    # LATENCY rows carry live measurements — they stay out of every fingerprint
    return [d for d in (reg or {}).get("drifts", []) if d.get("kind") != "LATENCY"]


def _behavior_hash_input(negotiated_protocol, protocol_era, conf, sec, reg) -> dict:
    return {
        "negotiated_protocol": negotiated_protocol,
        "protocol_era": protocol_era,
        # verdicts only: evidence strings can embed stderr tails and other
        # environment noise, so they belong to the audit hash, not this one
        "conformance": [{"id": r["id"], "level": r["level"], "status": r["status"]}
                        for r in conf],
        "security": [{"id": r["id"], "level": r["level"], "status": r["status"]}
                     for r in sec],
        "regression": reg and {
            "drifts": [{"fixture": d["fixture"], "tool": d["tool"],
                        "kind": d["kind"], "detail": d["detail"]}
                       for d in _non_latency_drifts(reg)],
            "fixtures_sha256": reg.get("fixtures_sha256"),
        },
    }


def _run_hash_input(tool_version, server_cmd, negotiated_protocol, protocol_era,
                    conf, sec, reg) -> dict:
    # FROZEN: the schema-v2 run-hash recipe, kept verbatim so `verify` can
    # still check reports written by mcp-proof ≤ 0.7.1. New fields go into
    # _document_hash_input (v3), never here.
    return {
        "tool": {"name": "mcp-proof", "version": tool_version},
        "server_cmd": server_cmd,
        "negotiated_protocol": negotiated_protocol,
        "protocol_era": protocol_era,
        "conformance": conf,
        "security": sec,
        "regression": reg and {
            "drifts": _non_latency_drifts(reg),
            "fixtures_sha256": reg.get("fixtures_sha256"),
        },
    }


# the run fingerprint covers everything EXCEPT itself, its sibling, and the
# volatile observation block (generated_at timestamp)
_DOC_HASH_EXCLUDED = ("behavior_sha256", "run_hash", "observation")


def _document_hash_input(model: dict) -> dict:
    """Schema v3 run-hash input: the whole report document minus its own
    fingerprints and ``observation``. Built by subtraction, not enumeration,
    so a field added to the model later is hashed by default instead of
    silently joining the editable set. Latency rows carry live measurements —
    they and their summary counter are filtered, exactly as the behaviour
    hash filters them, so a latency advisory never changes a fingerprint."""
    doc = {k: v for k, v in model.items() if k not in _DOC_HASH_EXCLUDED}
    reg = doc.get("regression")
    if reg:
        reg = dict(reg)
        reg["drifts"] = _non_latency_drifts(reg)
        summary = dict(reg.get("summary") or {})
        summary.pop("latency", None)
        reg["summary"] = summary
        doc["regression"] = reg
    return doc


def recompute_hashes(model: dict) -> tuple[str, str]:
    """Recompute (behavior_sha256, run_hash) from a stored report model.

    The JSON model is self-contained: every hash input is a field it carries,
    so `mcp-proof verify` can check offline that nothing fingerprinted was
    edited after the report was written. Keys are canonicalized by obj_hash,
    so a JSON round-trip never changes the answer. The run-hash recipe is
    selected by the report's own schema version: v3 covers the whole document
    (verdict banner, audit status, summaries, MSSS, next steps included);
    v2 reports keep their original curated-field recipe, which covered check
    verdicts, drifts and evidence only. Editing the version field buys
    nothing — either recipe's recomputation then disagrees with the stored
    hash. Raises UnsupportedReportSchema for versions newer than this build.
    """
    version = model.get("report_schema_version")
    version = version if isinstance(version, int) else 2
    if version > REPORT_SCHEMA_VERSION:
        raise UnsupportedReportSchema(
            f"report declares schema v{version}, newer than this mcp-proof "
            f"understands (≤{REPORT_SCHEMA_VERSION}) — upgrade mcp-proof to verify it"
        )
    server = model["server"]
    # pass the stored dicts through untouched: they are the very objects the
    # build hashed, so any extra/missing key is a difference we WANT to catch
    conf = model["conformance"]["checks"]
    sec = model["security"]["checks"]
    reg = model.get("regression")
    behavior = obj_hash(_behavior_hash_input(server["revision"], server["era"], conf, sec, reg))
    if version >= 3:
        run = obj_hash(_document_hash_input(model))
    else:
        run = obj_hash(_run_hash_input(
            model["tool"]["version"], server["cmd"], server["revision"], server["era"],
            conf, sec, reg,
        ))
    return behavior, run


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


def build_model(
    *,
    server_name: str,
    server_cmd: list[str],
    negotiated_protocol: str | None,
    conformance: list,
    security: list,
    regression: dict | None,
    msss: dict | None = None,
    protocol_era: str = "legacy",
    discovery: str | None = None,
    audit_error: str | None = None,
) -> dict:
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
    if audit_error:
        # the auditor failed, not the target: nothing below counts as evidence
        blockers.append("audit did not complete — internal auditor error (not target behaviour)")
    if must_ok < must_total:
        blockers.append(f"{must_total - must_ok} MUST conformance check(s) failing")
    if sec_fails:
        blockers.append(f"{sec_fails} security finding(s)")
    if reg and not reg.get("summary", {}).get("gate_pass", True):
        s = reg["summary"]
        drifting = s.get("breaking", 0) + s.get("value", 0) + s.get("error", 0)
        blockers.append(f"{drifting} behavioural drift(s)")

    behavior_sha256 = obj_hash(
        _behavior_hash_input(negotiated_protocol, protocol_era, conf, sec, reg)
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

    if audit_error:
        next_steps = [{
            "p": "P0",
            "text": "Audit inconclusive — mcp-proof's own check logic failed, so nothing was "
                    "proven about the target either way. Re-run the audit; if this reproduces, "
                    "file the auditor error above as an mcp-proof bug.",
        }]
    else:
        next_steps = _next_steps(conf, sec, reg)

    model = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "tool": {"name": "mcp-proof", "version": __version__},
        # status/error stay out of the behaviour hash (they describe this
        # run's completeness, not the target's behaviour) but the document
        # hash below covers them: a report edited from "inconclusive" to
        # "complete" must not verify
        "audit": {
            "status": "inconclusive" if audit_error else "complete",
            "error": audit_error or "",
        },
        "behavior_sha256": behavior_sha256,
        "run_hash": "",  # filled below, once the document it covers exists
        "server": {
            "name": server_name,
            "cmd": list(server_cmd),
            "era": protocol_era,
            "revision": negotiated_protocol,
            "discovery": discovery,
        },
        "protocol": {
            "era_label": era_label,
            "verb": protocol_verb,
            "note": protocol_note,
            "spec_reference": spec_reference,
        },
        "verdict": {"ship_ready": not blockers, "blockers": blockers},
        "conformance": {
            "checks": conf,
            "must_ok": must_ok, "must_total": must_total,
            "should_ok": should_ok, "should_total": should_total,
        },
        "security": {"checks": sec, "fails": sec_fails, "warns": sec_warns},
        "msss": msss,
        "regression": reg,
        "next_steps": next_steps,
        # context, never hashed
        "observation": {"generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")},
    }
    model["run_hash"] = obj_hash(_document_hash_input(model))
    return model
