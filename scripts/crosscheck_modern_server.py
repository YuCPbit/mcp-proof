"""Cross-validate the hand-rolled modern test server against the OFFICIAL v2 SDK client.

tests/modern_target_server.py implements the 2026-07-28 wire format from the
spec, with zero dependencies — this script proves that format is the real
one by driving it with the official mcp>=2 client in auto-negotiation mode:
discover must be adopted (modern era), tools listed, and a tool called.

The project venv pins mcp<2, so run this from any venv with the v2 SDK:

    python -m venv /tmp/mcp2 && /tmp/mcp2/bin/pip install "mcp>=2"
    /tmp/mcp2/bin/python scripts/crosscheck_modern_server.py

Not wired into CI (CI installs the pinned 1.x SDK); run it whenever the
modern server or the modern checks change.
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "tests" / "modern_target_server.py"


async def main() -> int:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client._probe import negotiate_auto
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        print(f"✗ this script needs the v2 SDK (pip install 'mcp>=2'): {exc}")
        return 2

    server_python = sys.argv[1] if len(sys.argv) > 1 else sys.executable
    params = StdioServerParameters(command=server_python, args=[str(SERVER)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await negotiate_auto(session)
            assert session.discover_result is not None, (
                "official client fell back to the legacy handshake — "
                "the hand-rolled server was not recognized as modern"
            )
            print("✓ official v2 client adopted the modern era via server/discover")

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            assert names == ["echo", "price"], names
            print(f"✓ tools/list under the official client: {names}")

            result = await session.call_tool("price", {"item": "widget"})
            text = "".join(c.text for c in result.content if c.type == "text")
            assert "$42.00" in text, text
            assert result.structured_content == {"total": 42.0, "currency": "USD"}, (
                result.structured_content
            )
            print(f"✓ tools/call price → {text!r}, structured {result.structured_content}")

            print("PASS: hand-rolled modern server speaks the official 2026-07-28 wire format")
            return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
