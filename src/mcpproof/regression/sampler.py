"""Deterministic argument synthesis from a tool's JSON Schema.

Recording needs the same args on every run, so sampling is rule-driven:
declared examples/default/enum win, otherwise a fixed value per type,
clamped to the schema's bounds. Unusable schemas yield {} rather than raise.
"""

import math

_MAX_DEPTH = 8
_STRING_SEED = "example"


def sample_args(schema: dict) -> dict:
    try:
        value = _sample(schema, _MAX_DEPTH)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _sample(schema, depth):
    if depth <= 0 or not isinstance(schema, dict):
        return {}
    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        return examples[0]
    if "default" in schema:
        return schema["default"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    for combinator in ("anyOf", "oneOf", "allOf"):
        subs = schema.get(combinator)
        if isinstance(subs, list) and subs:
            return _sample(subs[0], depth - 1)
    stype = schema.get("type")
    if isinstance(stype, list) and stype:
        stype = stype[0]
    if stype is None and isinstance(schema.get("properties"), dict):
        stype = "object"
    if stype == "string":
        return _sample_string(schema)
    if stype == "integer":
        return _sample_integer(schema)
    if stype == "number":
        return float(_clamp(1.5, schema))
    if stype == "boolean":
        return True
    if stype == "array":
        items = schema.get("items")
        return [_sample(items, depth - 1)] if isinstance(items, dict) else []
    if stype == "object":
        props = schema.get("properties")
        required = schema.get("required")
        out = {}
        if isinstance(props, dict) and isinstance(required, list):
            for name in required:
                if isinstance(name, str) and name in props:
                    out[name] = _sample(props[name], depth - 1)
        return out
    return {}


def _sample_string(schema) -> str:
    text = _STRING_SEED
    min_len = schema.get("minLength")
    if isinstance(min_len, int) and min_len > len(text):
        text = (text * (min_len // len(text) + 1))[:min_len]
    max_len = schema.get("maxLength")
    if isinstance(max_len, int) and 0 <= max_len < len(text):
        text = text[:max_len]
    return text


def _sample_integer(schema) -> int:
    value = 2
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if isinstance(minimum, (int, float)) and value < minimum:
        value = math.ceil(minimum)
    if isinstance(maximum, (int, float)) and value > maximum:
        value = math.floor(maximum)
    return int(value)


def _clamp(value, schema):
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if isinstance(minimum, (int, float)) and value < minimum:
        value = minimum
    if isinstance(maximum, (int, float)) and value > maximum:
        value = maximum
    return value
