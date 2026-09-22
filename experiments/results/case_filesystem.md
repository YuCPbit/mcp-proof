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
