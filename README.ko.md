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

종료 코드가 곧 게이트입니다. **`0`** — 모든 MUST 체크 통과, 차단급 보안 발견 없음(권고는 남아 있어도 됨), 행위 드리프트 없음. **`1`** — 감사는 완료되었고 서버가 불합격. **`2`** — 감사 자체가 완료되지 않아(베이스라인 없음, 감사기 내부 오류) 어느 방향으로도 서버에 대한 증거가 되지 않음.

```bash
mcp-proof plan python my_server.py                             # 자동 베이스라인이 무엇을, 왜 호출하는지
mcp-proof record python my_server.py --fixtures fixtures/      # 행위 계약 동결
mcp-proof replay --fixtures fixtures/ -- python my_server.py   # 드리프트 발생 시 실패
mcp-proof inspect python my_server.py --out baseline.json      # 계약 표면 동결
mcp-proof diff baseline.json current.json                      # BREAKING / ADDITIVE / METADATA, breaking이면 exit 1
mcp-proof verify report.json                                   # 리포트 내부 지문을 오프라인 재검증
mcp-proof effects --sqlite state.db -- python my_server.py     # 선언된 효과 vs 관측된 외부 효과 (v0.8)
```

내장 데모 한 쌍 — 깨끗한 서버와 9곳에 위반을 심은 서버 — 으로 60초 만에 차이를 확인:

```bash
mcp-proof run python demo/good_server.py --fixtures demo/fixtures-good --out report-good.html   # → SHIP-READY
mcp-proof run python demo/bad_server.py --out report-bad.html                                    # → MUST 실패 5건, 보안 발견 3건
```

## 🔬 네 개의 레인

| 레인 | 증명하는 것 | 방식 |
|---|---|---|
| **프로토콜 준수** | 서버가 와이어에서 MCP를 올바르게 구현한다 — 세대 협상, JSON-RPC 오류 의미론, tool/resource/prompt 표면, 출력 스키마, capability 일관성, 페이지네이션, stdout 위생 | 수제 JSON-RPC 프로브가 원시 바이트 스트림을 관찰하므로 SDK가 매끈하게 다듬는 것이 없음 |
| **보안·위생** | 툴 메타데이터가 깨끗하다: 주입 지시문, 보이지 않는 유니코드, 유출 시크릿, 무제약 실행 표면 없음 | 결정적 정적 분석, 발견마다 해당 MSSS 컨트롤 ID를 지님 |
| **행위 회귀** | 서버가 납품 시점과 정확히 같은 행위를 한다 | 출처 지문이 붙은 골든 픽스처의 기록/리플레이, 드리프트를 심각도로 분류 |
| **효과 준수** (v0.8, 연구 레인) | 툴이 외부 상태에 미친 관측 효과가 선언 어노테이션과 일치한다; 생성물은 이름이 아니라 프로브로 분류된다 | 대역외 옵저버가 호출 전후로 서버의 상태 저장소를 스냅샷하고, 프로브가 생성물을 행사 — 관측 채널 필요, 아래 참조 |

네 레인이 하나의 리포트로 모이고, 리포트는 우선순위가 매겨진 수정 목록으로 끝나 그대로 시정 계획이 됩니다.

## ✅ 검증

감사 도구는 자신이 감사하는 대상보다 더 많은 신뢰를 얻어야 합니다. 모든 릴리스 뒤에는:

