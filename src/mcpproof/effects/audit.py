"""Drive a call plan, observe external state around every call, build records.

For each ``(tool, args)`` the audit snapshots external state before and after
the call (out-of-band), diffs the two, and assembles an EffectRecord whose
every field carries how it was known:

* effect_type / targets — observed from the state diff, not the response;
* persistence — observed: does a created object survive to the final snapshot;
* authority_bearing / effectiveness — probed: does exercising the object
  authorize an action;
* authorized_by — declared: the grant the session ran under;
* depends_on — probed differentially: revoke each candidate dependency, re-
  exercise, and keep only those whose removal actually disables the object.
  This is what separates 'authorized_by' from 'depends_on' — a key authorized
  by a grant but still effective after that grant is revoked does not depend
  on it.

No field is invented: with a NullProbe, authority/effectiveness/depends_on
stay ``unknown`` and downstream checks degrade to SKIP.
"""

from __future__ import annotations

from .model import (
    A_NO,
    A_UNKNOWN,
    A_YES,
    E_CREATE,
    E_DELETE,
    E_NONE,
    E_UPDATE,
    EFF_EFFECTIVE,
    EFF_INEFFECTIVE,
    EFF_UNKNOWN,
    HOW_DECLARED,
    HOW_OBSERVED,
    HOW_PROBED,
    HOW_UNKNOWN,
    EffectRecord,
    Evidenced,
    TargetRef,
)
from .observe import CREATE, DELETE, UPDATE, Observer
from .probes import EFFECTIVE, INEFFECTIVE, NOT_APPLICABLE, LifecycleController, NullProbe, Probe

# effect_type headline precedence when a call touches several objects
_PRECEDENCE = {E_CREATE: 3, E_DELETE: 2, E_UPDATE: 1, E_NONE: 0}
_OP_TO_EFFECT = {CREATE: E_CREATE, UPDATE: E_UPDATE, DELETE: E_DELETE}


async def run_effect_audit(
    session,
    plan: list[tuple[str, dict]],
    observer: Observer,
    *,
    declared: dict[str, dict] | None = None,
    probe: Probe | None = None,
    lifecycle: LifecycleController | None = None,
    session_grant: str | None = None,
) -> list[EffectRecord]:
    """Execute ``plan`` against ``session``, observing effects with ``observer``.

    ``declared`` maps tool name -> advertised annotations (from tools/list);
    when omitted the record's declared block is empty. ``probe`` exercises
    created objects; ``lifecycle`` enables differential depends_on probing.
    """
    probe = probe or NullProbe()
    declared = declared or {}
    records: list[EffectRecord] = []
    created_index: list[tuple[EffectRecord, TargetRef, dict | None]] = []

    for i, (tool, args) in enumerate(plan, 1):
        call_id = f"call#{i}:{tool}"
        before = observer.snapshot()
        response_text = ""
        try:
            result = await session.call_tool(tool, args)
            response_text = _response_text(result)
        except Exception:  # a raised call still gets a record (effects may have landed)
            response_text = ""
        after = observer.snapshot()
        deltas = observer.diff(before, after)

        rec = EffectRecord(call_id=call_id, tool=tool, args=args,
                            declared=dict(declared.get(tool, {})),
                            response_text=response_text)
        _fill_effect_type(rec, deltas)
        _fill_targets(rec, deltas)
        if any(d.op == CREATE for d in deltas):
            rec.created_via = call_id  # lineage: which call produced the object(s)
        if session_grant is not None and rec.effect_type.value == E_CREATE:
            rec.authorized_by = Evidenced(
                session_grant, HOW_DECLARED,
                f"creating call ran under session grant {session_grant!r}",
            )
        _fill_authority_and_effectiveness(rec, deltas, probe)
        records.append(rec)
        for d in deltas:
            if d.op == CREATE:
                created_index.append((rec, TargetRef(d.store, d.key), d.after))

    # persistence: a created object is persistent iff it survives to the final
    # snapshot (created-then-deleted within the plan is not persistent)
    final = observer.snapshot()
    _fill_persistence(created_index, final)

    # depends_on: differential probing, only for created authority objects and
    # only when a lifecycle controller can revoke/restore candidates
    if lifecycle is not None:
        _fill_depends_on(created_index, probe, lifecycle)

    return records


def _response_text(result) -> str:
    """Concatenate text parts of a tool result — what a response-level auditor
    would read. Accepts SDK objects (content list of parts) or dicts."""
    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")
    out: list[str] = []
    for part in content or []:
        text = getattr(part, "text", None)
        if text is None and isinstance(part, dict):
            text = part.get("text")
        if isinstance(text, str):
            out.append(text)
    return "\n".join(out)


