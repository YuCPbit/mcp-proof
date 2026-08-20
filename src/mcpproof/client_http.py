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

from . import __version__, LATEST_SPEC
from .client import DEFAULT_TIMEOUT

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
        self._client: httpx.AsyncClient | None = None
        self._next_id = 0

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

    def _headers(self) -> dict[str, str]:
        headers = {"accept": ACCEPT, "content-type": "application/json"}
        if self.session_id:
            headers[MCP_SESSION_ID] = self.session_id
        if self.protocol_version:
            headers[MCP_PROTOCOL_VERSION] = self.protocol_version
        return headers

    async def _post(self, msg: dict, req_id: int | None) -> dict | None:
        assert self._client
        async with self._client.stream(
            "POST", self.url, json=msg, headers=self._headers()
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
        self, method: str, params: dict | None = None, timeout: float | None = None
    ) -> dict | None:
        """Send a request; return the raw response envelope, or None on
        timeout or transport error."""
        self._next_id += 1
        req_id = self._next_id
        msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        try:
            return await asyncio.wait_for(
                self._post(msg, req_id), timeout or self.timeout
            )
        except _TRANSPORT_ERRORS:
            return None

    async def notify(self, method: str, params: dict | None = None) -> None:
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        try:
            await asyncio.wait_for(self._post(msg, None), self.timeout)
        except _TRANSPORT_ERRORS:
            pass

    async def initialize(self, protocol_version: str = LATEST_SPEC) -> dict | None:
        """Handshake requesting the latest spec, so the negotiated version in the
        response reveals whether the server has migrated."""
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