- **151개 테스트**, 감사기 자신을 공격하는 적대적 스위트 포함: 페이지네이션 2페이지에 숨긴 위반, 변조된 픽스처와 매니페스트, 해시 제거 다운그레이드 시도, 판정 배너가 수정된 리포트, 과거에 빠져나가던 드리프트 유형, 유효하지 않은 합성 베이스라인 — 효과 레인에도 자체 적대 세트가 있습니다: 읽기 전용으로 주석되었지만 자격 증명을 발급해 대역외로만 탐지 가능한 툴, authority-bearing으로 분류되어서는 안 되는 지속 객체, 그리고 프로브 없는 감사에서 권한 판정이 통과가 아니라 `unknown`/SKIP으로 강등되는지.
- **Linux·macOS·Windows × Python 3.11 / 3.12 / 3.13 CI**, 더해서 wheel을 빌드하고 새로 설치한 뒤 실제 서버에 실제 감사를 돌려 본 다음에야 출하하는 패키징 잡.
- **공식 v2 SDK와 양방향 교차 검증**: 공식 클라이언트가 `server/discover`를 통해 mcp-proof의 수제 모던 테스트 서버를 받아들이고, mcp-proof는 공식 v2 SDK 서버에 대해 두 전송 모두에서 전부 초록(`scripts/crosscheck_modern_server.py`).
- **설계상 fail-closed**: 끊긴 페이지네이션, 변조되었거나 검증 불가한 픽스처, 없는 베이스라인, 감사기 내부 오류 — 각각이 감사를 요란하게 멈춥니다. 모든 커맨드가 같은 분류로 답합니다: exit `2`와 안정된 한 줄. 트레이스백 없음, 조용히 축소되는 감사 없음, 대상에 불리한 증거가 되는 일도 없음.
- **오프라인 검증 가능한 리포트**: `mcp-proof verify report.json`은 리포트 자체 필드에서 두 지문을 재계산합니다. 문서 지문은 독자가 보는 모든 것 — 판정 배너, 감사 상태, 요약 카운터, MSSS 표, 다음 단계 — 을 덮으므로 사후 편집은 무엇이든 검증을 깨뜨립니다. 이는 내부 일관성 증명이지 서명이 아닙니다(attestation은 로드맵에 있음).

## ✨ 내부 구조

