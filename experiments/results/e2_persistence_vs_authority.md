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
