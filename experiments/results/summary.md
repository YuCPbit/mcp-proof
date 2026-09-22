# Effect-aware conformance — experiment summary

Controlled-testbed measurements; ground truth is out-of-band. Not production prevalence.

# E1 — declared effect vs observed effect

Detector precision/recall (aggregated over honest + 6 single-lie servers):

| detector | precision | recall | F1 | TP | FP | FN |
|---|---|---|---|---|---|---|
| effect_aware | 1.0 | 1.0 | 1.0 | 6 | 0 | 0 |
| response_level | 1.0 | 0.333 | 0.5 | 2 | 0 | 4 |
| name_heuristic | 1.0 | 0.333 | 0.5 | 2 | 0 | 4 |

Per-lie catch table (✓ = detector flagged the lying tool):

| lie | tool | response-invisible | effect_aware | response_level | name_heuristic |
|---|---|---|---|---|---|
| lie-readonly | save_note | no | ✓ | ✓ | · |
| hide-destructive | delete_note | no | ✓ | ✓ | ✓ |
| webhook-readonly | create_webhook | no | ✓ | · | ✓ |
| silent-keymint | get_note | yes | ✓ | · | · |
| shadow-webhook | list_notes | yes | ✓ | · | · |
| phantom-write | ping | yes | ✓ | · | · |

# E2 — persistence vs authority-bearing state

Corpus: 8 objects across the persistent×authority quadrants.

| detector | accuracy | TP | FP | TN | FN |
|---|---|---|---|---|---|
| persistence | 0.625 | 4 | 2 | 1 | 1 |
| name_keyword | 0.875 | 5 | 1 | 2 | 0 |
| probe | 1.0 | 5 | 0 | 3 | 0 |

Per-object predictions (T=authority-bearing):

| object | persistent | truth | persistence | name | probe | note |
|---|---|---|---|---|---|---|
| api_keys/key_0001 | T | T | T | T | T |  |
| api_keys/key_0002 | T | T | T | T | T |  |
| webhooks/wh_0001 | T | T | T | T | T |  |
| share_links/share_0001 | T | T | T | T | T |  |
| notes/welcome | T | F | T | F | F |  |
| notes/api_key_backup | T | F | T | T | F | decoy: credential-looking note name |
| notes/scratch | F | F | F | F | F | ephemeral note (created, then deleted in-plan) |
| api_keys/key_0003 | F | T | F | T | T | counterexample: credential minted then removed out-of-band — authority without persistence |

# E3 — existence vs current effectiveness after lifecycle events

Detector accuracy and error types over the lifecycle scenarios (false-ineffective = residual authority missed):

| detector | accuracy | correct | false-effective | false-ineffective |
|---|---|---|---|---|
| existence | 0.5 | 3 | 3 | 0 |
| delegation_centric | 0.333 | 2 | 3 | 1 |
| probe | 1.0 | 6 | 0 | 0 |

Per-scenario (truth = is the key actually effective):

| scenario | truth | existence | delegation | probe | note |
|---|---|---|---|---|---|
| no_event | eff | eff | eff | eff | key minted under an active grant, nothing revoked |
| grant_revoked | eff | eff | dead | eff | the authorizing grant is revoked; the key still works (residual authority) |
| key_revoked | dead | eff | eff | dead | the key itself is revoked; it is still listed but dead |
| key_unlisted | dead | dead | eff | dead | the key row is deleted; not listed and dead |
| ttl_expired | dead | eff | eff | dead | the key's TTL has passed; still listed but dead |
| grant_revoked_cascade | dead | eff | dead | dead | grant revoked on a server that cascades; the key is dead |

# Case study — @modelcontextprotocol/server-memory@2026.8.31

Third-party server (modelcontextprotocol (official reference server)); store: knowledge-graph JSONL file (MEMORY_FILE_PATH). 10 calls; observed effects: 2 create / 2 update / 2 delete. Annotation profile: 9/9 tools annotated (3 readOnly, 3 destructive, 6 idempotent).

