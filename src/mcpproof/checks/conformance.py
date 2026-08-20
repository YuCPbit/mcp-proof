"""Conformance lane: wire-level lifecycle, JSON-RPC and tool-metadata checks.

Dual-era (SEP-2575). Era selection mirrors the official client's auto mode:
``server/discover`` is probed first and anything that is not positive modern
evidence falls back to the legacy ``initialize`` handshake — on a fresh
probe, because a dual-era server locks a connection to the era of its first
frame and the audit must never observe a session perturbed by its own
negotiation. Each era then runs its own check set over a single coherent
probe session (stdout hygiene is judged across all of it).
"""

from dataclasses import dataclass, field

from jsonschema import Draft202012Validator
from jsonschema import validate as jsonschema_validate
from jsonschema.exceptions import SchemaError, ValidationError

from .. import KNOWN_SPECS, LATEST_LEGACY_SPEC, LATEST_SPEC
from ..client import RawProbe
from ..era import (
    AUTO,
    HEADER_MISMATCH,
    LEGACY,
    MODERN,
    RESULT_TYPES,
    SERVER_INFO_META_KEY,
    UNSUPPORTED_PROTOCOL_VERSION,
    EraInfo,
    parse_discover_result,
)
from .base import FAIL, MUST, PASS, SHOULD, SKIP, WARN, CheckResult

DISCOVER_TIMEOUT = 8.0  # era probe: snappy fallback beats a full request timeout

_CHECKS: dict[str, tuple[str, str, str]] = {
    # ---- legacy era (initialize handshake) ----
    "LIFE-01": (
        "initialize returns protocolVersion, capabilities and serverInfo",
        MUST,
        "Return protocolVersion, capabilities and serverInfo in the initialize result.",
    ),
    "LIFE-02": (
        f"server negotiates the newest handshake revision ({LATEST_LEGACY_SPEC})",
        SHOULD,
        "Upgrade the server SDK to a release that negotiates the newest "
        f"initialize-handshake revision ({LATEST_LEGACY_SPEC}).",
    ),
    "LIFE-03": (
        "server answers tools/list after the initialized notification",
        MUST,
        "Keep serving requests after the handshake; tools/list must return a result.",
    ),
    # ---- modern era (2026-07-28, server/discover) ----
    "DISC-01": (
        "server/discover advertises supportedVersions and capabilities",
        MUST,
        "Answer server/discover with supportedVersions and capabilities "
        "(identity travels in the result's _meta).",
    ),
    "ENV-01": (
        "requests without the _meta protocol envelope are rejected",
        MUST,
        "Reject requests missing io.modelcontextprotocol/protocolVersion and "
        "clientCapabilities in params._meta (INVALID_PARAMS).",
    ),
    "VER-01": (
        "unsupported protocol versions are rejected with -32022",
        MUST,
        "Return UnsupportedProtocolVersionError (-32022) with the supported list "
        "when a request names a protocol version the server does not speak.",
    ),
    "RTYPE-01": (
        "every result carries the required resultType field",
        MUST,
        'Stamp resultType ("complete" or "input_required") on every result object.',
    ),
    "CACHE-01": (
        "tools/list results carry the required ttlMs and cacheScope",
        MUST,
        'Return ttlMs (milliseconds) and cacheScope ("public"/"private") on list results '
        "(CacheableResult, SEP-2549).",
    ),
    "META-01": (
        "results identify the server via _meta serverInfo",
        SHOULD,
        "Include io.modelcontextprotocol/serverInfo in each result's _meta.",
    ),
    "ORD-01": (
        "tools/list returns tools in a deterministic order",
        SHOULD,
        "Return tools in a stable order so clients and LLM prompt caches can rely on it.",
    ),
    "HTTP-01": (
        "mismatched Mcp-Method routing headers are rejected with -32020",
        SHOULD,
        "Validate the Mcp-Method / Mcp-Name headers against the request body and "
        "reject mismatches with HeaderMismatchError (-32020).",
    ),
    # ---- shared across eras ----
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
        "Declare capabilities.tools exactly when the server serves tools/list.",
    ),
    "CAP-02": (
        "declared capabilities match served features (resources)",
        SHOULD,
        "Declare capabilities.resources exactly when the server serves resources/list.",
    ),
    "CAP-03": (
        "declared capabilities match served features (prompts)",
        SHOULD,
        "Declare capabilities.prompts exactly when the server serves prompts/list.",
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
    "RES-01": (
        "advertised resources capability serves resources/list",
        MUST,
        "Answer resources/list with a result when capabilities declare resources.",
    ),
    "RES-02": (
        "every resource carries a uri and a name",
        MUST,
        "Give every entry in resources/list a non-empty uri and name.",
    ),
    "RES-03": (
        "resources/read returns contents for an advertised resource",
        MUST,
        "Serve resources/read for every resource resources/list advertises; "
        "each content entry must carry its uri.",
    ),
    "RES-04": (
        "resources/list pagination terminates (no cursor loop)",
        MUST,
        "Return a nextCursor that advances and eventually ends; a repeating cursor hangs clients.",
    ),
    "PROMPT-01": (
        "advertised prompts capability serves prompts/list",
        MUST,
        "Answer prompts/list with a result when capabilities declare prompts.",
    ),
    "PROMPT-02": (
        "every prompt has a name and well-formed argument metadata",
        MUST,
        "Give every prompt a non-empty name; every declared argument needs a name.",
    ),
    "PROMPT-03": (
        "prompts/get rejects a call missing required arguments",
        MUST,
        "Validate prompt arguments and return an error when required ones are missing.",
    ),
}

