# Effect-aware conformance (v0.8)

This document is the research description of mcp-proof's effect lane: what it
measures, how the experiments are designed, what the results actually
establish, and — as carefully — what they do not.

## 1. The question

mcp-proof's older lanes ask whether a server's **responses** honour its
declared contract:

```
declared input constraints   vs.  observed input behaviour     (TOOL-07)
declared output schema        vs.  observed structuredContent   (TOOL-08)
```

The effect lane adds the third comparison, one level deeper than the response
payload:

```
declared effect semantics     vs.  observed external state change   (EFF-01..06)
```

**Research question.** Can black-box, probe-based observation of a tool's
effect on external state establish three properties that response-level
auditing is structurally unable to see:

1. whether a tool's executed effect contradicts its declared MCP annotations
   (`readOnlyHint` / `destructiveHint` / `idempotentHint`);
2. whether an object a tool creates is *authority-bearing* (usable to authorize
   a later action) as opposed to merely *persistent*;
3. whether such an object remains *effective* after a lifecycle event
   (a grant revocation, a key revocation, a TTL expiry) — as opposed to merely
   still *existing*.

The MCP specification itself states that clients MUST treat tool annotations as
untrusted, and the official Tool Annotations Interest Group (2026‑03) is openly
asking whether annotations should be *evaluated at runtime rather than declared
statically*. This lane is a measurement instrument for exactly that gap.

## 2. Why response-level auditing is insufficient

The current auditor's notion of "behaviour" is the response byte stream. A tool
whose side effect never appears in its response — a read-only-annotated
`get_note` that silently mints an API key, a `list_notes` that registers a
webhook, a `ping` that writes a note — produces a response indistinguishable
from the honest tool. No amount of response inspection can recover the hidden
effect. The effect lane observes the external state directly, out-of-band, so
the effect is visible whether or not the tool narrates it.

## 3. Architecture

The lane is an isolated layer under `src/mcpproof/effects/`; the deterministic
delivery report, its fingerprints and every existing lane are untouched.

- **`observe.py`** — an `Observer` snapshots external state and diffs two
  snapshots into per-object create/update/delete deltas. It reads the state
  **directly** (a SQLite file, a directory tree), never through the audited MCP
  tools — this is the independence boundary. `SqliteObserver` introspects any
  SQLite-backed server; `FilesystemObserver` snapshots a jailed directory.
- **`probes.py`** — a `Probe.exercise` *uses* a created object to authorize an
  action and reports effective / ineffective / not_applicable; a
  `LifecycleController` performs the reversible out-of-band revocations that
  differential probing needs. `NullProbe` returns `unknown` (never a
  definitive "no") when no exercise channel exists.
