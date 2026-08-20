"""HTTP siblings of the stdio clients in client.py.

HttpProbe speaks JSON-RPC over the MCP Streamable HTTP transport directly so
checks can observe wire-level behaviour the SDK would normalize away: raw
envelopes, exact error codes, and session / protocol-version header handling.

open_session_http wraps the official SDK for high-level work, mirroring
open_session.
"""

import asyncio
import json
from contextlib import asynccontextmanager

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from . import LATEST_LEGACY_SPEC, __version__
from .client import DEFAULT_TIMEOUT
from .era import MCP_METHOD_HEADER, MCP_NAME_HEADER, NAME_BEARING_METHODS, modern_envelope

ACCEPT = "application/json, text/event-stream"
MCP_SESSION_ID = "mcp-session-id"
MCP_PROTOCOL_VERSION = "mcp-protocol-version"

_TRANSPORT_ERRORS = (
    httpx.HTTPError,
    httpx.InvalidURL,
    httpx.StreamError,
    OSError,
    ValueError,
    asyncio.TimeoutError,
)


class HttpProbe:
    transport = "http"

    def __init__(self, url: str, timeout: float = DEFAULT_TIMEOUT):
        self.url = url
        self.timeout = timeout
        # HTTP has no stdout to pollute; kept empty for probe-interface parity.
        self.non_jsonrpc_stdout: list[str] = []
        self.server_messages: list[dict] = []
        self.session_id: str | None = None
        self.protocol_version: str | None = None
        # set via enable_modern(): stamped into params._meta on every request
        self.modern_meta: dict | None = None
        self._modern_revision: str | None = None
        # (method, result) for every result envelope received — modern-era
        # checks (resultType, _meta serverInfo) read the session's evidence here
        self.observed_results: list[tuple[str, dict]] = []
        self._client: httpx.AsyncClient | None = None
        self._next_id = 0

    def enable_modern(self, revision: str) -> None:
        """Speak the 2026-07-28 era: every request carries the _meta envelope
        plus the Mcp-Method / Mcp-Name / MCP-Protocol-Version headers, and no
        protocol session is expected (SEP-2567 removed Mcp-Session-Id)."""
        self.modern_meta = modern_envelope(revision, "mcp-proof", __version__)
        self._modern_revision = revision

    async def __aenter__(self) -> "HttpProbe":
        self._client = httpx.AsyncClient(timeout=None, follow_redirects=True)
        return self

    async def __aexit__(self, *exc) -> None:
        assert self._client
        if self.session_id:
            try:
                await asyncio.wait_for(
                    self._client.delete(self.url, headers=self._headers()), timeout=3
                )
            except _TRANSPORT_ERRORS:
                pass
        await self._client.aclose()

    def _headers(self, msg: dict | None = None, overrides: dict | None = None) -> dict[str, str]:
        headers = {"accept": ACCEPT, "content-type": "application/json"}
        if self.modern_meta is not None:
            # SEP-2243 routing headers; no session header in the modern era
            headers[MCP_PROTOCOL_VERSION] = self._modern_revision or ""
            if msg is not None:
                headers[MCP_METHOD_HEADER] = str(msg.get("method", ""))
                name_key = NAME_BEARING_METHODS.get(msg.get("method", ""))
                params = msg.get("params") or {}
                if name_key and isinstance(params, dict) and name_key in params:
                    headers[MCP_NAME_HEADER] = str(params[name_key])
        else:
            if self.session_id:
                headers[MCP_SESSION_ID] = self.session_id
            if self.protocol_version:
                headers[MCP_PROTOCOL_VERSION] = self.protocol_version
        if overrides:
            headers.update(overrides)
        return headers

    async def _post(
        self, msg: dict, req_id: int | None, header_overrides: dict | None = None
    ) -> dict | None:
        assert self._client
        async with self._client.stream(
            "POST", self.url, json=msg, headers=self._headers(msg, header_overrides)
        ) as response:
            sid = response.headers.get(MCP_SESSION_ID)
            if sid:
                self.session_id = sid
            if req_id is None or response.status_code == 202:
                return None
            content_type = response.headers.get("content-type", "").lower()
            if content_type.startswith("application/json"):
                envelope = json.loads(await response.aread())
                if isinstance(envelope, dict) and (
                    "result" in envelope or "error" in envelope
                ):
                    return envelope
                return None
            if content_type.startswith("text/event-stream"):
                return await self._read_sse(response, req_id)
            return None

    async def _read_sse(self, response: httpx.Response, req_id: int) -> dict | None:
        data_lines: list[str] = []

        def dispatch() -> dict | None:
            if not data_lines:
                return None
            payload = "\n".join(data_lines)
            data_lines.clear()
            try:
                envelope = json.loads(payload)
            except ValueError:
                return None
            if not isinstance(envelope, dict):
                return None
            if envelope.get("id") == req_id and (
                "result" in envelope or "error" in envelope
            ):
                return envelope
            self.server_messages.append(envelope)
            return None

        async for line in response.aiter_lines():
            if line == "":
                found = dispatch()
                if found is not None:
                    return found
                continue
            if line.startswith("data:"):
                value = line[5:]
                data_lines.append(value[1:] if value.startswith(" ") else value)
        return dispatch()

    async def request(
        self, method: str, params: dict | None = None, timeout: float | None = None,
        header_overrides: dict | None = None,
    ) -> dict | None:
        """Send a request; return the raw response envelope, or None on
        timeout or transport error."""
        self._next_id += 1
        req_id = self._next_id
        msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if self.modern_meta is not None and method != "initialize":
            params = {**(params or {})}
            params.setdefault("_meta", self.modern_meta)
        if params is not None:
            msg["params"] = params
        try:
            resp = await asyncio.wait_for(
                self._post(msg, req_id, header_overrides), timeout or self.timeout
            )
        except _TRANSPORT_ERRORS:
            return None
        if isinstance(resp, dict) and isinstance(resp.get("result"), dict):
            self.observed_results.append((method, resp["result"]))
        return resp

    async def notify(self, method: str, params: dict | None = None) -> None:
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        try:
            await asyncio.wait_for(self._post(msg, None), self.timeout)
        except _TRANSPORT_ERRORS:
            pass

    async def initialize(self, protocol_version: str = LATEST_LEGACY_SPEC) -> dict | None:
        """Legacy-era handshake requesting the newest revision it can carry,
        so the response reveals which revision the server negotiates."""
        resp = await self.request(
            "initialize",
            {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "mcp-proof", "version": __version__},
            },
        )
        if resp is not None and "result" in resp:
            result = resp["result"]
            negotiated = result.get("protocolVersion") if isinstance(result, dict) else None
            if negotiated:
                # sent as mcp-protocol-version on every request after negotiation
                self.protocol_version = str(negotiated)
            await self.notify("notifications/initialized")
        return resp


@asynccontextmanager
async def open_session_http(url: str):
    """Official-SDK session over Streamable HTTP for high-level tool interaction."""
    async with streamable_http_client(url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            session.mcp_proof_init = init  # stash for callers that need metadata
            yield session