_SHARED_IDS = (
    "RPC-01", "RPC-02", "RPC-03",
    "TOOL-01", "TOOL-02", "TOOL-03", "TOOL-04", "TOOL-05", "TOOL-06",
    "LIST-01", "HYG-01", "CAP-01",
    "RES-01", "RES-02", "RES-03", "RES-04",
    "PROMPT-01", "PROMPT-02", "PROMPT-03",
    "CAP-02", "CAP-03",
)
_LEGACY_IDS = ("LIFE-01", "LIFE-02", "LIFE-03", *_SHARED_IDS)
_MODERN_IDS = (
    "DISC-01", "ENV-01", "VER-01", "RTYPE-01", "CACHE-01", "META-01", "ORD-01", "HTTP-01",
    *_SHARED_IDS,
)


@dataclass
class ConformanceOutcome:
    """Check results plus what era detection learned (feeds report + other lanes)."""

    results: list[CheckResult]
    era: str  # "modern" | "legacy"
    revision: str | None = None
    discovery: str | None = None  # "server/discover" | "initialize"
    server_name: str | None = None
    tools: list = field(default_factory=list)


def _res(check_id: str, status: str, evidence: str = "") -> CheckResult:
    title, level, fix_hint = _CHECKS[check_id]
    return CheckResult(
        id=check_id, title=title, level=level, status=status,
        evidence=evidence, fix_hint=fix_hint,
    )


def _handshake_failed(detail: str) -> list[CheckResult]:
    out = [_res("LIFE-01", FAIL, detail)]
    out += [_res(cid, SKIP, "handshake failed") for cid in _LEGACY_IDS if cid != "LIFE-01"]
    return out


def _discover_failed(detail: str) -> list[CheckResult]:
    out = [_res("DISC-01", FAIL, detail)]
    out += [_res(cid, SKIP, "server/discover failed") for cid in _MODERN_IDS if cid != "DISC-01"]
    return out


async def _safe(coro):
    """Probe transport failures (dead pipe, etc.) count as no-response."""
    try:
        return await coro
    except Exception:
        return None


async def _failure_context(probe) -> str:
    """Exit code + stderr tail, when the probe can produce them (stdio only)."""
    collect = getattr(probe, "failure_context", None)
    if collect is None:
        return ""
    try:
        return await collect()
    except Exception:
        return ""


def _make_probe(cmd: list[str] | None, url: str | None):
    if url:
        from ..client_http import HttpProbe

        return HttpProbe(url)
    return RawProbe(cmd)


