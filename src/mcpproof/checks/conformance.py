"""Conformance lane: wire-level lifecycle, JSON-RPC and tool-metadata checks.

Everything runs over a single RawProbe pass so the report reflects one
coherent server session (and stdout hygiene is judged across all of it).
"""

from jsonschema import Draft202012Validator
from jsonschema import validate as jsonschema_validate
from jsonschema.exceptions import SchemaError, ValidationError

from .. import KNOWN_SPECS, LATEST_SPEC
from ..client import RawProbe
from .base import FAIL, MUST, PASS, SHOULD, SKIP, WARN, CheckResult

_CHECKS: dict[str, tuple[str, str, str]] = {
    "LIFE-01": (
        "initialize returns protocolVersion, capabilities and serverInfo",
        MUST,
        "Return protocolVersion, capabilities and serverInfo in the initialize result.",
    ),
    "LIFE-02": (
        f"server negotiates the latest spec revision ({LATEST_SPEC})",
        SHOULD,
        f"Upgrade the server SDK to a release that speaks the {LATEST_SPEC} spec revision.",
    ),
    "LIFE-03": (
        "server answers tools/list after the initialized notification",
        MUST,
        "Keep serving requests after the handshake; tools/list must return a result.",
    ),
    "RPC-01": (
        "unknown method gets a JSON-RPC error response",
        MUST,
        "Return a JSON-RPC error object for unrecognized methods, never a result or silence.",
    ),
    "RPC-02": (
        "unknown method error code is -32601 (method not found)",
        SHOULD,
        "Use JSON-RPC 2.0 code -32601 when rejecting unknown methods.",
    ),
    "RPC-03": (
        "malformed tools/call params are rejected with an error",
        MUST,
        "Validate tools/call params and return an error when required fields are missing.",
    ),
    "TOOL-01": (
        "every tool has a non-empty name and an inputSchema",
        MUST,
        "Give every tool in tools/list a name and an inputSchema.",
    ),
    "TOOL-02": (
        "every tool has a non-empty description",
        SHOULD,
        "Add a one-line description to every tool so agents can choose correctly.",
    ),
    "TOOL-03": (
        "every tool inputSchema compiles as JSON Schema",
        MUST,
        "Fix the inputSchema so it validates under JSON Schema draft 2020-12.",
    ),
    "TOOL-04": (
        "calling a nonexistent tool is rejected",
        MUST,
        "Return a JSON-RPC error or an isError result when tools/call names an unknown tool.",
    ),
    "TOOL-05": (
        "a call missing required arguments is rejected",
        MUST,
        "Validate arguments against the inputSchema and reject calls missing required params.",
    ),
    "HYG-01": (
        "stdout carries only JSON-RPC messages",
        MUST,
        "Send logs and banners to stderr; stdout is reserved for the protocol stream.",
    ),
    "CAP-01": (
        "declared capabilities match served features (tools)",
        SHOULD,
        "Declare capabilities.tools in initialize exactly when the server serves tools/list.",
    ),
    "LIST-01": (
        "tools/list pagination terminates (no cursor loop)",
        MUST,
        "Return a nextCursor that advances and eventually ends; a repeating cursor hangs clients.",
    ),
    "TOOL-06": (
        "declared outputSchemas compile and structured results match them",
        MUST,
        "Ship a structuredContent that validates against the declared outputSchema.",
    ),
}


def _res(check_id: str, status: str, evidence: str = "") -> CheckResult:
    title, level, fix_hint = _CHECKS[check_id]
    return CheckResult(
        id=check_id, title=title, level=level, status=status,
        evidence=evidence, fix_hint=fix_hint,
    )


def _handshake_failed(detail: str) -> list[CheckResult]:
    out = [_res("LIFE-01", FAIL, detail)]
    out += [_res(cid, SKIP, "handshake failed") for cid in _CHECKS if cid != "LIFE-01"]
    return out


async def _safe(coro):
    """Probe transport failures (dead pipe, etc.) count as no-response."""
    try:
        return await coro
    except Exception:
        return None


