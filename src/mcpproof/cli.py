import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    # Legacy Windows consoles use narrow code pages; progress glyphs (→ ✓ ⚠)
    # must degrade to replacement characters instead of crashing the CLI.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass
    parser = argparse.ArgumentParser(
        prog="mcp-proof",
        description="Ship an MCP server with a receipt: deterministic conformance, "
        "security and regression audit with a client-ready delivery report.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Full audit and delivery report")
    run_p.add_argument("server_cmd", nargs="*", help="Command that starts the server (stdio)")
    run_p.add_argument("--url", default=None, help="Audit a running Streamable-HTTP server instead")
    run_p.add_argument(
        "--era", choices=["auto", "modern", "legacy"], default="auto",
        help="Protocol era for the conformance lane: auto probes server/discover "
             "(2026-07-28) and falls back to the initialize handshake (default: auto)",
    )
    run_p.add_argument("--out", default="mcp-proof-report.html", help="Report output path")
    run_p.add_argument("--fixtures", default=None, help="Fixtures dir; enables regression lane")
    run_p.add_argument("--server-name", default=None, help="Display name for the report")
    run_p.add_argument(
        "--semantic", action="store_true",
        help="(reserved for a future release) opt-in LLM semantic lane",
    )
    run_p.add_argument(
        "--include-destructive", action="store_true",
        help="Also record write/delete/exec-style tools when creating a baseline (default: skip them)",
    )
    run_p.add_argument(
        "--edge-cases", action="store_true",
        help="Baseline boundary inputs too (long strings, injection probes, empty strings)",
    )
    run_p.add_argument(
        "--pdf", action="store_true",
        help="Also export the report as PDF next to the HTML (uses a local Chrome/Chromium)",
    )

    rec_p = sub.add_parser("record", help="Record golden fixtures from live tool calls")
    rec_p.add_argument("server_cmd", nargs="*")
    rec_p.add_argument("--url", default=None, help="Record from a running Streamable-HTTP server")
    rec_p.add_argument(
        "--era", choices=["auto", "modern", "legacy"], default="auto",
        help="Protocol era for the session: auto probes server/discover first "
             "(default: auto)",
    )
    rec_p.add_argument("--fixtures", default="fixtures", help="Output fixtures dir")
    rec_p.add_argument(
        "--include-destructive", action="store_true",
        help="Also record write/delete/exec-style tools (default: skip them)",
    )
    rec_p.add_argument(
        "--edge-cases", action="store_true",
        help="Baseline boundary inputs too (long strings, injection probes, empty strings)",
    )

    rep_p = sub.add_parser("replay", help="Replay fixtures and report drift (CI gate)")
    rep_p.add_argument("server_cmd", nargs="*")
    rep_p.add_argument("--url", default=None, help="Replay against a running Streamable-HTTP server")
    rep_p.add_argument(
        "--era", choices=["auto", "modern", "legacy"], default="auto",
        help="Protocol era for the session: auto probes server/discover first "
             "(default: auto)",
    )
    rep_p.add_argument("--fixtures", default="fixtures")

    plan_p = sub.add_parser("plan", help="Show which tools auto-baselining would call, and why")
    plan_p.add_argument("server_cmd", nargs="*")
    plan_p.add_argument("--url", default=None, help="Plan against a running Streamable-HTTP server")
    plan_p.add_argument(
        "--era", choices=["auto", "modern", "legacy"], default="auto",
        help="Protocol era for the session (default: auto)",
    )

    ins_p = sub.add_parser("inspect", help="Capture the server's contract manifest as JSON")
    ins_p.add_argument("server_cmd", nargs="*")
    ins_p.add_argument("--url", default=None, help="Inspect a running Streamable-HTTP server")
    ins_p.add_argument(
        "--era", choices=["auto", "modern", "legacy"], default="auto",
        help="Protocol era for the session (default: auto)",
    )
    ins_p.add_argument("--out", default="mcp-contract.json", help="Manifest output path")

    diff_p = sub.add_parser(
        "diff", help="Classify contract changes between two manifests (CI gate: exit 1 on BREAKING)"
    )
    diff_p.add_argument("baseline", help="Baseline manifest JSON (from `mcp-proof inspect`)")
    diff_p.add_argument("current", help="Current manifest JSON")
    diff_p.add_argument(
        "--fail-on", choices=["breaking", "any", "never"], default="breaking",
        help="Exit non-zero on this class of change (default: breaking)",
    )

    args = parser.parse_args(argv)
    if args.command != "diff" and bool(args.server_cmd) == bool(args.url):
        parser.error("provide either a server command (stdio) or --url (HTTP), not both/neither")

    from .runner import dispatch  # deferred: keeps --help fast

    return dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
