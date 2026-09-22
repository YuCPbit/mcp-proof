"""Shared experiment harness: run an effect audit against a fresh SaaS testbed
instance, and the detectors/baselines the experiments compare.

Everything here is deterministic given the mutation set and plan. Each run
starts the SaaS server on a throwaway SQLite file, drives a fixed call plan
through a real MCP session, and returns the EffectRecords plus the server's
declared annotations. The three E1 detectors are pure functions over those
records, so all three read the *same* execution — the response-only baseline
and the effect observer never disagree because they saw different runs.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "testbed"))
sys.path.insert(0, str(_ROOT / "src"))

from effect_adapters import SaasLifecycle, SaasProbe, make_observer  # noqa: E402
from mutations import CATALOGUE_BY_NAME, annotations_for  # noqa: E402

from mcpproof.client import open_session  # noqa: E402
from mcpproof.effects.audit import run_effect_audit  # noqa: E402
from mcpproof.effects.model import (  # noqa: E402
    A_YES,
    E_CREATE,
    E_DELETE,
    E_UPDATE,
    EffectRecord,
)
from mcpproof.regression.recorder import is_destructive  # noqa: E402

PYTHON = str(_ROOT / ".venv" / "bin" / "python")
if not Path(PYTHON).exists():
    PYTHON = sys.executable
SERVER = str(_ROOT / "testbed" / "saas_server.py")

_WRITE = (E_CREATE, E_UPDATE, E_DELETE)
_DELETE_NAME = re.compile(r"\b(delete|remove|drop|purge|wipe|destroy|truncate)\b", re.I)
_RESPONSE_VERB = re.compile(
    r"\b(saved|stored|created|deleted|removed|revoked|registered|minted|updated|wrote|written)\b", re.I
)


def default_plan() -> list[tuple[str, dict]]:
    """One call per catalogue tool, ordered so prerequisites exist. Every tool
    gets at least one record, so any hidden effect has a chance to be seen."""
    return [
        ("save_note", {"title": "welcome", "body": "hello world"}),
        ("ping", {}),
        ("list_notes", {}),
        ("get_note", {"title": "welcome"}),
        ("create_api_key", {"label": "ci"}),
        ("create_webhook", {"url": "https://example.com/hook"}),
        ("create_share_link", {"title": "welcome"}),
        ("revoke_api_key", {"key_id": "key_0001"}),
        ("cleanup_notes", {}),
        ("delete_note", {"title": "welcome"}),
    ]


async def run_audit(
    mutations: list[str],
    plan: list[tuple[str, dict]] | None = None,
    *,
    grant: str = "grant_root",
    cascade: bool = False,
    differential: bool = True,
) -> tuple[list[EffectRecord], str]:
    """Run one effect audit against a fresh SaaS server. Returns (records, db_path).
    The db file is left on disk for the caller to inspect/clean."""
    plan = plan or default_plan()
    db = tempfile.mktemp(suffix=".db")
    cmd = [PYTHON, SERVER, "--db", db, "--grant", grant]
    if mutations:
        cmd += ["--mutate", *mutations]
    if cascade:
        cmd += ["--cascade-revoke"]
    declared = {n: annotations_for(n, set(mutations)) for n in CATALOGUE_BY_NAME}
    lifecycle = SaasLifecycle(db) if differential else None
    async with open_session(cmd) as session:
        records = await run_effect_audit(
            session, plan, make_observer(db),
            declared=declared, probe=SaasProbe(db, cascade_grant=cascade),
            lifecycle=lifecycle, session_grant=grant,
        )
    return records, db


# --------------------------------------------------------------------------
# E1 detectors — each returns the set of tools it flags as effect-inconsistent
# --------------------------------------------------------------------------


def detect_effect_aware(records: list[EffectRecord]) -> set[str]:
    """Flag a tool when an out-of-band state observation contradicts its
    declared effect semantics: a readOnly tool that wrote, a delete under an
    explicit destructiveHint=false claim (an unset hint defaults to true per
    the spec and is not a claim), or authority minted behind a readOnly
    claim."""
    flagged: set[str] = set()
    for r in records:
        ro = r.declared.get("readOnlyHint") is True
        de_false = r.declared.get("destructiveHint") is False
        deleted = (any(t.op == E_DELETE for t in r.targets)
                   or r.effect_type.value == E_DELETE)  # per-target, not headline
        if ro and r.effect_type.value in _WRITE:
            flagged.add(r.tool)
        elif deleted and de_false:
            flagged.add(r.tool)
        elif ro and r.authority_bearing.value == A_YES and r.effect_type.value == E_CREATE:
            flagged.add(r.tool)
    return flagged


def detect_response_level(records: list[EffectRecord]) -> set[str]:
    """The current-mcp-proof-style baseline: only the tool's RESPONSE is
    available (no external observation). Flag a readOnly tool whose response
    narrates a write, or a delete-verb response under an explicit
    destructiveHint=false claim (same spec-default semantics as the other
    detectors — absence is not a claim)."""
    flagged: set[str] = set()
    for r in records:
        ro = r.declared.get("readOnlyHint") is True
        de_false = r.declared.get("destructiveHint") is False
        verb = _RESPONSE_VERB.search(r.response_text or "")
        if ro and verb:
            flagged.add(r.tool)
        elif verb and re.search(r"\b(deleted|removed|revoked)\b", r.response_text or "", re.I) and de_false:
            flagged.add(r.tool)
    return flagged


def detect_name_heuristic(records: list[EffectRecord]) -> set[str]:
    """A metadata-only baseline: flag a tool whose NAME/description contradicts
    its annotations — readOnly claimed but a mutating-looking name, or a
    delete-looking name under an explicit destructiveHint=false claim. Never
    observes behaviour."""
    flagged: set[str] = set()
    for r in records:
        spec = CATALOGUE_BY_NAME.get(r.tool)
        desc = spec.description if spec else ""
        ro = r.declared.get("readOnlyHint") is True
        de_false = r.declared.get("destructiveHint") is False
        if ro and is_destructive(r.tool, desc):
            flagged.add(r.tool)
        elif _DELETE_NAME.search(f"{r.tool} {desc}") and de_false:
            flagged.add(r.tool)
    return flagged


DETECTORS = {
    "effect_aware": detect_effect_aware,
    "response_level": detect_response_level,
    "name_heuristic": detect_name_heuristic,
}


def score(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}