async def run_conformance(
    cmd: list[str] | None, url: str | None = None, era: str = AUTO
) -> ConformanceOutcome:
    try:
        if era in (AUTO, MODERN):
            async with _make_probe(cmd, url) as probe:
                probe.enable_modern(LATEST_SPEC)
                disc = await _safe(probe.request("server/discover", {}, timeout=DISCOVER_TIMEOUT))
                result = disc.get("result") if isinstance(disc, dict) else None
                info = parse_discover_result(result) if isinstance(result, dict) else None
                if info is not None:
                    results = await _run_modern_checks(probe, info)
                    return ConformanceOutcome(
                        results, MODERN, info.revision, "server/discover",
                        info.server_info.get("name"), _tools_of(probe),
                    )
                if era == MODERN:
                    if disc is None:
                        detail = "server/discover timed out or transport failed"
                        ctx = await _failure_context(probe)
                        detail = f"{detail} — {ctx}" if ctx else detail
                    elif "error" in disc:
                        detail = f"server/discover returned error: {disc.get('error')}"
                    else:
                        detail = (
                            f"server/discover answered without a mutually supported modern "
                            f"revision (need {LATEST_SPEC}): {result}"
                        )
                    return ConformanceOutcome(
                        _discover_failed(detail), MODERN, None, "server/discover", None, [],
                    )
        # legacy era, on a fresh probe: the discover attempt above must never
        # colour the session the legacy checks observe
        async with _make_probe(cmd, url) as probe:
            results, init_result, tools = await _run_legacy_checks(probe)
            server_info = init_result.get("serverInfo")
            return ConformanceOutcome(
                results, LEGACY,
                init_result.get("protocolVersion"), "initialize",
                server_info.get("name") if isinstance(server_info, dict) else None,
                tools,
            )
    except Exception as exc:  # server never came up; report instead of raising
        detail = f"could not start probe: {type(exc).__name__}: {exc}"
        if era == MODERN:
            return ConformanceOutcome(_discover_failed(detail), MODERN)
        return ConformanceOutcome(_handshake_failed(detail), LEGACY)


def _tools_of(probe) -> list:
    return getattr(probe, "mcp_proof_tools", [])


# --------------------------------------------------------------------------
# legacy lane
# --------------------------------------------------------------------------


async def _run_legacy_checks(probe) -> tuple[list[CheckResult], dict, list]:
    init = await _safe(probe.initialize())
    if init is None:
        detail = "initialize timed out or transport failed"
        ctx = await _failure_context(probe)
        return _handshake_failed(f"{detail} — {ctx}" if ctx else detail), {}, []
    if "result" not in init:
        return _handshake_failed(f"initialize returned error: {init.get('error')}"), {}, []

    results: list[CheckResult] = []
    init_result = init["result"] if isinstance(init["result"], dict) else {}

    missing = [k for k in ("protocolVersion", "capabilities", "serverInfo") if k not in init_result]
    if missing:
        results.append(_res("LIFE-01", FAIL, "initialize result missing: " + ", ".join(missing)))
    else:
        results.append(_res("LIFE-01", PASS, "protocolVersion, capabilities and serverInfo all present"))

    negotiated = init_result.get("protocolVersion")
    if negotiated == LATEST_LEGACY_SPEC:
        results.append(_res(
            "LIFE-02", PASS,
            f"negotiated {negotiated}, the newest revision the initialize handshake carries",
        ))
    elif negotiated == LATEST_SPEC:
        results.append(_res(
            "LIFE-02", WARN,
            f"negotiated {negotiated} over the legacy initialize handshake — the modern era "
            "is announced via server/discover, which this handshake cannot verify",
        ))
    elif negotiated in KNOWN_SPECS:
        results.append(_res(
            "LIFE-02", WARN,
            f"negotiated {negotiated}; the newest handshake revision is {LATEST_LEGACY_SPEC} — "
            "a newer server SDK will negotiate it",
        ))
    else:
        results.append(_res(
            "LIFE-02", FAIL,
            f"requested {LATEST_LEGACY_SPEC}, negotiated unknown revision {negotiated!r}",
        ))

    caps = init_result.get("capabilities")
    tools_declared = isinstance(caps, dict) and "tools" in caps

    tools_resp = await _safe(probe.request("tools/list"))
    tools_served = tools_resp is not None and "result" in tools_resp
    tools: list[dict] = []
    if tools_served:
        raw = tools_resp["result"].get("tools")
        tools = raw if isinstance(raw, list) else []
        results.append(_res("LIFE-03", PASS, f"tools/list returned {len(tools)} tool(s) after initialized"))
    elif not tools_declared:
        # a resources- or prompts-only server is spec-legal: nothing to demand here
        results.append(_res(
            "LIFE-03", SKIP,
            "capabilities do not declare tools and tools/list is not served — "
            "no tools surface to check",
        ))
    elif tools_resp is None:
        results.append(_res("LIFE-03", FAIL, "tools/list timed out after the initialized notification"))
    else:
        results.append(_res("LIFE-03", FAIL, f"tools/list returned error: {tools_resp.get('error')}"))

    results.append(await _pagination_check(probe, tools_resp, tools_declared, tools_served))
    results.extend(await _rpc_checks(probe))
    results.extend(await _tool_checks(
        probe, tools, tools_served,
        skip_reason="tools/list failed" if tools_declared else "no tools surface to check",
    ))
    results.extend(await _surface_checks(probe, caps if isinstance(caps, dict) else {}))
    results.append(_hygiene_check(probe))
    results.append(_cap_check("CAP-01", "tools", tools_declared, tools_served, len(tools)))

    probe.mcp_proof_tools = tools  # stashed for the outcome
    return results, init_result, tools


