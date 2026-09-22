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
