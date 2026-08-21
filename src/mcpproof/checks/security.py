"""Security lane: static analysis of tools/list metadata, MSSS-aligned.

Pure functions over the tool dicts a server advertises — nothing here
executes tools, so the lane is deterministic and safe to run on any server.

Each check's msss_ref carries the canonical MSSS control ID(s) it evidences
(comma-separated when several), per the MCP Server Security Standard v0.1
control matrix — see checks/msss.py for the full taxonomy and evaluation.
"""

import json
import re

from ..client import RawProbe
from ..schemas import iter_properties
from .base import FAIL, MUST, PASS, SHOULD, WARN, CheckResult

_META: dict[str, tuple[str, str, str, str]] = {
    "SEC-01": (
        "no prompt-injection patterns in tool descriptions",
        MUST,
        "Rewrite descriptions to describe tool behaviour; remove instructions aimed at the model.",
        "MCP-INPUT-01",
    ),
    "SEC-02": (
        "no invisible or bidi control characters in tool metadata",
        MUST,
        "Strip zero-width, bidi-control and tag-block characters from tool names and descriptions.",
        "MCP-INPUT-01",
    ),
    "SEC-03": (
        "no secret-looking strings in tool metadata",
        MUST,
        "Remove embedded credentials from descriptions/schemas and rotate any real keys.",
        "MCP-LOG-02",
    ),
    "SEC-04": (
        "injection-surface string params carry constraints",
        SHOULD,
        "Add enum, pattern or maxLength to path/url/command-like string params.",
        "MCP-INPUT-02",
    ),
    "SEC-05": (
        "tool descriptions stay under 2000 chars",
        SHOULD,
        "Shorten oversized descriptions; long metadata prose is a common poisoning carrier.",
        "MCP-INPUT-01",
    ),
    "SEC-06": (
        "no tool advertises unconstrained arbitrary execution",
        SHOULD,
        "Replace free-form command/shell tools with parameterized, allowlisted operations "
        "(MSSS MCP-EXEC-01/02).",
        "MCP-EXEC-01,MCP-EXEC-02",
    ),
}

_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (all |any )?(previous|prior|above) (instructions|context)",
        r"do not (tell|inform|reveal|mention)( this)? to (the )?user",
        r"<(system|important|secret|hidden)>",
        r"always (call|use|invoke) this tool (first|before)",
        r"instead,? (call|use|send)",
        r"exfiltrat",
        r"(send|post|forward) .{0,40}(credentials|password|token|key)",
    )
]

# zero-width U+200B-200F/U+2060/U+FEFF, bidi controls, Unicode tag block
_INVISIBLE = re.compile(
    "[\u200b-\u200f\u2060\ufeff\u202a-\u202e\u2066-\u2069"
    "\U000e0000-\U000e007f]"
)

_SECRET_PATTERNS = [
    re.compile(p)
    for p in (
        r"sk-[A-Za-z0-9]{16,}",
        r"ghp_[A-Za-z0-9]{30,}",
        r"AKIA[0-9A-Z]{16}",
        r"xox[abps]-[A-Za-z0-9-]{10,}",
        r"AIza[0-9A-Za-z_\-]{30,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY",
    )
]

_INJECTION_PARAM = re.compile(
    r"path|file|dir|url|uri|cmd|command|exec|shell|query|sql", re.IGNORECASE
)

# schema keys that bound a string parameter (shared by SEC-04 and SEC-06)
_CONSTRAINT_KEYS = ("enum", "pattern", "maxLength")

# tool-name tokens that advertise command/shell execution (SEC-06)
_EXEC_NAME_TOKENS = frozenset(
    {"shell", "bash", "sh", "zsh", "exec", "execute", "terminal", "cmd", "command", "powershell"}
)
_ARBITRARY_EXEC_DESC = re.compile(
    r"\b(?:runs?|executes?)\s+(?:any|arbitrary)\s+(?:shell\s+|system\s+)?command", re.IGNORECASE
)

_MAX_DESCRIPTION = 2000


def _sec(check_id: str, status: str, evidence: str) -> CheckResult:
    title, level, fix_hint, msss_ref = _META[check_id]
    return CheckResult(
        id=check_id, title=title, level=level, status=status,
        evidence=evidence, fix_hint=fix_hint, msss_ref=msss_ref,
    )


def _name(i: int, tool: dict) -> str:
    return tool.get("name") or f"tool[{i}]"


