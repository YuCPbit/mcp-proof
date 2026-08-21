"""Schema-violating inputs: does the server enforce what it declares?

Each variant is a *verified-valid* baseline with exactly one field mutated
past a declared constraint — a minimal reproducer by construction. Both
halves of that claim are proven with ``jsonschema`` before a variant is
offered: the baseline must validate (otherwise the mutated field cannot be
shown to be what makes the candidate invalid) and the candidate must not.
If either proof fails, no variant is emitted — a TOOL-07 finding can never
be an artifact of sloppy generation. Deterministic, like the sampler.
"""

from jsonschema import Draft202012Validator

from .sampler import resolve, sample_args


def _violates(schema: dict, candidate: dict) -> bool:
    try:
        validator = Draft202012Validator(schema)
        return not validator.is_valid(candidate)
    except Exception:
        return False


def _constraint_breakers(spec: dict) -> list:
    """Values that overshoot one declared constraint of this property."""
    out: list = []
    stype = spec.get("type")
    max_len = spec.get("maxLength")
    if isinstance(max_len, int):
        out.append("x" * (max_len + 1))
    min_len = spec.get("minLength")
    if isinstance(min_len, int) and min_len > 0:
        out.append("x" * (min_len - 1))
    maximum = spec.get("maximum")
    if isinstance(maximum, int | float):
        out.append(maximum + 1)
    minimum = spec.get("minimum")
    if isinstance(minimum, int | float):
        out.append(minimum - 1)
    if isinstance(spec.get("enum"), list):
        out.append("__not_in_enum__")
    if isinstance(spec.get("pattern"), str):
        out.append("§§ no match §§")
    max_items = spec.get("maxItems")
    if isinstance(max_items, int) and isinstance(spec.get("items"), dict):
        out.append([sample_args(spec["items"]) or "x"] * (max_items + 1))
    # a type flip violates even fully-unconstrained declarations
    # (boolean gets an int: lax validators coerce "yes"-style strings)
    wrong_type = {
        "string": 12345, "integer": "not-a-number", "number": "not-a-number",
        "boolean": 12345, "array": "not-an-array", "object": "not-an-object",
    }.get(stype if isinstance(stype, str) else "")
    if wrong_type is not None:
        out.append(wrong_type)
    return out


def negative_variants(schema: dict, limit: int = 2) -> list[tuple[str, dict]]:
    """Up to ``limit`` verified-invalid argument sets: ``(case, args)``."""
    if not isinstance(schema, dict):
        return []
    base = sample_args(schema)
    try:
        if not Draft202012Validator(schema).is_valid(base):
            # an invalid baseline cannot prove that the single mutated field
            # is what makes the candidate invalid — no minimal reproducer
            return []
    except Exception:
        return []
    props = schema.get("properties")
    props = props if isinstance(props, dict) else {}
    required = [r for r in (schema.get("required") or []) if isinstance(r, str)]
    variants: list[tuple[str, dict]] = []

    for name in required:
        if name not in props or len(variants) >= limit:
            break
        spec = resolve(props[name], schema)
        for value in _constraint_breakers(spec):
            candidate = {**base, name: value}
            if _violates(schema, candidate):
                label = "oversized" if isinstance(value, str) and len(value) > 40 else repr(value)[:40]
                variants.append((f"{name}={label}", candidate))
                break

    if required and len(variants) < limit:
        candidate = {k: v for k, v in base.items() if k != required[0]}
        if _violates(schema, candidate):
            variants.append((f"missing required {required[0]!r}", candidate))

    return variants[:limit]
