"""Effect-conformance checks: declared annotations vs observed external effects.

Consumes the EffectRecords built by effects.audit (out-of-band observation +
probes) and emits CheckResults in the same PASS/FAIL/WARN/SKIP vocabulary the
rest of the report speaks. The comparison is per record: what the tool
declared (readOnlyHint / destructiveHint / idempotentHint) against what an
independent observer saw it do to the world, and what a probe found the result
to be worth.

The comparison follows the spec's annotation semantics exactly. Defaults are
pessimistic (an unannotated tool is assumed non-read-only, possibly
destructive, non-idempotent), so an ABSENT hint is never a contradiction —
only an explicit claim the observed effect falsifies is. And destructiveHint /
idempotentHint are meaningful only when readOnlyHint is false: a readOnly-
declared tool that writes is EFF-01's finding alone, never double-counted.

Evidence discipline carries over: a dimension no channel could establish is
SKIP with the reason, never a silent PASS. Every FAIL/WARN quotes the observed
delta or the probe basis that produced it.

Check set (kept small and non-overlapping):
  EFF-01 (MUST)   readOnlyHint honoured — no observed write under readOnly=true
  EFF-02 (MUST)   observed deletes consistent with destructiveHint — an explicit
                  destructiveHint=false contradicted by an observed delete fails;
                  an unset hint falls back to the spec default (true) and passes
  EFF-03 (SHOULD) idempotent honoured — a repeated identical call is a no-op
  EFF-06 (SHOULD) no residual authority by default — a created authority object
                  still depends on the grant that authorized it
The per-object effect/authority evidence itself is rendered from the records
(see report), not folded into a pass/fail.
"""

from __future__ import annotations

from ..effects.model import (
    A_YES,
    E_CREATE,
    E_DELETE,
    E_UPDATE,
    HOW_PROBED,
    EffectRecord,
)
from ..provenance import canonical_json
from .base import FAIL, MUST, PASS, SHOULD, SKIP, WARN, CheckResult

_WRITE_EFFECTS = (E_CREATE, E_UPDATE, E_DELETE)

_EFF_META: dict[str, tuple[str, str, str]] = {
    "EFF-01": (
        "readOnlyHint is honoured (no observed external write)",
        MUST,
        "A tool annotated readOnlyHint=true must not create, update or delete "
        "external state; remove the annotation or stop the write.",
    ),
    "EFF-02": (
        "observed deletes are consistent with destructiveHint "
        "(explicit false contradicted ⇒ fail; unset ⇒ spec default true)",
        MUST,
        "A tool that deletes external state must not declare destructiveHint=false; "
        "declare it true (or leave it unset — the spec default is true) so hosts gate it.",
    ),
    "EFF-03": (
        "idempotentHint is honoured (a repeated identical call is a no-op)",
        SHOULD,
        "A tool annotated idempotentHint=true must leave external state unchanged "
        "when called again with identical arguments.",
    ),
    "EFF-06": (
        "created authority does not outlive its authorizing grant",
        SHOULD,
        "An object minted under a grant should stop working when that grant is "
        "revoked; a probe found it still effective, so revocation of the "
        "delegation will not disable it (residual authority).",
    ),
}


def _res(check_id: str, status: str, evidence: str = "") -> CheckResult:
    title, level, fix = _EFF_META[check_id]
    return CheckResult(id=check_id, title=title, level=level, status=status,
                       evidence=evidence, fix_hint=fix)


def _read_only(rec: EffectRecord) -> bool:
    return rec.declared.get("readOnlyHint") is True


def _deleted_targets(rec: EffectRecord) -> list[str]:
    """Every object this call deleted, read from the per-target ops — NOT from
    the headline effect_type, whose precedence keeps only the strongest op. A
    call that creates one object and deletes another (a move, a rotate) has
    headline `create` yet absolutely performed a delete; found for real by the
    filesystem-server case study (move_file), where the headline-only version
    of this check was blind to the deleted source path."""
    ops = [f"{t.store}/{t.key}" for t in rec.targets if t.op == E_DELETE]
    if not ops and rec.effect_type.value == E_DELETE:
        # legacy/hand-built records without per-target ops: trust the headline
        ops = [f"{t.store}/{t.key}" for t in rec.targets] or ["(unattributed delete)"]
    return ops


def _declares_non_destructive(rec: EffectRecord) -> bool:
    """Only an EXPLICIT destructiveHint=false claims 'additive updates only'.
    An unset hint defaults to true per the spec (pessimistic), so absence can
    never be contradicted by an observed delete."""
    return rec.declared.get("destructiveHint") is False


def _idempotent(rec: EffectRecord) -> bool:
    return rec.declared.get("idempotentHint") is True


def run_effect_checks(records: list[EffectRecord]) -> list[CheckResult]:
    return [
        _eff01(records),
        _eff02(records),
        _eff03(records),
        _eff06(records),
    ]


