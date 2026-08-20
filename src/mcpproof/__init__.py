__version__ = "0.2.1"

# Newest published MCP revision (modern era: server/discover, stateless _meta).
LATEST_SPEC = "2026-07-28"
# Newest revision the legacy initialize handshake can negotiate. The probe
# speaks the handshake era; modern-era (server/discover) probing lands in v0.3.
LATEST_LEGACY_SPEC = "2025-11-25"
KNOWN_SPECS = ["2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
