# server-starter

A minimal [fastmcp](https://gofastmcp.com) server (three tools, in-memory data)
that passes the mcp-proof audit out of the box. Each practice maps to the check
that rewards it:

| Practice | Where | Check |
|---|---|---|
| One-line behavioural description on every tool — no model-directed instructions | all three tools | `TOOL-02`, `SEC-01` |
| Constrained string params: `pattern` + `max_length` render into `inputSchema` | `lookup_order.order_id`, `search_faq.query` | `SEC-04` |
| Logging to **stderr** via `logging`, never `print()` — stdout is the protocol stream | `logging.basicConfig(stream=sys.stderr, ...)` | `HYG-01` |
| Typed returns emit `outputSchema` + `structuredContent` that validate | `lookup_order`, `server_stats` (dict returns) | `TOOL-06` |
| Failures raised as `ToolError` with an actionable message, not silent success | `lookup_order` unknown-ID branch | `TOOL-04`/`TOOL-05` error semantics |
| A valid `examples` entry on constrained params, so clients pick callable values | `lookup_order.order_id` | exercises `TOOL-06` dynamic validation |

The template audits fully green: fastmcp negotiates `2025-11-25`, the newest
revision the initialize handshake carries, so `LIFE-02` passes too.

## Delivery pipeline

1. Copy this directory into the engagement repo; rename the server.
2. Implement the real tools, keeping every practice above.
3. Audit + freeze behaviour:
   `mcp-proof run .venv/bin/python server.py --fixtures fixtures/ --out report.html`
4. Ship all three: the server, `report.html`, and `fixtures/` — the report
   embeds a CI workflow that replays the fixtures on every push.
