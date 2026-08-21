__version__ = "0.7.1"

# Newest published MCP revision (modern era: server/discover, stateless _meta).
LATEST_SPEC = "2026-07-28"
# Newest revision the legacy initialize handshake can negotiate; the probes
# speak both eras (see era.py) and auto-detect which one a server lives in.
LATEST_LEGACY_SPEC = "2025-11-25"
KNOWN_SPECS = ["2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
