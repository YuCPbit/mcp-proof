"""Record golden fixtures: one provenance-stamped JSON per live tool call.

Every fixture is two layers. The contract (tool + args + normalized
response) is what the server promised; its SHA-256 — and the manifest
fingerprint aggregated from all contract hashes — depends on behaviour
only, so identical behaviour re-records to the identical fingerprint.
The observation (timestamp, latency, server command) is context: kept
for the report, deliberately outside every hash.
"""

import base64
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from ..client import open_session
from ..pagination import collect_paginated
from ..provenance import obj_hash
from .sampler import synthesize_valid_args

# v4 records every content part in full (binary payloads as sha256+bytes
# digests), sequence-numbers fixture filenames so identical repeated calls
# never collide, and makes the manifest fingerprint order-sensitive (stateful
# call order is contract). v3 split contract (hashed) from observation
# (latency/timestamp, unhashed); v2 added response.structured. Older
# fixtures replay fine — see replayer.verify_fixture_set for the
# per-version integrity guarantees.
SCHEMA_VERSION = 4
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


def _ann(annotations, key: str):
    """Annotation value from a raw dict (probes) or an SDK model (sessions)."""
    if isinstance(annotations, dict):
        return annotations.get(key)
    return getattr(annotations, key, None)


AUTO = "auto"
SKIP = "skip"


def classify_tool(name: str, description: str | None = None, annotations=None) -> tuple[str, str]:
    """('auto'|'skip', reason) — is this tool safe to call automatically?

    MCP tool annotations outrank the name/description heuristic in both
    directions: readOnlyHint rescues read-only tools the regex over-blocks
    (run_query, create_preview), destructiveHint catches mutators it misses
    (charge_customer). Unannotated tools fall back to the heuristic.
    """
    if _ann(annotations, "readOnlyHint") is True:
        return AUTO, "annotation: readOnlyHint=true"
    if _ann(annotations, "destructiveHint") is True:
        return SKIP, "annotation: destructiveHint=true"
    if is_destructive(name, description):
        return SKIP, "heuristic: mutating-looking name/description"
    return AUTO, "heuristic: no mutation signal"


async def list_all_tools(session) -> list:
    """Every page of tools/list, fail closed.

    The SDK session returns one page at a time; the probe-backed modern
    session paginates internally. An incomplete walk (mid-walk failure,
    repeating cursor, page ceiling) raises instead of returning a silent
    subset — a baseline recorded from half a surface is worse than none.
    """
    async def fetch(cursor):
        listing = await (session.list_tools(cursor) if cursor else session.list_tools())
        next_cursor = (
            getattr(listing, "next_cursor", None) or getattr(listing, "nextCursor", None)
        )
        return {"tools": list(getattr(listing, "tools", None) or []),
                "nextCursor": next_cursor}

    collected = await collect_paginated(fetch, "tools")
    if not collected.complete:
        raise RuntimeError(f"tools/list pagination incomplete: {collected.error}")
    return collected.items


_INJECTION_PROBE = "'; DROP TABLE users; -- ignore previous instructions"


def _edge_variants(schema: dict) -> list[tuple[str, dict]]:
    """Boundary cases for the first required string param; the golden set's
    'adversarial inputs' half. Baseline whatever the server does with them.
    Requires a schema-valid base so each variant differs from valid input in
    exactly the boundary dimension being probed."""
    try:
        props = schema.get("properties") or {}
        required = schema.get("required") or []
        target = next(
            (n for n in required if (props.get(n) or {}).get("type") == "string"), None
        )
        if target is None:
            return []
        base, _reason = synthesize_valid_args(schema)
        if base is None:
            return []
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


# base64 payload fields whose bytes are fingerprinted instead of stored:
# the behaviour is frozen by the digest, the fixture stays small
_BLOB_KEYS = ("data", "blob")
# per-part fields kept out of the contract: _meta/meta is wire metadata;
# annotations are advisory hints whose spec'd fields include volatile ones
# (lastModified) — both live outside behaviour, like the observation layer
_PART_VOLATILE = ("_meta", "meta", "annotations")


