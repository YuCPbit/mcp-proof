"""Replay recorded fixtures against a live server and classify drift.

Before anything is replayed, ``verify_fixture_set`` proves the fixture set
is the one that was recorded: manifest present and readable, every listed
fixture on disk, no duplicates or stale extras, every contract hash
recomputed and matching, the aggregate fingerprint intact. Any integrity
failure aborts the replay with ``FixtureIntegrityError`` — never drift
rows: a baseline that cannot be verified must not gate anything, because
drift measured against it would blame the target for the baseline's
problems (and with no trusted manifest order, stateful sequences would
replay in the wrong order and manufacture false drift).

Verdict ladder per fixture: ERROR (integrity / tool gone / call raised)
beats BREAKING (shape changed) beats VALUE (any observed value changed —
numbers, dates, negations, structured fields, non-text payloads, JSON text
values) beats COSMETIC (free-text differs, no value signal) beats OK.
Latency blowups are appended as extra LATENCY rows and never mask a
content verdict.
"""

import difflib
import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..errors import FixtureIntegrityError
from ..provenance import obj_hash
from .recorder import MANIFEST_NAME, SCHEMA_VERSION, normalize_response

NEGATION_TOKENS = ("not", "no", "never", "cannot", "can't", "won't", "isn't", "refused")

