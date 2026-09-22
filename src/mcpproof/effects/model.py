"""The effect record and its evidence discipline.

Every load-bearing field carries *how it is known* — declared (the server
said so), observed (an out-of-band state diff showed it), probed (an
independent exercise confirmed it), or unknown (no channel could establish
it). This mirrors the repository's existing rule that absence of evidence is
never PASS: an effect the observer cannot see is `unknown`, not `none`, and a
verdict built on it becomes SKIP/INCONCLUSIVE rather than a pass.

The three lineage fields are kept deliberately distinct (collapsing them
would erase the very distinction the research turns on):

* created_via  — which tool call produced the object (observed by attribution)
* authorized_by — the grant the creating call ran under (declared by session)
* depends_on   — what the object's *continued effectiveness* actually needs,
                 established by differential probing (revoke a candidate, re-
                 exercise); a webhook authorized_by a grant but surviving that
                 grant's revocation does NOT depend_on it.

The effect-type vocabulary is intentionally tiny: none/create/update/delete.
No reversibility ontology, no persistence taxonomy beyond a single observed
boolean — the fields go only as far as the experiments need.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# how-known levels
HOW_DECLARED = "declared"
HOW_OBSERVED = "observed"
HOW_PROBED = "probed"
HOW_UNKNOWN = "unknown"

# effect types
E_NONE = "none"
E_CREATE = "create"
E_UPDATE = "update"
E_DELETE = "delete"

# authority / effectiveness statuses
A_YES = "yes"
A_NO = "no"
A_UNKNOWN = "unknown"

EFF_EFFECTIVE = "effective"
EFF_INEFFECTIVE = "ineffective"
EFF_UNKNOWN = "unknown"


@dataclass
class Evidenced:
    """A value plus how it was established and the supporting evidence line."""

    value: object
    how: str = HOW_UNKNOWN
    evidence: str = ""

    def to_dict(self) -> dict:
        return {"value": self.value, "how": self.how, "evidence": self.evidence}


@dataclass
class TargetRef:
    """One external object a call touched, identified independently of the
    tool's response (store + primary key from the out-of-band snapshot)."""

    store: str
    key: str

    def to_dict(self) -> dict:
        return {"store": self.store, "key": self.key}

    def __hash__(self) -> int:
        return hash((self.store, self.key))


@dataclass
class EffectRecord:
    """What one tool call did outside its response payload, with evidence.

    Built by the effect audit from an out-of-band before/after state diff
    (effect_type, targets, persistence) plus probes (authority_bearing,
    effectiveness, depends_on). `declared` holds the annotations the server
    advertised for the tool, so declared-vs-observed conformance is a
    comparison over this one record.
    """

    call_id: str
    tool: str
    args: dict
    declared: dict  # the tool's advertised annotations (readOnlyHint, ...)

    # the tool's own response text — what a response-level auditor sees; kept
    # so the response-only baseline and the effect observer read one execution
    response_text: str = ""
    effect_type: Evidenced = field(default_factory=lambda: Evidenced(E_NONE, HOW_UNKNOWN))
    targets: list[TargetRef] = field(default_factory=list)
    persistence: Evidenced = field(default_factory=lambda: Evidenced(None, HOW_UNKNOWN))
    authority_bearing: Evidenced = field(default_factory=lambda: Evidenced(A_UNKNOWN, HOW_UNKNOWN))

    # lineage — three separate fields, never merged
    created_via: str = ""                       # this call_id, when it created state
    authorized_by: Evidenced = field(default_factory=lambda: Evidenced(None, HOW_UNKNOWN))
    depends_on: Evidenced = field(default_factory=lambda: Evidenced(None, HOW_UNKNOWN))

    effectiveness: Evidenced = field(default_factory=lambda: Evidenced(EFF_UNKNOWN, HOW_UNKNOWN))

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "tool": self.tool,
            "args": self.args,
            "declared": self.declared,
            "response_text": self.response_text,
            "effect_type": self.effect_type.to_dict(),
            "targets": [t.to_dict() for t in self.targets],
            "persistence": self.persistence.to_dict(),
            "authority_bearing": self.authority_bearing.to_dict(),
            "created_via": self.created_via,
            "authorized_by": self.authorized_by.to_dict(),
            "depends_on": self.depends_on.to_dict(),
            "effectiveness": self.effectiveness.to_dict(),
        }

    @staticmethod
    def from_dict(d: dict) -> EffectRecord:
        def ev(x):
            return Evidenced(x.get("value"), x.get("how", HOW_UNKNOWN), x.get("evidence", ""))

        rec = EffectRecord(
            call_id=d["call_id"], tool=d["tool"], args=d.get("args", {}),
            declared=d.get("declared", {}), response_text=d.get("response_text", ""),
        )
        rec.effect_type = ev(d["effect_type"])
        rec.targets = [TargetRef(t["store"], t["key"]) for t in d.get("targets", [])]
        rec.persistence = ev(d["persistence"])
        rec.authority_bearing = ev(d["authority_bearing"])
        rec.created_via = d.get("created_via", "")
        rec.authorized_by = ev(d["authorized_by"])
        rec.depends_on = ev(d["depends_on"])
        rec.effectiveness = ev(d["effectiveness"])
        return rec


def records_to_dicts(records: list[EffectRecord]) -> list[dict]:
    return [r.to_dict() for r in records]


def _round_trippable(record: EffectRecord) -> dict:
    """Belt-and-suspenders: asdict on the dataclass is not used for output
    (Evidenced needs custom nesting), but kept available for debugging."""
    return asdict(record)
