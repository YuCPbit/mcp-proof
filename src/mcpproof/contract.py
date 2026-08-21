"""Contract manifest: the machine-readable surface an MCP server exposes.

``capture_manifest`` snapshots protocol identity, declared capabilities, and
the full (paginated) tools / resources / prompts listings. ``diff_manifests``
classifies what changed between two snapshots — BREAKING / ADDITIVE /
METADATA — forming the static half of the acceptance gate (record/replay is
the behavioural half).

Two fail-closed guarantees:

* volatile wire metadata is removed by **location**, never by key name —
  result-level fields (``nextCursor``, ``ttlMs``, ``cacheScope``,
  ``resultType``, ``_meta``) never enter the manifest because only the item
  lists are extracted, and the only key stripped from an item is its own
  top-level ``_meta``. A user's schema property that happens to be called
  ``ttlMs`` or ``nextCursor`` is contract and is preserved verbatim.
* an incomplete pagination walk (mid-walk failure, repeating cursor, page
  ceiling) aborts the capture — ``inspect`` refuses to freeze half a surface
  as if it were the whole baseline.
"""

from . import LATEST_SPEC
from .era import LEGACY, MODERN, parse_discover_result, sniff_era
from .pagination import PaginatedResult, collect_paginated
from .provenance import obj_hash

# v2: schema payloads preserved verbatim (volatile stripping is by wire
# location, not key name), plus the hashed `unserved` surface list.
MANIFEST_VERSION = 2

BREAKING = "BREAKING"
ADDITIVE = "ADDITIVE"
METADATA = "METADATA"

_SURFACES = (
    ("tools", "tools/list"),
    ("resources", "resources/list"),
    ("prompts", "prompts/list"),
)


def _strip_item(item):
    """Drop the item's own top-level ``_meta`` (wire metadata); everything
    below — inputSchema, outputSchema, annotations — is opaque contract."""
    if isinstance(item, dict):
        return {k: v for k, v in item.items() if k != "_meta"}
    return item


async def _list_surface(probe, method: str, key: str) -> PaginatedResult | None:
    """Every page of a list endpoint; None when the surface is not served
    (the first request errors out). A walk that starts but cannot finish
    comes back with ``complete=False`` for the caller to refuse."""
    try:
        first = await probe.request(method)
    except Exception:
        return None
    if first is None or not isinstance(first.get("result"), dict):
        return None

    async def fetch(cursor):
        try:
            resp = await probe.request(method, {"cursor": cursor} if cursor else None)
        except Exception:
            return None
        result = resp.get("result") if isinstance(resp, dict) else None
        return result if isinstance(result, dict) else None

    return await collect_paginated(fetch, key, first_page=first["result"])


def _probe_ctx(cmd: list[str] | None, url: str | None):
    if url:
        from .client_http import HttpProbe

        return HttpProbe(url)
    from .client import RawProbe

    return RawProbe(cmd)


async def capture_manifest(
    cmd: list[str] | None, url: str | None = None, era: str = "auto"
) -> dict:
    from datetime import UTC, datetime

    if era == "auto":
        era = await sniff_era(cmd, url)
    async with _probe_ctx(cmd, url) as probe:
        if era == MODERN:
            probe.enable_modern(LATEST_SPEC)
            resp = await probe.request("server/discover", {})
            result = resp.get("result") if isinstance(resp, dict) else None
            info = parse_discover_result(result) if isinstance(result, dict) else None
            if info is None:
                raise RuntimeError(f"server/discover failed: {(resp or {}).get('error', resp)}")
            capabilities = info.capabilities
            server = {"name": info.server_info.get("name"),
                      "version": info.server_info.get("version"),
                      "era": MODERN, "revision": info.revision}
        else:
            init = await probe.initialize()
            if init is None or "result" not in init:
                raise RuntimeError(
                    f"initialize failed: {(init or {}).get('error', 'no response')}"
                )
            result = init["result"] if isinstance(init["result"], dict) else {}
            capabilities = result.get("capabilities")
            capabilities = capabilities if isinstance(capabilities, dict) else {}
            server_info = result.get("serverInfo")
            server_info = server_info if isinstance(server_info, dict) else {}
            server = {"name": server_info.get("name"), "version": server_info.get("version"),
                      "era": LEGACY, "revision": result.get("protocolVersion")}

        surfaces: dict[str, list] = {}
        unserved: list[str] = []
        for key, method in _SURFACES:
            listed = await _list_surface(probe, method, key)
            if listed is None:
                surfaces[key] = []  # surface not served — recorded in `unserved`
                unserved.append(key)
                continue
            if not listed.complete:
                # fail closed: a partial listing frozen as "the baseline" would
                # make every later diff against the missing pages invisible
                raise RuntimeError(
                    f"{method} pagination incomplete ({listed.error}) — "
                    "refusing to write a partial contract manifest"
                )
            surfaces[key] = [_strip_item(x) for x in listed.items if isinstance(x, dict)]

    # `unserved` distinguishes "surface absent" from "surface served but
    # empty" — both used to collapse into []
    contract = {"capabilities": _strip_item(capabilities), "unserved": sorted(unserved), **surfaces}
    return {
        "manifest_version": MANIFEST_VERSION,
        "server": server,
        **contract,
        "contract_sha256": obj_hash(contract),
        # context, never hashed
        "observation": {
            "captured_at": datetime.now(UTC).isoformat(),
            "server_cmd": list(cmd) if cmd else ["--url", url],
        },
    }


