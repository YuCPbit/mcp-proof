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

Exit codes are the gate: **`0`** — every MUST check passed, no blocking security findings (advisories may remain), no behavioural drift. **`1`** — the audit completed and the server failed it. **`2`** — the audit did not complete (missing baseline, internal auditor error) and proves nothing about the server, in either direction.

```bash
mcp-proof plan python my_server.py                             # what would auto-baselining call, and why
mcp-proof record python my_server.py --fixtures fixtures/      # freeze the behavioural contract
mcp-proof replay --fixtures fixtures/ -- python my_server.py   # fail on any drift
mcp-proof inspect python my_server.py --out baseline.json      # freeze the contract surface
mcp-proof diff baseline.json current.json                      # BREAKING / ADDITIVE / METADATA, exit 1 on breaking
mcp-proof verify report.json                                   # recheck the report's internal fingerprints offline
mcp-proof effects --sqlite state.db -- python my_server.py     # declared vs observed external effects (v0.8)
```

See the difference in 60 seconds with the built-in demo pair — a clean server and one with nine planted violations:

```bash
mcp-proof run python demo/good_server.py --fixtures demo/fixtures-good --out report-good.html   # → SHIP-READY
mcp-proof run python demo/bad_server.py --out report-bad.html                                    # → 5 MUST failures, 3 security findings
```

## 🔬 The four lanes

| Lane | What it proves | How |
|---|---|---|
| **Protocol conformance** | The server implements MCP correctly on the wire — era negotiation, JSON-RPC error semantics, tool/resource/prompt surfaces, output schemas, capability consistency, pagination, stdout hygiene | A hand-rolled JSON-RPC probe observes the raw byte stream, so nothing is smoothed over |
| **Security & hygiene** | Tool metadata is clean: no injected instructions, hidden Unicode, leaked secrets, or unconstrained execution surfaces | Deterministic static analysis, every finding carrying its MSSS control ID |
| **Behaviour regression** | The server still does exactly what it did at delivery | Record/replay of provenance-fingerprinted golden fixtures, drift graded by severity |
| **Effect conformance** (v0.8, research lane) | A tool's observed effect on external state matches its declared annotations; created objects are classified by probing, not by name | An out-of-band observer snapshots the server's state store around every call; a probe exercises created objects — requires an observation channel, see below |

Every lane feeds one report — and the report ends with a prioritized fix list, so it doubles as a remediation plan.

## ✅ Validation

An audit tool has to earn more trust than the thing it audits. What stands behind every release:

- **151 tests**, including an adversarial suite that attacks the auditor itself: violations hidden on page 2 of paginated listings, tampered fixtures and manifests, hash-stripping downgrade attempts, reports with edited verdict banners, drift classes that used to slip through, invalid synthesized baselines — and, for the effect lane, a read-only-annotated tool that mints a credential detectable only out-of-band, a persistent object that must not be classified as authority-bearing, and a no-probe audit whose authority verdicts must degrade to `unknown`/SKIP instead of passing.
- **CI on Linux, macOS and Windows × Python 3.11 / 3.12 / 3.13**, plus a packaging job that builds the wheel, installs it fresh, and runs a real audit against a real server before anything ships.
- **Cross-validated against the official v2 SDK in both directions**: the official client adopts mcp-proof's hand-rolled modern test server via `server/discover`, and mcp-proof runs fully green against official v2 SDK servers on both transports (`scripts/crosscheck_modern_server.py`).
- **Fail-closed by design**: a broken pagination walk, a tampered or unverifiable fixture, a missing baseline or an internal auditor error each stop the audit loudly — and every command answers with the same taxonomy: exit `2` and one stable line, never a traceback, never a silently smaller audit, and never evidence against the target.
- **Offline-verifiable reports**: `mcp-proof verify report.json` recomputes both fingerprints from the report's own fields; the document fingerprint covers everything a reader sees — verdict banner, audit status, summary counters, the MSSS table, next steps — so any post-audit edit breaks it. It is an internal-consistency proof, not a signature (attestation is on the roadmap).

