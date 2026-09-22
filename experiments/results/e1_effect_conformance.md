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
