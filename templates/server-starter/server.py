"""Starter fastmcp server: passes the mcp-proof audit out of the box.

Copy this directory, rename the server, swap the in-memory data for your real
backend. README.md maps each practice here to the audit check it satisfies.
"""

import logging
import sys
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

# Logs go to stderr; stdout carries only JSON-RPC frames (HYG-01). Never print().
logging.basicConfig(
    stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
log = logging.getLogger("starter")

mcp = FastMCP("starter")

# Deterministic in-memory data so audits and recorded fixtures are reproducible.
_ORDERS: dict[str, dict[str, Any]] = {
    "ORD-100001": {"order_id": "ORD-100001", "status": "shipped", "items": 2, "total_usd": 84.00},
    "ORD-100002": {"order_id": "ORD-100002", "status": "processing", "items": 1, "total_usd": 19.50},
}
_FAQ: dict[str, str] = {
    "refund": "Refunds are available within 30 days of purchase.",
    "shipping": "Standard shipping takes 3-5 business days worldwide.",
    "warranty": "All hardware carries a two-year limited warranty.",
}


@mcp.tool
def lookup_order(
    order_id: Annotated[
        str,
        Field(
            description="Order identifier in the form ORD-######",
            pattern=r"^ORD-[0-9]{6}$",  # pattern + max_length land in inputSchema (SEC-04)
            max_length=10,
            examples=["ORD-100001"],  # a valid, existing ID: lets clients (and the audit) call it
        ),
    ],
) -> dict[str, Any]:
    """Look up one order by its ID and return status, item count and total."""
    log.info("lookup_order(%s)", order_id)
    order = _ORDERS.get(order_id)
    if order is None:
        # ToolError text is shown to the caller: actionable, and leaks nothing.
        raise ToolError(f"Unknown order ID {order_id!r}. Valid IDs look like ORD-100001.")
    return order


@mcp.tool
def search_faq(
    query: Annotated[str, Field(description="Free-text question", max_length=200)],
) -> str:
    """Search the FAQ and return the answer that best matches the query."""
    log.info("search_faq(%r)", query)
    words = {w.strip("?.,!").lower() for w in query.split()}
    for topic, answer in _FAQ.items():
        if topic in words:
            return answer
    return "No FAQ entry matches that question. Known topics: " + ", ".join(sorted(_FAQ))


@mcp.tool
def server_stats() -> dict[str, int]:
    """Report how many orders and FAQ topics this server currently holds."""
    return {"orders": len(_ORDERS), "faq_topics": len(_FAQ)}


if __name__ == "__main__":
    mcp.run()