# --------------------------------------------------------------- diffing ----


def _change(changes: list, level: str, ref: str, detail: str) -> None:
    changes.append({"level": level, "ref": ref, "detail": detail})


def diff_manifests(base: dict, current: dict) -> list[dict]:
    changes: list[dict] = []
    _diff_capabilities(base.get("capabilities") or {}, current.get("capabilities") or {}, changes)
    if "unserved" in base and "unserved" in current:  # both v2+: absent ≠ empty
        base_un, cur_un = set(base["unserved"] or []), set(current["unserved"] or [])
        for key in sorted(cur_un - base_un):
            _change(changes, BREAKING, f"surface {key}", "surface no longer served")
        for key in sorted(base_un - cur_un):
            _change(changes, ADDITIVE, f"surface {key}", "surface now served")
    _diff_named(base.get("tools") or [], current.get("tools") or [],
                "tool", "name", changes, _diff_tool)
    _diff_named(base.get("resources") or [], current.get("resources") or [],
                "resource", "uri", changes, _diff_resource)
    _diff_named(base.get("prompts") or [], current.get("prompts") or [],
                "prompt", "name", changes, _diff_prompt)
    return changes


def has_breaking(changes: list[dict]) -> bool:
    return any(c["level"] == BREAKING for c in changes)


def _diff_capabilities(old: dict, new: dict, changes: list) -> None:
    for cap in sorted(set(old) - set(new)):
        _change(changes, BREAKING, f"capabilities.{cap}", "capability removed")
    for cap in sorted(set(new) - set(old)):
        _change(changes, ADDITIVE, f"capabilities.{cap}", "capability added")
    for cap in sorted(set(old) & set(new)):
        if old[cap] != new[cap]:
            _change(changes, METADATA, f"capabilities.{cap}",
                    f"capability options changed: {old[cap]} → {new[cap]}")


def _diff_named(old: list, new: list, kind: str, id_key: str, changes: list, item_differ) -> None:
    olds = {i.get(id_key): i for i in old if i.get(id_key)}
    news = {i.get(id_key): i for i in new if i.get(id_key)}
    for name in sorted(set(olds) - set(news)):
        _change(changes, BREAKING, f"{kind} {name}", f"{kind} removed")
    for name in sorted(set(news) - set(olds)):
        _change(changes, ADDITIVE, f"{kind} {name}", f"{kind} added")
    for name in sorted(set(olds) & set(news)):
        item_differ(olds[name], news[name], f"{kind} {name}", changes)


def _diff_tool(old: dict, new: dict, ref: str, changes: list) -> None:
    # deliberately the same policy for input and output schemas: every rule
    # below is conservative in the caller's favour (tightening = BREAKING);
    # true consumer-compatibility variance for outputs is future work
    _diff_schema(f"{ref}.inputSchema", old.get("inputSchema"), new.get("inputSchema"), changes)
    _diff_schema(f"{ref}.outputSchema", old.get("outputSchema"), new.get("outputSchema"), changes)
    if (old.get("description") or "") != (new.get("description") or ""):
        _change(changes, METADATA, ref, "description changed")
    old_ann = old.get("annotations") or {}
    new_ann = new.get("annotations") or {}
    if old_ann != new_ann:
        # a tool quietly turning mutable is a safety contract change, not cosmetics
        if (old_ann.get("readOnlyHint") is True and new_ann.get("readOnlyHint") is not True) or (
            old_ann.get("destructiveHint") is not True and new_ann.get("destructiveHint") is True
        ):
            _change(changes, BREAKING, f"{ref}.annotations",
                    f"safety annotations weakened: {old_ann} → {new_ann}")
        else:
            _change(changes, METADATA, f"{ref}.annotations",
                    f"annotations changed: {old_ann} → {new_ann}")


def _diff_resource(old: dict, new: dict, ref: str, changes: list) -> None:
    if (old.get("mimeType") or "") != (new.get("mimeType") or ""):
        _change(changes, BREAKING, ref,
                f"mimeType changed: {old.get('mimeType')!r} → {new.get('mimeType')!r}")
    if (old.get("name") or "") != (new.get("name") or ""):
        _change(changes, METADATA, ref, "name changed")
    if (old.get("description") or "") != (new.get("description") or ""):
        _change(changes, METADATA, ref, "description changed")