def _eff01(records: list[EffectRecord]) -> CheckResult:
    scoped = [r for r in records if _read_only(r)]
    if not scoped:
        return _res("EFF-01", SKIP, "no exercised tool declared readOnlyHint=true")
    offenders = [
        f"{r.tool} declared readOnly but {r.effect_type.evidence}"
        for r in scoped if r.effect_type.value in _WRITE_EFFECTS
    ]
    if offenders:
        return _res("EFF-01", FAIL, "; ".join(offenders))
    return _res("EFF-01", PASS,
                f"{len(scoped)} readOnly-annotated tool call(s) caused no observed external write")


def _eff02(records: list[EffectRecord]) -> CheckResult:
    """destructiveHint is meaningful only when readOnlyHint is false (spec); a
    readOnly-declared tool that deletes is EFF-01's contradiction, not this
    one's. Among the rest, only an explicit destructiveHint=false is a claim an
    observed delete can falsify — an unset hint defaults to true. Deletes are
    read per target op, so a create+delete call cannot hide its delete behind
    the headline precedence."""
    deletes = [(r, _deleted_targets(r)) for r in records if not _read_only(r)]
    deletes = [(r, objs) for r, objs in deletes if objs]
    if not deletes:
        return _res("EFF-02", SKIP, "no observed delete effect to check")
    offenders = [
        f"{r.tool} declares destructiveHint=false but deleted {', '.join(objs)}"
        for r, objs in deletes if _declares_non_destructive(r)
    ]
    if offenders:
        return _res("EFF-02", FAIL, "; ".join(offenders))
    n_objs = sum(len(objs) for _, objs in deletes)
    declared = sum(1 for r, _objs in deletes if r.declared.get("destructiveHint") is True)
    defaulted = len(deletes) - declared
    parts = []
    if declared:
        parts.append(f"{declared} call(s) from tools declaring destructiveHint=true")
    if defaulted:
        parts.append(f"{defaulted} call(s) from tools leaving destructiveHint unset "
                     "(spec default: true — hosts must already treat them as destructive)")
    return _res("EFF-02", PASS,
                f"all {n_objs} observed deleted object(s) consistent with declared/default "
                f"destructive semantics: " + "; ".join(parts))


def _eff03(records: list[EffectRecord]) -> CheckResult:
    """Compare the first two identical (tool, args) calls: an idempotent tool's
    second call must produce no external effect. Scoped, like the spec scopes
    the hint itself, to tools not declaring readOnlyHint=true — a readOnly
    tool's writes are EFF-01's contradiction."""
    seen: dict[str, EffectRecord] = {}
    checked = 0
    offenders: list[str] = []
    for r in records:
        key = f"{r.tool}::{canonical_json(r.args)}"
        if key in seen:
            first = seen[key]
            if (_idempotent(first) or _idempotent(r)) and not _read_only(first):
                checked += 1
                if r.effect_type.value in _WRITE_EFFECTS:
                    offenders.append(
                        f"{r.tool} declared idempotent but the repeated call {r.effect_type.evidence}"
                    )
            continue
        seen[key] = r
    if not checked:
        return _res("EFF-03", SKIP,
                    "no idempotentHint-annotated (non-readOnly) tool was called twice "
                    "with identical arguments")
    if offenders:
        return _res("EFF-03", FAIL, "; ".join(offenders))
    return _res("EFF-03", PASS,
                f"{checked} repeated idempotent call(s) left external state unchanged")


def _eff06(records: list[EffectRecord]) -> CheckResult:
    """Residual authority: a created authority-bearing object whose probed
    depends_on excludes the grant that authorized it stays effective after the
    grant is revoked."""
    authority = [
        r for r in records
        if r.authority_bearing.value == A_YES and r.effect_type.value == E_CREATE
    ]
    if not authority:
        return _res("EFF-06", SKIP, "no created authority-bearing object to assess")
    # only records with a probed depends_on carry a conclusion; others → unknown
    probed = [r for r in authority if r.depends_on.how == HOW_PROBED]
    if not probed:
        return _res("EFF-06", SKIP,
                    "authority object(s) created, but depends_on was not probed "
                    "(no lifecycle controller / differential probe) — effectiveness "
                    "dependency unknown")
    residual: list[str] = []
    for r in probed:
        grant = r.authorized_by.value
        deps = r.depends_on.value or []
        grant_dep = grant is not None and any(str(grant) in str(d) for d in deps)
        if grant is not None and not grant_dep:
            residual.append(
                f"{r.tool}→{_targets(r)} authorized_by {grant} but depends_on {deps or 'nothing revocable'} "
                f"({r.depends_on.evidence})"
            )
    if residual:
        return _res("EFF-06", WARN, "; ".join(residual))
    return _res("EFF-06", PASS,
                f"all {len(probed)} created authority object(s) depend on their authorizing grant")


def _targets(rec: EffectRecord) -> str:
    return ",".join(f"{t.store}/{t.key}" for t in rec.targets) or "?"