- 🔍 **와이어 레벨 프로토콜 체크를 모든 표면·모든 페이지·두 세대에서** — mcp-proof는 서버에 원시 JSON-RPC로 말을 걸고 세대를 자동 감지합니다: 2026-07-28 모던 세대에 32개 체크(`server/discover`, `_meta` 엔벨로프 강제, `resultType`, 캐시 가능한 모든 결과의 `ttlMs`/`cacheScope`, `-32022` 버전 거부, HTTP 라우팅 헤더 강제), initialize 핸드셰이크 세대에 27개 — 정확한 오류 코드, 스키마 유효성, 구조화 출력, stdout 위생, 세 리스트 표면의 페이지네이션 안전성, 전용 resources·prompts 레인, 그리고 **검증된 네거티브 프로브**: TOOL-07은 선언된 inputSchema를 증명 가능하게 위반하는 입력(스키마 유효한 베이스라인에서 정확히 한 필드만 변이)을 보내고, 서버가 태연히 응답하면 경고합니다 — 행(hang)은 그 자체로 별도의 발견이며 결코 거부로 계산되지 않습니다. 페이지네이션 수집기는 전 레인에 하나뿐이라 2페이지에 숨은 툴도 1페이지처럼 감사됩니다.
- 🛡️ **공개 표준에 연결된 보안 감사** — 모든 페이지의 모든 공개 툴에 6개의 결정적 체크(툴 설명 포이즈닝, 보이지 않는/bidi 문자, 유출 자격 증명, 무제약 주입 표면, 광고된 셸 실행). 스키마 워커는 `$ref`/`allOf`/중첩/배열 요소를 꿰뚫습니다 — `config.shell.command`는 한 단계 아래에도 숨지 못합니다. 각 체크는 [MCP Server Security Standard](https://mcp-security-standard.org)의 24개 컨트롤 매트릭스(완전 문서화 23 + 미래 컨트롤 `MCP-DEPLOY-04` 플레이스홀더)의 정규 컨트롤 ID에 매핑되고, 판정이 증거를 넘지 않는 준수표로 렌더링됩니다: 완전한 직접 증거는 **met**, 깨끗하지만 간접적인 증거는 **partial**, 체크가 볼 수 없는 컨트롤은 **manual review**.
- 🧪 **응답이 아니라 세계를 읽는 효과 체크 (v0.8)** — 관측 채널을 설정하면(SQLite 백엔드 서버는 `--sqlite`, 격리 디렉터리는 파일시스템 옵저버), 효과 레인은 매 호출 전후로 외부 상태를 스냅샷하고 객체별 create/update/delete 효과로 diff하여 유발한 호출에 귀속시킵니다. 네 개의 체크가 이를 선언 어노테이션과 대조합니다: EFF-01(`readOnlyHint: true` 툴이 관측 가능한 쓰기를 일으키지 않음), EFF-02(관측된 삭제는 `destructiveHint` 툴에서 나옴), EFF-03(`idempotentHint` 툴의 동일 인자 재호출은 무동작), EFF-06(생성된 자격 증명의 지속 유효성이 그것을 승인한 grant에 여전히 의존함 — 후보 의존을 대역외로 철회하고 객체를 재행사한 뒤 복원하여 확립). 효과 레코드의 모든 필드는 알게 된 방식 — `declared`/`observed`/`probed`/`unknown` — 을 지니며, 채널이 없는 차원은 통과 대신 SKIP합니다.
- 📼 **클라이언트가 보관하고, 남을 판정하기 전에 스스로를 검증하는 회귀 스위트** — 두 프로토콜 세대 모두에서 기록. 골든 픽스처는 SHA-256 출처로 서버 행위를 동결하며 모든 콘텐츠 유형을 포함합니다(바이너리는 다이제스트로 저장되어, 바꿔치기된 이미지가 OK로 리플레이될 수 없음). 리플레이 전 무결성 게이트가 모든 계약 해시와 매니페스트 지문을 재계산합니다: 누락·변조·중복·잔존 픽스처는 조용히 건너뛰는 대신 리플레이를 중단시킵니다 — 픽스처의 저장 해시를 지우는 것은 옛 스키마가 아니라 변조로 계산되고, 계약 해시 이전의 베이스라인은 `--allow-legacy-fixtures`로 명시적으로 옵트인하지 않는 한 거부됩니다. 리플레이는 모든 드리프트를 분류하고(`BREAKING` / `VALUE` / `COSMETIC` / `LATENCY`) — 구조화/JSON 값 변화는 최소 `VALUE`, 뒤집힌 `"approved"→"denied"`가 cosmetic으로 통과할 수 없음 — 상태 의존 호출 순서를 보존합니다(연번 픽스처, 순서 민감 지문). 베이스라인은 결코 암묵적으로 생성되지 않습니다: 픽스처가 없으면 `run`은 fail-closed하며, `--record-if-missing`으로 옵트인해야만 기록합니다.
- 📄 **사람과 기계 모두를 위한 리포트** — 자체 완결 HTML: 고정 내비게이션, 체크별 앵커(`report.html#SEC-03`), attention/passed 필터, 증거 범위 카드, 접이식 MSSS 매트릭스. 인쇄는 `--pdf`. 같은 버전 모델이 `--json`(스키마 v3), 아무 CI용 `--junit`, GitHub Security 탭용 `--sarif`로도 출력됩니다. 효과 레인은 자체 증거 페이지를 렌더링합니다: 선언 어노테이션과 관측 효과를 나란히, 응답만 보는 감사기가 읽었을 내용, 생성된 객체들, 프로브의 권한/의존 판정 — 각 값에 알게 된 방식 태그가 붙습니다.
- 🔁 **설계된 재현성** — LLM 호출 0, API 키 0. 역할이 정직하게 분리된 두 지문: `behavior_sha256`은 서버 행위만으로 계산되고(체크 판정, 리플레이 판정, 프로토콜 사실 — 타임스탬프·지연·실행 커맨드·감사기 버전은 절대 포함 안 함), 동일한 서버 행위는 어느 머신에서든 동일하게 지문화됩니다. `run_hash`는 리포트 문서 전체 — 증거, 판정 배너, 감사 상태, 요약, MSSS 표 — 를 휘발성 타임스탬프 블록만 빼고 동결합니다. `mcp-proof verify`가 둘 다 오프라인으로 재검증: 사후 편집을 전부 깨뜨리는 내부 일관성 증명이지 서명이 아닙니다. 수용은 신뢰가 아니라 검증입니다.
- 🧯 **보수적 호출 계획과 v0.8의 신뢰 시정** — 자동 베이스라인은 보수적 이름/설명 휴리스틱으로 툴을 분류하고, `mcp-proof plan`은 무엇이 어떤 근거로 호출될지를 프로덕션에 닿기 전에 정확히 보여 줍니다. v0.8부터 MCP 어노테이션은 주의를 *더할* 수만 있습니다: `destructiveHint: true`는 여전히 스킵을 강제하지만, 검증되지 않은 `readOnlyHint: true`가 변경성으로 보이는 툴을 자동 호출 집합으로 구제하는 일은 더 이상 없습니다 — 스펙은 클라이언트가 어노테이션을 신뢰하지 말아야 한다(MUST)고 명시하며, 효과 레인이 존재하는 이유가 바로 "읽기 전용" 툴도 자격 증명을 발급할 수 있기 때문입니다. `--include-destructive`와 `--edge-cases`로 명시적으로 범위를 넓힐 수 있습니다.
- 📋 **CI를 위한 계약 diff** — `mcp-proof inspect`는 제공 표면(capabilities + tools + resources + prompts, 완전 페이지네이션, "부재"와 "빈 것"을 구분 기록)을 지문 있는 매니페스트로 동결합니다 — 페이지네이션이 완주되지 못하면 아예 기록을 거부합니다. 표면의 절반을 "베이스라인"으로 동결하면 빠진 절반에 대한 이후의 모든 diff가 보이지 않게 되기 때문입니다. 휘발성 와이어 메타데이터는 키 이름이 아니라 위치로 제거되므로, 우연히 `ttlMs`나 `nextCursor`라는 이름의 사용자 스키마 속성은 계약에 남습니다. `mcp-proof diff`는 모든 변경을 `BREAKING` / `ADDITIVE` / `METADATA`로 분류하고 breaking이면 비영으로 종료합니다 — 스키마 강화, enum 축소, 선택→필수 반전, 출력 필드 제거, 안전 어노테이션 약화가 전부 breaking입니다.

## 📊 실제 감사, 실제 리포트

| 대상 | 판정 | 리포트 |
|---|---|---|
| **공식 filesystem 서버** (`@modelcontextprotocol/server-filesystem`) | ✅ SHIP-READY — 11/11 MUST, 34/34 리플레이 클린, 쓰기 툴 4개 자동 스킵 | [라이브](https://yucpbit.github.io/mcp-proof/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| **공식 "everything" 레퍼런스 서버** (`@modelcontextprotocol/server-everything`) | ✅ SHIP-READY — 20/20 MUST + 7/7 SHOULD, 툴 13개에 보안 발견 0. 프로토콜 + 보안 레인; 기록은 의도적으로 스킵 — `get-env` 툴이 환경 변수를 덤프 | [라이브](https://yucpbit.github.io/mcp-proof/report-everything.html) |
| **공식 memory 서버** (`@modelcontextprotocol/server-memory`) | ✅ SHIP-READY — 16/16 MUST, 4/4 리플레이 클린, 쓰기/삭제 툴 5개 자동 스킵, 권고 1건: 무제약 `search_nodes.query`(SEC-04) | [라이브](https://yucpbit.github.io/mcp-proof/report-memory.html) |
| **공식 sequential-thinking 서버** (`@modelcontextprotocol/server-sequential-thinking`) | ✅ SHIP-READY — 11/11 MUST, 1/1 리플레이 클린, 권고 1건(2,781자 툴 설명, SEC-05); 정직한 TOOL-08 SKIP을 추적하다 제공 inputSchema가 런타임 필수 필드를 누락했음을 발견 | [라이브](https://yucpbit.github.io/mcp-proof/report-sequential-thinking.html) |
| **2026-07-28 모던 세대 서버** (무의존, 공식 v2 SDK와 교차 검증) | ✅ SHIP-READY — `server/discover`로 세대 자동 감지, 네거티브 프로브 포함 23/23 MUST, 2/2 리플레이 | [라이브](https://yucpbit.github.io/mcp-proof/report-modern.html) |
| **위반 9곳**을 심은 데모 서버 | ❌ NOT SHIP-READY — MUST 실패 5건 + 보안 발견 5건(차단 3, 권고 2), 전부 증거와 함께 포착 | [라이브](https://yucpbit.github.io/mcp-proof/report-bad.html) |
| 얌전한 데모 서버 | ✅ SHIP-READY — 18/18 MUST, 회귀 베이스라인 포함 전 레인 통과 | [라이브](https://yucpbit.github.io/mcp-proof/report-good.html) |
| **효과 테스트베드 `silent-keymint` 변이** | ❌ EFF-01 FAIL — `readOnlyHint: true`로 주석된 툴이 평범한 읽기 응답을 반환하면서 `api_keys` 테이블에 행을 삽입; 대역외 상태 diff가 그 쓰기를 해당 호출에 귀속 | [효과 증거](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-silent-keymint.html) |

## 🧪 효과 인지 연구 레인 (v0.8)

세 납품 레인은 와이어에서 멈춥니다: 그들의 "행위" 정의는 응답 바이트 스트림입니다. 효과 레인은 같은 "선언 vs 관측" 방법을 한 단계 더 깊이 확장합니다. 구성 요소를 구체적으로:

- **옵저버** (`effects/observe.py`): 매 툴 호출 전후로 외부 상태 — 파일을 직접 읽는 SQLite 저장소, 또는 디렉터리 트리 — 를 스냅샷하고, 두 스냅샷을 객체별 create/update/delete 델타로 diff합니다. 무엇이 바뀌었는지 툴에게 묻지 않으므로, 응답이 언급하든 말든 효과는 보입니다.
- **프로브** (`effects/probes.py`): 생성된 객체를 자격 증명 삼아 서비스의 실제 인가 규칙에 대고 *실제로 사용*해 봅니다. 그래서 "authority-bearing"은 관측된 결과(그 객체가 어떤 동작을 인가했다)이지 필드 이름에서의 추측이 아니고, "아직 유효"는 프로브가 지금 성공한다는 것이지 객체가 아직 목록에 있다는 게 아닙니다.
- **계보, 세 개의 독립 필드로 유지**: `created_via`(어느 호출이 객체를 만들었나 — 관측), `authorized_by`(세션이 어느 grant 아래에서 돌았나 — 선언), `depends_on`(지속 유효성이 실제로 무엇을 요구하나 — 각 후보를 대역외로 철회하고 재행사한 뒤 복원하여 확립). 이 구분이 핵심입니다: 어느 grant에 `authorized_by`되었지만 `depends_on`에 그 grant가 없는 API 키는 grant 철회를 살아남습니다.
- **테스트베드** (`testbed/`): 결정적 SQLite 백엔드 MCP 서버. 평범한 지속 객체(노트)와 자격 증명 객체(API 키, webhook, 공유 링크), 1비트 grant, 라이프사이클 툴, 그리고 한 번에 정확히 하나의 어노테이션 거짓을 심는 변이 플래그를 가집니다 — 문서화된 실제 사고 패턴(권한을 발급하는 읽기 경로, 캐스케이드하지 않는 철회)을 본떴습니다. 그라운드 트루스는 `testbed/saas_oracle.py`가 대역외로 읽으며, 감사 대상 MCP 표면을 결코 거치지 않습니다.

세 실험이 그 위에서 돌아갑니다(`python experiments/run_all.py`, 결정적, 두 번 실행해도 JSON이 바이트 단위로 동일). 수치는 이 통제된 환경에서 심어 둔 불일치에 대한 탐지 성능입니다 — **프로덕션 유병률이 아닙니다**:

| 실험 | 프로브 / 효과 관측 | 베이스라인 |
|---|---|---|
| **E1** — 선언 효과 vs 관측 효과. 정직한 서버 + 단일 거짓 6개 변이; 오라클 = 변이 장부 | precision / recall **1.000 / 1.000** | 응답 레벨 1.000 / 0.333 · 이름 휴리스틱 1.000 / 0.333 |
| **E2** — authority-bearing vs 단순 지속. `api_key_backup`이라는 이름의 미끼 노트와 지속되지 않은 자격 증명을 포함한 8객체 코퍼스; 오라클 = 구성상의 권한 라벨 | 정확도 **1.000** | 이름 키워드 0.875 · 지속⇒권한 0.625 |
| **E3** — 존재 vs 현재 유효성. 6개 라이프사이클 시나리오(grant 철회, 키 철회, 키 삭제, TTL 만료, 캐스케이드); 오라클 = 시나리오별 의도된 유효성 | 정확도 **1.000**, 거짓 무효 0 | 존재 0.500 · grant 상태 0.333, 거짓 무효 1 |

이 레인을 뒷받침하는 두 결과: E1에서 효과가 응답에 전혀 나타나지 않는 세 거짓(`silent-keymint`, `shadow-webhook`, `phantom-write`)은 상태 diff만이 잡아냅니다 — 응답 레벨 감사기는 그것들에 구조적으로 눈이 멀고, 그것이 두 베이스라인의 recall이 0.333에 머무는 이유입니다. E3의 `grant_revoked` 시나리오에서는 grant 아래에서 생성된 키가 grant 철회 후에도 유효한 채입니다(테스트베드의 인가 규칙은 키 자신의 행을 볼 뿐 grant를 보지 않습니다 — 문서화된 OAuth 앱 잔존 사고와 같은 모양). grant 상태라는 프록시는 그것을 무력화되었다고 보고하며, 그것이 표의 유일하고 위험한 거짓 무효입니다.

방법론, 오라클 설계, 베이스라인, 관련 연구와 한계: [docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) · 원시 증거가 딸린 결과: [평가 사이트](https://yucpbit.github.io/mcp-proof/evaluation/) · 재현: [experiments/README.md](experiments/README.md).

## 🧭 공식 conformance 스위트와의 관계

MCP 프로젝트는 [`modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance) — auth 플로우를 포함해 서버와 클라이언트의 프로토콜 행위를 검증하는 시나리오 테스트 — 를 관리합니다. 프로토콜 정합성 베이스라인이 필요하면 그것을 돌리세요. mcp-proof의 준수 레인은 자체 와이어 레벨 프로브로 겹치는 영역을 커버합니다.

mcp-proof는 공식 스위트가 하지 않는 나머지 절반 — **납품 증거** — 을 위해 존재합니다. 클라이언트가 보관할 수 있는 지문 있는 오프라인 검증 가능 리포트, MSSS 보안 매핑, fail-closed 무결성 게이트를 갖춘 골든 행위 회귀, CI 게이트로서의 계약 스냅샷/diff, SARIF/JUnit 산출물, 그리고 효과 준수 연구 레인. 공식 스위트로 프로토콜을 증명하고, mcp-proof로 납품을 증명하세요 — 둘은 조합되며, 공식 스위트와의 교차 검증은 로드맵에 있습니다.

## 📡 프로토콜 지원

| | |
|---|---|
| 전송 | stdio ✅ · Streamable HTTP ✅ |
| 표면 | tools ✅ · resources ✅ · prompts ✅ — 양방향 capability 인지 |
| 모던 세대 `2026-07-28` (`server/discover`, 무상태 `_meta`) | ✅ 준수 레인, 자동 감지 — `--era auto\|modern\|legacy` |
| Legacy 세대 (initialize 핸드셰이크, `2024-11-05` → `2025-11-25`) | ✅ 전체 레인 |
| 회귀 레인 | ✅ 두 세대 — SDK 세션(legacy) · 프로브 세션(modern) |

**어떤 언어**로 작성된 서버든 사용할 수 있습니다 — mcp-proof는 프로세스(또는 URL)와 대화하지, 코드베이스와 대화하지 않습니다.

## ⚙️ 한 단계 CI

```yaml
- uses: YuCPbit/mcp-proof@v0.8.0
  with:
    server-command: python my_server.py
    fixtures: fixtures/
```

서버가 ship-ready가 아니면 잡이 실패하고, 업로드용으로 `mcp-proof-report.html` / `.json` / `.junit.xml` / `.sarif`를 남깁니다. 원시 커맨드가 좋다면 `mcp-proof run … --junit r.xml --sarif r.sarif`에 `mcp-proof diff`를 더하면 같은 게이트입니다.

## 🏗️ 감사 클린 템플릿에서 시작하기

감사가 아니라 서버를 만드는 쪽이라면, [`templates/server-starter/`](templates/server-starter/)는 처음부터 이 감사를 통과하는 fastmcp 서버입니다 — 제약된 입력 스키마, 올바른 오류 의미론, 구조화 출력, 각 관행에 그것이 충족하는 체크 ID가 주석되어 있습니다. 복사하고, 툴을 구현하고, 감사하고, 리포트와 함께 납품하세요.

## 🖥️ 플랫폼

| | |
|---|---|
| macOS | ✅ 개발 및 완전 검증 |
| Linux | ✅ CI에서 실행 |
| Windows | ✅ CI에서 실행 (`--pdf`는 Chrome/Chromium 설치 필요) |

## 🗺️ 로드맵

| | |
|---|---|
| **현재 — v0.8.0** | 효과 인지 연구 레인: 대역외 효과 관측, 프로브 기반 권한 분류, 잔존 권한 측정(`mcp-proof effects`, [`experiments/`](experiments/), [문서](docs/effect-aware-conformance.md)); 어노테이션 신뢰 시정; [평가 사이트](https://yucpbit.github.io/mcp-proof/evaluation/) |
| **v0.7.2** | 진실성 패치: `verify`가 문서 전체를 지문화(리포트 스키마 v3), 픽스처 해시 제거는 변조 취급, legacy 베이스라인 fail-closed, 전 커맨드 통일 종료 코드 분류 |
| **다음** | 2026-07-28 심화: MRTR `input_required` 라운드트립 · CI에서 공식 스위트와 교차 검증 · 실제 프로바이더용 효과 옵저버 어댑터(효과 레인의 `Observer` 인터페이스는 이미 수용 가능) |
| **이후** | 서명된 증거 번들(attestation) · 옵트인 의미론 레인(LLM 채점 어서션) — 결정적 코어 완성까지 보류 |

릴리스 이력은 [CHANGELOG.md](CHANGELOG.md)에 있습니다.

## 🔍 한계

mcp-proof는 결정적으로 증명 가능한 것만 증명하며, 어느 것이 어느 쪽인지 명시합니다:

- 보안 체크는 관측 가능한 프로토콜·메타데이터 표면을 다룹니다. 배포·소스·프로세스 증거가 필요한 MSSS 컨트롤은 언제나 **manual review**로 보고됩니다 — 통과로 가정되지 않습니다.
- **인가 플로우는 납품 리포트의 범위 밖**입니다: OAuth 핸드셰이크는 감사하지 않습니다(공식 스위트가 auth 시나리오를 다룹니다). 효과 레인이 추론하는 것은 툴이 생성하는 *authority-bearing 객체*이며, 대역외 옵저버를 갖춘 통제된 테스트베드 위에서입니다 — 프로덕션 OAuth 배포를 감사하지 않습니다.
- **효과 레인은 측정 기기이지 블랙박스 레인이 아닙니다.** 관측 채널(SQLite 저장소, 격리 디렉터리)이 필요하고, 관측할 수 없는 시스템에 대한 효과는 `unknown`/SKIP으로 보고될 뿐 없다고 가정되지 않습니다. 수치는 합성 테스트베드에서의 탐지 성능이지 프로덕션 유병률이 아닙니다. [docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) §7 참조.
- 자동 베이스라인은 보수적 이름/설명 휴리스틱으로 툴을 분류합니다. v0.8부터 검증되지 않은 `readOnlyHint`는 이를 무시하지 못합니다. 프로덕션 서버에 대해 기록된 베이스라인을 신뢰하기 전에 fixtures 매니페스트의 스킵 목록을 검토하세요.
- 의미적 정확성(답의 *의미*가 맞는가)은 설계상 결정적 코어 밖에 있습니다.

## 📄 라이선스

MIT — MSSS 준수 섹션의 분류 체계는 [MCP Server Security Standard](https://mcp-security-standard.org)(CC BY-SA 4.0)를 따릅니다.