def _string_params(tool: dict) -> list[tuple[str, dict]]:
    """(path, effective schema) for every string-typed property reachable in
    the tool's inputSchema — through ``$ref``, ``allOf``, nested objects,
    array items and ``anyOf``/``oneOf`` branches, so an injection surface
    like ``config.shell.command`` cannot hide one level down."""
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        return []
    out: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for path, pschema in iter_properties(schema):
        if path in seen:
            continue
        ptype = pschema.get("type")
        if ptype == "string" or (isinstance(ptype, list) and "string" in ptype):
            seen.add(path)
            out.append((path, pschema))
    return out


async def fetch_tools(cmd: list[str]) -> list[dict]:
    """tools/list result dicts for the static lane; [] when the server can't be probed."""
    try:
        async with RawProbe(cmd) as probe:
            init = await probe.initialize()
            if init is None or "result" not in init:
                return []
            resp = await probe.request("tools/list")
            if resp is None or "result" not in resp:
                return []
            tools = resp["result"].get("tools")
            return [t for t in tools if isinstance(t, dict)] if isinstance(tools, list) else []
    except Exception:
        return []


def run_security(tools: list[dict]) -> list[CheckResult]:
    n = len(tools)
    results: list[CheckResult] = []

    injected = []
    for i, t in enumerate(tools):
        desc = t.get("description") or ""
        for pat in _INJECTION_PATTERNS:
            m = pat.search(desc)
            if m:
                injected.append(f'{_name(i, t)}: "{m.group(0)}"')
    if injected:
        results.append(_sec("SEC-01", FAIL, "; ".join(injected)))
    else:
        results.append(_sec("SEC-01", PASS, f"0 matches across {n} tools"))

    invisible = []
    for i, t in enumerate(tools):
        for field in ("name", "description"):
            value = t.get(field) or ""
            codepoints = sorted({f"U+{ord(c):04X}" for c in _INVISIBLE.findall(value)})
            if codepoints:
                invisible.append(f"{_name(i, t)}.{field}: {', '.join(codepoints)}")
    if invisible:
        results.append(_sec("SEC-02", FAIL, "; ".join(invisible)))
    else:
        results.append(_sec("SEC-02", PASS, f"0 invisible characters across {n} tools"))

    leaks = []
    for i, t in enumerate(tools):
        surface = (t.get("description") or "") + " " + json.dumps(t.get("inputSchema") or {})
        for pat in _SECRET_PATTERNS:
            m = pat.search(surface)
            if m:
                token = m.group(0)
                # never echo the whole candidate secret back into a report
                leaks.append(f"{_name(i, t)}: {token[:10]}… ({len(token)} chars)")
    if leaks:
        results.append(_sec("SEC-03", FAIL, "; ".join(leaks)))
    else:
        results.append(_sec("SEC-03", PASS, f"0 secret-like strings across {n} tools"))

    unconstrained = []
    for i, t in enumerate(tools):
        for pname, pschema in _string_params(t):
            if not _INJECTION_PARAM.search(pname):
                continue
            if any(k in pschema for k in _CONSTRAINT_KEYS):
                continue
            unconstrained.append(f"{_name(i, t)}.{pname}")
    if unconstrained:
        results.append(_sec(
            "SEC-04", WARN,
            "unconstrained injection-surface params: " + ", ".join(unconstrained),
        ))
    else:
        results.append(_sec("SEC-04", PASS, f"0 unconstrained injection-surface params across {n} tools"))

    oversized = [
        f"{_name(i, t)} ({len(t.get('description') or '')} chars)"
        for i, t in enumerate(tools)
        if len(t.get("description") or "") > _MAX_DESCRIPTION
    ]
    if oversized:
        results.append(_sec("SEC-05", WARN, "descriptions over 2000 chars: " + ", ".join(oversized)))
    else:
        longest = max((len(t.get("description") or "") for t in tools), default=0)
        results.append(_sec("SEC-05", PASS, f"longest description {longest} chars across {n} tools"))

    exec_tools = []
    for i, t in enumerate(tools):
        name_tokens = set(re.split(r"[^a-z0-9]+", (t.get("name") or "").lower())) - {""}
        desc = t.get("description") or ""
        if not (name_tokens & _EXEC_NAME_TOKENS or _ARBITRARY_EXEC_DESC.search(desc)):
            continue
        free = [
            pname for pname, pschema in _string_params(t)
            if not any(k in pschema for k in _CONSTRAINT_KEYS)
        ]
        if free:
            exec_tools.append(f"{_name(i, t)}({', '.join(free)})")
    if exec_tools:
        results.append(_sec(
            "SEC-06", WARN,
            "exec-style tools with free-form string params: " + "; ".join(exec_tools),
        ))
    else:
        results.append(_sec("SEC-06", PASS, f"0 exec-style tools with free-form params across {n} tools"))

    return results
