"""Tiny fastmcp target for regression-lane tests.

Run with --drift to simulate a behavioral regression: the price changes
and the refund policy drops its negation.
"""

import sys

from fastmcp import FastMCP

mcp = FastMCP("regression-target")

DRIFT = "--drift" in sys.argv


@mcp.tool
def echo(text: str) -> str:
    return text


@mcp.tool
def price(item: str) -> str:
    return "Total: $45.00" if DRIFT else "Total: $42.00"


@mcp.tool
def policy(q: str) -> str:
    if DRIFT:
        return "Refunds are allowed after 30 days"
    return "Refunds are not allowed after 30 days"


@mcp.tool
def wipe_data(confirm: bool) -> str:
    """Delete all stored records permanently."""
    return "wiped"


if __name__ == "__main__":
    mcp.run()
