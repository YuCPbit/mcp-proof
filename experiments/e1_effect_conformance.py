"""E1 — Declared effect vs observed effect (annotation-lie detection).

Research question: can out-of-band effect observation detect tools whose
executed effect contradicts their declared MCP annotations, in cases where a
response-only auditor (current mcp-proof) and a metadata/name heuristic
cannot?

Independent variable: server variant — honest, and one per planted lie
(readOnly-writes, undeclared-delete, and three *response-invisible* lies where
a read-only-annotated tool secretly mints authority or writes).
Dependent variable: per-tool detection precision/recall for three detectors.
Oracle: the testbed's mutation ledger (mutations.lying_tools), independent of
the MCP surface.
Baselines: response_level (what the current response-level audit can see) and
name_heuristic (metadata only).
Failure condition: effect_aware does not beat the baselines on recall, or
raises false positives on the honest server (precision < 1).

A result strengthens the project if effect_aware reaches recall≈1 including
the response-invisible lies where the baselines are structurally blind; it
would show the feature is unnecessary if the response baseline already
catches every lie.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import DETECTORS, run_audit, score  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "testbed"))
from mutations import CATALOGUE_BY_NAME, LIE_TABLE, RESPONSE_INVISIBLE, lying_tools  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

# single-lie servers: the six effect-type lies (idempotency is EFF-03, tested
# separately). "honest" measures false positives.
LIES = ["lie-readonly", "hide-destructive", "webhook-readonly",
        "silent-keymint", "shadow-webhook", "phantom-write"]
ALL_TOOLS = list(CATALOGUE_BY_NAME)


async def _run() -> dict:
    variants = ["honest"] + LIES
    per_detector = {name: {"tp": 0, "fp": 0, "fn": 0} for name in DETECTORS}
    catch_table: dict[str, dict] = {}
    per_variant: list[dict] = []

    for variant in variants:
        muts = [] if variant == "honest" else [variant]
        records, db = await run_audit(muts, differential=False)
        try:
            positives = set(lying_tools(set(muts)))
            row = {"variant": variant, "positives": sorted(positives), "flagged": {}}
            for name, fn in DETECTORS.items():
                flagged = fn(records)
                row["flagged"][name] = sorted(flagged)
                tp = len(flagged & positives)
                fp = len(flagged - positives)
                miss = len(positives - flagged)
                per_detector[name]["tp"] += tp
                per_detector[name]["fp"] += fp
                per_detector[name]["fn"] += miss
            per_variant.append(row)
            if variant != "honest":
                tool = LIE_TABLE[variant][0]
                catch_table[variant] = {
                    "tool": tool,
                    "response_invisible": variant in RESPONSE_INVISIBLE,
                    "caught_by": [n for n, fn in DETECTORS.items() if tool in fn(records)],
                }
        finally:
            if os.path.exists(db):
                os.unlink(db)

    scores = {name: score(**counts) for name, counts in per_detector.items()}
    return {
        "experiment": "E1_declared_vs_observed_effect",
        "variants": per_variant,
        "catch_table": catch_table,
        "scores": scores,
        "n_tools_per_variant": len(ALL_TOOLS),
        "n_variants": len(variants),
    }


def _render_table(result: dict) -> str:
    lines = ["# E1 — declared effect vs observed effect\n"]
    lines.append("Detector precision/recall (aggregated over honest + 6 single-lie servers):\n")
    lines.append("| detector | precision | recall | F1 | TP | FP | FN |")
    lines.append("|---|---|---|---|---|---|---|")
    for name, s in result["scores"].items():
        lines.append(f"| {name} | {s['precision']} | {s['recall']} | {s['f1']} "
                     f"| {s['tp']} | {s['fp']} | {s['fn']} |")
    lines.append("\nPer-lie catch table (✓ = detector flagged the lying tool):\n")
    lines.append("| lie | tool | response-invisible | effect_aware | response_level | name_heuristic |")
    lines.append("|---|---|---|---|---|---|")
    def mark(name: str, caught: list) -> str:
        return "✓" if name in caught else "·"

    for lie, info in result["catch_table"].items():
        cb = info["caught_by"]
        inv = "yes" if info["response_invisible"] else "no"
        lines.append(f"| {lie} | {info['tool']} | {inv} | {mark('effect_aware', cb)} "
                     f"| {mark('response_level', cb)} | {mark('name_heuristic', cb)} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    result = asyncio.run(_run())
    (RESULTS / "e1_effect_conformance.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    table = _render_table(result)
    (RESULTS / "e1_effect_conformance.md").write_text(table, encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()