def _diff_prompt(old: dict, new: dict, ref: str, changes: list) -> None:
    olds = {a.get("name"): a for a in old.get("arguments") or [] if isinstance(a, dict)}
    news = {a.get("name"): a for a in new.get("arguments") or [] if isinstance(a, dict)}
    for name in sorted(set(olds) - set(news)):
        _change(changes, BREAKING, f"{ref}.{name}", "prompt argument removed")
    for name in sorted(set(news) - set(olds)):
        level = BREAKING if news[name].get("required") else ADDITIVE
        _change(changes, level, f"{ref}.{name}",
                "required prompt argument added" if level == BREAKING else "optional prompt argument added")
    for name in sorted(set(olds) & set(news)):
        was, now = bool(olds[name].get("required")), bool(news[name].get("required"))
        if was != now:
            _change(changes, BREAKING if now else ADDITIVE, f"{ref}.{name}",
                    f"required changed: {was} → {now}")
    if (old.get("description") or "") != (new.get("description") or ""):
        _change(changes, METADATA, ref, "description changed")


_TIGHTEN = (  # (key, breaking when new value moves this way)
    ("maxLength", lambda o, n: n < o), ("minLength", lambda o, n: n > o),
    ("maximum", lambda o, n: n < o), ("minimum", lambda o, n: n > o),
    ("exclusiveMaximum", lambda o, n: n < o), ("exclusiveMinimum", lambda o, n: n > o),
    ("maxItems", lambda o, n: n < o), ("minItems", lambda o, n: n > o),
)


def _diff_schema(path: str, old, new, changes: list) -> None:
    if old == new:
        return
    if old is None:
        _change(changes, ADDITIVE, path, "schema declared")
        return
    if new is None:
        _change(changes, BREAKING, path, "schema removed")
        return
    if not (isinstance(old, dict) and isinstance(new, dict)):
        _change(changes, BREAKING, path, f"schema changed: {old!r} → {new!r}")
        return
    before = len(changes)

    if old.get("type") != new.get("type"):
        _change(changes, BREAKING, path, f"type changed: {old.get('type')} → {new.get('type')}")
    if old.get("const") != new.get("const") and ("const" in old or "const" in new):
        _change(changes, BREAKING, path, f"const changed: {old.get('const')!r} → {new.get('const')!r}")

    old_enum, new_enum = old.get("enum"), new.get("enum")
    if isinstance(old_enum, list) and isinstance(new_enum, list) and old_enum != new_enum:
        removed = [v for v in old_enum if v not in new_enum]
        added = [v for v in new_enum if v not in old_enum]
        if removed:
            _change(changes, BREAKING, path, f"enum values removed: {removed}")
        if added:
            _change(changes, ADDITIVE, path, f"enum values added: {added}")

    old_req = set(old.get("required") or [])
    new_req = set(new.get("required") or [])
    for name in sorted(new_req - old_req):
        _change(changes, BREAKING, f"{path}.{name}", "changed from optional to required")
    for name in sorted(old_req - new_req):
        _change(changes, ADDITIVE, f"{path}.{name}", "changed from required to optional")

    old_props = old.get("properties") if isinstance(old.get("properties"), dict) else {}
    new_props = new.get("properties") if isinstance(new.get("properties"), dict) else {}
    for name in sorted(set(old_props) - set(new_props)):
        _change(changes, BREAKING, f"{path}.{name}", "property removed")
    for name in sorted(set(new_props) - set(old_props)):
        if name not in new_req:  # newly-required already reported above
            _change(changes, ADDITIVE, f"{path}.{name}", "optional property added")
    for name in sorted(set(old_props) & set(new_props)):
        _diff_schema(f"{path}.{name}", old_props[name], new_props[name], changes)

    for key, tightened in _TIGHTEN:
        o, n = old.get(key), new.get(key)
        if o == n:
            continue
        if isinstance(o, int | float) and isinstance(n, int | float):
            level = BREAKING if tightened(o, n) else ADDITIVE
            verb = "tightened" if level == BREAKING else "loosened"
            _change(changes, level, path, f"{key} {verb}: {o} → {n}")
        elif o is None and n is not None:
            _change(changes, BREAKING, path, f"constraint added: {key}={n}")
        elif n is None and o is not None:
            _change(changes, ADDITIVE, path, f"constraint removed: {key} (was {o})")
    if old.get("pattern") != new.get("pattern"):
        _change(changes, BREAKING, path,
                f"pattern changed: {old.get('pattern')!r} → {new.get('pattern')!r}")
    if old.get("multipleOf") != new.get("multipleOf"):
        _change(changes, BREAKING, path,
                f"multipleOf changed: {old.get('multipleOf')!r} → {new.get('multipleOf')!r}")

    if isinstance(old.get("items"), dict) or isinstance(new.get("items"), dict):
        _diff_schema(f"{path}[]", old.get("items"), new.get("items"), changes)

    if len(changes) == before:
        # not equal, but nothing rule-worthy surfaced — never hide a change
        _change(changes, METADATA, path, "schema details changed")
