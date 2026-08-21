<div align="center">

# 🧾 mcp-proof

### Ship an MCP server with a receipt.

**Audit an MCP server from the wire. Get conformance, security and regression evidence in one reproducible, offline-verifiable delivery report.**

`stdio + Streamable HTTP · 2026-07-28 + legacy eras · HTML / JSON / JUnit / SARIF`

[![ci](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml/badge.svg)](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11+-blue)](pyproject.toml)
[![checks](https://img.shields.io/badge/checks-32_modern_·_27_legacy_·_6_security-6a5acd)](src/mcpproof/checks/)
[![transports](https://img.shields.io/badge/transports-stdio_·_HTTP-informational)](src/mcpproof/client_http.py)
[![license](https://img.shields.io/badge/license-MIT-black)](LICENSE)

[English](README.md) · [简体中文](README.zh-CN.md)

<img src="demo/report-filesystem.png" width="760" alt="mcp-proof delivery report for the official MCP filesystem server — SHIP-READY, 11/11 MUST checks, full MSSS compliance table, 34/34 replays clean">

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
```

See the difference in 60 seconds with the built-in demo pair — a clean server and one with nine planted violations:

```bash
mcp-proof run python demo/good_server.py --fixtures demo/fixtures-good --out report-good.html   # → SHIP-READY
mcp-proof run python demo/bad_server.py --out report-bad.html                                    # → 5 MUST failures, 3 security findings
```

## 🔬 The three lanes

| Lane | What it proves | How |
|---|---|---|
| **Protocol conformance** | The server implements MCP correctly on the wire — era negotiation, JSON-RPC error semantics, tool/resource/prompt surfaces, output schemas, capability consistency, pagination, stdout hygiene | A hand-rolled JSON-RPC probe observes the raw byte stream, so nothing is smoothed over |
| **Security & hygiene** | Tool metadata is clean: no injected instructions, hidden Unicode, leaked secrets, or unconstrained execution surfaces | Deterministic static analysis, every finding carrying its MSSS control ID |
| **Behaviour regression** | The server still does exactly what it did at delivery | Record/replay of provenance-fingerprinted golden fixtures, drift graded by severity |

Every lane feeds one report — and the report ends with a prioritized fix list, so it doubles as a remediation plan.

## ✅ Validation

An audit tool has to earn more trust than the thing it audits. What stands behind every release:

- **140 tests**, including an adversarial suite that attacks the auditor itself: violations hidden on page 2 of paginated listings, tampered fixtures and manifests, hash-stripping downgrade attempts, reports with edited verdict banners, drift classes that used to slip through, invalid synthesized baselines.
- **CI on Linux, macOS and Windows × Python 3.11 / 3.12 / 3.13**, plus a packaging job that builds the wheel, installs it fresh, and runs a real audit against a real server before anything ships.
- **Cross-validated against the official v2 SDK in both directions**: the official client adopts mcp-proof's hand-rolled modern test server via `server/discover`, and mcp-proof runs fully green against official v2 SDK servers on both transports (`scripts/crosscheck_modern_server.py`).
- **Fail-closed by design**: a broken pagination walk, a tampered or unverifiable fixture, a missing baseline or an internal auditor error each stop the audit loudly — and every command answers with the same taxonomy: exit `2` and one stable line, never a traceback, never a silently smaller audit, and never evidence against the target.
- **Offline-verifiable reports**: `mcp-proof verify report.json` recomputes both fingerprints from the report's own fields; the document fingerprint covers everything a reader sees — verdict banner, audit status, summary counters, the MSSS table, next steps — so any post-audit edit breaks it. It is an internal-consistency proof, not a signature (attestation is on the roadmap).

## ✨ What's under the hood

- 🔍 **Wire-level protocol checks across every surface, every page, both eras** — mcp-proof speaks raw JSON-RPC to your server and auto-detects its era: 32 checks for the 2026-07-28 modern era (`server/discover`, `_meta` envelope enforcement, `resultType`, `ttlMs`/`cacheScope` on every cacheable result, `-32022` version rejection, HTTP routing-header enforcement) and 27 for the initialize-handshake era — exact error codes, schema validity, structured output, stdout hygiene, pagination safety on all three list surfaces, dedicated resources & prompts lanes, and **verified negative probes**: TOOL-07 sends inputs that provably violate the declared inputSchema (a schema-valid baseline with exactly one field mutated) and warns when the server answers them normally — and treats a hang as its own finding, never as rejection. One pagination collector feeds every lane, so a tool hidden on page 2 is audited exactly like a tool on page 1.
- 🛡️ **Security audit tied to a public standard** — 6 deterministic checks (tool-description poisoning, invisible/bidi characters, leaked credentials, unconstrained injection surfaces, advertised shell execution) over every advertised tool on every page, with a schema walker that sees through `$ref`/`allOf`/nesting/array items — `config.shell.command` cannot hide one level down. Each check maps to canonical control IDs of the [MCP Server Security Standard](https://mcp-security-standard.org)'s 24-entry control matrix (23 fully documented controls plus the `MCP-DEPLOY-04` future-control placeholder), rendered as a compliance table whose verdicts never outrun their evidence: full direct proof says **met**, clean-but-indirect evidence says **partial**, and a control the checks cannot see says **manual review**.
- 📼 **A regression suite your client keeps — and that verifies itself before it judges anyone** — records in either protocol era; golden fixtures freeze the server's behaviour with SHA-256 provenance, including every content type (binary payloads as digests, so a swapped image can never replay as OK). Before replaying, an integrity gate recomputes every contract hash and the manifest fingerprint: a missing, tampered, duplicated or stale fixture aborts the replay instead of being silently skipped — deleting a fixture's stored hash counts as tampering, not as an older schema, and baselines that predate contract hashing are refused unless `--allow-legacy-fixtures` explicitly opts in. Replay grades every drift (`BREAKING` / `VALUE` / `COSMETIC` / `LATENCY`) — any structured or JSON value change is at least `VALUE`, a flipped `"approved"→"denied"` can never pass as cosmetic — and preserves stateful call order (sequence-numbered fixtures, order-sensitive fingerprint). A baseline is never created implicitly: `run` fails closed when fixtures are missing unless you opt in with `--record-if-missing`.
- 📄 **A report for humans *and* machines** — self-contained HTML with sticky navigation, per-check anchors (`report.html#SEC-03`), attention/passed filters, an evidence-scope card and a collapsible MSSS matrix; `--pdf` for print. The same versioned model ships as `--json` (schema v3), `--junit` for any CI, and `--sarif` for the GitHub Security tab.
- 🔁 **Reproducible by design** — zero LLM calls, zero API keys. Two fingerprints, honestly separated: `behavior_sha256` is computed from server behaviour alone (check verdicts, replay verdicts, protocol facts — never timestamps, latency, the launch command or the auditor's version), so identical server behaviour fingerprints identically on any machine; `run_hash` freezes the whole report document — evidence, verdict banner, audit status, summaries, MSSS table — minus only the volatile timestamp block. `mcp-proof verify` rechecks both offline: an internal-consistency proof that any post-audit edit breaks, not a signature. Acceptance is verification, not trust.
- 🧯 **Annotations-first call planning** — MCP tool annotations outrank the name heuristic in both directions: `readOnlyHint` rescues read-only tools the regex would over-block, `destructiveHint` catches mutators it would miss; unannotated tools fall back to the conservative heuristic. `mcp-proof plan` shows exactly what auto-baselining would call and on what basis, before anything touches production; `--include-destructive` and `--edge-cases` opt into more.
- 📋 **A contract diff for CI** — `mcp-proof inspect` freezes the served surface (capabilities + tools + resources + prompts, fully paginated, absent-vs-empty recorded) into a fingerprinted manifest — and refuses to write one at all if any pagination walk cannot be completed, because half a surface frozen as "the baseline" makes every later diff against the missing half invisible. Volatile wire metadata is removed by location, never by key name, so a schema property that happens to be called `ttlMs` or `nextCursor` stays part of the contract. `mcp-proof diff` classifies every change as `BREAKING` / `ADDITIVE` / `METADATA` and exits non-zero on breaking ones — schema tightening, enum narrowing, required-flips, removed output fields and weakened safety annotations all count.

## 📊 Real audits, real reports

| Target | Verdict | Report |
|---|---|---|
| **Official MCP filesystem server** (`@modelcontextprotocol/server-filesystem`) | ✅ SHIP-READY — 11/11 MUST checks, 34/34 replays clean, 4 write tools auto-skipped | [HTML](demo/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| **2026-07-28 modern-era server** (zero-dep, cross-validated against the official v2 SDK) | ✅ SHIP-READY — era auto-detected via `server/discover`, 23/23 MUST incl. negative probes, 2/2 replays | [HTML](demo/report-modern.html) |
| Demo server with **9 planted violations** | ❌ NOT SHIP-READY — 5 MUST failures + 3 security findings, every one caught with evidence | [HTML](demo/report-bad.html) |
| Well-behaved demo server | ✅ SHIP-READY — 18/18 MUST, full three-lane pass incl. regression baseline | [HTML](demo/report-good.html) |

## 🧭 How this relates to the official conformance suite

The MCP project maintains [`modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance) — scenario tests that verify protocol behaviour for servers and clients, including auth flows. If you need a protocol-correctness baseline, run it; mcp-proof's conformance lane covers overlapping ground from its own wire-level probes.

mcp-proof exists for the half the official suite doesn't do: **delivery evidence**. A fingerprinted, offline-verifiable report a client can keep; MSSS security mapping; golden behavioural regression with a fail-closed integrity gate; contract snapshot/diff as a CI gate; SARIF/JUnit artifacts. Use the official suite to prove the protocol; use mcp-proof to prove the delivery — they compose, and cross-validating against the official suite is on the roadmap.

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
- uses: YuCPbit/mcp-proof@v0.7.2
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
| **Current — v0.7.2** | Truthfulness patch: `verify` fingerprints the whole document (report schema v3 — edited verdict banners, audit status, summaries and MSSS tables no longer verify), fixture hash-stripping counts as tampering, legacy baselines fail closed (`--allow-legacy-fixtures`), one exit-code taxonomy across every command |
| **Next — v0.8** | 2026-07-28 depth: MRTR `input_required` round-trips, `subscriptions/listen` · cross-validation against the official conformance suite in CI |
| **Later** | Signed evidence bundles (attestation) · opt-in semantic lane (LLM-graded assertions) — parked until the deterministic core is complete |

Release history lives in [CHANGELOG.md](CHANGELOG.md).

## 🔍 Limitations

mcp-proof proves what can be proven deterministically, and says which is which:

- Security checks cover the observable protocol and metadata surface. MSSS controls that need deployment, source or process evidence are always reported as **manual review** — never as passed.
- **Authorization is out of scope**: OAuth/auth flows are not audited (the official conformance suite covers auth scenarios).
- Auto-baselining classifies tools by a conservative name/description heuristic. Review the skip list in the fixtures manifest before trusting a baseline recorded against production.
- Semantic correctness (does the answer *mean* the right thing?) is outside the deterministic core by design.

## 📄 License

MIT — the taxonomy in the MSSS compliance section follows the [MCP Server Security Standard](https://mcp-security-standard.org) (CC BY-SA 4.0).