async def run_conformance(cmd: list[str] | None, url: str | None = None) -> list[CheckResult]:
    try:
        if url:
            from ..client_http import HttpProbe

            async with HttpProbe(url) as probe:
                return await _run_checks(probe)
        async with RawProbe(cmd) as probe:
            return await _run_checks(probe)
    except Exception as exc:  # server never came up; report instead of raising
        return _handshake_failed(f"could not start probe: {type(exc).__name__}: {exc}")


async def _run_checks(probe: RawProbe) -> list[CheckResult]:
    init = await _safe(probe.initialize())
    if init is None:
        return _handshake_failed("initialize timed out or transport failed")
    if "result" not in init:
        return _handshake_failed(f"initialize returned error: {init.get('error')}")

    results: list[CheckResult] = []
    init_result = init["result"] if isinstance(init["result"], dict) else {}

    missing = [k for k in ("protocolVersion", "capabilities", "serverInfo") if k not in init_result]
    if missing:
        results.append(_res("LIFE-01", FAIL, "initialize result missing: " + ", ".join(missing)))
    else:
        results.append(_res("LIFE-01", PASS, "protocolVersion, capabilities and serverInfo all present"))

    negotiated = init_result.get("protocolVersion")
    if negotiated == LATEST_SPEC:
        results.append(_res("LIFE-02", PASS, f"negotiated {negotiated}"))
    elif negotiated in KNOWN_SPECS:
        results.append(_res(
            "LIFE-02", WARN,
            f"requested {LATEST_SPEC}, negotiated {negotiated} — "
            f"server not yet migrated to the {LATEST_SPEC} spec revision",
        ))
    else:
        results.append(_res(
            "LIFE-02", FAIL,
            f"requested {LATEST_SPEC}, negotiated unknown version {negotiated!r}",
        ))

    tools_resp = await _safe(probe.request("tools/list"))
    tools_served = tools_resp is not None and "result" in tools_resp
    tools: list[dict] = []
    if tools_served:
        raw = tools_resp["result"].get("tools")
        tools = raw if isinstance(raw, list) else []
        results.append(_res("LIFE-03", PASS, f"tools/list returned {len(tools)} tool(s) after initialized"))
    elif tools_resp is None:
        results.append(_res("LIFE-03", FAIL, "tools/list timed out after the initialized notification"))
    else:
        results.append(_res("LIFE-03", FAIL, f"tools/list returned error: {tools_resp.get('error')}"))

    if not tools_served:
        results.append(_res("LIST-01", SKIP, "tools/list unavailable"))
    else:
        cursor = tools_resp["result"].get("nextCursor")
        if not cursor:
            results.append(_res("LIST-01", PASS, "single page, no pagination cursor"))
        else:
            seen = {cursor}
            pages = 1
            verdict = None
            while cursor:
                page = await _safe(probe.request("tools/list", {"cursor": cursor}))
                if page is None or "result" not in page:
                    verdict = _res("LIST-01", FAIL, f"pagination broke at page {pages + 1}")
                    break
                pages += 1
                cursor = page["result"].get("nextCursor")
                if cursor in seen:
                    verdict = _res(
                        "LIST-01", FAIL,
                        f"cursor repeats after {pages} pages — clients following it loop forever",
                    )
                    break
                if cursor:
                    seen.add(cursor)
                if pages > 20:
                    verdict = _res("LIST-01", FAIL, "more than 20 pages — suspected unbounded pagination")
                    break
            results.append(verdict or _res("LIST-01", PASS, f"pagination terminates after {pages} page(s)"))

    unknown = await _safe(probe.request("mcpproof/nonexistent"))
    if unknown is not None and "error" in unknown:
        code = unknown["error"].get("code")
        results.append(_res("RPC-01", PASS, f"unknown method rejected with error code {code}"))
        if code == -32601:
            results.append(_res("RPC-02", PASS, "expected -32601, got -32601"))
        else:
            results.append(_res("RPC-02", FAIL, f"expected -32601, got {code}"))
    else:
        detail = "timed out (no response)" if unknown is None else "returned a result instead of an error"
        results.append(_res("RPC-01", FAIL, f"unknown method {detail}"))
        results.append(_res("RPC-02", SKIP, "no error response to inspect"))

    malformed = await _safe(probe.request("tools/call", {"nom": "x"}))
    if malformed is not None and "error" in malformed:
        results.append(_res(
            "RPC-03", PASS,
            f"malformed params rejected with error code {malformed['error'].get('code')}",
        ))
    elif malformed is None:
        results.append(_res("RPC-03", FAIL, "malformed tools/call timed out (no response)"))
    else:
        results.append(_res("RPC-03", FAIL, "malformed tools/call params returned a result instead of an error"))

    results.extend(await _tool_checks(probe, tools, tools_served))

    if getattr(probe, "transport", "stdio") != "stdio":
        results.append(_res("HYG-01", SKIP, "stdout hygiene only applies to the stdio transport"))
    else:
        pollution = probe.non_jsonrpc_stdout
        if pollution:
            sample = " | ".join(pollution[:3])
            results.append(_res("HYG-01", FAIL, f"{len(pollution)} non-JSON-RPC stdout line(s); first 3: {sample}"))
        else:
            results.append(_res("HYG-01", PASS, "no non-JSON-RPC stdout lines observed"))

    caps = init_result.get("capabilities")
    declared = isinstance(caps, dict) and "tools" in caps
    if declared and tools_served:
        results.append(_res("CAP-01", PASS, "capabilities.tools declared and tools/list served"))
    elif not declared and not tools_served:
        results.append(_res("CAP-01", PASS, "capabilities.tools not declared and tools/list not served"))
    elif declared:
        results.append(_res("CAP-01", WARN, "capabilities declare tools but tools/list did not return a result"))
    else:
        results.append(_res(
            "CAP-01", WARN,
            f"tools/list returned {len(tools)} tool(s) but capabilities do not declare tools",
        ))

    return results


