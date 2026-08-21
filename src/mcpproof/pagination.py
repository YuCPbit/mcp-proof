"""One pagination discipline for every list surface.

Before v0.7 the project had four cursor walkers with three different page
ceilings and two different failure semantics; a violation on page 2 could
vanish from the audit entirely. This collector is the single source of
truth: it accumulates every page's items, detects repeating cursors,
enforces one ceiling, and reports an incomplete walk explicitly instead of
returning a silent subset. Consumers decide what "incomplete" means for
them (conformance: FAIL the pagination check; inspect/record: refuse to
write a partial baseline) — but none of them may treat a partial walk as
the whole surface.
"""

from dataclasses import dataclass, field

MAX_PAGES = 50


@dataclass
class PaginatedResult:
    """The outcome of walking one list endpoint.

    ``complete`` is True only when the walk reached a page with no
    ``nextCursor``. Anything else — a failed page, a repeating cursor, the
    page ceiling — leaves ``complete`` False with the reason in ``error``;
    ``items`` then holds what was collected before the anomaly, for
    evidence, never for use as "the full surface".
    """

    items: list = field(default_factory=list)
    pages: int = 0
    complete: bool = False
    error: str | None = None


async def collect_paginated(fetch, key: str, *, max_pages: int = MAX_PAGES,
                            first_page: dict | None = None) -> PaginatedResult:
    """Walk ``fetch(cursor)`` pages, accumulating ``result[key]`` items.

    ``fetch(cursor)`` returns the JSON-RPC *result object* for that page
    (cursor is None for the first page), or a non-dict to signal a failed
    page; exceptions it raises propagate to the caller unchanged. Items are
    accumulated unfiltered — malformed entries are a finding for the
    consumer, not something to launder away here. ``first_page`` lets a
    caller that already fetched page 1 (to judge availability) hand it in
    instead of fetching it twice.
    """
    out = PaginatedResult()
    seen: set = set()
    cursor = None
    pending_first = first_page
    while True:
        if pending_first is not None:
            page, pending_first = pending_first, None
        else:
            page = await fetch(cursor)
        if not isinstance(page, dict):
            out.error = f"page {out.pages + 1} failed (no response or error)"
            return out
        out.pages += 1
        raw = page.get(key)
        if isinstance(raw, list):
            out.items += raw
        cursor = page.get("nextCursor")
        if not cursor:
            out.complete = True
            return out
        if cursor in seen:
            out.error = (
                f"cursor repeats after {out.pages} page(s) — "
                "clients following it loop forever"
            )
            return out
        seen.add(cursor)
        if out.pages >= max_pages:
            out.error = f"more than {max_pages} page(s) — suspected unbounded pagination"
            return out
