"""Minimal raw server whose tools/list nextCursor never advances (LIST-01 FAIL target)."""

import json
import sys


def reply(msg_id, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    method, msg_id = msg.get("method"), msg.get("id")
    if msg_id is None:
        continue
    if method == "initialize":
        reply(msg_id, {
            "protocolVersion": "2026-07-28",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "cursor-loop", "version": "0.0.1"},
        })
    elif method == "tools/list":
        reply(msg_id, {
            "tools": [{"name": "noop", "description": "does nothing",
                       "inputSchema": {"type": "object", "properties": {}}}],
            "nextCursor": "page-1",
        })
    else:
        sys.stdout.write(json.dumps({
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32601, "message": "Method not found"},
        }) + "\n")
        sys.stdout.flush()
