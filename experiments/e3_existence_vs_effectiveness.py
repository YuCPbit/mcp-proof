"""E3 — Object existence vs current effectiveness after lifecycle events.

Research question: after a lifecycle event (grant revoked, key revoked, key
deleted, TTL expiry), does a minimal-impact exercise probe report an object's
true effectiveness where the two naive proxies — "it is still listed" and "its
authorizing grant is still active" — do not? The dangerous error is
false-ineffective: believing an object is neutralized when it still works
(residual authority).

Independent variable: lifecycle scenario. Dependent variable: each detector's
accuracy and false-effective / false-ineffective counts. Oracle: the
by-construction intended effectiveness per scenario, modelled on documented
real behaviour (a revoked grant leaving a minted key alive — GitLab #222829,
Midnight Blizzard). Baselines: existence (inventory) and delegation-centric
(access follows the grant). Failure condition: the probe shows no advantage —
every proxy already agrees with true effectiveness in every scenario.

The headline is scenario `grant_revoked`: the key stays effective though the
grant that authorized it is gone; the delegation-centric view calls it
neutralized (false-ineffective), the probe does not.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "testbed"))
sys.path.insert(0, str(_ROOT / "src"))

import saas_oracle as oracle  # noqa: E402
from effect_adapters import make_observer  # noqa: E402
from harness import PYTHON, SERVER  # noqa: E402

from mcpproof.client import open_session  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

# Each scenario: (event applier, ground-truth effectiveness, cascade server?,
#                 human description)
SCENARIOS = [
    ("no_event", None, True, False,
     "key minted under an active grant, nothing revoked"),
    ("grant_revoked", "revoke_grant", True, False,
     "the authorizing grant is revoked; the key still works (residual authority)"),
    ("key_revoked", "revoke_key", False, False,
     "the key itself is revoked; it is still listed but dead"),
    ("key_unlisted", "unlist_key", False, False,
     "the key row is deleted; not listed and dead"),
    ("ttl_expired", "expire", False, False,
     "the key's TTL has passed; still listed but dead"),
    ("grant_revoked_cascade", "revoke_grant", False, True,
     "grant revoked on a server that cascades; the key is dead"),
]


async def _run_scenario(name, event, truth_effective, cascade) -> dict:
    db = tempfile.mktemp(suffix=".db")
    cmd = [PYTHON, SERVER, "--db", db, "--grant", "grant_root"]
    if cascade:
        cmd += ["--cascade-revoke"]
    observer = make_observer(db)
    async with open_session(cmd) as session:
        await session.call_tool("create_api_key", {"label": "svc"})  # key_0001
    # apply the lifecycle event out-of-band (ground-truth state change)
    if event == "revoke_grant":
        oracle.revoke_grant(db, "grant_root")
    elif event == "revoke_key":
        oracle.revoke_credential(db, "api_keys", "key_0001")
    elif event == "unlist_key":
        oracle.unlist_credential(db, "api_keys", "key_0001")
    elif event == "expire":
        oracle.set_expiry(db, "api_keys", "key_0001", tick=1)
        oracle.advance_tick(db, to=5)

    snap = observer.snapshot()
    key_row = snap.get("api_keys", {}).get("key_0001")
    grant_row = snap.get("grants", {}).get("grant_root")

    # three predictors of "is the key currently effective?"
    listed = key_row is not None
    grant_active = grant_row is not None and grant_row.get("status") == "active"
    if key_row is not None:
        probe_status, probe_basis = oracle.exercise(db, "api_keys", key_row, cascade_grant=cascade)
    else:
        probe_status, probe_basis = "ineffective", "object not listed; nothing to exercise"

    predictions = {
        "existence": listed,                       # inventory: listed ⇒ effective
        "delegation_centric": grant_active,        # access follows the grant
        "probe": probe_status == "effective",      # actually exercise it
    }
    os.unlink(db)
    return {
        "scenario": name, "description": None,
        "truth_effective": truth_effective,
        "listed": listed, "grant_active": grant_active,
        "probe_status": probe_status, "probe_basis": probe_basis,
        "predictions": predictions,
    }


async def _run() -> dict:
    rows = []
    for name, event, truth, cascade, desc in SCENARIOS:
        r = await _run_scenario(name, event, truth, cascade)
        r["description"] = desc
        rows.append(r)

    detectors = ("existence", "delegation_centric", "probe")
    tally = {d: {"correct": 0, "false_effective": 0, "false_ineffective": 0} for d in detectors}
    for r in rows:
        truth = r["truth_effective"]
        for d in detectors:
            pred = r["predictions"][d]
            if pred == truth:
                tally[d]["correct"] += 1
            elif pred and not truth:
                tally[d]["false_effective"] += 1
            else:
                tally[d]["false_ineffective"] += 1
    n = len(rows)
    scores = {d: {**t, "accuracy": round(t["correct"] / n, 3)} for d, t in tally.items()}
    return {
        "experiment": "E3_existence_vs_effectiveness",
        "n_scenarios": n,
        "scenarios": rows,
        "scores": scores,
    }


def _render(result: dict) -> str:
    lines = ["# E3 — existence vs current effectiveness after lifecycle events\n"]
    lines.append("Detector accuracy and error types over the lifecycle scenarios "
                 "(false-ineffective = residual authority missed):\n")
    lines.append("| detector | accuracy | correct | false-effective | false-ineffective |")
    lines.append("|---|---|---|---|---|")
    for d, s in result["scores"].items():
        lines.append(f"| {d} | {s['accuracy']} | {s['correct']} | {s['false_effective']} "
                     f"| {s['false_ineffective']} |")
    lines.append("\nPer-scenario (truth = is the key actually effective):\n")
    lines.append("| scenario | truth | existence | delegation | probe | note |")
    lines.append("|---|---|---|---|---|---|")
    mk = lambda b: "eff" if b else "dead"  # noqa: E731
    for r in result["scenarios"]:
        p = r["predictions"]
        lines.append(f"| {r['scenario']} | {mk(r['truth_effective'])} | {mk(p['existence'])} "
                     f"| {mk(p['delegation_centric'])} | {mk(p['probe'])} | {r['description']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    result = asyncio.run(_run())
    (RESULTS / "e3_existence_vs_effectiveness.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    table = _render(result)
    (RESULTS / "e3_existence_vs_effectiveness.md").write_text(table, encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()
