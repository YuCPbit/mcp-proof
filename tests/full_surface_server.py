"""Legacy-era (fastmcp) server advertising all three surfaces: tools,
resources and prompts. The capability-aware lanes must exercise each one
over the initialize handshake, not just over the modern era."""

from fastmcp import FastMCP

mcp = FastMCP("full-surface")


@mcp.tool()
def lookup(term: str) -> str:
    """Look up a term."""
    return f"definition of {term}"


@mcp.resource("demo://readme")
def readme() -> str:
    """A static text resource."""
    return "hello resource"


@mcp.prompt()
def summarize(topic: str) -> str:
    """Summarize a topic."""
    return f"Summarize {topic}"


if __name__ == "__main__":
    mcp.run()