## ✨ What's under the hood

- 🔍 **Wire-level protocol checks across every surface, every page, both eras** — mcp-proof speaks raw JSON-RPC to your server and auto-detects its era: 32 checks for the 2026-07-28 modern era (`server/discover`, `_meta` envelope enforcement, `resultType`, `ttlMs`/`cacheScope` on every cacheable result, `-32022` version rejection, HTTP routing-header enforcement) and 27 for the initialize-handshake era — exact error codes, schema validity, structured output, stdout hygiene, pagination safety on all three list surfaces, dedicated resources & prompts lanes, and **verified negative probes**: TOOL-07 sends inputs that provably violate the declared inputSchema (a schema-valid baseline with exactly one field mutated) and warns when the server answers them normally — and treats a hang as its own finding, never as rejection. One pagination collector feeds every lane, so a tool hidden on page 2 is audited exactly like a tool on page 1.
- 🛡️ **Security audit tied to a public standard** — 6 deterministic checks (tool-description poisoning, invisible/bidi characters, leaked credentials, unconstrained injection surfaces, advertised shell execution) over every advertised tool on every page, with a schema walker that sees through `$ref`/`allOf`/nesting/array items — `config.shell.command` cannot hide one level down. Each check maps to canonical control IDs of the [MCP Server Security Standard](https://mcp-security-standard.org)'s 24-entry control matrix (23 fully documented controls plus the `MCP-DEPLOY-04` future-control placeholder), rendered as a compliance table whose verdicts never outrun their evidence: full direct proof says **met**, clean-but-indirect evidence says **partial**, and a control the checks cannot see says **manual review**.
- 🧪 **Effect checks that read the world, not the response (v0.8)** — with an observation channel configured (`--sqlite` for a SQLite-backed server; a filesystem observer exists for jailed directories), the effect lane snapshots external state before and after every call and diffs it into per-object create/update/delete effects, attributed to the call that caused them. Four checks compare that against the declared annotations: EFF-01 (a `readOnlyHint: true` tool caused no observed write), EFF-02 (an observed delete came from a `destructiveHint` tool), EFF-03 (an `idempotentHint` tool's repeated identical call was a no-op), EFF-06 (a created credential's continued effectiveness still depends on the grant that authorized it — established by revoking each candidate dependency out-of-band and re-exercising the object, then restoring it). Every field of every effect record carries how it was known — `declared`, `observed`, `probed`, or `unknown` — and a dimension with no channel SKIPs rather than passing.
- 📼 **A regression suite your client keeps — and that verifies itself before it judges anyone** — records in either protocol era; golden fixtures freeze the server's behaviour with SHA-256 provenance, including every content type (binary payloads as digests, so a swapped image can never replay as OK). Before replaying, an integrity gate recomputes every contract hash and the manifest fingerprint: a missing, tampered, duplicated or stale fixture aborts the replay instead of being silently skipped — deleting a fixture's stored hash counts as tampering, not as an older schema, and baselines that predate contract hashing are refused unless `--allow-legacy-fixtures` explicitly opts in. Replay grades every drift (`BREAKING` / `VALUE` / `COSMETIC` / `LATENCY`) — any structured or JSON value change is at least `VALUE`, a flipped `"approved"→"denied"` can never pass as cosmetic — and preserves stateful call order (sequence-numbered fixtures, order-sensitive fingerprint). A baseline is never created implicitly: `run` fails closed when fixtures are missing unless you opt in with `--record-if-missing`.
- 📄 **A report for humans *and* machines** — self-contained HTML with sticky navigation, per-check anchors (`report.html#SEC-03`), attention/passed filters, an evidence-scope card and a collapsible MSSS matrix; `--pdf` for print. The same versioned model ships as `--json` (schema v3), `--junit` for any CI, and `--sarif` for the GitHub Security tab. The effect lane renders its own evidence page: declared annotations beside the observed effect, the response a response-only auditor would have read, the objects that resulted, and the probe's authority/dependency verdict, each value tagged with how it was known.
- 🔁 **Reproducible by design** — zero LLM calls, zero API keys. Two fingerprints, honestly separated: `behavior_sha256` is computed from server behaviour alone (check verdicts, replay verdicts, protocol facts — never timestamps, latency, the launch command or the auditor's version), so identical server behaviour fingerprints identically on any machine; `run_hash` freezes the whole report document — evidence, verdict banner, audit status, summaries, MSSS table — minus only the volatile timestamp block. `mcp-proof verify` rechecks both offline: an internal-consistency proof that any post-audit edit breaks, not a signature. Acceptance is verification, not trust.
- 🧯 **Conservative call planning, and a trust correction (v0.8)** — auto-baselining classifies tools by a conservative name/description heuristic, and `mcp-proof plan` shows exactly what would be called and on what basis before anything touches production. As of v0.8, MCP annotations may only *add* caution: `destructiveHint: true` still forces a skip, but an unverified `readOnlyHint: true` no longer rescues a mutating-looking tool into the auto-call set — the spec says clients MUST treat annotations as untrusted, and the effect lane exists precisely because a "read-only" tool can mint credentials. `--include-destructive` and `--edge-cases` opt into more.
- 📋 **A contract diff for CI** — `mcp-proof inspect` freezes the served surface (capabilities + tools + resources + prompts, fully paginated, absent-vs-empty recorded) into a fingerprinted manifest — and refuses to write one at all if any pagination walk cannot be completed, because half a surface frozen as "the baseline" makes every later diff against the missing half invisible. Volatile wire metadata is removed by location, never by key name, so a schema property that happens to be called `ttlMs` or `nextCursor` stays part of the contract. `mcp-proof diff` classifies every change as `BREAKING` / `ADDITIVE` / `METADATA` and exits non-zero on breaking ones — schema tightening, enum narrowing, required-flips, removed output fields and weakened safety annotations all count.

## 📊 Real audits, real reports

| Target | Verdict | Report |
|---|---|---|
| **Official MCP filesystem server** (`@modelcontextprotocol/server-filesystem`) | ✅ SHIP-READY — 11/11 MUST checks, 34/34 replays clean, 4 write tools auto-skipped | [Live report](https://yucpbit.github.io/mcp-proof/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| **Official "everything" reference server** (`@modelcontextprotocol/server-everything`) | ✅ SHIP-READY — 20/20 MUST + 7/7 SHOULD, 0 security findings across 13 tools. Protocol + security lanes; recording deliberately skipped — its `get-env` tool dumps environment variables | [Live report](https://yucpbit.github.io/mcp-proof/report-everything.html) |
| **Official memory server** (`@modelcontextprotocol/server-memory`) | ✅ SHIP-READY — 16/16 MUST, 4/4 replays clean, 5 write/delete tools auto-skipped, one advisory: unconstrained `search_nodes.query` (SEC-04) | [Live report](https://yucpbit.github.io/mcp-proof/report-memory.html) |
| **Official sequential-thinking server** (`@modelcontextprotocol/server-sequential-thinking`) | ✅ SHIP-READY — 11/11 MUST, 1/1 replays clean, one advisory (2,781-char tool description, SEC-05); investigating its honest TOOL-08 skip exposed the served inputSchema omitting a runtime-required field | [Live report](https://yucpbit.github.io/mcp-proof/report-sequential-thinking.html) |
| **2026-07-28 modern-era server** (zero-dep, cross-validated against the official v2 SDK) | ✅ SHIP-READY — era auto-detected via `server/discover`, 23/23 MUST incl. negative probes, 2/2 replays | [Live report](https://yucpbit.github.io/mcp-proof/report-modern.html) |
| Demo server with **9 planted violations** | ❌ NOT SHIP-READY — 5 MUST failures + 5 security findings (3 blocking, 2 advisory), every one caught with evidence | [Live report](https://yucpbit.github.io/mcp-proof/report-bad.html) |
| Well-behaved demo server | ✅ SHIP-READY — 18/18 MUST, full three-lane pass incl. regression baseline | [Live report](https://yucpbit.github.io/mcp-proof/report-good.html) |
| **Effect testbed, `silent-keymint` variant** | ❌ EFF-01 FAIL — a tool annotated `readOnlyHint: true` returns a normal read response while inserting an `api_keys` row; the out-of-band state diff attributes the write to the call | [Effect evidence](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-silent-keymint.html) |

## 🧪 The effect-aware research lane (v0.8)

The three delivery lanes stop at the wire: their notion of behaviour is the response byte stream. The effect lane extends the same declared-vs-observed method one level deeper. Its parts, concretely:

- **Observer** (`effects/observe.py`): snapshots external state — a SQLite store read directly from the file, or a directory tree — before and after each tool call, and diffs the snapshots into per-object create/update/delete deltas. It never asks the tools what changed, so an effect is seen whether or not the response mentions it.
- **Probe** (`effects/probes.py`): attempts to *use* a created object as a credential against the service's real authorization rule. "Authority-bearing" is then an observed outcome (the object authorized an action), not a guess from a field name; "still effective" is the probe succeeding now, not the object still being listed.
- **Lineage, kept as three separate fields**: `created_via` (which call produced the object — observed), `authorized_by` (the grant the session ran under — declared), and `depends_on` (what its continued effectiveness actually requires — established by revoking each candidate out-of-band, re-exercising, and restoring). The distinction is the point: an API key `authorized_by` a grant whose `depends_on` does not include that grant survives the grant's revocation.
- **Testbed** (`testbed/`): a deterministic SQLite-backed MCP server with ordinary persistent objects (notes) and credential objects (API keys, webhooks, share links), a one-bit grant, lifecycle tools, and mutation flags that plant exactly one annotation lie each — modelled on documented incident patterns (a read path that mints authority; revocation that doesn't cascade). Ground truth is read out-of-band by `testbed/saas_oracle.py`, never through the audited MCP surface.

Three experiments run against it (`python experiments/run_all.py`, deterministic, byte-identical JSON across runs). The numbers are detection behaviour on planted inconsistencies in this controlled setting — **not production prevalence**:

| Experiment | Probe / effect observation | Baselines |
|---|---|---|
| **E1** — declared vs observed effect, honest server + 6 single-lie variants; oracle = the mutation ledger | precision / recall **1.000 / 1.000** | response-level 1.000 / 0.333 · name heuristic 1.000 / 0.333 |
| **E2** — authority-bearing vs merely persistent, 8-object corpus incl. a decoy note named `api_key_backup` and a credential that never persisted; oracle = by-construction authority labels | accuracy **1.000** | name keyword 0.875 · persistence⇒authority 0.625 |
| **E3** — existence vs current effectiveness across 6 lifecycle scenarios (grant revoked, key revoked, key deleted, TTL expired, cascade); oracle = per-scenario intended effectiveness | accuracy **1.000**, 0 false-ineffective | existence 0.500 · grant-status 0.333, 1 false-ineffective |

The two results that motivate the lane: in E1, the three lies whose effects never appear in the response (`silent-keymint`, `shadow-webhook`, `phantom-write`) are caught only by the state diff — a response-level auditor is structurally blind to them, which is why all-lane recall for the baselines is 0.333. In E3's `grant_revoked` scenario, the key created under the grant remains effective after the grant is revoked (the testbed's auth rule checks the key's own row, not the grant — the same shape as documented OAuth-app persistence incidents); the grant-status proxy reports it neutralized, which is the one dangerous false-ineffective in the table.

Methodology, oracle design, baselines, related work and limitations: [docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) · results with raw evidence: [evaluation site](https://yucpbit.github.io/mcp-proof/evaluation/) · reproduction: [experiments/README.md](experiments/README.md).

## 🧭 How this relates to the official conformance suite

The MCP project maintains [`modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance) — scenario tests that verify protocol behaviour for servers and clients, including auth flows. If you need a protocol-correctness baseline, run it; mcp-proof's conformance lane covers overlapping ground from its own wire-level probes.

mcp-proof exists for the half the official suite doesn't do: **delivery evidence**. A fingerprinted, offline-verifiable report a client can keep; MSSS security mapping; golden behavioural regression with a fail-closed integrity gate; contract snapshot/diff as a CI gate; SARIF/JUnit artifacts; and the effect-conformance research lane. Use the official suite to prove the protocol; use mcp-proof to prove the delivery — they compose, and cross-validating against the official suite is on the roadmap.

## 📡 Protocol support

| | |
|---|---|
| Transports | stdio ✅ · Streamable HTTP ✅ |
| Surfaces | tools ✅ · resources ✅ · prompts ✅ — capability-aware in both directions |
| Modern era `2026-07-28` (`server/discover`, stateless `_meta`) | ✅ conformance lane, auto-detected — `--era auto\|modern\|legacy` |
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

The job fails unless the server is ship-ready, and leaves `mcp-proof-report.html` / `.json` /
`.junit.xml` / `.sarif` behind for upload. Prefer raw commands? `mcp-proof run … --junit r.xml --sarif r.sarif`
plus `mcp-proof diff` is the same gate.

## 🏗️ Build on the audit-clean template

Building a server rather than auditing one? [`templates/server-starter/`](templates/server-starter/) is a fastmcp server that passes this audit out of the box — constrained input schemas, proper error semantics, structured output, every practice annotated with the check ID it satisfies. Copy, implement your tools, audit, ship with the report.

## 🖥️ Platforms

| | |
|---|---|
| macOS | ✅ developed & fully validated |
| Linux | ✅ exercised in CI |
| Windows | ✅ exercised in CI (`--pdf` needs Chrome/Chromium installed) |

## 🗺️ Roadmap

| | |
|---|---|
| **Current — v0.8.0** | Effect-aware research lane: out-of-band effect observation, probe-backed authority classification, residual-authority measurement (`mcp-proof effects`, [`experiments/`](experiments/), [docs](docs/effect-aware-conformance.md)); annotation-trust correction; the [evaluation site](https://yucpbit.github.io/mcp-proof/evaluation/) |
| **v0.7.2** | Truthfulness patch: `verify` fingerprints the whole document (report schema v3), fixture hash-stripping counts as tampering, legacy baselines fail closed, one exit-code taxonomy across every command |
| **Next** | 2026-07-28 depth: MRTR `input_required` round-trips · cross-validation against the official conformance suite in CI · a real-provider effect observer adapter (the effect lane's `Observer` interface already admits one) |
| **Later** | Signed evidence bundles (attestation) · opt-in semantic lane (LLM-graded assertions) — parked until the deterministic core is complete |

Release history lives in [CHANGELOG.md](CHANGELOG.md).

## 🔍 Limitations

mcp-proof proves what can be proven deterministically, and says which is which:

- Security checks cover the observable protocol and metadata surface. MSSS controls that need deployment, source or process evidence are always reported as **manual review** — never as passed.
- **Authorization flows are out of scope** for the delivery report: OAuth handshakes are not audited (the official conformance suite covers auth scenarios). The effect lane reasons about *authority-bearing objects* a tool creates, on a controlled testbed with an out-of-band observer — it does not audit a production OAuth deployment.
- **The effect lane is a measurement instrument, not a black-box lane.** It needs an observation channel (a SQLite store, a jailed directory); effects to systems it cannot observe are reported `unknown`/SKIP, never assumed absent. Its numbers are detection behaviour on a synthetic testbed, not production prevalence. See [docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) §7.
- Auto-baselining classifies tools by a conservative name/description heuristic; as of v0.8 an unverified `readOnlyHint` no longer overrides it. Review the skip list in the fixtures manifest before trusting a baseline recorded against production.
- Semantic correctness (does the answer *mean* the right thing?) is outside the deterministic core by design.

## 📄 License

MIT — the taxonomy in the MSSS compliance section follows the [MCP Server Security Standard](https://mcp-security-standard.org) (CC BY-SA 4.0).
