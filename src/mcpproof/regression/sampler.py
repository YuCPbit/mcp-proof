"""Deterministic argument synthesis from a tool's JSON Schema.

Recording needs the same args on every run, so sampling is rule-driven, in
declaration-strength order: local ``$ref`` resolution → ``const`` →
``examples`` → ``default`` → ``enum`` → merged ``allOf`` → first
``anyOf``/``oneOf`` branch → type-based synthesis honouring ``pattern``,
``format``, length/bound/``multipleOf``/item-count constraints. Unusable
schemas yield ``{}`` rather than raise.

The rules are heuristics and can miss (an unmatched ``pattern``, conflicting
``allOf`` constraints, a ``oneOf`` branch constrained from outside), so
nothing downstream may trust a synthesized candidate blindly: callers that
are about to *call a live tool* or *prove a baseline valid* go through
``synthesize_valid_args``, which validates the candidate against the schema
itself and reports failure instead of shipping a known-invalid input.

Everything here is deterministic — same schema, same args, every run.
"""

import math
import re

from ..schemas import resolve

__all__ = ["resolve", "sample_args", "synthesize_valid_args"]

_MAX_DEPTH = 8

# tried in order against `pattern` until one matches (fullmatch)
_PATTERN_CANDIDATES = (
    "example", "test", "abc", "a", "A", "A1", "1", "123", "abc123",
    "2024-01-01", "user@example.com", "https://example.com", "1.0.0",
    "/tmp/example", "en", "true", "",
)

_FORMAT_SEEDS = {
    "date-time": "2024-01-01T00:00:00Z",
    "date": "2024-01-01",
    "time": "00:00:00Z",
    "email": "user@example.com",
    "idn-email": "user@example.com",
    "uri": "https://example.com/",
    "url": "https://example.com/",
    "uri-reference": "/example",
    "uuid": "00000000-0000-4000-8000-000000000000",
    "hostname": "example.com",
    "ipv4": "192.0.2.1",
    "ipv6": "2001:db8::1",
}


def sample_args(schema: dict) -> dict:
    try:
        value = _sample(schema, _MAX_DEPTH, schema)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def synthesize_valid_args(schema: dict) -> tuple[dict | None, str]:
    """``(args, "")`` when synthesis produced schema-valid arguments,
    ``(None, reason)`` otherwise.

    This is the fail-closed entry point: a candidate the sampler could not
    make valid is reported, never called — so a conformance finding or a
    recorded baseline can never be an artifact of sloppy generation.
    """
    from jsonschema import Draft202012Validator

    if not isinstance(schema, dict):
        return None, "inputSchema is not an object"
    args = sample_args(schema)
    try:
        validator = Draft202012Validator(schema)
        error = next(validator.iter_errors(args), None)
    except Exception as exc:
        return None, f"inputSchema does not compile: {exc}"
    if error is not None:
        return None, f"synthesized arguments do not satisfy the schema ({error.message})"
    return args, ""


def _sample(schema, depth, root):
    if depth <= 0:
        return {}
    schema = resolve(schema, root)
    if not schema:
        return {}
    if "const" in schema:
        return schema["const"]
    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        return examples[0]
    if "default" in schema:
        return schema["default"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    for combinator in ("anyOf", "oneOf"):
        subs = schema.get(combinator)
        if isinstance(subs, list) and subs:
            return _sample(subs[0], depth - 1, root)
    stype = schema.get("type")
    if isinstance(stype, list) and stype:
        stype = next((t for t in stype if t != "null"), stype[0])
    if stype is None and isinstance(schema.get("properties"), dict):
        stype = "object"
    if stype == "string":
        return _sample_string(schema)
    if stype == "integer":
        return _sample_integer(schema)
    if stype == "number":
        return _sample_number(schema)
    if stype == "boolean":
        return True
    if stype == "array":
        return _sample_array(schema, depth, root)
    if stype == "object":
        props = schema.get("properties")
        required = schema.get("required")
        out = {}
        if isinstance(props, dict) and isinstance(required, list):
            for name in required:
                if isinstance(name, str) and name in props:
                    out[name] = _sample(props[name], depth - 1, root)
        return out
    return {}


def _sample_string(schema) -> str:
    pattern = schema.get("pattern")
    if isinstance(pattern, str):
        try:
            compiled = re.compile(pattern)
        except re.error:
            compiled = None
        if compiled is not None:
            for candidate in _PATTERN_CANDIDATES:
                if compiled.fullmatch(candidate):
                    return candidate
            # no candidate matches this pattern — the returned seed is a known
            # miss; synthesize_valid_args catches it before anything is called
            return "example"
    fmt = schema.get("format")
    if isinstance(fmt, str) and fmt in _FORMAT_SEEDS:
        return _FORMAT_SEEDS[fmt]
    text = "example"
    min_len = schema.get("minLength")
    if isinstance(min_len, int) and min_len > len(text):
        text = (text * (min_len // len(text) + 1))[:min_len]
    max_len = schema.get("maxLength")
    if isinstance(max_len, int) and 0 <= max_len < len(text):
        text = text[:max_len]
    return text


def _bounds(schema) -> tuple[float | None, float | None]:
    lo = schema.get("minimum")
    hi = schema.get("maximum")
    exc_lo = schema.get("exclusiveMinimum")
    exc_hi = schema.get("exclusiveMaximum")
    if isinstance(exc_lo, int | float):
        lo = max(lo, exc_lo + 1e-9) if isinstance(lo, int | float) else exc_lo + 1e-9
    if isinstance(exc_hi, int | float):
        hi = min(hi, exc_hi - 1e-9) if isinstance(hi, int | float) else exc_hi - 1e-9
    return (lo if isinstance(lo, int | float) else None,
            hi if isinstance(hi, int | float) else None)


def _sample_integer(schema) -> int:
    lo, hi = _bounds(schema)
    value = 2
    if lo is not None and value < lo:
        value = math.ceil(lo)
    if hi is not None and value > hi:
        value = math.floor(hi)
    step = schema.get("multipleOf")
    if isinstance(step, int | float) and step > 0:
        value = int(math.ceil(value / step) * step)
        if hi is not None and value > hi:
            value = int(math.floor(hi / step) * step)
    return int(value)


def _sample_number(schema) -> float:
    lo, hi = _bounds(schema)
    value = 1.5
    if lo is not None and value < lo:
        value = float(lo)
    if hi is not None and value > hi:
        value = float(hi)
    step = schema.get("multipleOf")
    if isinstance(step, int | float) and step > 0:
        value = math.ceil(value / step) * step
        if hi is not None and value > hi:
            value = math.floor(hi / step) * step
    return float(value)


def _sample_array(schema, depth, root) -> list:
    items = schema.get("items")
    if not isinstance(items, dict):
        return []
    n = schema.get("minItems")
    n = n if isinstance(n, int) and n > 0 else 1
    max_items = schema.get("maxItems")
    if isinstance(max_items, int):
        n = min(n, max_items)
    element = _sample(items, depth - 1, root)
    return [element for _ in range(n)]