| check | level | status | evidence |
|---|---|---|---|
| EFF-01 | MUST | PASS | 3 readOnly-annotated tool call(s) caused no observed external write |
| EFF-02 | MUST | PASS | all 2 observed deleted object(s) consistent with declared/default destructive semantics: 2 call(s) from tools declaring destructiveHint=true |
| EFF-03 | SHOULD | PASS | 1 repeated idempotent call(s) left external state unchanged |
| EFF-06 | SHOULD | SKIP | no created authority-bearing object to assess |

- All nine tools ship full annotations; the three readOnlyHint=true tools (read_graph, search_nodes, open_nodes) caused no observed change — EFF-01 verified against the server's own declarations.
- delete_entities is declared idempotentHint=true and the repeated identical call produced no further effect — the declaration held under an actual repeat, not by trust.
- Observation granularity is per stored object: deleting a single observation from an entity is observed as an UPDATE of that entity object (the row shrinks), not as a delete — the object-level diff is honest about this.

# Case study — @modelcontextprotocol/server-filesystem@2026.8.31

Third-party server (modelcontextprotocol (official reference server)); store: jailed directory tree. 16 calls; observed effects: 3 create / 1 update / 0 delete. Annotation profile: 14/14 tools annotated (10 readOnly, 3 destructive, 2 idempotent).

| check | level | status | evidence |
|---|---|---|---|
| EFF-01 | MUST | PASS | 10 readOnly-annotated tool call(s) caused no observed external write |
| EFF-02 | MUST | PASS | all 1 observed deleted object(s) consistent with declared/default destructive semantics: 1 call(s) from tools declaring destructiveHint=true |
| EFF-03 | SHOULD | PASS | 2 repeated idempotent call(s) left external state unchanged |
| EFF-06 | SHOULD | SKIP | no created authority-bearing object to assess |

- All ten readOnlyHint=true tools caused no observed filesystem change — EFF-01 verified against the server's own declarations.
- move_file is observed as create(destination) + delete(source); its destructiveHint=true declaration covers the observed delete (EFF-02).
- This call improved the instrument: EFF-02's first implementation read only the record's headline effect, where create outranks delete — so move_file's delete was invisible to it (a lying tool could mask a delete by also creating something). EFF-02 now reads per-target ops; the gap was found by this case study, not by the testbed.
- write_file and create_directory declare idempotentHint=true; the repeated identical calls left the tree byte-identical, so the claim held under an actual repeat.

# Case study — @executeautomation/database-server@1.1.0

Third-party server (ExecuteAutomation (community)); store: SQLite database file. 10 calls; observed effects: 3 create / 1 update / 1 delete. Annotation profile: 0/10 tools annotated (0 readOnly, 0 destructive, 0 idempotent).

| check | level | status | evidence |
|---|---|---|---|
| EFF-01 | MUST | SKIP | no exercised tool declared readOnlyHint=true |
| EFF-02 | MUST | PASS | all 1 observed deleted object(s) consistent with declared/default destructive semantics: 1 call(s) from tools leaving destructiveHint unset (spec default: true — hosts must already treat them as destructive) |
| EFF-03 | SHOULD | SKIP | no idempotentHint-annotated (non-readOnly) tool was called twice with identical arguments |
| EFF-06 | SHOULD | SKIP | no created authority-bearing object to assess |

- No tool declares any annotation — the ecosystem's common case. EFF-01/03 SKIP (nothing declared to verify); the observed DELETE from write_query is covered by the spec's pessimistic default for an unset destructiveHint and is therefore consistent, not a contradiction.
- Effects are still attributed per row (create/update/delete of items/<id>) even with nothing declared — observation does not depend on annotations.
- append_insight turned out to persist into a table the audit never created (mcp_insights) — caught because the observer introspects sqlite_master rather than diffing a hand-listed table set. (Its archived Python predecessor kept insights in process memory; verifying before writing this note corrected our own assumption.)
- Observation granularity, honestly: create_table of an EMPTY table is a schema-level change below the row-level diff (no rows → no per-object delta); the table becomes visible the moment it holds a row. The record for create_table therefore shows no observed per-object change.
