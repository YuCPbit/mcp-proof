"""Render flagship effect-evidence reports from a full audit (observer + probe).

Two reports side by side — an honest server and one with a planted
response-invisible lie (silent-keymint: a read-only-annotated get_note that
secretly mints an API key). Both show the five things a reader needs: declared
annotations, observed effect, the evidence, the resulting objects, and where
authority/effectiveness was probed.

    python experiments/make_report.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import run_audit  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mcpproof.checks.effects import run_effect_checks  # noqa: E402
from mcpproof.effects.report import render_effect_report  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

_OBSERVER = "an out-of-band SQLite read of the server's state store"
_PROBE = "exercising each created credential against the server's real auth rule"


async def _one(name: str, mutations: list[str], out: Path) -> None:
    records, db = await run_audit(mutations, differential=True)
    try:
        checks = run_effect_checks(records)
        html = render_effect_report(
            f"saas-testbed ({name})", records, checks,
            observer_desc=_OBSERVER, probe_desc=_PROBE,
            mutations=mutations or None,
        )
        out.write_text(html, encoding="utf-8")
        verdict = ", ".join(f"{c.id}={c.status}" for c in checks)
        print(f"✓ {out.name}: {verdict}")
    finally:
        if os.path.exists(db):
            os.unlink(db)


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    asyncio.run(_one("honest", [], RESULTS / "effect-report-honest.html"))
    asyncio.run(_one("silent-keymint", ["silent-keymint"],
                     RESULTS / "effect-report-silent-keymint.html"))


if __name__ == "__main__":
    main()