async def _tool_checks(probe: RawProbe, tools: list, tools_served: bool) -> list[CheckResult]:
    if not tools_served:
        return [
            _res(cid, SKIP, "tools/list failed")
            for cid in ("TOOL-01", "TOOL-02", "TOOL-03", "TOOL-04", "TOOL-05", "TOOL-06")
        ]

    results: list[CheckResult] = []

    def label(i: int, t: object) -> str:
        return (t.get("name") if isinstance(t, dict) else None) or f"tool[{i}]"

    offenders = []
    for i, t in enumerate(tools):
        if not isinstance(t, dict):
            offenders.append(f"tool[{i}]: not an object")
            continue
        problems = []
        if not t.get("name"):
            problems.append("empty name")
        if "inputSchema" not in t:
            problems.append("no inputSchema")
        if problems:
            offenders.append(f"{label(i, t)}: {', '.join(problems)}")
    if offenders:
        results.append(_res("TOOL-01", FAIL, "; ".join(offenders)))
    else:
        results.append(_res("TOOL-01", PASS, f"all {len(tools)} tools have a name and an inputSchema"))

    undocumented = [
        label(i, t) for i, t in enumerate(tools)
        if isinstance(t, dict) and not (t.get("description") or "").strip()
    ]
    if undocumented:
        results.append(_res("TOOL-02", WARN, "undocumented tools: " + ", ".join(undocumented)))
    else:
        results.append(_res("TOOL-02", PASS, f"all {len(tools)} tools carry a description"))

    invalid = []
    for i, t in enumerate(tools):
        if not isinstance(t, dict) or "inputSchema" not in t:
            continue  # absence is TOOL-01's finding
        try:
            Draft202012Validator.check_schema(t["inputSchema"])
        except SchemaError as exc:
            invalid.append(f"{label(i, t)}: {exc.message}")
    if invalid:
        results.append(_res("TOOL-03", FAIL, "; ".join(invalid)))
    else:
        results.append(_res("TOOL-03", PASS, f"all {len(tools)} inputSchemas compile as JSON Schema draft 2020-12"))

    ghost = await _safe(probe.request(
        "tools/call", {"name": "mcpproof__no_such_tool", "arguments": {}}
    ))
    if ghost is None:
        results.append(_res("TOOL-04", FAIL, "call to nonexistent tool timed out (no response)"))
    elif "error" in ghost:
        results.append(_res(
            "TOOL-04", PASS,
            f"rejected as JSON-RPC error (code {ghost['error'].get('code')})",
        ))
    elif isinstance(ghost.get("result"), dict) and ghost["result"].get("isError"):
        results.append(_res("TOOL-04", PASS, "rejected as tool result with isError=true"))
    else:
        results.append(_res("TOOL-04", FAIL, "call to nonexistent tool returned a normal result"))

    target = next(
        (
            t for t in tools
            if isinstance(t, dict) and t.get("name")
            and isinstance(t.get("inputSchema"), dict) and t["inputSchema"].get("required")
        ),
        None,
    )
    if target is None:
        results.append(_res("TOOL-05", SKIP, "no tool declares required params"))
    else:
        name = target["name"]
        resp = await _safe(probe.request("tools/call", {"name": name, "arguments": {}}))
        if resp is None:
            results.append(_res("TOOL-05", FAIL, f"{name} with empty args timed out (no response)"))
        elif "error" in resp:
            results.append(_res(
                "TOOL-05", PASS,
                f"{name} with empty args rejected as JSON-RPC error (code {resp['error'].get('code')})",
            ))
        elif isinstance(resp.get("result"), dict) and resp["result"].get("isError"):
            results.append(_res("TOOL-05", PASS, f"{name} with empty args rejected via isError=true"))
        else:
            results.append(_res(
                "TOOL-05", FAIL,
                f"{name} called with empty args returned a normal result (silent success)",
            ))

    results.append(await _output_schema_check(probe, tools))

    return results


