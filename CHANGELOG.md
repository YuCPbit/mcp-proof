# Changelog

## 0.7.0 — 2026-08-22

Integrity hardening: v0.1–v0.6 proved the tool can do a lot; v0.7 proves it knows
when it must not quietly keep going. No new lanes — every change makes an existing
verdict harder to fool. Driven by an external code review of v0.6.0 (all of whose
findings reproduced) plus our own audit of the same code.

- **One pagination discipline** (`pagination.py`): a single fail-closed collector
  replaces four ad-hoc cursor walkers with three different page ceilings. Conformance,
  security, contract capture and both recorders now audit **every page** of tools,
  resources and prompts — a prompt-injection tool hidden on page 2 is seen exactly
  like one on page 1. Repeating cursors and mid-walk failures are explicit outcomes,
  never silent truncation. Prompts gained the pagination check the other surfaces
  always had (**PROMPT-04**, MUST). Check counts: 32 modern · 27 legacy · 6 security.
- **Fixture-set integrity gate** (`replayer.verify_fixture_set`): before anything
  replays, every contract hash is recomputed and the manifest fingerprint verified.
  A manifest-listed fixture missing from disk, a fixture edited after recording, a
  tampered manifest fingerprint, duplicate entries, stale unlisted files, or a missing
  manifest each produce an ERROR row that fails the gate — previously they were
  silently skipped, alphabetized, or replayed out of order. Pre-v3 fixtures (no
  stored hashes) still replay; their integrity is honestly reported as unverifiable.
- **Fixture schema v4**: every content part is recorded in full (v3 collapsed
  non-text parts to `{"type": ...}` — a completely different image replayed as OK);
  binary payloads become `{sha256, bytes}` digests so behaviour is frozen without
  megabytes in git. Fixture filenames carry a sequence prefix (`0001__tool__hash`),
  so calling the same tool twice with the same args no longer overwrites the first
  recording, and the manifest fingerprint is order-sensitive — `save→get` and
  `get→save` are different contracts. v1–v3 fixtures replay unchanged.
- **Drift semantics that respect machines**: any value change in `structuredContent`
  — or in text that parses as JSON — is now at least `VALUE` and fails the gate;
  `"approved"→"denied"` can never pass as COSMETIC again. Number comparison uses
  `Decimal`, so a drifted 17-digit integer is no longer folded away by float precision.
- **Synthesis is fail-closed**: `synthesize_valid_args` validates every generated
  candidate against the schema before anything is called; unsatisfiable schemas are
  reported (`skipped_synthesis` in the manifest, SKIP evidence in checks) instead of
  being called with known-invalid arguments. Negative probes prove their baseline
  valid first — without that, "exactly one field mutated" proves nothing.
- **Evidence semantics**: TOOL-06 split into a static MUST (declared outputSchemas
  compile) and **TOOL-08** (observed structuredContent validates; up to three safe
  candidates tried; unobservable → SKIP with the reason — "unverified" can no longer
  read as PASS). TOOL-07 no longer counts a timeout as rejection: a server that hangs
  on invalid input is reported as exactly that, matching TOOL-04/05.
- **Security lane sees the whole schema**: shared walker (`schemas.py`) resolves
  `$ref`/`allOf` and descends nested objects, array items and `anyOf`/`oneOf`
  branches — SEC-04/SEC-06 now flag `config.shell.command`, not just top-level params.
- **MSSS verdicts never outrun evidence**: new `partial` status for controls whose
  mapped checks were skipped or WARNed, and for controls whose automated evidence is
  only *supporting* — MCP-LOG-02 ("Secret Redaction in Logs") is now capped at
  partial from a clean metadata scan (a found secret still gaps it). A WARN like
  SEC-04's "unconstrained injection-surface params" can no longer produce a `met`
  for "Input Bounds Enforcement".
- **Contract capture strips by wire location, not key name**: only an item's own
  top-level `_meta` is removed — a user schema property named `ttlMs` or
  `nextCursor` is contract and survives capture and diff (manifest v2, which also
  records `unserved` so "surface absent" is distinguishable from "surface empty").
  `inspect` refuses to write a manifest when any pagination walk is incomplete.
  The dead `side` parameter of `_diff_schema` is gone.
- **Two fingerprints** (report schema v2): `behavior_sha256` covers check/replay
  verdicts and protocol facts only — reproducible across machines, shown in the
  HTML; `run_hash` additionally freezes auditor version, launch command and full
  evidence text. `RawProbe` now lets task cancellation propagate (dead-server
  futures get `ConnectionError` instead of a cancel that masked real cancellation)
  and awaits its reader tasks on exit.
- **30 adversarial tests** (`tests/test_v07.py` + `paginated_surfaces_server.py`):
  page-2 violations on all three surfaces, cursor loops, mid-walk failures, every
  fixture-tampering vector, order-sensitive fingerprints, image-payload drift,
  structured/JSON string flips, float-folding, invalid-baseline negative probes,
  deep-schema injection surfaces, hash stability across environment noise. 107 total.

## 0.6.0 — 2026-08-21

The sampler grows up, and the audit learns to ask the question schemas only imply:
does the server actually enforce what it declares?

- **Two-phase argument synthesis**: local `$ref` resolution, `allOf` merging (properties
  union, required union, first-wins otherwise), `const`, `pattern` (deterministic candidate
  matching), `format` seeds (date-time/email/uri/uuid/…), `exclusiveMinimum`/`Maximum`,
  `multipleOf` snapping, `minItems`/`maxItems`. Same schema, same args, every run.
- **Verified negative variants** (`regression/negative.py`): the valid baseline with exactly
  one field pushed past a declared constraint — oversized strings, out-of-range numbers,
  enum outsiders, pattern misses, type flips (booleans get an int, because lax validators
  coerce "yes"-style strings). Every candidate is checked against the schema with
  `jsonschema` before use: if it doesn't provably violate the declaration, it is discarded.
- **TOOL-07 (SHOULD, both eras)**: sends up to two verified-invalid inputs to up to three
  side-effect-safe tools (same annotations-first policy as recording). A server that answers
  them normally gets a WARN quoting the minimal reproducer. Strictly-validating servers PASS;
  the modern test target grew a `--loose-validation` flag to plant the gap.


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
