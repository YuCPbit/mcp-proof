"""Well-behaved demo MCP server: the audit's positive fixture."""

from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

mcp = FastMCP("docs-helper")

_notes: dict[str, str] = {}


@mcp.tool
def save_note(title: str, text: str) -> str:
    """Store a note under the given title, replacing any earlier text."""
    _notes[title] = text
    return f"Saved note '{title}' ({len(text)} chars)."


@mcp.tool
def get_note(title: str) -> str:
    """Return the text of a previously saved note."""
    if title not in _notes:
        raise ToolError(f"No note titled '{title}'.")
    return _notes[title]


@mcp.tool
def calc_sum(numbers: list[float]) -> float:
    """Sum a list of numbers and return the total."""
    return float(sum(numbers))


# max_length keeps the free-text param constrained (audit check SEC-04)
@mcp.tool
def search_docs(query: Annotated[str, Field(max_length=200)]) -> str:
    """Search the product docs and return the most relevant snippet."""
    return "Refund window is 30 days from purchase; see policy section 4.2."


if __name__ == "__main__":
    mcp.run()
