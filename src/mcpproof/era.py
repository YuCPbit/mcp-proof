"""Protocol-era negotiation (2026-07-28, SEP-2575).

Modern servers advertise themselves through ``server/discover`` and expect
every request to carry the ``io.modelcontextprotocol/*`` envelope in
``params._meta``; legacy servers negotiate through the ``initialize``
handshake. Era selection mirrors the official client's ``auto`` mode —
``server/discover`` probed first, anything that is not positive modern
evidence falls back to the handshake — with one auditing difference: each
era attempt gets a fresh probe, so the server under test is never observed
on a connection perturbed by the negotiation itself (a dual-era server
locks a connection to the era of its first frame).

Wire facts cross-checked against the official SDK (mcp 2.0.0) and the
2026-07-28 changelog; the modern test server in tests/ is validated against
the official v2 client.
"""

from dataclasses import dataclass, field

from . import LATEST_SPEC

AUTO = "auto"
MODERN = "modern"
LEGACY = "legacy"

# Reserved _meta keys (basic/index "Per-request protocol fields")
PROTOCOL_VERSION_META_KEY = "io.modelcontextprotocol/protocolVersion"
CLIENT_CAPABILITIES_META_KEY = "io.modelcontextprotocol/clientCapabilities"
CLIENT_INFO_META_KEY = "io.modelcontextprotocol/clientInfo"
SERVER_INFO_META_KEY = "io.modelcontextprotocol/serverInfo"

# JSON-RPC error codes minted by the 2026-07-28 revision
UNSUPPORTED_PROTOCOL_VERSION = -32022
HEADER_MISMATCH = -32020

# Streamable HTTP request headers (SEP-2243), lowercase
MCP_METHOD_HEADER = "mcp-method"
MCP_NAME_HEADER = "mcp-name"

# method → params key whose value is mirrored into the Mcp-Name header
NAME_BEARING_METHODS = {"tools/call": "name", "prompts/get": "name", "resources/read": "uri"}

RESULT_TYPES = ("complete", "input_required")


def modern_envelope(revision: str, client_name: str, client_version: str) -> dict:
    """The ``params._meta`` object every modern request must carry."""
    return {
        PROTOCOL_VERSION_META_KEY: revision,
        CLIENT_CAPABILITIES_META_KEY: {},
        CLIENT_INFO_META_KEY: {"name": client_name, "version": client_version},
    }


@dataclass
class EraInfo:
    """What era detection learned; feeds both the checks and the report header."""

    era: str  # MODERN | LEGACY
    revision: str | None  # modern: selected revision · legacy: negotiated version
    discovery: str  # "server/discover" | "initialize"
    server_info: dict = field(default_factory=dict)
    capabilities: dict = field(default_factory=dict)
    supported_versions: list = field(default_factory=list)  # modern only
    raw_result: dict = field(default_factory=dict)  # the discover/initialize result object


def parse_discover_result(result: dict) -> EraInfo | None:
    """EraInfo from a server/discover result — None when the result is not
    positive modern evidence (mirrors the official denylist policy: a server
    that answers discover but advertises no mutually supported modern version
    is a legacy advertisement, not an incompatibility)."""
    if not isinstance(result, dict):
        return None
    supported = result.get("supportedVersions")
    if not isinstance(supported, list) or LATEST_SPEC not in supported:
        return None
    meta = result.get("_meta") if isinstance(result.get("_meta"), dict) else {}
    server_info = meta.get(SERVER_INFO_META_KEY)
    caps = result.get("capabilities")
    return EraInfo(
        era=MODERN,
        revision=LATEST_SPEC,
        discovery="server/discover",
        server_info=server_info if isinstance(server_info, dict) else {},
        capabilities=caps if isinstance(caps, dict) else {},
        supported_versions=[v for v in supported if isinstance(v, str)],
        raw_result=result,
    )
