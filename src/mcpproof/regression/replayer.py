"""Replay recorded fixtures against a live server and classify drift.

Verdict ladder per fixture: ERROR (tool gone / call raised) beats
BREAKING (shape changed) beats VALUE (a number, date, or negation flipped)
beats COSMETIC (text differs, meaning-neutral) beats OK. Latency blowups
are appended as extra LATENCY rows and never mask a content verdict.
"""

import difflib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from ..client import open_session
from .recorder import normalize_response

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


def _replay_order(fixtures_dir: Path) -> list[Path]:
    """Manifest order == recording order; stateful call sequences depend on it."""
    on_disk = {p.name: p for p in fixtures_dir.glob("*.json") if not p.name.startswith("_")}
    manifest_path = fixtures_dir / "_manifest.json"
    if manifest_path.exists():
        try:
            listed = json.loads(manifest_path.read_text(encoding="utf-8"))["fixtures"]
            ordered = [on_disk.pop(name) for name in listed if name in on_disk]
            return ordered + [on_disk[n] for n in sorted(on_disk)]
        except Exception:
            pass
    return [on_disk[n] for n in sorted(on_disk)]


async def replay(
    cmd: list[str] | None, fixtures_dir: str | Path, url: str | None = None
) -> list[DriftResult]:
    from .recorder import _session_ctx

    fixtures_dir = Path(fixtures_dir)
    paths = _replay_order(fixtures_dir)
    results: list[DriftResult] = []
    async with _session_ctx(cmd, url) as session:
        listing = await session.list_tools()
        available = {t.name for t in listing.tools}
        for path in paths:
            try:
                fixture = json.loads(path.read_text(encoding="utf-8"))
                tool = fixture["tool"]
                args = fixture["args"]
                recorded = fixture["response"]
            except Exception as exc:
                results.append(DriftResult(path.name, "?", "ERROR", f"fixture unreadable: {exc}"))
                continue
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
            results.append(_classify(path.name, tool, recorded, normalize_response(result)))
            recorded_ms = int(fixture.get("latency_ms", 0) or 0)
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
    counts["gate_pass"] = not (counts["breaking"] or counts["value"] or counts["error"])
    return counts


def _classify(fixture: str, tool: str, old: dict, new: dict) -> DriftResult:
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
    structured = _structured_drift(old, new)
    if structured:
        kind, detail = structured
        return DriftResult(fixture, tool, kind, detail)
    old_text = _concat_text(old_parts)
    new_text = _concat_text(new_parts)
    structural = _json_structure_drift(old_text, new_text)
    if structural:
        return DriftResult(fixture, tool, "BREAKING", structural)
    value = _value_drift(old_text, new_text)
    if value:
        return DriftResult(fixture, tool, "VALUE", value)
    if old_text == new_text:
        return DriftResult(fixture, tool, "OK", "")
    return DriftResult(fixture, tool, "COSMETIC", _diff_snippet(old_text, new_text))


def _concat_text(parts: list[dict]) -> str:
    return "\n".join(p.get("text", "") for p in parts if p.get("type") == "text")


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
    from ..provenance import canonical_json

    old_json, new_json = canonical_json(o), canonical_json(n)
    value = _value_drift(old_json, new_json)
    if value:
        return "VALUE", "structuredContent: " + value
    return "COSMETIC", "structuredContent differs: " + _diff_snippet(old_json, new_json)


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
        for a, b in zip(old_dates, new_dates):
            if a != b:
                return f"date changed: {a} → {b}"
        return f"dates changed: {old_dates} → {new_dates}"
    # strip dates first so their digit groups are not double-counted as numbers
    old_nums = _numbers(_DATE_RE.sub(" ", old_text))
    new_nums = _numbers(_DATE_RE.sub(" ", new_text))
    if [v for _, v in old_nums] != [v for _, v in new_nums]:
        for (old_tok, old_val), (new_tok, new_val) in zip(old_nums, new_nums):
            if old_val != new_val:
                return f"number changed: {old_tok} → {new_tok}"
        return f"numbers changed: {[t for t, _ in old_nums]} → {[t for t, _ in new_nums]}"
    old_neg = _negations(old_text)
    new_neg = _negations(new_text)
    if old_neg != new_neg:
        return f"negation flip: {sorted(old_neg)} → {sorted(new_neg)}"
    return None


def _numbers(text: str) -> list[tuple[str, float]]:
    out = []
    for token in _NUMBER_RE.findall(text):
        try:
            out.append((token, float(token.lstrip("$").replace(",", ""))))
        except ValueError:
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
