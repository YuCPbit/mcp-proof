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