# --------------------------------------------------------------------------
# modern lane (2026-07-28)
# --------------------------------------------------------------------------


async def _run_modern_checks(probe, info: EraInfo) -> list[CheckResult]:
    results: list[CheckResult] = []

    identity = info.server_info.get("name") or "no serverInfo in _meta"
    results.append(_res(
        "DISC-01", PASS,
        f"supportedVersions={info.supported_versions}, "
        f"capabilities: {', '.join(sorted(info.capabilities)) or 'none'}, identity: {identity}",
    ))

    tools_declared = "tools" in info.capabilities

    tools_resp = await _safe(probe.request("tools/list"))
    tools_served = tools_resp is not None and "result" in tools_resp
    tools: list[dict] = []
    if tools_served:
        raw = tools_resp["result"].get("tools")
        tools = raw if isinstance(raw, list) else []

    results.append(await _pagination_check(probe, tools_resp, tools_declared, tools_served))
    results.extend(await _rpc_checks(probe))

    # negative probe: strip the envelope for one request (rung 1 of the ladder)
    probe.modern_meta = None
    bare = await _safe(probe.request("tools/list"))
    probe.enable_modern(info.revision)
    if bare is not None and "error" in bare:
        results.append(_res(
            "ENV-01", PASS,
            f"request without _meta envelope rejected (code {bare['error'].get('code')})",
        ))
    elif bare is None:
        results.append(_res("ENV-01", FAIL, "request without _meta envelope got no response"))
    else:
        results.append(_res(
            "ENV-01", FAIL,
            "request without the _meta protocol envelope was answered as a normal result",
        ))

    # negative probe: claim a protocol version the server cannot speak (rung 3);
    # enable_modern keeps envelope and HTTP version header coherent, so this
    # tests version rejection rather than a header mismatch
    probe.enable_modern("1999-01-01")
    wrong = await _safe(probe.request("tools/list"))
    probe.enable_modern(info.revision)
    if wrong is not None and "error" in wrong:
        code = wrong["error"].get("code")
        if code == UNSUPPORTED_PROTOCOL_VERSION:
            supported = (wrong["error"].get("data") or {}).get("supported")
            results.append(_res(
                "VER-01", PASS,
                f"version 1999-01-01 rejected with -32022, supported={supported}",
            ))
        else:
            results.append(_res(
                "VER-01", FAIL,
                f"unsupported version rejected with code {code}; the spec names -32022 "
                "(UnsupportedProtocolVersionError)",
            ))
    elif wrong is None:
        results.append(_res("VER-01", FAIL, "request at an unsupported version got no response"))
    else:
        results.append(_res("VER-01", FAIL, "request at an unsupported version was answered normally"))

    results.append(await _header_check(probe))

    results.extend(await _tool_checks(
        probe, tools, tools_served,
        skip_reason="tools/list failed" if tools_declared else "no tools surface to check",
    ))

    # deterministic order (SHOULD, 2026-07-28 minor change 3)
    if not tools_served:
        results.append(_res("ORD-01", SKIP, "tools/list unavailable"))
    else:
        again = await _safe(probe.request("tools/list"))
        first = [t.get("name") for t in tools if isinstance(t, dict)]
        if again is None or "result" not in again:
            results.append(_res("ORD-01", SKIP, "second tools/list call failed"))
        else:
            raw = again["result"].get("tools")
            second = [t.get("name") for t in raw if isinstance(t, dict)] if isinstance(raw, list) else []
            if first == second:
                results.append(_res("ORD-01", PASS, f"two calls returned {len(first)} tool(s) in identical order"))
            else:
                results.append(_res("ORD-01", WARN, f"tool order differs between calls: {first} vs {second}"))

    results.extend(await _surface_checks(probe, info.capabilities))

    # CacheableResult fields (MUST, SEP-2549) on every cacheable result the
    # session observed: tools/resources/prompts lists and resources/read
    cacheable = [
        (method, r) for method, r in getattr(probe, "observed_results", [])
        if method in ("tools/list", "resources/list", "prompts/list",
                      "resources/read", "resources/templates/list")
    ]
    problems = []
    for method, r in cacheable:
        if not isinstance(r.get("ttlMs"), int | float):
            problems.append(f"{method}: ttlMs missing or non-numeric")
        elif r.get("cacheScope") not in ("public", "private"):
            problems.append(f"{method}: cacheScope missing or invalid ({r.get('cacheScope')!r})")
    if not cacheable:
        results.append(_res("CACHE-01", SKIP, "no cacheable results observed"))
    elif problems:
        results.append(_res("CACHE-01", FAIL, "; ".join(sorted(set(problems))[:6])))
    else:
        results.append(_res(
            "CACHE-01", PASS,
            f"all {len(cacheable)} cacheable result(s) carry ttlMs and cacheScope "
            f"({', '.join(sorted({m for m, _ in cacheable}))})",
        ))

    # resultType on every observed result (required at 2026-07-28)
    observed = getattr(probe, "observed_results", [])
    missing_rt = [
        f"{method} ({rt!r})"
        for method, rt in ((m, r.get("resultType")) for m, r in observed)
        if rt not in RESULT_TYPES
    ]
    if not observed:
        results.append(_res("RTYPE-01", SKIP, "no results observed"))
    elif missing_rt:
        results.append(_res(
            "RTYPE-01", FAIL,
            f"{len(missing_rt)}/{len(observed)} results lack a valid resultType: "
            + ", ".join(missing_rt[:5]),
        ))
    else:
        results.append(_res("RTYPE-01", PASS, f'all {len(observed)} observed results carry resultType'))

    # identity in _meta (SHOULD)
    carrying = sum(
        1 for _, r in observed
        if isinstance(r.get("_meta"), dict) and SERVER_INFO_META_KEY in r["_meta"]
    )
    if not observed:
        results.append(_res("META-01", SKIP, "no results observed"))
    elif carrying == len(observed):
        results.append(_res("META-01", PASS, f"all {len(observed)} results carry _meta serverInfo"))
    elif carrying:
        results.append(_res("META-01", WARN, f"only {carrying}/{len(observed)} results carry _meta serverInfo"))
    else:
        results.append(_res("META-01", WARN, "no result carries io.modelcontextprotocol/serverInfo in _meta"))

    results.append(_hygiene_check(probe))
    results.append(_cap_check("CAP-01", "tools", tools_declared, tools_served, len(tools)))

    probe.mcp_proof_tools = tools
    return results