- **`model.py`** — the `EffectRecord`. Every load-bearing field carries **how
  it is known**: `declared` (the server's word), `observed` (a state diff),
  `probed` (an exercise), or `unknown` (no channel). The three lineage fields
  are kept distinct on purpose:
  - `created_via` — which call created the object (observed by attribution);
  - `authorized_by` — the grant the creating call ran under (declared);
  - `depends_on` — what the object's *continued effectiveness* actually needs,
    established by **differential probing**: revoke each candidate, re-exercise,
    keep only those whose removal disables it.
- **`audit.py`** — drives a call plan, snapshots around each call, and assembles
  the records. With a `NullProbe`, authority/effectiveness/`depends_on` stay
  `unknown` and the dependent checks SKIP — no dimension is ever invented.
- **`checks/effects.py`** — EFF‑01 (readOnly honoured), EFF‑02 (destructive
  declared), EFF‑03 (idempotent honoured), EFF‑06 (no residual authority),
  in the same PASS/FAIL/WARN/SKIP vocabulary as every other lane.

The **trust inversion** (v0.8): `classify_tool` no longer lets a `readOnlyHint`
claim *rescue* a heuristically-mutating tool into being auto-called. Annotations
may only add caution now, never remove it — because auto-calling a
"read-only"-labelled tool against production on its own unverified word is
precisely the risk this lane exists to measure.

## 4. The testbed (independent ground truth)

`testbed/` is a controlled SaaS-like MCP server over SQLite (`saas_server.py`,
raw JSON-RPC, deterministic). Its tools create ordinary persistent objects
(notes) and authority-bearing objects (API keys, webhooks, share links), plus
lifecycle operations (revoke, cleanup) and a one-bit grant. Ground truth comes
from two sources the audited MCP surface cannot influence:

- **out-of-band state**: `saas_oracle.py` reads the SQLite file directly;
- **by-construction labels**: `saas_core.AUTHORITY_BEARING` and the mutation
  ledger `mutations.LIE_TABLE`.

The server's authorization rule (`credential_effective`) deliberately checks
only the key's own row, never the grant that authorized it — so a key survives
revocation of its grant. This is residual authority by construction, in the
shape of documented real incidents (Midnight Blizzard's minted OAuth apps;
GitLab #222829 "revoking access does not revoke grants"). `--cascade-revoke`
flips it to the rare correct behaviour as a negative control.

**Mutations** make exactly one tool lie, each derived from a documented real
inconsistency class (the two DCI categories; rug-pull; hidden authority
minting), so a detector is scored against a known per-tool label.

The probe replays the server's *real* auth rule out-of-band (shared code, so it
cannot drift from the server). In production this step would be a real provider
API call with the credential; in the testbed it is faithful by construction.

## 5. Experiments

All three run from a clean state via `python experiments/run_all.py`, which also
renders `experiments/results/index.html` (figures + tables) from the runners'
own JSON. **These are controlled-testbed measurements, not production
prevalence.**

### E1 — declared effect vs observed effect

- **RQ**: can effect observation catch annotation lies the baselines miss?
- **IV**: server variant (honest + 6 single lies, 3 of them *response-invisible*).
- **DV**: per-tool detection precision/recall.
- **Oracle**: the mutation ledger (`lying_tools`).
- **Baselines**: `response_level` (what a response-only auditor can see) and
  `name_heuristic` (metadata only). All three detectors read the *same*
  execution, so the comparison is fair.
- **Result**:

  | detector | precision | recall | F1 |
  |---|---|---|---|
  | **effect_aware** | **1.0** | **1.0** | **1.0** |
  | response_level | 1.0 | 0.33 | 0.50 |
  | name_heuristic | 1.0 | 0.33 | 0.50 |

  The three response-invisible lies (silent-keymint, shadow-webhook,
  phantom-write) are caught **only** by effect observation; even among the
  visible lies each baseline has a real blind spot (the name heuristic misses
  "save"; the response baseline misses a webhook creator that returns JSON).
  No false positives on the honest server (precision 1.0) — not a strawman.
- **Failure condition** (did not occur): the response baseline already catches
  every lie, or effect_aware false-positives on honest tools.

### E2 — persistence ≠ authority-bearing

- **RQ**: does a probe classify authority-bearing objects more accurately than
  "persistent ⇒ authority" and a credential-name keyword?
- **IV**: a corpus spanning the persistent×authority quadrants.
- **DV**: per-detector confusion matrix / accuracy.
- **Oracle**: by-construction authority labels.
- **Baselines**: `persistence` (persistent ⇒ authority), `name_keyword`.
- **Result**:

  | detector | accuracy |
  |---|---|
  | **probe** | **1.0** |
  | name_keyword | 0.88 |
  | persistence | 0.63 |

  The probe is correct where the baselines fail: a persistent note named
  `api_key_backup` (fools both persistence and name) is `not_applicable` to the
  probe → not authority; a credential that does not persist is exercised
  successfully → authority. The probe classifies by *use*, not appearance.
- **Failure condition** (did not occur): every detector agrees on every object
  (the distinction would be academic).

### E3 — existence ≠ current effectiveness

- **RQ**: after a lifecycle event, does an exercise probe report true
  effectiveness where "still listed" and "grant still active" do not? The
  dangerous error is **false-ineffective**: believing an object is neutralized
  when it still works (residual authority).
- **IV**: lifecycle scenario (no event, grant revoked, key revoked, key
  unlisted, TTL expired, grant revoked under cascade).
- **DV**: accuracy and false-effective / false-ineffective counts.
- **Oracle**: the by-construction effectiveness per scenario.
- **Baselines**: `existence` (inventory), `delegation_centric` (access follows
  the grant).
- **Result**:

  | detector | accuracy | false-ineffective |
  |---|---|---|
  | **probe** | **1.0** | **0** |
  | existence | 0.50 | 0 |
  | delegation_centric | 0.33 | **1** |

  The headline is the `grant_revoked` scenario: the key stays effective though
  its grant is revoked. The delegation-centric view calls it neutralized — the
  one false-ineffective, i.e. residual authority missed — while the probe does
  not. Existence never distinguishes a live key from a listed-but-dead one.
- **Failure condition** (did not occur): every proxy agrees with true
  effectiveness in every scenario.

## 6. What was kept, changed, dropped

- **Kept**: the whole evidence discipline (fail-closed, SKIP over silent pass,
  how-known on every field), the probe/session/report infrastructure, the
  deterministic zero-LLM stance.
- **Changed**: `classify_tool` trust model (annotations may only add caution).
  The real lineage vocabulary now lives where it belongs — the effect record's
  `created_via` / `authorized_by` / `depends_on` — rather than being conflated
  with the existing `provenance.py` SHA-256 helper (left as-is: it is woven
  through the tested fingerprint paths and is not worth destabilising for a
  rename).
- **Dropped**: a fourth "sufficiency" experiment (feed effect records vs raw
  transcript to a downstream authorizer). It was circular — the record schema is
  designed to make the rule decidable, so "winning" was built in. EFF-03
  (idempotency) is exercised by tests rather than promoted to an E1 headline,
  because response-diffing can also detect it and it is not the interesting
  case. Both decisions are recorded here rather than hidden.

## 7. Limitations (read this before citing a number)

- **Synthetic**: every result is from one controlled testbed. The numbers are
  detection behaviour on *planted* inconsistencies, not a prevalence estimate.
  Mutation classes are drawn from documented real cases to bound this, but
  external validity is genuinely limited.
- **Observation boundary**: the effect lane sees only what its observer can see
  (a SQLite store, a jailed directory). Effects to systems outside the observer
  — a real third-party API, `openWorldHint` channels — are `unknown`, reported
  as SKIP, never assumed absent.
- **Probe faithfulness**: authority/effectiveness verdicts are only as good as
  the probe's exercise of the object. In the testbed the probe replays the
  server's real rule and is faithful by construction; a real deployment would
  need a real exercise (an API call), and a wrong probe gives a wrong verdict.
- **Adversarial servers**: a server that behaves only when unobserved (a
  rug-pull that detects the audit) can evade a single-session audit. This lane
  measures; it does not contain.
- **Declared fields in the wild**: real MCP tools declare only the four
  annotations, not `effect_type`/`persistence`/`authority`. Those richer fields
  exist as *observed/probed* record semantics here, not as something servers
  claim — so this lane *verifies existing declarations* (the annotations) and
  *proposes and demonstrates* the richer effect semantics; it does not verify a
  declaration that does not exist.

## 8. Related work and novelty risks

Positioning (see the repository's prior-art notes for the full list):

- **Static description/code inconsistency** — the 10,240-server study
  (arXiv:2602.03580) and DCIChecker (arXiv:2606.04769) own "declared vs actual
  behaviour, including undeclared side effects" for MCP, but **statically**,
  requiring source. This lane is **dynamic, black-box, probe-verified**, and
  handles closed servers — but any claim must cite and differentiate these.
- **Dynamic MCP sandbox inspection** — MCP-SandboxScan (arXiv:2601.01241) and
  mcp-annotation-enforcement observe/enforce tool behaviour in a sandbox; their
  lens is data-flow/containment, not declared-vs-observed *effect conformance*
  with authority lineage.
- **Effect/reversibility taxonomies** — "Revisable by Design" (arXiv:2604.23283)
  and the Irreversibility Budget (arXiv:2609.00275) classify and price effects;
  this lane adds the authority-bearing and persistence dimensions they lack, and
  targets third-party tool conformance rather than the agent's own actions.
- **Residual / lingering authority** — arXiv:2609.21284 (root-scoped quiescence,
  concurrent, Sept 2026) formalizes revocation not closing every authority
  carrier; arXiv:2609.08258 ("Revoked but Still Authoritative") runs a
  revoke-then-probe study for agent *memory*. E3's methodology is the same shape
  in the *tool-created authority* domain. These are the nearest novelty risks;
  treat 2609.21284 as concurrent work.

**We do not claim** to be the first to study declared-vs-observed MCP behaviour;
the defensible contribution is the *combination* — dynamic probe-verified effect
conformance with authority classification, effectiveness probing, and the three
distinct lineage fields — demonstrated on a controlled testbed with independent
ground truth.

## 9. Place in the broader agent-authorization trajectory

This project is step 1 of a stated trajectory in agent authorization/security:
tool behaviour, executable effect evidence, and effect-level semantics. It
deliberately stops at **measurement**. It establishes the instrumentation the
later delegated-authority work will need — an out-of-band effect observer, an
authority-by-exercise probe, and the `created_via` / `authorized_by` /
`depends_on` distinction — and it demonstrates, in one controlled setting, that
authority created under a delegation can outlive that delegation's revocation
(E3). What it does **not** do, and leaves for the later paper, is any general
delegation protocol, authority graph, cross-provider revocation, or provenance
system. Those are out of scope here by design.