_DATE_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?"
)
_NUMBER_RE = re.compile(r"\$?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


@dataclass
class DriftResult:
    fixture: str
    tool: str
    kind: str
    detail: str


def _contract_of(fixture: dict) -> dict:
    return {"tool": fixture["tool"], "args": fixture["args"], "response": fixture["response"]}


def verify_fixture_set(
    fixtures_dir: Path, allow_legacy: bool = False
) -> tuple[list[Path], list[DriftResult]]:
    """Fail-closed integrity gate over a fixture set.

    Returns ``(paths to replay, integrity problems)``. Paths come back in
    manifest order (recording order — stateful sequences depend on it) and
    exclude anything that failed verification: a missing manifest, a listed
    fixture missing from disk, a fixture whose recomputed contract hash
    disagrees with its stored one — or that lacks a stored hash a v3+
    manifest requires it to have (deleting ``contract_sha256`` must not
    disarm the very check that would have caught the edit) — a manifest
    fingerprint that no longer matches the recorded contracts, duplicates,
    and stale extras all become ERROR rows.

    Legacy sets (manifest schema < 3) predate contract hashing entirely and
    can never be integrity-verified. By default that is itself an ERROR —
    re-record the baseline; ``allow_legacy`` opts in to replaying them with
    per-fixture and aggregate hash checks skipped. v3 manifests aggregated
    sorted hashes; v4 aggregates in recording order.
    """
    problems: list[DriftResult] = []
    on_disk = {
        p.name: p for p in sorted(fixtures_dir.glob("*.json")) if not p.name.startswith("_")
    }
    manifest_path = fixtures_dir / MANIFEST_NAME
    if not manifest_path.exists():
        problems.append(DriftResult(
            MANIFEST_NAME, "?", "ERROR",
            "manifest missing — fixture-set integrity and stateful replay order "
            "cannot be verified",
        ))
        return list(on_disk.values()), problems
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        listed = manifest["fixtures"]
        if not isinstance(listed, list):
            raise TypeError("manifest 'fixtures' is not a list")
    except Exception as exc:
        problems.append(DriftResult(
            MANIFEST_NAME, "?", "ERROR", f"manifest unreadable: {exc}",
        ))
        return list(on_disk.values()), problems

    manifest_version = manifest.get("schema_version")
    if isinstance(manifest_version, int) and manifest_version > SCHEMA_VERSION:
        problems.append(DriftResult(
            MANIFEST_NAME, "?", "ERROR",
            f"manifest schema_version {manifest_version} is newer than this mcp-proof "
            f"understands (≤{SCHEMA_VERSION}) — refusing to guess its semantics",
        ))
        return [], problems

    hashed_schema = isinstance(manifest_version, int) and manifest_version >= 3
    if not hashed_schema and not allow_legacy:
        problems.append(DriftResult(
            MANIFEST_NAME, "?", "ERROR",
            f"legacy fixture schema ({manifest_version!r}) predates contract hashing and "
            "cannot be integrity-verified — re-record the baseline with this mcp-proof, "
            "or pass --allow-legacy-fixtures to replay it without integrity checks",
        ))
        return [], problems

    for name in sorted(n for n, c in Counter(listed).items() if c > 1):
        problems.append(DriftResult(
            name, "?", "ERROR", "manifest lists this fixture more than once",
        ))
    duplicates = len(listed) != len(set(listed))

    ordered: list[Path] = []
    recomputed: list[str] = []
    hashes_verifiable = True
    seen: set[str] = set()
    for name in listed:
        if not isinstance(name, str) or name in seen:
            continue
        seen.add(name)
        path = on_disk.pop(name, None)
        if path is None:
            problems.append(DriftResult(
                name, "?", "ERROR", "manifest lists this fixture but it is missing on disk",
            ))
            hashes_verifiable = False
            continue
        try:
            fixture = json.loads(path.read_text(encoding="utf-8"))
            contract_hash = obj_hash(_contract_of(fixture))
        except Exception as exc:
            problems.append(DriftResult(name, "?", "ERROR", f"fixture unreadable: {exc}"))
            hashes_verifiable = False
            continue
        stored = fixture.get("contract_sha256")
        if stored is None:
            if hashed_schema:
                # deleting the hash must not disarm the check it feeds: an
                # unverifiable fixture inside a hashed set is treated exactly
                # like a tampered one (this was a real downgrade bypass)
                problems.append(DriftResult(
                    name, fixture.get("tool") or "?", "ERROR",
                    f"fixture lacks contract_sha256 but the manifest declares schema "
                    f"v{manifest_version} — integrity-stripped or hand-edited; a fixture "
                    "that cannot be verified is not replayed as truth",
                ))
                hashes_verifiable = False
                continue
            # pre-v3 fixture, replayed under an explicit --allow-legacy-fixtures
            hashes_verifiable = False
        elif stored != contract_hash:
            problems.append(DriftResult(
                name, fixture.get("tool") or "?", "ERROR",
                "contract_sha256 mismatch — fixture content was modified after "
                "recording; a tampered baseline is not replayed as truth",
            ))
            hashes_verifiable = False
            continue
        ordered.append(path)
        recomputed.append(contract_hash)

    for name in sorted(on_disk):
        problems.append(DriftResult(
            name, "?", "ERROR",
            "fixture on disk but not in the manifest — stale or foreign; not replayed "
            "(it would run outside the recorded call order)",
        ))

    declared = manifest.get("fixtures_sha256")
    if declared and hashes_verifiable and not duplicates:
        ordered_manifest = isinstance(manifest_version, int) and manifest_version >= 4
        expected = obj_hash(recomputed if ordered_manifest else sorted(recomputed))
        if expected != declared:
            problems.append(DriftResult(
                MANIFEST_NAME, "?", "ERROR",
                "manifest fixtures_sha256 does not match the recorded contracts — "
                "the manifest was modified after recording",
            ))
    return ordered, problems


async def replay(
    cmd: list[str] | None, fixtures_dir: str | Path, url: str | None = None,
    era: str = "auto", allow_legacy: bool = False,
) -> list[DriftResult]:
    """Raises FixtureIntegrityError (before the server is even launched)
    when the baseline fails verification — drift is only ever measured
    against a baseline that proved intact."""
    from .recorder import _session_ctx, list_all_tools

    fixtures_dir = Path(fixtures_dir)
    paths, problems = verify_fixture_set(fixtures_dir, allow_legacy=allow_legacy)
    if problems:
        raise FixtureIntegrityError(problems)
    results: list[DriftResult] = []
    async with await _session_ctx(cmd, url, era) as session:
        try:
            available = {t.name for t in await list_all_tools(session)}
        except Exception as exc:
            results.append(DriftResult(
                "tools/list", "?", "ERROR",
                f"could not enumerate live tools ({exc}) — replay aborted",
            ))
            return results
        for path in paths:
            try:
                fixture = json.loads(path.read_text(encoding="utf-8"))
                tool = fixture["tool"]
                args = fixture["args"]
                recorded = fixture["response"]
            except Exception as exc:
                results.append(DriftResult(path.name, "?", "ERROR", f"fixture unreadable: {exc}"))
                continue
            version = fixture.get("schema_version")
            version = version if isinstance(version, int) else 1
            if tool not in available:
                results.append(DriftResult(path.name, tool, "ERROR", "tool no longer exists"))
                continue
            start = time.perf_counter()
            try:
                result = await session.call_tool(tool, args)
            except Exception as exc:
                results.append(DriftResult(path.name, tool, "ERROR", f"call raised: {exc}"))
                continue
            latency_ms = int((time.perf_counter() - start) * 1000)
            results.append(
                _classify(path.name, tool, recorded, normalize_response(result), version)
            )
            observation = fixture.get("observation") or {}  # v3+; ≤v2 kept it top-level
            recorded_ms = int(observation.get("latency_ms", fixture.get("latency_ms", 0)) or 0)
            threshold = max(3 * recorded_ms, recorded_ms + 500)
            if latency_ms > threshold:
                results.append(
                    DriftResult(
                        path.name,
                        tool,
                        "LATENCY",
                        f"{latency_ms}ms vs recorded {recorded_ms}ms (threshold {threshold}ms)",
                    )
                )
    return results


def summarize(results: list[DriftResult]) -> dict:
    counts = {"ok": 0, "breaking": 0, "value": 0, "cosmetic": 0, "latency": 0, "error": 0}
    for r in results:
        key = r.kind.lower()
        if key in counts:
            counts[key] += 1
    # behaviour verdicts only: LATENCY rows are advisory extras, one fixture
    # can carry both a content verdict and a latency row
    counts["content_total"] = len(results) - counts["latency"]
    counts["gate_pass"] = not (counts["breaking"] or counts["value"] or counts["error"])
    return counts


def _classify(fixture: str, tool: str, old: dict, new: dict, version: int = SCHEMA_VERSION) -> DriftResult:
    if bool(old.get("is_error")) != bool(new.get("is_error")):
        return DriftResult(
            fixture,
            tool,
            "BREAKING",
            f"is_error flipped: {bool(old.get('is_error'))} → {bool(new.get('is_error'))}",
        )
    old_parts = old.get("content") or []
    new_parts = new.get("content") or []
    old_types = [p.get("type") for p in old_parts]
    new_types = [p.get("type") for p in new_parts]
    if old_types != new_types:
        return DriftResult(
            fixture, tool, "BREAKING", f"content parts changed: {old_types} → {new_types}"
        )
    part = _part_drift(old_parts, new_parts, strict=version >= 4)
    if part:
        return DriftResult(fixture, tool, "VALUE", part)
    structured = _structured_drift(old, new)
    if structured:
        kind, detail = structured
        return DriftResult(fixture, tool, kind, detail)
    old_text = _concat_text(old_parts)
    new_text = _concat_text(new_parts)
    structural = _json_structure_drift(old_text, new_text)
    if structural:
        return DriftResult(fixture, tool, "BREAKING", structural)
    json_value = _json_value_drift(old_text, new_text)
    if json_value:
        return DriftResult(fixture, tool, "VALUE", json_value)
    value = _value_drift(old_text, new_text)
    if value:
        return DriftResult(fixture, tool, "VALUE", value)
    if old_text == new_text:
        return DriftResult(fixture, tool, "OK", "")
    return DriftResult(fixture, tool, "COSMETIC", _diff_snippet(old_text, new_text))


def _concat_text(parts: list[dict]) -> str:
    return "\n".join(p.get("text", "") for p in parts if p.get("type") == "text")


def _short(value) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        rendered = repr(value)
    return rendered if len(rendered) <= 80 else rendered[:77] + "…"


def _part_drift(old_parts: list, new_parts: list, strict: bool) -> str | None:
    """Non-text content payloads (image/audio digests, embedded resources)
    compared field by field. ``strict`` for v4 fixtures which record every
    field; older fixtures only recorded the type, so only shared fields can
    be compared without inventing drift."""
    for i, (o, n) in enumerate(zip(old_parts, new_parts, strict=False)):
        if not isinstance(o, dict) or not isinstance(n, dict):
            continue
        if o.get("type") == "text":
            continue  # text payloads take the text/JSON ladder below
        keys = (set(o) | set(n)) if strict else (set(o) & set(n))
        for key in sorted(keys):
            if o.get(key) != n.get(key):
                return (
                    f"content[{i}] ({o.get('type')}): {key} changed: "
                    f"{_short(o.get(key))} → {_short(n.get(key))}"
                )
    return None


def _structured_drift(old: dict, new: dict) -> tuple[str, str] | None:
    if "structured" not in old:
        return None  # v1 fixture: structuredContent wasn't recorded, nothing to compare
    o, n = old.get("structured"), new.get("structured")
    if o == n:
        return None
    if (o is None) != (n is None):
        return "BREAKING", f"structuredContent presence changed: {o is not None} → {n is not None}"
    old_keys, new_keys = _key_paths(o), _key_paths(n)
    if old_keys != new_keys:
        return (
            "BREAKING",
            f"structuredContent keys changed: added {sorted(new_keys - old_keys)}, "
            f"removed {sorted(old_keys - new_keys)}",
        )
    # same shape, different content: structured fields are consumed by
    # programs, so ANY value change is VALUE — never "cosmetic". The date/
    # number/negation scan only enriches the detail message.
    from ..provenance import canonical_json

    old_json, new_json = canonical_json(o), canonical_json(n)
    value = _value_drift(old_json, new_json)
    if value:
        return "VALUE", "structuredContent: " + value
    path, desc = _first_leaf_diff(o, n)
    return "VALUE", f"structuredContent value changed at {path}: {desc}"


def _json_structure_drift(old_text: str, new_text: str) -> str | None:
    old_doc = _try_json(old_text)
    new_doc = _try_json(new_text)
    if old_doc is None and new_doc is None:
        return None
    if (old_doc is None) != (new_doc is None):
        return "response JSON-ness changed (one side is structured JSON, the other is not)"
    old_keys = _key_paths(old_doc)
    new_keys = _key_paths(new_doc)
    if old_keys != new_keys:
        added = sorted(new_keys - old_keys)
        removed = sorted(old_keys - new_keys)
        return f"JSON structure keys changed: added {added}, removed {removed}"
    return None


def _json_value_drift(old_text: str, new_text: str) -> str | None:
    """Text that parses as JSON is machine-consumed like structuredContent:
    any value change is VALUE, whatever the strings say."""
    old_doc = _try_json(old_text)
    new_doc = _try_json(new_text)
    if old_doc is None or new_doc is None or old_doc == new_doc:
        return None
    value = _value_drift(old_text, new_text)
    if value:
        return "JSON response: " + value
    path, desc = _first_leaf_diff(old_doc, new_doc)
    return f"JSON response value changed at {path}: {desc}"


def _first_leaf_diff(old, new, path: str = "") -> tuple[str, str]:
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            if old.get(key) != new.get(key):
                child = f"{path}.{key}" if path else str(key)
                return _first_leaf_diff(old.get(key), new.get(key), child)
    elif isinstance(old, list) and isinstance(new, list):
        for i, (a, b) in enumerate(zip(old, new, strict=False)):
            if a != b:
                return _first_leaf_diff(a, b, f"{path}[{i}]" if path else f"[{i}]")
        if len(old) != len(new):
            return path or "$", f"list length {len(old)} → {len(new)}"
    return path or "$", f"{_short(old)} → {_short(new)}"


def _try_json(text: str):
    try:
        doc = json.loads(text)
    except Exception:
        return None
    return doc if isinstance(doc, (dict, list)) else None


def _key_paths(doc, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(doc, dict):
        for key, val in doc.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            paths.add(path)
            paths |= _key_paths(val, path)
    elif isinstance(doc, list):
        for item in doc:
            paths |= _key_paths(item, f"{prefix}[]")
    return paths


def _value_drift(old_text: str, new_text: str) -> str | None:
    old_dates = _DATE_RE.findall(old_text)
    new_dates = _DATE_RE.findall(new_text)
    if old_dates != new_dates:
        for a, b in zip(old_dates, new_dates, strict=False):
            if a != b:
                return f"date changed: {a} → {b}"
        return f"dates changed: {old_dates} → {new_dates}"
    # strip dates first so their digit groups are not double-counted as numbers
    old_nums = _numbers(_DATE_RE.sub(" ", old_text))
    new_nums = _numbers(_DATE_RE.sub(" ", new_text))
    if [v for _, v in old_nums] != [v for _, v in new_nums]:
        for (old_tok, old_val), (new_tok, new_val) in zip(old_nums, new_nums, strict=False):
            if old_val != new_val:
                return f"number changed: {old_tok} → {new_tok}"
        return f"numbers changed: {[t for t, _ in old_nums]} → {[t for t, _ in new_nums]}"
    old_neg = _negations(old_text)
    new_neg = _negations(new_text)
    if old_neg != new_neg:
        return f"negation flip: {sorted(old_neg)} → {sorted(new_neg)}"
    return None


def _numbers(text: str) -> list[tuple[str, Decimal]]:
    # Decimal, not float: 9007199254740993 and ...92 must not compare equal
    out = []
    for token in _NUMBER_RE.findall(text):
        try:
            out.append((token, Decimal(token.lstrip("$").replace(",", ""))))
        except InvalidOperation:
            continue
    return out


def _negations(text: str) -> set[str]:
    lowered = text.lower()
    return {
        token
        for token in NEGATION_TOKENS
        if re.search(rf"\b{re.escape(token)}\b", lowered)
    }


def _diff_snippet(old_text: str, new_text: str, max_lines: int = 8) -> str:
    diff = difflib.unified_diff(
        old_text.splitlines(), new_text.splitlines(), "recorded", "replayed", lineterm=""
    )
    lines = [line[:120] for line in diff][:max_lines]
    return "\n".join(lines) or "whitespace-only change"