async def _header_check(probe) -> CheckResult:
    """HTTP-01: a deliberately mismatched Mcp-Method header must be refused (-32020)."""
    if getattr(probe, "transport", "stdio") == "stdio":
        return _res("HTTP-01", SKIP, "routing headers only apply to the Streamable HTTP transport")
    resp = await _safe(probe.request(
        "tools/list", header_overrides={"mcp-method": "prompts/list"}
    ))
    if resp is not None and "error" in resp:
        code = resp["error"].get("code")
        if code == HEADER_MISMATCH:
            return _res("HTTP-01", PASS, "Mcp-Method mismatch rejected with -32020")
        return _res("HTTP-01", WARN, f"Mcp-Method mismatch rejected with code {code}, spec names -32020")
    if resp is None:
        return _res("HTTP-01", WARN, "Mcp-Method mismatch probe got no response")
    return _res("HTTP-01", WARN, "server answered normally despite a mismatched Mcp-Method header")


# --------------------------------------------------------------------------
# shared blocks
# --------------------------------------------------------------------------


async def _pagination_check(
    probe, first_resp, declared: bool, served: bool,
    *, check_id: str = "LIST-01", method: str = "tools/list",
) -> CheckResult:
    if not served:
        return _res(
            check_id, SKIP,
            f"{method} unavailable" if declared else "no surface to paginate",
        )
    cursor = first_resp["result"].get("nextCursor")
    if not cursor:
        return _res(check_id, PASS, "single page, no pagination cursor")
    seen = {cursor}
    pages = 1
    while cursor:
        page = await _safe(probe.request(method, {"cursor": cursor}))
        if page is None or "result" not in page:
            return _res(check_id, FAIL, f"pagination broke at page {pages + 1}")
        pages += 1
        cursor = page["result"].get("nextCursor")
        if cursor in seen:
            return _res(
                check_id, FAIL,
                f"cursor repeats after {pages} pages — clients following it loop forever",
            )
        if cursor:
            seen.add(cursor)
        if pages > 20:
            return _res(check_id, FAIL, "more than 20 pages — suspected unbounded pagination")
    return _res(check_id, PASS, f"pagination terminates after {pages} page(s)")


