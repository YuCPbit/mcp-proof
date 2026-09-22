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
