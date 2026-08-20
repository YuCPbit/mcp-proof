"""Spec-legal MCP server with no tools surface at all: resources only.

Raw JSON-RPC over stdio, no SDK. Exists to prove the audit never fails a
server for lacking a capability it does not advertise (LIFE-03 / CAP-01).
"""

import json
import sys


def reply(msg_id, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(msg):
    method = msg.get("method")
    msg_id = msg.get("id")
    if msg_id is None:
        return  # notification
    if method == "initialize":
        reply(
            msg_id,
            result={
                "protocolVersion": "2025-11-25",
                "capabilities": {"resources": {}},
                "serverInfo": {"name": "resources-only", "version": "1.0"},
            },
        )
    elif method == "resources/list":
        reply(msg_id, result={"resources": []})
    else:
        reply(msg_id, error={"code": -32601, "message": f"Method not found: {method}"})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        handle(msg)


if __name__ == "__main__":
    main()
