# Experiments — effect-aware conformance

Reproducible experiments behind the [evaluation site](https://yucpbit.github.io/mcp-proof/evaluation/)
([local copy](results/index.html)). Full methodology, oracle design, baselines and
limitations: [docs/effect-aware-conformance.md](../docs/effect-aware-conformance.md).

## Reproduce everything

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # once, from the repo root
.venv/bin/python experiments/run_all.py       # E1–E3 + flagship reports + the results page
```

`run_all.py` re-runs all three experiments against fresh testbed instances, writes
per-experiment JSON + markdown into `results/`, renders the two flagship
effect-evidence reports, and rebuilds `results/index.html`. Every number on the
page is read back from the runners' JSON, so the page cannot drift from what was
measured. The pipeline is deterministic: two runs produce byte-identical files —
and **CI enforces this**, re-running the pipeline in a fresh environment and
failing unless the outputs match the committed results exactly.

## Case studies (third-party servers)

```bash
.venv/bin/python experiments/case_studies.py            # all three targets
.venv/bin/python experiments/case_studies.py memory     # one target
```

`case_studies.py` runs the same effect audit against three published MCP servers
we did not build — the official memory server (JSONL store), the official
filesystem server (jailed directory, stock observer) and a community SQLite
server (no annotations) — at pinned versions, and writes `case_*.json/md` plus a
per-target effect-evidence report into `results/`. These runs need `npx` (and
network on first download), so they are **not** part of the CI byte-identical
gate; `run_all.py` renders their committed JSON into the page without re-running
them. Their evidence is a record of a real audit — responses may embed real
timestamps; local paths are replaced with stable placeholders.

## Layout

| File | Role |
|---|---|
| `harness.py` | Shared runner: fresh SaaS-testbed audit per call plan + the three E1 detectors (all read the *same* execution) |
| `e1_effect_conformance.py` | E1 — the detection experiment: declared vs observed effect (honest + 6 single-lie variants) |
| `e2_persistence_vs_authority.py` | E2 — construct validation: persistence ≠ authority (probe vs name/persistence baselines) |
| `e3_existence_vs_effectiveness.py` | E3 — lifecycle measurement: existence ≠ current effectiveness (residual authority) |
| `case_studies.py` | Effect audits of three third-party servers (pinned versions, committed evidence) |
| `run_all.py` | Orchestrates E1–E3 + flagship reports, renders committed case results, builds the page |
| `results_page.py` | Static page builder — component functions over the runners' JSON, no framework, no chart library |
| `make_report.py` | Renders the per-call effect-evidence reports (honest + `silent-keymint`); invoked by `run_all.py` |
| `results/` | Committed outputs: JSON (source of truth), markdown tables, `index.html`, effect-evidence reports, case-study evidence |

## Ground-truth independence

The oracle never goes through the audited MCP surface: E1 scores against the
testbed's mutation ledger, E2 against by-construction authority labels, E3 against
per-scenario intended effectiveness — all read out-of-band from the SQLite store
(`testbed/saas_oracle.py`). These are controlled-testbed measurements of detection
behaviour on planted inconsistencies, **not** production prevalence. The case
studies carry no oracle — they verify servers' own declarations against observed
effects, and report honest SKIPs where nothing is declared or no probe exists.
