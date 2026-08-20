# Changelog

## 0.5.0 — 2026-08-21

One report model, every output format a CI could want.

- **Versioned JSON report model** (`report_schema_version: 1`): the single source of truth
  every format renders from — HTML, JSON (`--json`), JUnit XML (`--junit`), SARIF 2.1.0
  (`--sarif`). The fingerprint discipline carries over: `run_hash` covers behaviour only,
  timestamps live under `observation`.
- **JUnit**: one testcase per check and per replayed fixture — FAIL → `<failure>`,
  SKIP → `<skipped>`, WARN passes with its evidence in `<system-out>`.
- **SARIF**: FAILs as `error`, WARNs as `warning`, drift classes as synthetic `REG-*` rules —
  ready for the GitHub Security tab.
- **Reusable GitHub Action** (`action.yml`, composite): point it at a server command or URL,
  get the full audit plus all four artifacts, job fails unless ship-ready.
- **Report UI**: sticky section navigation, per-check anchors (`report.html#SEC-03`),
  All / Attention / Passed row filters, collapsible 24-row MSSS matrix — all vanilla JS,
  self-contained, and print/PDF-safe (filters and collapse are neutralized in print CSS).


## 0.4.0 — 2026-08-21

The conformance lane now covers every MCP surface, and the audit gains its static half:
a contract manifest with a breaking-change gate.

- **Capability-aware resources & prompts lanes** (both eras): RES-01..04 — an advertised
  resources capability must serve `resources/list`, every resource carries a uri and name,
  `resources/read` works for advertised resources, pagination terminates; PROMPT-01..03 —
  prompts/list served when declared, metadata well-formed, missing required arguments
  rejected; CAP-02/CAP-03 — declared↔served consistency per surface. Surfaces a server
  does not advertise are skipped, never failed. CACHE-01 (modern) now validates
  `ttlMs`/`cacheScope` on **every** cacheable result the session observed.
- **Contract engine**: `mcp-proof inspect` captures a fingerprinted manifest of the served
  surface (capabilities + fully-paginated tools/resources/prompts; volatile wire fields and
  timestamps stay outside the hash, so identical surface ⇒ identical `contract_sha256`).
  `mcp-proof diff` classifies changes as BREAKING / ADDITIVE / METADATA — removed items,
  optional→required flips, type/enum/constraint tightening, removed output fields, and
  weakened safety annotations (`readOnlyHint`/`destructiveHint`) are breaking — and exits
  non-zero on breaking changes (`--fail-on breaking|any|never`).
- **Annotations-first call planning**: `classify_tool` lets MCP annotations outrank the
  name heuristic in both directions; `mcp-proof plan` prints the AUTO-CALL / SKIPPED plan
  with the basis for each decision. Recording, TOOL-06's dynamic call and the plan all
  share one policy.
- Tool listings are now fully paginated in the recorder, replayer and plan (previously
  first-page only).
- New test servers: a fastmcp legacy server exposing all three surfaces, and the modern
  target grew resources, prompts, annotations and a `--drop-tool` contract-drift knob.


## 0.3.0 — 2026-08-21

Dual-era protocol support: the conformance lane now speaks both the 2026-07-28 modern era and
the legacy initialize handshake.

- **Era auto-detection** (`--era auto|modern|legacy`): `server/discover` is probed first, exactly
  like the official client's auto mode; anything that is not positive modern evidence falls back
  to the handshake — on a fresh probe, so the audited session is never perturbed by negotiation.
- **19 modern-era checks**, including three negative probes with teeth: requests without the
  `_meta` envelope must be rejected (ENV-01), an unsupported protocol version must return
  `-32022` with the supported list (VER-01), and a mismatched `Mcp-Method` routing header must
  return `-32020` over Streamable HTTP (HTTP-01). Plus `resultType` on every result (RTYPE-01),
  `ttlMs`/`cacheScope` on list results (CACHE-01), `_meta` serverInfo identity (META-01), and
  deterministic tool order (ORD-01). The 12 shared RPC/TOOL/LIST/HYG/CAP checks run in both eras.
