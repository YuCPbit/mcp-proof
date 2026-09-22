<div align="center">

# 🧾 mcp-proof

### Ship an MCP server with a receipt.

**Audit an MCP server from the wire. Get conformance, security, regression — and effect — evidence in one reproducible, offline-verifiable delivery report.**

`stdio + Streamable HTTP · 2026-07-28 + legacy eras · HTML / JSON / JUnit / SARIF`

[![ci](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml/badge.svg)](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11+-blue)](pyproject.toml)
[![checks](https://img.shields.io/badge/checks-32_modern_·_27_legacy_·_6_security_·_4_effect-6a5acd)](src/mcpproof/checks/)
[![transports](https://img.shields.io/badge/transports-stdio_·_HTTP-informational)](src/mcpproof/client_http.py)
[![license](https://img.shields.io/badge/license-MIT-black)](LICENSE)

**English** · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Français](README.fr.md)

<a href="https://yucpbit.github.io/mcp-proof/report-filesystem.html"><img src="demo/report-filesystem.png" width="760" alt="mcp-proof delivery report for the official MCP filesystem server — SHIP-READY, 11/11 MUST checks, full MSSS compliance table, 34/34 replays clean"></a>

**[Browse the live reports →](https://yucpbit.github.io/mcp-proof/)** · **[Effect-aware evaluation →](https://yucpbit.github.io/mcp-proof/evaluation/)**

*A real audit of the official MCP filesystem server: 27 conformance checks, the MSSS compliance table, 34 regression replays — ship-ready, one advisory finding.*

</div>

---

## 🚀 Quick start

```bash
pip install git+https://github.com/YuCPbit/mcp-proof
mcp-proof run python my_server.py --fixtures fixtures/ --record-if-missing --out report.html
```

Auditing a running HTTP server instead? `mcp-proof run --url http://localhost:8000/mcp --out report.html`

Exit codes are the gate: **`0`** — every MUST check passed, no blocking security findings, no behavioural drift. **`1`** — the audit completed and the server failed it. **`2`** — the audit did not complete and proves nothing about the server, in either direction.

```bash
mcp-proof plan python my_server.py                             # what would auto-baselining call, and why
mcp-proof record python my_server.py --fixtures fixtures/      # freeze the behavioural contract
mcp-proof replay --fixtures fixtures/ -- python my_server.py   # fail on any drift
mcp-proof inspect python my_server.py --out baseline.json      # freeze the contract surface
mcp-proof diff baseline.json current.json                      # BREAKING / ADDITIVE / METADATA, exit 1 on breaking
mcp-proof verify report.json                                   # recheck the report's fingerprints offline
mcp-proof effects --sqlite state.db -- python my_server.py     # declared vs observed external effects (v0.8)
```

See the difference in 60 seconds with the built-in demo pair — a clean server and one with nine planted violations:

```bash
mcp-proof run python demo/good_server.py --fixtures demo/fixtures-good --out report-good.html   # → SHIP-READY
mcp-proof run python demo/bad_server.py --out report-bad.html                                    # → 5 MUST failures, 3 security findings
```

## 🔬 The four lanes

| Lane | Question it answers | How |
|---|---|---|
| **Protocol conformance** | Does the server implement MCP correctly on the wire? | A hand-rolled JSON-RPC probe observes the raw byte stream — era negotiation, error semantics, all three surfaces, pagination, stdout hygiene, verified negative probes |
| **Security & hygiene** | Is the advertised tool metadata clean? | Deterministic static analysis — injected instructions, hidden Unicode, leaked secrets, unconstrained execution surfaces — each finding mapped to an MSSS control ID |
| **Behaviour regression** | Does the server still do exactly what it did at delivery? | Record/replay of SHA-256-fingerprinted golden fixtures behind a fail-closed integrity gate, drift graded by severity |
| **Effect conformance** (v0.8, research) | Does a tool's effect on the world match what it declared? | An out-of-band observer diffs external state around every call; a probe exercises created objects — see [the evaluation](https://yucpbit.github.io/mcp-proof/evaluation/) |

Every lane feeds one report, and the report ends with a prioritized fix list, so it doubles as a remediation plan.

## ✨ What's under the hood

- **Wire-level checks, every surface, every page, both eras.** 32 modern-era (2026-07-28: `server/discover`, `_meta` envelope, `resultType`, `ttlMs`/`cacheScope`, `-32022`, routing headers) and 27 legacy-era checks; one pagination collector feeds every lane, so a violation on page 2 is audited exactly like page 1.
- **Verified negative probes.** TOOL-07 sends inputs that *provably* violate the declared schema (a schema-valid baseline with exactly one field mutated, both halves proven with `jsonschema`); a server that answers them normally is flagged, and a hang is its own finding — never counted as rejection.
- **Security checks tied to a public standard.** Six deterministic scans over every advertised tool, with a schema walker that sees through `$ref`/`allOf`/nesting — mapped to the [MCP Server Security Standard](https://mcp-security-standard.org)'s 24-control matrix, whose verdicts never outrun evidence: **met** / **partial** / **gap** / **manual review**.
- **A regression suite that verifies itself before judging anyone.** Fixtures carry per-contract SHA-256 and an order-sensitive manifest fingerprint; tampering, deletion, duplication — or stripping the hash itself — aborts the replay. Any structured/JSON value change is at least `VALUE` drift; `"approved"→"denied"` can never pass as cosmetic.
- **Two honest fingerprints.** `behavior_sha256` covers server behaviour only (reproducible across machines); `run_hash` seals the whole document by subtraction. `mcp-proof verify` rechecks both offline — an internal-consistency proof, not a signature.
- **Conservative call planning.** Auto-baselining skips mutating-looking tools; as of v0.8, MCP annotations may only *add* caution — an unverified `readOnlyHint` no longer makes a tool auto-callable, matching the spec's "annotations are untrusted" stance.
- **A contract diff for CI.** `inspect` freezes the fully-paginated served surface into a fingerprinted manifest (refusing to freeze half a surface); `diff` classifies `BREAKING` / `ADDITIVE` / `METADATA` — schema tightening, enum narrowing, required-flips and weakened safety annotations all count as breaking.
- **Reproducible by design.** Zero LLM calls, zero API keys, deterministic argument synthesis; identical server behaviour reproduces identical fingerprints on any machine.

## 🧪 The effect-aware research lane (v0.8)

Protocol conformance asks whether the server *speaks* MCP correctly. The effect lane asks whether a tool's **effect on the world** matches what it declared — by reading external state out-of-band (never the tool's response) and by **exercising** created objects instead of trusting names or persistence.

```bash
python experiments/run_all.py         # E1–E3 from a clean state → experiments/results/index.html
python experiments/make_report.py     # flagship effect-evidence reports
```

Measured on a controlled synthetic testbed with out-of-band ground truth (detection behaviour on planted inconsistencies — **not** production prevalence):

| Property | Probe / effect observation | Best baseline |
|---|---|---|
| Annotation-lie detection (incl. 3 response-invisible lies) | precision / recall **1.000 / 1.000** | 1.000 / 0.333 |
| Authority-bearing vs merely persistent | accuracy **1.000** | 0.875 (name) · 0.625 (persistence) |
| Effective vs merely still-listed, after lifecycle events | accuracy **1.000**, 0 residual-authority misses | 0.500 · 0.333, 1 miss |

Two findings an ordinary auditor cannot see: a `readOnlyHint: true` tool that silently mints an API key is caught from the state diff though its response is a normal read; and an API key stays **effective after the grant that authorized it is revoked** — residual authority, measured by an exercise probe, not assumed from the object still existing.

Full methodology, oracle, baselines and limitations: [docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) · live results: [evaluation site](https://yucpbit.github.io/mcp-proof/evaluation/).

## ✅ Validation

- **151 tests**, including an adversarial suite that attacks the auditor itself: violations hidden on page 2, tampered fixtures and manifests, hash-stripping downgrades, edited report verdicts — plus the effect lane's own adversarial set (a response-invisible lie caught only out-of-band, persistence ≠ authority, no-probe → `unknown` → SKIP).
- **CI on Linux, macOS, Windows × Python 3.11–3.13**, plus a fresh-install packaging job that audits a real server end to end.
- **Cross-validated against the official v2 SDK in both directions** (`scripts/crosscheck_modern_server.py`).
- **Fail-closed everywhere**: exit `2` and one stable line for anything the audit cannot prove — never a traceback, never a silently smaller audit, never evidence against the target.

## 📊 Real audits, real reports

| Target | Verdict | Report |
|---|---|---|
| **Official filesystem server** | ✅ SHIP-READY — 11/11 MUST, 34/34 replays clean, 4 write tools auto-skipped | [Live report](https://yucpbit.github.io/mcp-proof/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| **Official "everything" server** | ✅ SHIP-READY — 20/20 MUST + 7/7 SHOULD, 0 security findings across 13 tools (recording deliberately skipped: its `get-env` tool dumps environment variables) | [Live report](https://yucpbit.github.io/mcp-proof/report-everything.html) |
| **Official memory server** | ✅ SHIP-READY — 16/16 MUST, 4/4 replays, one advisory (unconstrained `search_nodes.query`) | [Live report](https://yucpbit.github.io/mcp-proof/report-memory.html) |
| **Official sequential-thinking server** | ✅ SHIP-READY — 11/11 MUST; investigating its honest TOOL-08 skip exposed a served inputSchema omitting a runtime-required field | [Live report](https://yucpbit.github.io/mcp-proof/report-sequential-thinking.html) |
| **2026-07-28 modern-era server** (zero-dep, SDK-cross-validated) | ✅ SHIP-READY — era auto-detected, 23/23 MUST incl. negative probes | [Live report](https://yucpbit.github.io/mcp-proof/report-modern.html) |
| Demo server with **9 planted violations** | ❌ NOT SHIP-READY — 5 MUST failures + 5 security findings, every one caught with evidence | [Live report](https://yucpbit.github.io/mcp-proof/report-bad.html) |
| **Effect testbed, `silent-keymint` variant** | ❌ EFF-01 FAIL — a read-only-annotated tool mints an API key; caught out-of-band | [Effect evidence](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-silent-keymint.html) |

## 🧭 How this relates to the official conformance suite

The MCP project maintains [`modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance) — scenario tests for protocol behaviour, including auth flows. Use it to prove the protocol. mcp-proof exists for the half it doesn't do: **delivery evidence** — a fingerprinted, offline-verifiable report a client can keep, MSSS mapping, fail-closed behavioural regression, contract diff as a CI gate, SARIF/JUnit artifacts, and the effect-conformance research lane. They compose.

## 📡 Protocol support

| | |
|---|---|
| Transports | stdio ✅ · Streamable HTTP ✅ |
| Surfaces | tools ✅ · resources ✅ · prompts ✅ — capability-aware in both directions |
| Modern era `2026-07-28` (`server/discover`, stateless `_meta`) | ✅ auto-detected — `--era auto\|modern\|legacy` |
| Legacy era (initialize handshake, `2024-11-05` → `2025-11-25`) | ✅ all lanes |
| Regression lane | ✅ both eras — SDK session (legacy) · probe-backed session (modern) |

Works with servers in **any language** — mcp-proof talks to the process (or URL), not to your codebase.

## ⚙️ CI in one step

```yaml
- uses: YuCPbit/mcp-proof@v0.8.0
  with:
    server-command: python my_server.py
    fixtures: fixtures/
```

The job fails unless the server is ship-ready, and leaves `mcp-proof-report.html` / `.json` / `.junit.xml` / `.sarif` behind for upload.

## 🏗️ Build on the audit-clean template

Building a server rather than auditing one? [`templates/server-starter/`](templates/server-starter/) passes this audit out of the box — every practice annotated with the check ID it satisfies.

## 🗺️ Roadmap

| | |
|---|---|
| **Current — v0.8.0** | Effect-aware research lane: out-of-band effect observation, probe-backed authority classification, residual-authority measurement (`mcp-proof effects`, [`experiments/`](experiments/), [docs](docs/effect-aware-conformance.md)); annotation-trust correction; redesigned [evaluation site](https://yucpbit.github.io/mcp-proof/evaluation/) |
| **v0.7.2** | Truthfulness patch: whole-document fingerprints, fixture hash-stripping counts as tampering, one exit-code taxonomy |
| **Next** | 2026-07-28 depth (MRTR `input_required` round-trips) · official-suite cross-validation in CI · a real-provider effect observer adapter |
| **Later** | Signed evidence bundles (attestation) · opt-in semantic lane — parked until the deterministic core is complete |

Release history lives in [CHANGELOG.md](CHANGELOG.md).

## 🔍 Limitations

mcp-proof proves what can be proven deterministically, and says which is which:

- Security checks cover the observable protocol and metadata surface; MSSS controls needing deployment, source or process evidence are always **manual review** — never assumed passed.
- **Authorization flows are out of scope** for the delivery report (the official suite covers auth scenarios). The effect lane reasons about authority-bearing *objects*, on a controlled testbed — it does not audit a production OAuth deployment.
- **The effect lane is a measurement instrument, not a black-box lane.** It needs an observation channel (a SQLite store, a jailed directory); what it cannot observe is reported `unknown`/SKIP, never assumed absent. Its numbers are testbed detection behaviour, not production prevalence ([details](docs/effect-aware-conformance.md)).
- Auto-baselining uses a conservative name heuristic; since v0.8 an unverified `readOnlyHint` no longer overrides it. Review the skip list before trusting a baseline recorded against production.
- Semantic correctness (does the answer *mean* the right thing?) is outside the deterministic core by design.

## 📄 License

MIT — the taxonomy in the MSSS compliance section follows the [MCP Server Security Standard](https://mcp-security-standard.org) (CC BY-SA 4.0).
