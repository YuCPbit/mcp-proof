"""E2 — Persistence vs authority-bearing state (classification validity).

Research question: does probe-backed classification separate authority-bearing
objects from ordinary persistent objects more accurately than the two naive
signals — "persistent ⇒ authority" and "the name looks like a credential"?

Independent variable: a corpus of created objects spanning four quadrants
(persistent×authority). Dependent variable: per-detector confusion matrix and
accuracy. Oracle: by-construction authority labels (saas_core.AUTHORITY_BEARING),
independent of the MCP surface. Baselines: persistence⇒authority, name-keyword.
Failure condition: the probe does not beat both baselines, or the corpus cannot
populate a quadrant (the distinction would then be academic).

Strengthens the project if the probe is correct where the baselines fail — a
persistent note named "api_key_backup" (fools name + persistence) and a
credential that is not persistent (fools persistence). Would show the
distinction is trivial if every detector agrees on every object.
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

import re  # noqa: E402

import saas_oracle as oracle  # noqa: E402
from effect_adapters import make_observer  # noqa: E402
from harness import PYTHON, SERVER  # noqa: E402

from mcpproof.client import open_session  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
_NAME_KEYWORD = re.compile(r"key|token|secret|webhook|share|api|credential", re.I)


def _classify_persistence(persistent: bool) -> bool:
    return persistent  # persistent ⇒ authority


def _classify_name(store: str, key: str, row: dict) -> bool:
    hay = f"{store} {key} {row.get('label','')} {row.get('url','')}"
    return bool(_NAME_KEYWORD.search(hay))


def _classify_probe_status(status: str) -> bool:
    # authority-bearing = the probe could exercise the object as a credential
    # at the time it existed (effective, or a credential that is now
    # revoked/expired but still IS one); a note is not_applicable → not authority
    return status in ("effective", "ineffective")


async def _run() -> dict:
    db = tempfile.mktemp(suffix=".db")
    cmd = [PYTHON, SERVER, "--db", db, "--grant", "grant_root"]
    observer = make_observer(db)

    # every created object with the REAL row observed at creation, and the
    # probe verdict taken then (while the object genuinely exists) — faithful,
    # not reconstructed
    created: list[dict] = []

    async def create_step(session, tool, args, note=""):
        before = observer.snapshot()
        await session.call_tool(tool, args)
        after = observer.snapshot()
        for d in observer.diff(before, after):
            if d.op == "create":
                status, _ = oracle.exercise(db, d.store, d.after)  # probe at creation time
                created.append({
                    "store": d.store, "key": d.key, "row": d.after,
                    "probe_status": status, "note": note,
                })

    async with open_session(cmd) as session:
        # persistent + authority
        await create_step(session, "create_api_key", {"label": "ci"})            # key_0001
        await create_step(session, "create_api_key", {"label": "revoked-soon"})  # key_0002
        await create_step(session, "create_webhook", {"url": "https://example.com/hook"})
        await create_step(session, "create_share_link", {"title": "welcome"})
        # persistent + non-authority
        await create_step(session, "save_note", {"title": "welcome", "body": "hi"})
        await create_step(session, "save_note", {"title": "api_key_backup",       # DECOY name
                                                 "body": "reminder: rotate keys"})
        # ephemeral + non-authority (created then deleted)
        await create_step(session, "save_note", {"title": "scratch", "body": "temp"},
                          note="ephemeral note (created, then deleted in-plan)")
        await session.call_tool("delete_note", {"title": "scratch"})
        # ephemeral + authority (a short-lived credential: minted then unlisted)
        await create_step(session, "create_api_key", {"label": "ephemeral"},      # key_0003
                          note="counterexample: credential minted then removed out-of-band — "
                               "authority without persistence")
        # out-of-band lifecycle: revoke key_0002 (still persistent, now
        # ineffective) and unlist key_0003 (a credential that does not persist)
        oracle.revoke_credential(db, "api_keys", "key_0002")
        oracle.unlist_credential(db, "api_keys", "key_0003")
        final = observer.snapshot()

    corpus: list[dict] = []
    for obj in created:
        store, key = obj["store"], obj["key"]
        truth = oracle.by_construction_authority(store)
        if truth is None:
            continue
        persistent = key in final.get(store, {})
        corpus.append({
            "store": store, "key": key, "persistent": persistent,
            "ground_truth_authority": bool(truth), "note": obj["note"]
            or ("decoy: credential-looking note name" if key == "api_key_backup" else ""),
            "pred": {
                "persistence": _classify_persistence(persistent),
                "name_keyword": _classify_name(store, key, obj["row"]),
                "probe": _classify_probe_status(obj["probe_status"]),
            },
        })

    os.unlink(db)

    detectors = ("persistence", "name_keyword", "probe")
    conf = {d: {"tp": 0, "fp": 0, "tn": 0, "fn": 0} for d in detectors}
    for obj in corpus:
        truth = obj["ground_truth_authority"]
        for d in detectors:
            pred = obj["pred"][d]
            if pred and truth:
                conf[d]["tp"] += 1
            elif pred and not truth:
                conf[d]["fp"] += 1
            elif not pred and not truth:
                conf[d]["tn"] += 1
            else:
                conf[d]["fn"] += 1
    scores = {}
    for d, c in conf.items():
        total = sum(c.values())
        correct = c["tp"] + c["tn"]
        scores[d] = {**c, "accuracy": round(correct / total, 3) if total else 0.0}
    return {
        "experiment": "E2_persistence_vs_authority",
        "n_objects": len(corpus),
        "corpus": corpus,
        "confusion": scores,
    }


def _render(result: dict) -> str:
    lines = ["# E2 — persistence vs authority-bearing state\n"]
    lines.append(f"Corpus: {result['n_objects']} objects across the persistent×authority quadrants.\n")
    lines.append("| detector | accuracy | TP | FP | TN | FN |")
    lines.append("|---|---|---|---|---|---|")
    for d, s in result["confusion"].items():
        lines.append(f"| {d} | {s['accuracy']} | {s['tp']} | {s['fp']} | {s['tn']} | {s['fn']} |")
    lines.append("\nPer-object predictions (T=authority-bearing):\n")
    lines.append("| object | persistent | truth | persistence | name | probe | note |")
    lines.append("|---|---|---|---|---|---|---|")
    mk = lambda b: "T" if b else "F"  # noqa: E731
    for o in result["corpus"]:
        p = o["pred"]
        lines.append(f"| {o['store']}/{o['key']} | {mk(o['persistent'])} | {mk(o['ground_truth_authority'])} "
                     f"| {mk(p['persistence'])} | {mk(p['name_keyword'])} | {mk(p['probe'])} | {o['note']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    result = asyncio.run(_run())
    (RESULTS / "e2_persistence_vs_authority.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    table = _render(result)
    (RESULTS / "e2_persistence_vs_authority.md").write_text(table, encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()