- **Dual-era test targets**: a hand-rolled, zero-dependency modern server (stdio + Streamable
  HTTP, with planted-violation flags) — hand-rolled because the 1.x and 2.x client SDKs cannot
  share a venv. Its wire format is cross-validated against the official v2 SDK in both
  directions (`scripts/crosscheck_modern_server.py`): the official client adopts it via
  `server/discover`, and mcp-proof audits an official v2 SDK server fully green.
- Report header and fingerprint now carry the protocol era and discovery method.
- **Dual-era regression sessions**: the recorder and replayer pick their session by era —
  the pinned 1.x SDK for handshake-era servers (unchanged, battle-tested), a probe-backed
  session (`client_modern.py`) for 2026-07-28 servers. Repinning onto the 2.x SDK was not an
  option: the fastmcp dev targets require `mcp<2.0`, so the two SDKs can never share a venv.
  The probe session paginates tools/list, stamps the `_meta` envelope and the SEP-2243 routing
  headers on every call, and mirrors the SDK contract (protocol errors raise, `isError` results
  return) so the recorder, replayer and fixture format are untouched. `--era` is now accepted by
  `record` and `replay` too; `run` reuses the era the conformance lane already detected.
- End-to-end against the official v2 SDK: all three lanes run fully green — including recorded
  and replayed fixtures — on official servers over **both transports**, stdio and Streamable
  HTTP with SSE responses, and HTTP-01 confirms the official transport enforces `Mcp-Method`
  header mismatches with `-32020`.

## 0.2.1 — 2026-08-21

Truth patch: every README claim is now backed by code, and a fresh install works again.

### Fixed
- **Fresh installs no longer break**: `mcp` is pinned `>=1.29,<2`. The 2.x SDK (2026-07-28 spec era)
  renames the client-facing model fields this package reads (`Tool.inputSchema` → `input_schema`),
  so an unpinned install crashed during recording. `httpx` is now a declared dependency instead of
  arriving transitively.
- **CI can no longer go green without HTTP coverage**: the HTTP transport tests locate the interpreter
  via the shared `venv_python()` helper (works on GitHub runners and Windows), and in CI a target-server
  boot failure fails the suite instead of silently skipping it.
- **`LIFE-02` reports the protocol era honestly.** The probe requests `2025-11-25` — the newest revision
  the legacy initialize handshake carries. Negotiating it is a PASS; the misleading
  "not yet migrated to 2026-07-28" verdict is gone (that revision is announced via `server/discover`,
  which an initialize handshake can never verify — dual-era probing lands in v0.3).
- **Capability honesty (`LIFE-03`)**: a resources- or prompts-only server that does not advertise
  `capabilities.tools` is SKIPped, not failed. Verified by a dedicated resources-only test server.
- **The reproducibility claim is now mathematically true.** Fixtures split into a hashed *contract*
  layer (tool + args + normalized response) and an unhashed *observation* layer (timestamp, latency,
  server command). The manifest fingerprint aggregates contract hashes only, and the report fingerprint
  excludes LATENCY advisory rows — identical behaviour now reproduces identical hashes, including
  across re-recordings. Fixture schema v3; v1/v2 fixtures keep replaying.
- **Regression tile arithmetic**: the denominator counts behaviour verdicts; latency advisories are
  shown separately instead of inflating the replay count.
- **Crashed servers leave evidence**: the stdio probe captures a bounded stderr tail and the exit code
  into the report instead of a bare timeout, and pending requests fail fast when the server process dies.

### Changed
- README/architecture wording aligned with what the code proves: "fingerprinted" (not "signed"),
  explicit transport and protocol-revision support matrix, three deterministic lanes + planned semantic
  extension, a Limitations section, and a live CI badge instead of a static test count.
- CI: Ubuntu 3.11/3.12/3.13 + macOS + Windows matrix, `ruff` lint gate, and a fresh-install package job
  (build wheel → install runtime deps only → audit the zero-dependency demo end to end).

## 0.2.0 — 2026-08-20

Initial public release: 15 wire-level conformance checks, 6 MSSS-mapped security checks,
record/replay behaviour regression with drift grading, stdio + Streamable HTTP transports,
self-contained HTML delivery report with PDF export, audit-clean server starter template.
