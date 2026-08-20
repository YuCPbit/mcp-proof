<div align="center">

# 🧾 mcp-proof

### Ship an MCP server with a receipt.

**One command audits any MCP server — and hands your client a signed, reproducible delivery report plus a CI regression suite they keep.**

[![tests](https://img.shields.io/badge/tests-36_passing-brightgreen)](tests/)
[![python](https://img.shields.io/badge/python-3.11+-blue)](pyproject.toml)
[![checks](https://img.shields.io/badge/checks-15_conformance_·_6_security-6a5acd)](src/mcpproof/checks/)
[![transports](https://img.shields.io/badge/transports-stdio_·_HTTP-informational)](src/mcpproof/client_http.py)
[![license](https://img.shields.io/badge/license-MIT-black)](LICENSE)

[English](README.md) · [简体中文](README.zh-CN.md)

<img src="demo/report-filesystem.png" width="760" alt="mcp-proof delivery report for the official MCP filesystem server — SHIP-READY, 11/11 MUST checks, full MSSS compliance table, 34/34 replays clean">

*A real audit of the official MCP filesystem server: 15 conformance checks, MSSS compliance table, 34 regression fixtures — all green.*

</div>

---

## ✨ What you get

- 🔍 **15 wire-level protocol checks** — mcp-proof speaks raw JSON-RPC to your server, so it verifies what actually crosses the wire: handshake completeness, exact error codes, tool-schema validity, structured-output correctness, stdout hygiene, pagination safety, and spec-version currency.
- 🛡️ **Security audit tied to a public standard** — 6 deterministic checks (tool-description poisoning, invisible/bidi characters, leaked credentials, unconstrained injection surfaces, advertised shell execution), each mapped to canonical control IDs of the 24-control [MCP Server Security Standard](https://mcp-security-standard.org), rendered as a full compliance table in every report.
- 📼 **A regression suite your client keeps** — golden fixtures with SHA-256 provenance freeze the server's behaviour; replay grades every drift (`BREAKING` / `VALUE` / `COSMETIC` / `LATENCY`), understands structured output, preserves stateful call order, and ships with a ready-to-paste GitHub Actions gate.
- 📄 **A report non-engineers can read** — verdict banner, score tiles, per-finding evidence and fixes, MSSS table, and a priority-ordered **Recommended next steps** list. Self-contained HTML; add `--pdf` for a PDF.
- 🔁 **Reproducible by design** — zero LLM calls, zero API keys, zero flakiness. Identical server behaviour produces an identical report fingerprint, so acceptance is verification, not trust.
- 🧯 **Safe against live servers** — baselining skips mutating tools (`write_*`, `delete_*`, `exec`, …) unless you opt in with `--include-destructive`; `--edge-cases` additionally baselines oversized, empty, and injection-shaped inputs.

## 🚀 Quick start

```bash
pip install git+https://github.com/YuCPbit/mcp-proof
mcp-proof run python my_server.py --fixtures fixtures/ --out report.html
```

Auditing a running HTTP server instead? `mcp-proof run --url http://localhost:8000/mcp --out report.html`

Exit code `0` means: every MUST check passed, zero security findings, zero behavioural drift — a one-line CI gate.

```bash
mcp-proof record python my_server.py --fixtures fixtures/    # freeze the behavioural contract
mcp-proof replay --fixtures fixtures/ -- python my_server.py  # fail on any drift
```

See the difference in 60 seconds with the built-in demo pair — a clean server and one with nine planted violations:

```bash
mcp-proof run python demo/good_server.py --fixtures demo/fixtures-good --out report-good.html   # → SHIP-READY
mcp-proof run python demo/bad_server.py --out report-bad.html                                    # → 5 MUST failures, 3 security findings
```

## 📊 Real audits, real reports

| Target | Verdict | Report |
|---|---|---|
| **Official MCP filesystem server** (`@modelcontextprotocol/server-filesystem`) | ✅ SHIP-READY — 11/11 MUST checks, 34/34 replays clean | [HTML](demo/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| Demo server with **9 planted violations** | ❌ NOT SHIP-READY — 5 MUST failures + 3 security findings, every one caught with evidence | [HTML](demo/report-bad.html) |
| Well-behaved demo server | ✅ SHIP-READY — full three-lane pass incl. regression baseline | [HTML](demo/report-good.html) |

## 🔬 The three lanes

| Lane | What it proves | How |
|---|---|---|
| **Protocol conformance** | The server implements MCP correctly on the wire — handshake, JSON-RPC error semantics, tool & output schemas, capability consistency, pagination, stdout hygiene | A hand-rolled JSON-RPC probe observes the raw byte stream, so nothing is smoothed over |
| **Security & hygiene** | Tool metadata is clean: no injected instructions, hidden Unicode, leaked secrets, or unconstrained execution surfaces | Deterministic static analysis, every finding carrying its MSSS control ID |
| **Behaviour regression** | The server still does exactly what it did at delivery | Record/replay of provenance-fingerprinted golden fixtures, drift graded by severity |

Every lane feeds one report — and the report ends with a prioritized fix list, so it doubles as a remediation plan.

## 🏗️ Build on the audit-clean template

Building a server rather than auditing one? [`templates/server-starter/`](templates/server-starter/) is a fastmcp server that passes this audit out of the box — constrained input schemas, proper error semantics, structured output, every practice annotated with the check ID it satisfies. Copy, implement your tools, audit, ship with the report.

## 🖥️ Platforms

| | |
|---|---|
| macOS | ✅ developed & fully validated |
| Linux | ✅ exercised in CI |
| Windows | ✅ exercised in CI |

Works with servers in **any language** — mcp-proof talks to the process (or URL), not to your codebase.

## 🗺️ Roadmap

- Opt-in semantic lane (LLM-graded, promptfoo-compatible assertions) for teams that also want meaning-level checks — the core stays deterministic.

## 📄 License

MIT — the taxonomy in the MSSS compliance section follows the [MCP Server Security Standard](https://mcp-security-standard.org) (CC BY-SA 4.0).
