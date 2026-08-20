"""Tiny fastmcp target served over Streamable HTTP for transport tests.

Usage: python http_target_server.py <port>
"""

import sys

from fastmcp import FastMCP

mcp = FastMCP("http-target")


@mcp.tool
def echo(text: str) -> str:
    return text


@mcp.tool
def price(item: str) -> str:
    return "Total: $42.00"


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="127.0.0.1",
        port=int(sys.argv[1]),
        show_banner=False,
        log_level="warning",
    )