def _fill_effect_type(rec: EffectRecord, deltas: list) -> None:
    if not deltas:
        rec.effect_type = Evidenced(
            E_NONE, HOW_OBSERVED, "no external object changed between before/after snapshots"
        )
        return
    headline = max((_OP_TO_EFFECT[d.op] for d in deltas), key=lambda e: _PRECEDENCE[e])
    summary = ", ".join(f"{d.op} {d.store}/{d.key}" for d in deltas[:6])
    rec.effect_type = Evidenced(headline, HOW_OBSERVED, f"observed {len(deltas)} change(s): {summary}")


def _fill_targets(rec: EffectRecord, deltas: list) -> None:
    rec.targets = [TargetRef(d.store, d.key, _OP_TO_EFFECT[d.op]) for d in deltas]


def _fill_persistence(created_index: list, final) -> None:
    for rec, target, _row in created_index:
        alive = target.key in final.get(target.store, {})
        rec.persistence = Evidenced(
            bool(alive), HOW_OBSERVED,
            f"{target.store}/{target.key} "
            + ("present in" if alive else "absent from") + " the final snapshot",
        )


def _fill_authority_and_effectiveness(rec: EffectRecord, deltas: list, probe: Probe) -> None:
    creates = [d for d in deltas if d.op == CREATE]
    if not creates:
        # nothing created → not an authority-bearing outcome to classify here
        rec.authority_bearing = Evidenced(
            A_NO, HOW_OBSERVED, "call created no object to bear authority"
        ) if rec.effect_type.value != E_NONE else Evidenced(
            A_NO, HOW_OBSERVED, "no object created"
        )
        return
    verdicts = []
    for d in creates:
        status, basis = probe.exercise(d.store, d.key, d.after)
        verdicts.append((d, status, basis))
    # authority: yes if any created object could be exercised as a credential
    if any(s == EFFECTIVE for _, s, _ in verdicts):
        d, _s, basis = next(v for v in verdicts if v[1] == EFFECTIVE)
        rec.authority_bearing = Evidenced(A_YES, HOW_PROBED, f"probe: {basis}")
        rec.effectiveness = Evidenced(EFF_EFFECTIVE, HOW_PROBED, f"probe: {basis}")
    elif all(s == NOT_APPLICABLE for _, s, _ in verdicts):
        _d, _s, basis = verdicts[0]
        rec.authority_bearing = Evidenced(A_NO, HOW_PROBED, f"probe: {basis}")
        rec.effectiveness = Evidenced(EFF_UNKNOWN, HOW_UNKNOWN, "not a credential; effectiveness n/a")
    elif any(s == INEFFECTIVE for _, s, _ in verdicts):
        # a credential-shaped object that does not currently authorize: it can
        # bear authority (it is that kind of object) but is not effective now
        _d, _s, basis = next(v for v in verdicts if v[1] == INEFFECTIVE)
        rec.authority_bearing = Evidenced(A_YES, HOW_PROBED, f"probe: {basis} (credential, not currently effective)")
        rec.effectiveness = Evidenced(EFF_INEFFECTIVE, HOW_PROBED, f"probe: {basis}")
    else:
        rec.authority_bearing = Evidenced(A_UNKNOWN, HOW_UNKNOWN, "probe inconclusive")


def _fill_depends_on(created_index: list, probe: Probe, lifecycle: LifecycleController) -> None:
    for rec, target, row in created_index:
        if rec.authority_bearing.value != A_YES:
            continue
        base_status, _ = probe.exercise(target.store, target.key, row)
        if base_status != EFFECTIVE:
            rec.depends_on = Evidenced(
                [], HOW_PROBED, "object not currently effective; no live dependency to probe"
            )
            continue
        candidates = lifecycle.candidate_dependencies(target.store, target.key, row)
        depends: list[str] = []
        notes: list[str] = []
        for cand in candidates:
            lifecycle.revoke(cand)
            try:
                status, _ = probe.exercise(target.store, target.key, row)
            finally:
                lifecycle.restore(cand)
            if status != EFFECTIVE:
                depends.append(cand)
                notes.append(f"revoking {cand} disables it")
            else:
                notes.append(f"survives revoking {cand}")
        rec.depends_on = Evidenced(
            depends, HOW_PROBED,
            "; ".join(notes) or "no candidate dependencies to probe",
        )