async def _output_schema_check(probe: RawProbe, tools: list) -> CheckResult:
    from ..regression.recorder import is_destructive
    from ..regression.sampler import sample_args

    declaring = [
        t for t in tools
        if isinstance(t, dict) and t.get("name") and isinstance(t.get("outputSchema"), dict)
    ]
    if not declaring:
        return _res("TOOL-06", SKIP, "no tool declares an outputSchema")

    bad = []
    for t in declaring:
        try:
            Draft202012Validator.check_schema(t["outputSchema"])
        except SchemaError as exc:
            bad.append(f"{t['name']}: {exc.message}")
    if bad:
        return _res("TOOL-06", FAIL, "outputSchema does not compile: " + "; ".join(bad))

    # dynamic half: call one side-effect-safe declaring tool for real
    candidate = next(
        (t for t in declaring if not is_destructive(t["name"], t.get("description"))), None
    )
    compiled = f"all {len(declaring)} outputSchema(s) compile"
    if candidate is None:
        return _res(
            "TOOL-06", PASS,
            f"{compiled}; dynamic validation skipped (declaring tools look destructive)",
        )
    name = candidate["name"]
    resp = await _safe(probe.request(
        "tools/call",
        {"name": name, "arguments": sample_args(candidate.get("inputSchema") or {})},
    ))
    result_obj = resp.get("result") if isinstance(resp, dict) else None
    if not isinstance(result_obj, dict) or result_obj.get("isError"):
        return _res(
            "TOOL-06", PASS,
            f"{compiled}; dynamic call to {name} did not yield a normal result, structured output unverified",
        )
    structured = result_obj.get("structuredContent")
    if structured is None:
        return _res("TOOL-06", WARN, f"{name} declares an outputSchema but returned no structuredContent")
    try:
        jsonschema_validate(instance=structured, schema=candidate["outputSchema"])
    except ValidationError as exc:
        return _res("TOOL-06", FAIL, f"{name} structuredContent violates its outputSchema: {exc.message}")
    return _res("TOOL-06", PASS, f"{name} structuredContent validates against its outputSchema")
