# Experiments — effect-aware conformance

Reproducible experiments behind the [evaluation site](https://yucpbit.github.io/mcp-proof/evaluation/)
([local copy](results/index.html)). Full methodology, oracle design, baselines and
limitations: [docs/effect-aware-conformance.md](../docs/effect-aware-conformance.md).

## Reproduce everything

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # once, from the repo root
.venv/bin/python experiments/run_all.py       # E1–E3 from a clean state → results/
.venv/bin/python experiments/make_report.py   # per-call effect-evidence reports (honest + silent-keymint)
```

`run_all.py` re-runs all three experiments against fresh testbed instances, writes
per-experiment JSON + markdown into `results/`, and rebuilds `results/index.html`.
Every number on the page is read back from the runners' JSON, so the page cannot
drift from what was measured. The pipeline is deterministic: two runs produce
byte-identical JSON.

## Layout

| File | Role |
|---|---|
| `harness.py` | Shared runner: fresh SaaS-testbed audit per call plan + the three E1 detectors (all read the *same* execution) |
| `e1_effect_conformance.py` | E1 — declared effect vs observed effect (annotation-lie detection, honest + 6 single-lie variants) |
| `e2_persistence_vs_authority.py` | E2 — persistence ≠ authority (probe vs name/persistence baselines over an object corpus) |
| `e3_existence_vs_effectiveness.py` | E3 — existence ≠ current effectiveness across lifecycle events (residual authority) |
| `run_all.py` | Orchestrates E1–E3, aggregates, builds the results page |
| `results_page.py` | Static page builder — component functions over the runners' JSON, no framework, no chart library |
| `make_report.py` | Renders the per-call effect-evidence reports (honest + `silent-keymint`) |
| `results/` | Committed outputs: JSON (source of truth), markdown tables, `index.html`, effect-evidence reports |

## Ground-truth independence

The oracle never goes through the audited MCP surface: E1 scores against the
testbed's mutation ledger, E2 against by-construction authority labels, E3 against
per-scenario intended effectiveness — all read out-of-band from the SQLite store
(`testbed/saas_oracle.py`). These are controlled-testbed measurements of detection
behaviour on planted inconsistencies, **not** production prevalence.
