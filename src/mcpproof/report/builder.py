"""Render the report model into its delivery formats.

`build_model` (model.py) is the single source of truth; this module turns it
into the client-facing HTML and, on request, the machine-native artifacts:
versioned JSON, JUnit XML and SARIF.
"""

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..checks.base import CheckResult
from .model import build_model

_TEMPLATE_DIR = Path(__file__).parent


def render_html(model: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(default=True, default_for_string=True),
    )
    conf, sec = model["conformance"], model["security"]
    return env.get_template("template.html").render(
        server_name=model["server"]["name"],
        server_cmd=" ".join(model["server"]["cmd"]),
        generated_at=model["observation"]["generated_at"],
        tool_version=model["tool"]["version"],
        negotiated_protocol=model["server"]["revision"] or "unknown",
        protocol_note=model["protocol"]["note"],
        protocol_verb=model["protocol"]["verb"],
        era_label=model["protocol"]["era_label"],
        spec_reference=model["protocol"]["spec_reference"],
        behavior_sha256=model["behavior_sha256"],
        conformance=conf["checks"],
        must_ok=conf["must_ok"], must_total=conf["must_total"],
        should_ok=conf["should_ok"], should_total=conf["should_total"],
        security=sec["checks"],
        sec_fails=sec["fails"], sec_warns=sec["warns"],
        msss=model["msss"],
        regression=model["regression"],
        verdict_pass=model["verdict"]["ship_ready"],
        blockers=model["verdict"]["blockers"],
        next_steps=model["next_steps"],
        audit_status=model["audit"]["status"],
        audit_error=model["audit"]["error"],
    )


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
    json_path: str | Path | None = None,
    junit_path: str | Path | None = None,
    sarif_path: str | Path | None = None,
    audit_error: str | None = None,
) -> Path:
    """regression: None when the lane didn't run, else
    {"summary": dict from replayer.summarize, "drifts": [DriftResult-like],
     "fixtures_sha256": str, "action_yaml": str, "fixtures_dir": str,
     "baseline_created": bool}

    msss: pre-computed evaluate_msss() dict; when None (the default) it is
    derived from the conformance + security results.

    audit_error: set when mcp-proof's own machinery failed — renders the
    report INCONCLUSIVE instead of blaming the target.
    """
    model = build_model(
        server_name=server_name,
        server_cmd=server_cmd,
        negotiated_protocol=negotiated_protocol,
        conformance=conformance,
        security=security,
        regression=regression,
        msss=msss,
        protocol_era=protocol_era,
        discovery=discovery,
        audit_error=audit_error,
    )

    out = Path(out_path)
    out.write_text(render_html(model), encoding="utf-8")

    if json_path:
        Path(json_path).write_text(
            json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    if junit_path:
        from .junit import junit_xml

        Path(junit_path).write_text(junit_xml(model), encoding="utf-8")
    if sarif_path:
        from .sarif import sarif_json

        Path(sarif_path).write_text(
            json.dumps(sarif_json(model), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return out
