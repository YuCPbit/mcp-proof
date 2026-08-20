"""Probe-backed session for modern-era (2026-07-28) servers.

The SDK sessions in client.py / client_http.py ride the pinned 1.x client,
which speaks only the initialize handshake — a modern-only server rejects it
with -32022. Repinning onto the 2.x SDK is not an option today: the fastmcp
dev targets require ``mcp<2.0`` (fastmcp-slim), so both SDKs can never share
this venv. Instead the regression lane reuses the dual-era probes that the
conformance lane already cross-validated against the official v2 SDK in both
directions: this adapter exposes the two RPCs recording needs (tools/list,
tools/call) behind the same attribute shapes the SDK session returns, so the
recorder and replayer run unchanged in either era.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

from . import LATEST_SPEC
from .era import parse_discover_result


class ModernSessionError(RuntimeError):
    """The server did not behave as a modern-era peer for this session."""


def _shim_tool(t: dict) -> SimpleNamespace:
    return SimpleNamespace(
        name=t.get("name"),
        description=t.get("description"),
        inputSchema=t.get("inputSchema"),
        annotations=t.get("annotations"),
    )


def _shim_part(p: dict) -> SimpleNamespace:
    return SimpleNamespace(type=p.get("type", "unknown"), text=p.get("text", ""))


class ModernProbeSession:
    """tools/list and tools/call over a modern-era probe, SDK-shaped results.

    Mirrors the 1.x ``ClientSession`` contract the regression lane relies on:
    JSON-RPC protocol errors raise, tool-level failures (``isError: true``)
    return as results.
    """

    def __init__(self, probe):
        self._probe = probe

    async def list_tools(self) -> SimpleNamespace:
        tools: list[SimpleNamespace] = []
        cursor: str | None = None
        pages = 0
        while True:
            resp = await self._probe.request(
                "tools/list", {"cursor": cursor} if cursor else {}
            )
            if resp is None or "result" not in resp:
                raise ModernSessionError(
                    f"tools/list failed: {(resp or {}).get('error', 'no response')}"
                )
            page = resp["result"]
            raw = page.get("tools")
            if isinstance(raw, list):
                tools += [_shim_tool(t) for t in raw if isinstance(t, dict)]
            cursor = page.get("nextCursor")
            pages += 1
            if not cursor or pages > 50:
                return SimpleNamespace(tools=tools)

    async def call_tool(self, name: str, arguments: dict) -> SimpleNamespace:
        resp = await self._probe.request("tools/call", {"name": name, "arguments": arguments})
        if resp is None:
            raise ModernSessionError(f"tools/call {name}: no response")
        if "error" in resp:
            raise ModernSessionError(f"tools/call {name} returned error: {resp['error']}")
        result = resp.get("result") if isinstance(resp.get("result"), dict) else {}
        parts = result.get("content")
        return SimpleNamespace(
            content=[_shim_part(p) for p in parts if isinstance(p, dict)]
            if isinstance(parts, list) else [],
            structuredContent=result.get("structuredContent"),
            isError=bool(result.get("isError")),
        )


def _probe_ctx(cmd: list[str] | None, url: str | None):
    if url:
        from .client_http import HttpProbe

        return HttpProbe(url)
    from .client import RawProbe

    return RawProbe(cmd)


@asynccontextmanager
async def open_modern_session(cmd: list[str] | None, url: str | None = None):
    """Modern-era session over one probe: discover up front (the spec's
    connect-time version selection), then serve list/call with the envelope
    stamped on every request."""
    async with _probe_ctx(cmd, url) as probe:
        probe.enable_modern(LATEST_SPEC)
        resp = await probe.request("server/discover", {})
        result = resp.get("result") if isinstance(resp, dict) else None
        info = parse_discover_result(result) if isinstance(result, dict) else None
        if info is None:
            raise ModernSessionError(
                "server did not answer server/discover with a mutually supported "
                f"modern revision: {(resp or {}).get('error', resp)}"
            )
        yield ModernProbeSession(probe)
