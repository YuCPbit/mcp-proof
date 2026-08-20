"""Hand-rolled 2026-07-28 (modern era) MCP server. Pure stdlib, no SDK.

Why hand-rolled: the project venv pins the 1.x client SDK (mcp<2), and the
1.x and 2.x SDKs cannot share a venv — so the modern-era test target
implements the wire format directly from the spec instead. The format is
cross-validated against the official v2 SDK client by
scripts/crosscheck_modern_server.py (run it from any venv with mcp>=2).

Serves stdio by default; ``--http PORT`` serves Streamable HTTP (plain-JSON
responses). Validation mirrors the spec's inbound ladder, in rung order:
1. params._meta carries protocolVersion + clientCapabilities → else -32602
2. HTTP: MCP-Protocol-Version / Mcp-Method / Mcp-Name headers match the body
   → else -32020 (HeaderMismatchError)
3. the envelope's version is supported → else -32022 with {supported, requested}

Planted-violation flags for negative tests:
  --omit-cache        tools/list drops ttlMs/cacheScope   (CACHE-01)
  --omit-result-type  results drop resultType             (RTYPE-01)
"""

import json
import sys

SUPPORTED = ["2026-07-28"]
SERVER_INFO = {"name": "modern-target", "version": "1.0"}

PV_KEY = "io.modelcontextprotocol/protocolVersion"
CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"
NAME_BEARING = {"tools/call": "name", "prompts/get": "name", "resources/read": "uri"}

OMIT_CACHE = "--omit-cache" in sys.argv
OMIT_RESULT_TYPE = "--omit-result-type" in sys.argv

TOOLS = [
    {
        "name": "echo",
        "description": "Echo text back.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "maxLength": 200}},
            "required": ["text"],
        },
    },
    {
        "name": "price",
        "description": "Quote the price of an item.",
        "inputSchema": {
            "type": "object",
            "properties": {"item": {"type": "string", "maxLength": 100}},
            "required": ["item"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {"total": {"type": "number"}, "currency": {"type": "string"}},
            "required": ["total", "currency"],
        },
    },
]


def _result(payload: dict) -> dict:
    out = dict(payload)
    if not OMIT_RESULT_TYPE:
        out["resultType"] = "complete"
    out["_meta"] = {SERVER_INFO_KEY: SERVER_INFO}
    return out


def _error(code: int, message: str, data=None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return err


def _rung1_envelope(params) -> tuple[dict | None, dict | None]:
    """-> (meta, None) or (None, error)"""
    meta = (params or {}).get("_meta")
    if not isinstance(meta, dict):
        return None, _error(-32602, "params._meta missing: modern requests carry the protocol envelope")
    missing = [k for k in (PV_KEY, CAPS_KEY) if k not in meta]
    if missing:
        return None, _error(-32602, "missing _meta keys: " + ", ".join(missing))
    return meta, None


def _rung2_headers(headers, method: str, params, meta: dict) -> dict | None:
    if headers is None:
        return None
    hv = headers.get("mcp-protocol-version")
    if hv is not None and hv != meta.get(PV_KEY):
        return _error(-32020, f"MCP-Protocol-Version header ({hv}) does not match the _meta envelope")
    hm = headers.get("mcp-method")
    if hm is not None and hm != method:
        return _error(-32020, f"Mcp-Method header ({hm}) does not match the request method ({method})")
    name_key = NAME_BEARING.get(method)
    hn = headers.get("mcp-name")
    if name_key and hn is not None and hn != str((params or {}).get(name_key, "")):
        return _error(-32020, "Mcp-Name header does not match the request body")
    return None


def _rung3_version(meta: dict) -> dict | None:
    version = meta.get(PV_KEY)
    if version not in SUPPORTED:
        return _error(
            -32022, f"unsupported protocol version: {version!r}",
            {"supported": SUPPORTED, "requested": version},
        )
    return None


def handle(method: str, params, headers=None) -> tuple[str, dict]:
    """-> ("result"|"error", payload)"""
    if method == "initialize":
        # modern-only server: the handshake era is not spoken here
        return "error", _error(
            -32022, "initialize is a legacy-era method; this server speaks server/discover",
            {"supported": SUPPORTED, "requested": (params or {}).get("protocolVersion")},
        )
    meta, err = _rung1_envelope(params)
    if err:
        return "error", err
    err = _rung2_headers(headers, method, params, meta)
    if err:
        return "error", err
    err = _rung3_version(meta)
    if err:
        return "error", err

    if method == "server/discover":
        return "result", _result({"supportedVersions": SUPPORTED, "capabilities": {"tools": {}}})
    if method == "tools/list":
        payload: dict = {"tools": TOOLS}
        if not OMIT_CACHE:
            payload["ttlMs"] = 60000
            payload["cacheScope"] = "private"
        return "result", _result(payload)
    if method == "tools/call":
        name = (params or {}).get("name")
        args = (params or {}).get("arguments") or {}
        if not isinstance(name, str):
            return "error", _error(-32602, "tools/call requires params.name")
        if name == "echo":
            if not isinstance(args.get("text"), str):
                return "error", _error(-32602, "echo requires arguments.text (string)")
            return "result", _result(
                {"content": [{"type": "text", "text": args["text"]}], "isError": False}
            )
        if name == "price":
            if not isinstance(args.get("item"), str):
                return "error", _error(-32602, "price requires arguments.item (string)")
            return "result", _result({
                "content": [{"type": "text", "text": "Total: $42.00"}],
                "structuredContent": {"total": 42.0, "currency": "USD"},
                "isError": False,
            })
        return "error", _error(-32602, f"unknown tool: {name}")
    return "error", _error(-32601, f"Method not found: {method}")


# ---------------------------------------------------------------- stdio ----


def serve_stdio() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict) or msg.get("id") is None:
            continue  # notification
        kind, payload = handle(msg.get("method", ""), msg.get("params"))
        envelope = {"jsonrpc": "2.0", "id": msg["id"], kind: payload}
        sys.stdout.write(json.dumps(envelope) + "\n")
        sys.stdout.flush()


# ----------------------------------------------------------------- http ----


def serve_http(port: int) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 (http.server naming)
            length = int(self.headers.get("content-length") or 0)
            try:
                msg = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                return
            if not isinstance(msg, dict) or msg.get("id") is None:
                self.send_response(202)
                self.end_headers()
                return
            headers = {k.lower(): v for k, v in self.headers.items()}
            kind, payload = handle(msg.get("method", ""), msg.get("params"), headers)
            body = json.dumps({"jsonrpc": "2.0", "id": msg["id"], kind: payload}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            self.send_response(405)
            self.end_headers()

        def log_message(self, *args):  # stderr silence: keep test output clean
            pass

    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    if "--http" in sys.argv:
        serve_http(int(sys.argv[sys.argv.index("--http") + 1]))
    else:
        serve_stdio()
