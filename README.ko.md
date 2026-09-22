<div align="center">

# 🧾 mcp-proof

### MCP 서버를 "영수증"과 함께 납품하세요.

**MCP 서버를 와이어 레벨에서 감사합니다. 프로토콜 준수·보안·회귀 — 그리고 효과 — 증거를 재현 가능하고 오프라인 검증 가능한 한 장의 납품 리포트로.**

`stdio + Streamable HTTP · 2026-07-28 및 legacy 두 세대 · HTML / JSON / JUnit / SARIF`

[![ci](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml/badge.svg)](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11+-blue)](pyproject.toml)
[![checks](https://img.shields.io/badge/checks-32_modern_·_27_legacy_·_6_security_·_4_effect-6a5acd)](src/mcpproof/checks/)
[![transports](https://img.shields.io/badge/transports-stdio_·_HTTP-informational)](src/mcpproof/client_http.py)
[![license](https://img.shields.io/badge/license-MIT-black)](LICENSE)

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · **한국어** · [Français](README.fr.md)

<a href="https://yucpbit.github.io/mcp-proof/report-filesystem.html"><img src="demo/report-filesystem.png" width="760" alt="공식 MCP filesystem 서버에 대한 mcp-proof 납품 리포트 — SHIP-READY, MUST 체크 11/11, MSSS 준수표, 리플레이 34/34 클린"></a>

**[라이브 리포트 보기 →](https://yucpbit.github.io/mcp-proof/)** · **[효과 인지 평가 →](https://yucpbit.github.io/mcp-proof/evaluation/)**

*공식 MCP filesystem 서버의 실제 감사: 준수 체크 27건, MSSS 준수표, 회귀 리플레이 34회 — ship-ready, 권고 1건.*

</div>

---

## 🚀 빠른 시작

```bash
pip install git+https://github.com/YuCPbit/mcp-proof
mcp-proof run python my_server.py --fixtures fixtures/ --record-if-missing --out report.html
```

실행 중인 HTTP 서버를 감사하려면: `mcp-proof run --url http://localhost:8000/mcp --out report.html`

종료 코드가 곧 게이트입니다. **`0`** — 모든 MUST 체크 통과, 차단급 보안 발견 없음, 행위 드리프트 없음. **`1`** — 감사는 완료되었고 서버가 불합격. **`2`** — 감사 자체가 완료되지 않아 어느 방향으로도 서버에 대한 증거가 되지 않음.

```bash
mcp-proof plan python my_server.py                             # 자동 베이스라인이 무엇을, 왜 호출하는지
mcp-proof record python my_server.py --fixtures fixtures/      # 행위 계약 동결
mcp-proof replay --fixtures fixtures/ -- python my_server.py   # 드리프트 발생 시 실패
mcp-proof inspect python my_server.py --out baseline.json      # 계약 표면 동결
mcp-proof diff baseline.json current.json                      # BREAKING / ADDITIVE / METADATA, breaking이면 exit 1
mcp-proof verify report.json                                   # 리포트 지문을 오프라인 재검증
mcp-proof effects --sqlite state.db -- python my_server.py     # 선언된 효과 vs 관측된 외부 효과 (v0.8)
```

내장 데모 한 쌍 — 깨끗한 서버와 9곳에 위반을 심은 서버 — 으로 60초 만에 차이를 확인:

```bash
mcp-proof run python demo/good_server.py --fixtures demo/fixtures-good --out report-good.html   # → SHIP-READY
mcp-proof run python demo/bad_server.py --out report-bad.html                                    # → MUST 실패 5건, 보안 발견 3건
```

## 🔬 네 개의 레인

| 레인 | 답하는 질문 | 방식 |
|---|---|---|
| **프로토콜 준수** | 서버가 와이어에서 MCP를 올바르게 구현하는가? | 수제 JSON-RPC 프로브가 원시 바이트 스트림을 관찰 — 세대 협상, 오류 의미론, 세 표면 전부, 페이지네이션, stdout 위생, 검증된 네거티브 프로브 |
| **보안·위생** | 공개된 툴 메타데이터가 깨끗한가? | 결정적 정적 분석 — 주입 지시문, 보이지 않는 유니코드, 유출 시크릿, 무제약 실행 표면 — 발견마다 MSSS 컨트롤 ID에 매핑 |
| **행위 회귀** | 서버가 납품 시점과 정확히 같은 행위를 하는가? | SHA-256 지문이 붙은 골든 픽스처의 기록/리플레이. fail-closed 무결성 게이트를 통과한 뒤 드리프트를 심각도로 분류 |
| **효과 준수** (v0.8, 연구용) | 툴이 세계에 미친 효과가 선언과 일치하는가? | 대역외 옵저버가 호출 전후의 외부 상태를 diff하고, 프로브가 생성물을 실제로 행사 — [평가 사이트](https://yucpbit.github.io/mcp-proof/evaluation/) 참조 |

네 레인이 하나의 리포트로 모이고, 리포트는 우선순위가 매겨진 수정 목록으로 끝나 그대로 시정 계획이 됩니다.

## ✨ 내부 구조

- **와이어 레벨 체크를 모든 표면·모든 페이지·두 세대에서.** 현대 세대(2026-07-28: `server/discover`, `_meta` 엔벨로프, `resultType`, `ttlMs`/`cacheScope`, `-32022`, 라우팅 헤더) 32건, legacy 세대 27건. 페이지네이션 수집기가 하나로 통일되어 2페이지에 숨은 위반도 1페이지와 동일하게 감사됩니다.
- **검증된 네거티브 프로브.** TOOL-07은 선언 스키마를 *증명 가능하게* 위반하는 입력을 보냅니다(스키마 유효한 베이스라인에서 정확히 한 필드만 변이, 양쪽 모두 `jsonschema`로 증명). 태연히 응답하는 서버는 플래그되고, 행(hang)은 그 자체로 별도 발견이며 거부로 계산되지 않습니다.
- **공개 표준에 연결된 보안 체크.** 공개된 모든 툴에 대한 6종의 결정적 스캔. 스키마 워커는 `$ref`/`allOf`/중첩을 꿰뚫어 봅니다 — [MCP Server Security Standard](https://mcp-security-standard.org)의 24개 컨트롤 매트릭스에 매핑되며, 판정은 증거를 넘지 않습니다: **met** / **partial** / **gap** / **manual review**.
- **남을 판정하기 전에 스스로를 검증하는 회귀 스위트.** 픽스처는 계약별 SHA-256과 순서 민감 매니페스트 지문을 지니며, 변조·누락·중복 — 해시 자체를 지우는 것조차 — 리플레이를 중단시킵니다. 구조화/JSON 값 변화는 최소 `VALUE` 드리프트. `"approved"→"denied"`가 cosmetic으로 통과할 수는 없습니다.
- **역할이 다른 두 개의 지문.** `behavior_sha256`은 서버 행위만 커버(머신 간 재현 가능), `run_hash`는 감산 방식으로 문서 전체를 봉인. `mcp-proof verify`가 둘 다 오프라인 재계산 — 내부 일관성 증명이지 서명이 아닙니다.
- **보수적 호출 계획.** 자동 베이스라인은 변경성으로 보이는 툴을 건너뜁니다. v0.8부터 MCP 어노테이션은 주의를 *더할* 수만 있습니다 — 검증되지 않은 `readOnlyHint`가 툴을 자동 호출 가능하게 만들지 못하며, 이는 "어노테이션은 신뢰할 수 없다"는 스펙의 입장과 일치합니다.
- **CI용 계약 diff.** `inspect`는 완전히 페이지네이션된 제공 표면을 지문 있는 매니페스트로 동결(절반만 동결은 거부), `diff`는 `BREAKING` / `ADDITIVE` / `METADATA`로 분류 — 스키마 강화, enum 축소, 선택→필수 반전, 안전 어노테이션 약화는 모두 breaking입니다.
- **설계된 재현성.** LLM 호출 0, API 키 0, 결정적 인자 합성. 동일한 서버 행위는 어느 머신에서든 동일한 지문을 재현합니다.

## 🧪 효과 인지 연구 레인 (v0.8)

프로토콜 준수는 서버가 MCP를 올바르게 *말하는지*를 묻습니다. 효과 레인은 툴이 **세계에 미친 효과**가 선언과 일치하는지를 묻습니다 — 툴의 응답이 아니라 외부 상태를 대역외로 읽고, 이름이나 지속성을 믿는 대신 생성물을 **실제로 행사**함으로써.

```bash
python experiments/run_all.py         # 클린 상태에서 E1–E3 → experiments/results/index.html
python experiments/make_report.py     # 대표 효과 증거 리포트
```

대역외 그라운드 트루스를 갖춘 통제된 합성 테스트베드에서의 측정치(심어 둔 불일치에 대한 탐지 성능이며, **프로덕션 유병률이 아닙니다**):

| 성질 | 프로브 / 효과 관측 | 최고 베이스라인 |
|---|---|---|
| 어노테이션 거짓 탐지(응답에 안 보이는 3건 포함) | precision / recall **1.000 / 1.000** | 1.000 / 0.333 |
| authority-bearing vs 단순 지속 | 정확도 **1.000** | 0.875(이름) · 0.625(지속성) |
| 라이프사이클 이벤트 후: 유효 vs 단순 목록 잔존 | 정확도 **1.000**, 잔존 권한 놓침 0 | 0.500 · 0.333, 놓침 1 |

일반 감사기가 볼 수 없는 두 가지 발견: `readOnlyHint: true` 툴이 몰래 API 키를 발급 — 응답은 평범한 읽기처럼 보이지만 상태 diff가 잡아냅니다. 그리고 API 키는 **그것을 승인한 grant가 철회된 뒤에도 유효** — 잔존 권한(residual authority)은 객체가 아직 존재한다는 사실에서 추정되는 게 아니라 행사 프로브로 측정됩니다.

전체 방법론·오라클·베이스라인·한계: [docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) · 라이브 결과: [평가 사이트](https://yucpbit.github.io/mcp-proof/evaluation/).

## ✅ 검증

- **151개 테스트**, 감사기 자신을 공격하는 적대적 스위트 포함: 2페이지에 숨긴 위반, 변조된 픽스처와 매니페스트, 해시 제거 다운그레이드, 수정된 리포트 판정 — 그리고 효과 레인의 자체 적대 세트(응답에 안 보이는 거짓은 대역외로만 포착, 지속 ≠ 권한, 프로브 없음 → `unknown` → SKIP).
- **Linux·macOS·Windows × Python 3.11–3.13 CI**, 그리고 실제 서버를 엔드투엔드로 감사하는 클린 설치 패키징 잡.
- **공식 v2 SDK와 양방향 교차 검증** (`scripts/crosscheck_modern_server.py`).
- **어디서나 fail-closed**: 감사가 증명할 수 없는 것은 전부 exit `2`와 안정된 한 줄로 끝납니다 — 트레이스백 없음, 조용히 축소되는 감사 없음, 대상에 대한 불리한 증거가 되는 일도 없음.

## 📊 실제 감사, 실제 리포트

| 대상 | 판정 | 리포트 |
|---|---|---|
| **공식 filesystem 서버** | ✅ SHIP-READY — 11/11 MUST, 34/34 리플레이 클린, 쓰기 툴 4개 자동 스킵 | [라이브](https://yucpbit.github.io/mcp-proof/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| **공식 "everything" 서버** | ✅ SHIP-READY — 20/20 MUST + 7/7 SHOULD, 툴 13개에 보안 발견 0(기록은 의도적으로 스킵: `get-env` 툴이 환경 변수를 덤프) | [라이브](https://yucpbit.github.io/mcp-proof/report-everything.html) |
| **공식 memory 서버** | ✅ SHIP-READY — 16/16 MUST, 4/4 리플레이, 권고 1건(무제약 `search_nodes.query`) | [라이브](https://yucpbit.github.io/mcp-proof/report-memory.html) |
| **공식 sequential-thinking 서버** | ✅ SHIP-READY — 11/11 MUST. 정직한 TOOL-08 SKIP을 추적하다 제공 inputSchema가 런타임 필수 필드를 누락한 것을 발견 | [라이브](https://yucpbit.github.io/mcp-proof/report-sequential-thinking.html) |
| **2026-07-28 현대 세대 서버**(무의존, SDK 교차 검증) | ✅ SHIP-READY — 세대 자동 감지, 네거티브 프로브 포함 23/23 MUST | [라이브](https://yucpbit.github.io/mcp-proof/report-modern.html) |
| **위반 9곳**을 심은 데모 서버 | ❌ NOT SHIP-READY — MUST 실패 5건 + 보안 발견 5건, 전부 증거와 함께 포착 | [라이브](https://yucpbit.github.io/mcp-proof/report-bad.html) |
| **효과 테스트베드 `silent-keymint` 변이** | ❌ EFF-01 FAIL — 읽기 전용으로 주석된 툴이 API 키를 발급. 대역외에서 포착 | [효과 증거](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-silent-keymint.html) |

## 🧭 공식 conformance 스위트와의 관계

MCP 프로젝트는 [`modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance)(auth 플로우를 포함한 프로토콜 행위의 시나리오 테스트)를 관리합니다. 프로토콜 증명은 그쪽으로. mcp-proof는 그것이 하지 않는 나머지 절반 — **납품 증거** — 을 위해 존재합니다: 클라이언트가 보관할 수 있는 지문 있는 오프라인 검증 가능 리포트, MSSS 매핑, fail-closed 행위 회귀, CI 게이트로서의 계약 diff, SARIF/JUnit 산출물, 그리고 효과 준수 연구 레인. 둘은 상호 보완적입니다.

## 📡 프로토콜 지원

| | |
|---|---|
| 전송 | stdio ✅ · Streamable HTTP ✅ |
| 표면 | tools ✅ · resources ✅ · prompts ✅ — 양방향 capability 인지 |
| 현대 세대 `2026-07-28` (`server/discover`, 무상태 `_meta`) | ✅ 자동 감지 — `--era auto\|modern\|legacy` |
| Legacy 세대 (initialize 핸드셰이크, `2024-11-05` → `2025-11-25`) | ✅ 전체 레인 |
| 회귀 레인 | ✅ 두 세대 — SDK 세션(legacy) · 프로브 세션(modern) |

**어떤 언어**로 작성된 서버든 사용 가능 — mcp-proof는 프로세스(또는 URL)와 대화하지, 코드베이스와 대화하지 않습니다.

## ⚙️ 한 단계 CI

```yaml
- uses: YuCPbit/mcp-proof@v0.8.0
  with:
    server-command: python my_server.py
    fixtures: fixtures/
```

서버가 ship-ready가 아니면 잡이 실패하고, 업로드용으로 `mcp-proof-report.html` / `.json` / `.junit.xml` / `.sarif`를 남깁니다.

## 🏗️ 감사 클린 템플릿에서 시작하기

감사가 아니라 서버를 만드는 쪽이라면, [`templates/server-starter/`](templates/server-starter/)는 처음부터 이 감사를 통과합니다 — 각 관행에 그것이 충족하는 체크 ID가 주석되어 있습니다.

## 🗺️ 로드맵

| | |
|---|---|
| **현재 — v0.8.0** | 효과 인지 연구 레인: 대역외 효과 관측, 프로브 기반 권한 분류, 잔존 권한 측정(`mcp-proof effects`, [`experiments/`](experiments/), [문서](docs/effect-aware-conformance.md)). 어노테이션 신뢰 시정. 새로 설계된 [평가 사이트](https://yucpbit.github.io/mcp-proof/evaluation/) |
| **v0.7.2** | 진실성 패치: 전체 문서 지문, 픽스처 해시 제거는 변조로 간주, 통일된 종료 코드 분류 |
| **다음** | 2026-07-28 심화(MRTR `input_required` 라운드트립) · CI에서 공식 스위트와 교차 검증 · 실제 프로바이더용 효과 옵저버 어댑터 |
| **이후** | 서명된 증거 번들(attestation) · 옵트인 의미론 레인 — 결정적 코어 완성까지 보류 |

릴리스 이력은 [CHANGELOG.md](CHANGELOG.md)에 있습니다.

## 🔍 한계

mcp-proof는 결정적으로 증명 가능한 것만 증명하며, 그 경계를 명시합니다:

- 보안 체크는 관측 가능한 프로토콜·메타데이터 표면을 다룹니다. 배포·소스·프로세스 증거가 필요한 MSSS 컨트롤은 언제나 **manual review** — 통과로 가정되지 않습니다.
- **인가 플로우는 납품 리포트의 범위 밖**입니다(공식 스위트가 auth 시나리오를 다룹니다). 효과 레인이 다루는 것은 authority-bearing한 *객체*이며, 통제된 테스트베드 위에서입니다 — 프로덕션 OAuth 배포를 감사하지 않습니다.
- **효과 레인은 측정 기기이지 블랙박스 레인이 아닙니다.** 관측 채널(SQLite 스토어, jail 디렉터리)이 필요하며, 관측할 수 없는 것은 `unknown`/SKIP으로 보고될 뿐 없다고 가정되지 않습니다. 수치는 테스트베드 탐지 성능이지 프로덕션 유병률이 아닙니다([상세](docs/effect-aware-conformance.md)).
- 자동 베이스라인은 보수적 이름 휴리스틱을 사용합니다. v0.8부터 검증되지 않은 `readOnlyHint`는 이를 무시하지 못합니다. 프로덕션 서버로 베이스라인을 기록하기 전에 스킵 목록을 검토하세요.
- 의미적 정확성(답의 *의미*가 맞는가)은 설계상 결정적 코어 밖에 있습니다.

## 📄 라이선스

MIT — MSSS 준수 섹션의 분류 체계는 [MCP Server Security Standard](https://mcp-security-standard.org)(CC BY-SA 4.0)를 따릅니다.
