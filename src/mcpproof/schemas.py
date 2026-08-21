"""Shared JSON Schema traversal.

Three subsystems need to see through a tool's inputSchema — the argument
sampler, the negative-probe builder and the security lane. Before v0.7 each
had its own partial view (security looked one level deep and missed every
``$ref``/``allOf``/nested injection surface). This module is the one walker
they all consume.
"""

_MAX_REF_HOPS = 16
_MAX_WALK_DEPTH = 12
_MAX_PROPERTIES = 512  # runaway guard for pathological/self-referential schemas


def resolve(schema, root) -> dict:
    """Follow a local ``$ref`` (``#/...``) and merge ``allOf`` into one
    effective schema dict; anything unresolvable becomes ``{}``."""
    seen = 0
    while isinstance(schema, dict) and "$ref" in schema and seen < _MAX_REF_HOPS:
        ref = schema["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            return {k: v for k, v in schema.items() if k != "$ref"}
        target = root
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or part not in target:
                return {}
            target = target[part]
        extra = {k: v for k, v in schema.items() if k != "$ref"}
        schema = {**target, **extra} if isinstance(target, dict) else {}
        seen += 1
    if not isinstance(schema, dict):
        return {}
    subs = schema.get("allOf")
    if isinstance(subs, list) and subs:
        merged: dict = {k: v for k, v in schema.items() if k != "allOf"}
        for sub in subs:
            sub = resolve(sub, root)
            for k, v in sub.items():
                if k == "properties" and isinstance(v, dict):
                    props = dict(merged.get("properties") or {})
                    props.update(v)
                    merged["properties"] = props
                elif k == "required" and isinstance(v, list):
                    merged["required"] = sorted(set(merged.get("required") or []) | set(v))
                else:
                    merged.setdefault(k, v)
        schema = merged
    return schema


def iter_properties(schema, *, max_depth: int = _MAX_WALK_DEPTH):
    """Yield ``(path, effective_schema)`` for every named property reachable
    through local ``$ref``, ``allOf`` merges, nested objects, array items and
    ``anyOf``/``oneOf`` branches.

    Paths are dotted (``config.shell.command``), with ``[]`` marking array
    items. The same path can appear once per combinator branch; consumers
    that need uniqueness dedupe on it. Traversal is depth- and count-capped
    so self-referential schemas terminate.
    """
    if not isinstance(schema, dict):
        return
    budget = [_MAX_PROPERTIES]
    yield from _walk(schema, schema, "", max_depth, budget)


def _walk(node, root, path, depth, budget):
    if depth <= 0 or budget[0] <= 0 or not isinstance(node, dict):
        return
    eff = resolve(node, root)
    props = eff.get("properties")
    if isinstance(props, dict):
        for name, sub in props.items():
            if not isinstance(sub, dict) or budget[0] <= 0:
                continue
            sub_eff = resolve(sub, root)
            child = f"{path}.{name}" if path else str(name)
            budget[0] -= 1
            yield child, sub_eff
            yield from _walk(sub_eff, root, child, depth - 1, budget)
    items = eff.get("items")
    if isinstance(items, dict):
        yield from _walk(resolve(items, root), root, f"{path}[]" if path else "[]",
                         depth - 1, budget)
    for combinator in ("anyOf", "oneOf"):
        subs = eff.get(combinator)
        if isinstance(subs, list):
            for sub in subs:
                if isinstance(sub, dict):
                    yield from _walk(resolve(sub, root), root, path, depth - 1, budget)
