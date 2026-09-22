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
