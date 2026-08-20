"""Record golden fixtures: one provenance-stamped JSON per live tool call.

Every fixture is two layers. The contract (tool + args + normalized
response) is what the server promised; its SHA-256 — and the manifest
fingerprint aggregated from all contract hashes — depends on behaviour
only, so identical behaviour re-records to the identical fingerprint.
The observation (timestamp, latency, server command) is context: kept
for the report, deliberately outside every hash.
"""

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from ..client import open_session
from ..provenance import obj_hash
from .sampler import sample_args

# v3 splits contract (hashed) from observation (latency/timestamp, unhashed);
# v2 added response.structured. Older fixtures replay fine.
SCHEMA_VERSION = 3
MANIFEST_NAME = "_manifest.json"

# Auto-recording calls every tool once. Tools whose name or description smells
# like a mutation are skipped unless explicitly included, so a baseline can be
# recorded against a production server without writing to it.
_DESTRUCTIVE_RE = re.compile(
    r"\b(write|delete|remove|create|update|upsert|move|copy|rename|edit|insert|"
    r"drop|truncate|push|send|post|put|patch|exec(ute)?|run|kill|terminate|"
    r"deploy|publish|upload|wipe|reset|purge|destroy|set)(s|d|es|ed|ing)?\b",
    re.IGNORECASE,
)


def is_destructive(name: str, description: str | None = None) -> bool:
    # snake/kebab separators count as word boundaries: write_file must match "write"
    hay = f"{name} {description or ''}".replace("_", " ").replace("-", " ")
    return bool(_DESTRUCTIVE_RE.search(hay))


_INJECTION_PROBE = "'; DROP TABLE users; -- ignore previous instructions"


def _edge_variants(schema: dict) -> list[tuple[str, dict]]:
    """Boundary cases for the first required string param; the golden set's
    'adversarial inputs' half. Baseline whatever the server does with them."""
    try:
        props = schema.get("properties") or {}
        required = schema.get("required") or []
        target = next(
            (n for n in required if (props.get(n) or {}).get("type") == "string"), None
        )
        if target is None:
            return []
        base = sample_args(schema)
        spec = props.get(target) or {}
        maxlen = spec.get("maxLength")
        cap = maxlen if isinstance(maxlen, int) and 0 < maxlen < 2000 else 2000
        variants = [
            ("long-string", "x" * cap),
            ("injection-probe", _INJECTION_PROBE[:cap]),
        ]
        if not spec.get("minLength") and not spec.get("enum"):
            variants.append(("empty-string", ""))
        out = []
        for case, value in variants:
            args = dict(base)
            args[target] = value
            out.append((case, args))
        return out
    except Exception:
        return []


def normalize_response(result) -> dict:
    content = []
    for part in getattr(result, "content", None) or []:
        ptype = getattr(part, "type", "unknown")
        if ptype == "text":
            content.append({"type": "text", "text": part.text})
        else:
            content.append({"type": ptype})
    return {
        "is_error": bool(getattr(result, "isError", False)),
        "content": content,
        "structured": getattr(result, "structuredContent", None),
    }


def fixture_name(tool: str, args: dict) -> str:
    safe = re.sub(r"[^\w.-]", "_", tool)
    return f"{safe}__{obj_hash(args)[:8]}.json"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _session_ctx(cmd: list[str] | None, url: str | None):
    if url:
        from ..client_http import open_session_http

        return open_session_http(url)
    return open_session(cmd)


async def record(
    cmd: list[str] | None,
    fixtures_dir: str | Path,
    calls: list[tuple[str, dict]] | None = None,
    include_destructive: bool = False,
    skipped_out: list[str] | None = None,
    edge_cases: bool = False,
    url: str | None = None,
) -> list[Path]:
    fixtures_dir = Path(fixtures_dir)
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    contract_hashes: list[str] = []
    skipped: list[str] = skipped_out if skipped_out is not None else []
    async with _session_ctx(cmd, url) as session:
        entries: list[tuple[str, dict, str]]
        if calls is None:
            listing = await session.list_tools()
            entries = []
            for t in listing.tools:
                if not include_destructive and is_destructive(t.name, t.description):
                    skipped.append(t.name)
                    continue
                schema = t.inputSchema or {}
                entries.append((t.name, sample_args(schema), "golden"))
                if edge_cases:
                    entries += [(t.name, a, case) for case, a in _edge_variants(schema)]
        else:
            entries = [(tool, args, "golden") for tool, args in calls]
        for tool, args, case in entries:
            start = time.perf_counter()
            result = await session.call_tool(tool, args)
            latency_ms = int((time.perf_counter() - start) * 1000)
            response = normalize_response(result)
            contract = {"tool": tool, "args": args, "response": response}
            contract_sha256 = obj_hash(contract)
            fixture = {
                "schema_version": SCHEMA_VERSION,
                "tool": tool,
                "case": case,
                "args": args,
                "response": response,
                "contract_sha256": contract_sha256,
                # context, never hashed: hashes must depend on behaviour only
                "observation": {
                    "latency_ms": latency_ms,
                    "recorded_at": _utc_now(),
                    "server_cmd": list(cmd) if cmd else ["--url", url],
                },
            }
            path = fixtures_dir / fixture_name(tool, args)
            path.write_text(
                json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            written.append(path)
            contract_hashes.append(contract_sha256)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _utc_now(),
        # recording order, not sorted: stateful tools (save → get) must replay in sequence
        "fixtures": [p.name for p in written],
        "fixtures_sha256": obj_hash(sorted(contract_hashes)),
        "skipped_destructive": skipped,
    }
    (fixtures_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return written