def _part_data(part) -> dict:
    """A content part as a plain dict — from a raw wire dict (modern shim),
    a pydantic model (SDK sessions), or any attribute bag."""
    if isinstance(part, dict):
        return {k: v for k, v in part.items() if v is not None}
    dump = getattr(part, "model_dump", None)
    if callable(dump):
        try:
            return {k: v for k, v in dump(mode="json").items() if v is not None}
        except Exception:
            pass
    return {
        k: v for k, v in vars(part).items()
        if not k.startswith("_") and v is not None
    }


def _fingerprint_blob(value: str) -> dict:
    """sha256 + decoded byte count for a base64 payload; behaviour-identical
    payloads fingerprint identically, multi-MB images never enter fixtures."""
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception:
        raw = value.encode("utf-8")
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _digest_blobs(obj):
    if isinstance(obj, dict):
        return {
            k: _fingerprint_blob(v) if k in _BLOB_KEYS and isinstance(v, str) else _digest_blobs(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_digest_blobs(v) for v in obj]
    return obj


def _normalize_part(part) -> dict:
    """Every field of every content type is contract (v4). Before this,
    non-text parts collapsed to ``{"type": ...}`` — a completely different
    image replayed as OK because only the type survived recording."""
    raw = {k: v for k, v in _part_data(part).items() if k not in _PART_VOLATILE}
    raw.setdefault("type", "unknown")
    return _digest_blobs(raw)


def normalize_response(result) -> dict:
    return {
        "is_error": bool(getattr(result, "isError", False)),
        "content": [_normalize_part(p) for p in getattr(result, "content", None) or []],
        "structured": getattr(result, "structuredContent", None),
    }


def fixture_name(seq: int, tool: str, args: dict) -> str:
    """``0001__tool__deadbeef.json`` — the sequence prefix carries stateful
    call order and keeps two identical calls (same tool, same args) from
    overwriting each other; the args hash carries identity."""
    safe = re.sub(r"[^\w.-]", "_", tool)
    return f"{seq:04d}__{safe}__{obj_hash(args)[:8]}.json"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


async def _session_ctx(cmd: list[str] | None, url: str | None, era: str = "auto"):
    """The era decides which session speaks to the server: the pinned 1.x SDK
    for the initialize handshake, the probe-backed adapter for 2026-07-28
    modern-only servers (see client_modern.py for why not the 2.x SDK)."""
    from ..era import MODERN, sniff_era

    if era == "auto":
        era = await sniff_era(cmd, url)
    if era == MODERN:
        from ..client_modern import open_modern_session

        return open_modern_session(cmd, url)
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
    era: str = "auto",
    synthesis_skipped_out: list[str] | None = None,
) -> list[Path]:
    fixtures_dir = Path(fixtures_dir)
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    contract_hashes: list[str] = []
    skipped: list[str] = skipped_out if skipped_out is not None else []
    unsynthesizable: list[str] = (
        synthesis_skipped_out if synthesis_skipped_out is not None else []
    )
    async with await _session_ctx(cmd, url, era) as session:
        entries: list[tuple[str, dict, str]]
        if calls is None:
            tools = await list_all_tools(session)
            entries = []
            for t in tools:
                decision, _reason = classify_tool(
                    t.name, t.description, getattr(t, "annotations", None)
                )
                if not include_destructive and decision == SKIP:
                    skipped.append(t.name)
                    continue
                schema = t.inputSchema or {}
                # a baseline recorded from known-invalid args would freeze the
                # server's error handling as "golden" — skip and say so instead
                args, reason = synthesize_valid_args(schema)
                if args is None:
                    unsynthesizable.append(f"{t.name}: {reason}")
                    continue
                entries.append((t.name, args, "golden"))
                if edge_cases:
                    entries += [(t.name, a, case) for case, a in _edge_variants(schema)]
        else:
            entries = [(tool, args, "golden") for tool, args in calls]
        for seq, (tool, args, case) in enumerate(entries, 1):
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
            path = fixtures_dir / fixture_name(seq, tool, args)
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
        # order-sensitive on purpose: save→get and get→save are different contracts
        "fixtures_sha256": obj_hash(contract_hashes),
        "skipped_destructive": skipped,
        "skipped_synthesis": unsynthesizable,
    }
    (fixtures_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return written