async def _rpc_checks(probe) -> list[CheckResult]:
    results: list[CheckResult] = []
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
    return results


def _hygiene_check(probe) -> CheckResult:
    if getattr(probe, "transport", "stdio") != "stdio":
        return _res("HYG-01", SKIP, "stdout hygiene only applies to the stdio transport")
    pollution = probe.non_jsonrpc_stdout
    if pollution:
        sample = " | ".join(pollution[:3])
        return _res("HYG-01", FAIL, f"{len(pollution)} non-JSON-RPC stdout line(s); first 3: {sample}")
    return _res("HYG-01", PASS, "no non-JSON-RPC stdout lines observed")


def _cap_check(check_id: str, surface: str, declared: bool, served: bool, n: int) -> CheckResult:
    if declared and served:
        return _res(check_id, PASS, f"capabilities.{surface} declared and {surface}/list served")
    if not declared and not served:
        return _res(check_id, PASS, f"capabilities.{surface} not declared and {surface}/list not served")
    if declared:
        return _res(check_id, WARN, f"capabilities declare {surface} but {surface}/list did not return a result")
    return _res(
        check_id, WARN,
        f"{surface}/list returned {n} item(s) but capabilities do not declare {surface}",
    )


async def _surface_checks(probe, caps: dict) -> list[CheckResult]:
    """Capability-aware resources and prompts lanes, shared across eras."""
    results: list[CheckResult] = []

    # ---- resources ----
    declared = isinstance(caps, dict) and "resources" in caps
    resp = await _safe(probe.request("resources/list"))
    served = resp is not None and "result" in resp
    resources: list[dict] = []
    if served:
        raw = resp["result"].get("resources")
        resources = [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []

    if declared and served:
        results.append(_res("RES-01", PASS, f"resources/list returned {len(resources)} resource(s)"))
    elif declared:
        detail = "timed out (no response)" if resp is None else f"returned error: {resp.get('error')}"
        results.append(_res("RES-01", FAIL, f"capabilities declare resources but resources/list {detail}"))
    else:
        results.append(_res("RES-01", SKIP, "resources capability not advertised"))

    if not served:
        results.append(_res("RES-02", SKIP, "resources/list unavailable"))
    else:
        offenders = [
            f"resource[{i}]: missing {', '.join(k for k in ('uri', 'name') if not r.get(k))}"
            for i, r in enumerate(resources)
            if not r.get("uri") or not r.get("name")
        ]
        if offenders:
            results.append(_res("RES-02", FAIL, "; ".join(offenders)))
        else:
            results.append(_res("RES-02", PASS, f"all {len(resources)} resource(s) carry a uri and a name"))

    first = next((r for r in resources if r.get("uri")), None)
    if first is None:
        results.append(_res("RES-03", SKIP, "no listed resource to read"))
    else:
        uri = first["uri"]
        read = await _safe(probe.request("resources/read", {"uri": uri}))
        contents = (
            read["result"].get("contents")
            if read is not None and isinstance(read.get("result"), dict) else None
        )
        if read is None:
            results.append(_res("RES-03", FAIL, f"resources/read {uri} timed out (no response)"))
        elif "error" in read:
            results.append(_res(
                "RES-03", FAIL,
                f"resources/read {uri} rejected its own advertised resource: {read['error']}",
            ))
        elif not isinstance(contents, list) or not contents:
            results.append(_res("RES-03", FAIL, f"resources/read {uri} returned no contents list"))
        elif any(not isinstance(c, dict) or not c.get("uri") for c in contents):
            results.append(_res("RES-03", FAIL, f"resources/read {uri}: content entries missing their uri"))
        else:
            results.append(_res("RES-03", PASS, f"read {uri}: {len(contents)} content entr(y/ies), uri echoed"))

    results.append(await _pagination_check(
        probe, resp, declared, served, check_id="RES-04", method="resources/list",
    ))

    # ---- prompts ----
    p_declared = isinstance(caps, dict) and "prompts" in caps
    p_resp = await _safe(probe.request("prompts/list"))
    p_served = p_resp is not None and "result" in p_resp
    prompts: list[dict] = []
    if p_served:
        raw = p_resp["result"].get("prompts")
        prompts = [p for p in raw if isinstance(p, dict)] if isinstance(raw, list) else []

    if p_declared and p_served:
        results.append(_res("PROMPT-01", PASS, f"prompts/list returned {len(prompts)} prompt(s)"))
    elif p_declared:
        detail = "timed out (no response)" if p_resp is None else f"returned error: {p_resp.get('error')}"
        results.append(_res("PROMPT-01", FAIL, f"capabilities declare prompts but prompts/list {detail}"))
    else:
        results.append(_res("PROMPT-01", SKIP, "prompts capability not advertised"))

    if not p_served:
        results.append(_res("PROMPT-02", SKIP, "prompts/list unavailable"))
    else:
        offenders = []
        for i, p in enumerate(prompts):
            if not p.get("name"):
                offenders.append(f"prompt[{i}]: empty name")
                continue
            args = p.get("arguments")
            if args is not None and (
                not isinstance(args, list)
                or any(not isinstance(a, dict) or not a.get("name") for a in args)
            ):
                offenders.append(f"{p['name']}: malformed argument metadata")
        if offenders:
            results.append(_res("PROMPT-02", FAIL, "; ".join(offenders)))
        else:
            results.append(_res("PROMPT-02", PASS, f"all {len(prompts)} prompt(s) carry valid metadata"))

    demanding = next(
        (
            p for p in prompts
            if p.get("name") and isinstance(p.get("arguments"), list)
            and any(isinstance(a, dict) and a.get("required") for a in p["arguments"])
        ),
        None,
    )
    if demanding is None:
        results.append(_res("PROMPT-03", SKIP, "no prompt declares required arguments"))
    else:
        name = demanding["name"]
        got = await _safe(probe.request("prompts/get", {"name": name, "arguments": {}}))
        if got is None:
            results.append(_res("PROMPT-03", FAIL, f"prompts/get {name} with empty args timed out"))
        elif "error" in got:
            results.append(_res(
                "PROMPT-03", PASS,
                f"{name} with empty args rejected (code {got['error'].get('code')})",
            ))
        else:
            results.append(_res(
                "PROMPT-03", FAIL,
                f"prompts/get {name} missing its required argument returned a normal result",
            ))

    results.append(_cap_check("CAP-02", "resources", declared, served, len(resources)))
    results.append(_cap_check("CAP-03", "prompts", p_declared, p_served, len(prompts)))
    return results


async def _tool_checks(
    probe, tools: list, tools_served: bool, skip_reason: str = "tools/list failed"
) -> list[CheckResult]:
    if not tools_served:
        return [
            _res(cid, SKIP, skip_reason)
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


async def _output_schema_check(probe, tools: list) -> CheckResult:
    from ..regression.recorder import classify_tool
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
    # (annotations outrank the name heuristic — see classify_tool)
    candidate = next(
        (
            t for t in declaring
            if classify_tool(t["name"], t.get("description"), t.get("annotations"))[0] == "auto"
        ),
        None,
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
