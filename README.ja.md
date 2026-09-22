<div align="center">

# 🧾 mcp-proof

### MCP サーバーを、「レシート」付きで納品する。

**MCP サーバーをワイヤレベルで監査。プロトコル準拠・セキュリティ・回帰 — そして効果 — の証拠を、再現可能でオフライン検証可能な 1 通の納品レポートに。**

`stdio + Streamable HTTP · 2026-07-28 と legacy の両世代 · HTML / JSON / JUnit / SARIF`

[![ci](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml/badge.svg)](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11+-blue)](pyproject.toml)
[![checks](https://img.shields.io/badge/checks-32_modern_·_27_legacy_·_6_security_·_4_effect-6a5acd)](src/mcpproof/checks/)
[![transports](https://img.shields.io/badge/transports-stdio_·_HTTP-informational)](src/mcpproof/client_http.py)
[![license](https://img.shields.io/badge/license-MIT-black)](LICENSE)

[English](README.md) · [简体中文](README.zh-CN.md) · **日本語** · [한국어](README.ko.md) · [Français](README.fr.md)

<a href="https://yucpbit.github.io/mcp-proof/report-filesystem.html"><img src="demo/report-filesystem.png" width="760" alt="公式 MCP filesystem サーバーに対する mcp-proof 納品レポート — SHIP-READY、MUST チェック 11/11、MSSS 準拠表、リプレイ 34/34 クリーン"></a>

**[ライブレポートを見る →](https://yucpbit.github.io/mcp-proof/)** · **[効果認識評価 →](https://yucpbit.github.io/mcp-proof/evaluation/)**

*公式 MCP filesystem サーバーの実監査：準拠チェック 27 項目、MSSS 準拠表、回帰リプレイ 34 回 — ship-ready、勧告 1 件。*

</div>

---

## 🚀 クイックスタート

```bash
pip install git+https://github.com/YuCPbit/mcp-proof
mcp-proof run python my_server.py --fixtures fixtures/ --record-if-missing --out report.html
```

稼働中の HTTP サーバーを監査する場合：`mcp-proof run --url http://localhost:8000/mcp --out report.html`

終了コードがそのままゲートです。**`0`** — すべての MUST チェックに合格、ブロッキングなセキュリティ所見なし、挙動ドリフトなし。**`1`** — 監査は完了し、サーバーが不合格。**`2`** — 監査自体が完了せず、どちらの方向にもサーバーの証拠にはならない。

```bash
mcp-proof plan python my_server.py                             # 自動ベースラインが何をなぜ呼ぶか
mcp-proof record python my_server.py --fixtures fixtures/      # 挙動契約を凍結
mcp-proof replay --fixtures fixtures/ -- python my_server.py   # ドリフトがあれば失敗
mcp-proof inspect python my_server.py --out baseline.json      # 契約面を凍結
mcp-proof diff baseline.json current.json                      # BREAKING / ADDITIVE / METADATA、breaking で exit 1
mcp-proof verify report.json                                   # レポートのフィンガープリントをオフライン再検証
mcp-proof effects --sqlite state.db -- python my_server.py     # 宣言された効果 vs 観測された外部効果（v0.8）
```

組み込みのデモペア（クリーンなサーバーと 9 件の違反を仕込んだサーバー）で、60 秒で違いを確認：

```bash
mcp-proof run python demo/good_server.py --fixtures demo/fixtures-good --out report-good.html   # → SHIP-READY
mcp-proof run python demo/bad_server.py --out report-bad.html                                    # → MUST 失敗 5 件、セキュリティ所見 3 件
```

## 🔬 4 つのレーン

| レーン | 答える問い | 方法 |
|---|---|---|
| **プロトコル準拠** | サーバーはワイヤ上で MCP を正しく実装しているか？ | 手書き JSON-RPC プローブが生のバイトストリームを観察 — 世代ネゴシエーション、エラー意味論、3 つのサーフェス、ページネーション、stdout 衛生、検証済みネガティブプローブ |
| **セキュリティと衛生** | 公開されたツールメタデータはクリーンか？ | 決定的静的解析 — 注入指示、不可視 Unicode、漏洩シークレット、無制約の実行面 — 各所見を MSSS コントロール ID に対応付け |
| **挙動回帰** | サーバーは納品時と厳密に同じ挙動か？ | SHA-256 フィンガープリント付きゴールデンフィクスチャの記録/リプレイ。fail-closed の完全性ゲートを通過後、ドリフトを重大度で分類 |
| **効果準拠**（v0.8、研究向け） | ツールが世界に及ぼす効果は宣言と一致するか？ | 帯域外オブザーバーが各呼び出し前後の外部状態を diff し、プローブが生成物を実際に行使 — [評価サイト](https://yucpbit.github.io/mcp-proof/evaluation/)参照 |

全レーンが 1 通のレポートに集約され、優先度順の修正リストで締めくくられるため、そのまま是正計画として使えます。

## ✨ 内部のしくみ

- **ワイヤレベルのチェックを、全サーフェス・全ページ・両世代で。** 現代世代（2026-07-28：`server/discover`、`_meta` エンベロープ、`resultType`、`ttlMs`/`cacheScope`、`-32022`、ルーティングヘッダー）32 項目、legacy 世代 27 項目。ページネーション収集器は 1 つに統一され、2 ページ目に隠れた違反も 1 ページ目と同様に監査されます。
- **検証済みネガティブプローブ。** TOOL-07 は宣言スキーマに*証明可能に*違反する入力を送ります（スキーマ有効なベースラインの 1 フィールドだけを変異させ、両側を `jsonschema` で証明）。平然と応答するサーバーはフラグされ、ハングはそれ自体が所見であり拒否とは決して数えません。
- **公開標準に紐づくセキュリティチェック。** 全公開ツールに対する 6 種の決定的スキャン。スキーマウォーカーは `$ref`/`allOf`/ネストを見通します — [MCP Server Security Standard](https://mcp-security-standard.org) の 24 コントロール行列に対応付けられ、判定が証拠を超えることはありません：**met** / **partial** / **gap** / **manual review**。
- **他者を裁く前に自らを検証する回帰スイート。** フィクスチャは契約ごとの SHA-256 と順序依存のマニフェスト指紋を持ち、改竄・欠落・重複 — ハッシュ自体の削除さえ — がリプレイを中止させます。構造化/JSON 値の変化は最低でも `VALUE` ドリフト。`"approved"→"denied"` が cosmetic として通ることはあり得ません。
- **役割の異なる 2 つのフィンガープリント。** `behavior_sha256` はサーバーの挙動のみ（マシン間で再現可能）。`run_hash` は文書全体を減算方式で封印。`mcp-proof verify` は両方をオフラインで再計算 — 内部一貫性の証明であり、署名ではありません。
- **保守的な呼び出し計画。** 自動ベースラインは変更系に見えるツールをスキップ。v0.8 以降、MCP アノテーションは注意を*加える*ことしかできません — 未検証の `readOnlyHint` がツールを自動呼び出し可能にすることはなくなり、仕様の「アノテーションは信頼できない」という立場に一致します。
- **CI 用の契約 diff。** `inspect` は完全ページネーション済みの提供面を指紋付きマニフェストに凍結（半分だけの凍結は拒否）。`diff` は `BREAKING` / `ADDITIVE` / `METADATA` を分類 — スキーマの厳格化、enum の縮小、任意→必須の反転、安全アノテーションの弱体化はすべて breaking です。
- **設計としての再現性。** LLM 呼び出しゼロ、API キーゼロ、決定的な引数合成。同一のサーバー挙動はどのマシンでも同一のフィンガープリントを再現します。

## 🧪 効果認識研究レーン（v0.8）

プロトコル準拠は、サーバーが MCP を正しく*話している*かを問います。効果レーンはツールの**世界への効果**が宣言と一致するかを問います — ツールの応答ではなく外部状態を帯域外で読み、名前や永続性を信じる代わりに生成物を**実際に行使**することによって。

```bash
python experiments/run_all.py         # クリーン状態から E1–E3 → experiments/results/index.html
python experiments/make_report.py     # 旗艦の効果証拠レポート
```

帯域外グラウンドトゥルースを持つ統制された合成テストベッドでの測定値（仕込んだ不一致に対する検出性能であり、**本番環境の有病率ではありません**）：

| 性質 | プローブ / 効果観測 | 最良ベースライン |
|---|---|---|
| アノテーション虚偽の検出（応答に現れない 3 件を含む） | precision / recall **1.000 / 1.000** | 1.000 / 0.333 |
| authority-bearing か単に永続的か | 精度 **1.000** | 0.875（名前）· 0.625（永続性） |
| ライフサイクルイベント後：有効か単に列挙されているだけか | 精度 **1.000**、残存権限の見逃し 0 | 0.500 · 0.333、見逃し 1 |

通常の監査器には見えない 2 つの発見：`readOnlyHint: true` のツールが密かに API キーを鋳造 — 応答は普通の読み取りに見えるのに、状態 diff がそれを捕捉。そして API キーは**それを承認した grant の失効後も有効なまま** — 残存権限（residual authority）は、オブジェクトの存在から推定するのではなく、行使プローブで測定されます。

方法論・オラクル・ベースライン・限界の全文：[docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) · ライブ結果：[評価サイト](https://yucpbit.github.io/mcp-proof/evaluation/)。

## ✅ 検証

- **151 テスト**。監査器自身を攻撃する敵対的スイートを含みます：2 ページ目に隠した違反、改竄されたフィクスチャとマニフェスト、ハッシュ剥離ダウングレード、書き換えられたレポート判定 — さらに効果レーン独自の敵対セット（応答に現れない虚偽は帯域外でのみ捕捉可能、永続 ≠ 権限、プローブなし → `unknown` → SKIP）。
- **Linux・macOS・Windows × Python 3.11–3.13 の CI**、加えて実サーバーをエンドツーエンドで監査するクリーンインストールのパッケージングジョブ。
- **公式 v2 SDK と双方向のクロス検証**（`scripts/crosscheck_modern_server.py`）。
- **あらゆる場所で fail-closed**：監査が証明できないものはすべて exit `2` と安定した 1 行で終わります — トレースバックなし、黙って縮小される監査なし、対象への不利な証拠になることもありません。

## 📊 実監査・実レポート

| 対象 | 判定 | レポート |
|---|---|---|
| **公式 filesystem サーバー** | ✅ SHIP-READY — 11/11 MUST、34/34 リプレイクリーン、書き込み系ツール 4 つを自動スキップ | [ライブ](https://yucpbit.github.io/mcp-proof/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| **公式 "everything" サーバー** | ✅ SHIP-READY — 20/20 MUST + 7/7 SHOULD、13 ツールでセキュリティ所見 0（記録は意図的にスキップ：`get-env` ツールが環境変数をダンプするため） | [ライブ](https://yucpbit.github.io/mcp-proof/report-everything.html) |
| **公式 memory サーバー** | ✅ SHIP-READY — 16/16 MUST、4/4 リプレイ、勧告 1 件（無制約の `search_nodes.query`） | [ライブ](https://yucpbit.github.io/mcp-proof/report-memory.html) |
| **公式 sequential-thinking サーバー** | ✅ SHIP-READY — 11/11 MUST。誠実な TOOL-08 SKIP を追ったところ、提供 inputSchema が実行時必須フィールドを欠いていることが判明 | [ライブ](https://yucpbit.github.io/mcp-proof/report-sequential-thinking.html) |
| **2026-07-28 現代世代サーバー**（依存ゼロ、SDK クロス検証済み） | ✅ SHIP-READY — 世代自動検出、ネガティブプローブ込みで 23/23 MUST | [ライブ](https://yucpbit.github.io/mcp-proof/report-modern.html) |
| **9 件の違反**を仕込んだデモサーバー | ❌ NOT SHIP-READY — MUST 失敗 5 件 + セキュリティ所見 5 件、すべて証拠付きで捕捉 | [ライブ](https://yucpbit.github.io/mcp-proof/report-bad.html) |
| **効果テストベッド `silent-keymint` 変異体** | ❌ EFF-01 FAIL — 読み取り専用と注釈されたツールが API キーを鋳造。帯域外で捕捉 | [効果証拠](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-silent-keymint.html) |

## 🧭 公式 conformance スイートとの関係

MCP プロジェクトは [`modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance)（auth フローを含むプロトコル挙動のシナリオテスト）を保守しています。プロトコルの証明にはそちらを。mcp-proof はもう半分 — **納品証拠** — のために存在します：クライアントが保管できる指紋付きオフライン検証可能レポート、MSSS 対応付け、fail-closed の挙動回帰、CI ゲートとしての契約 diff、SARIF/JUnit 成果物、そして効果準拠の研究レーン。両者は補完関係です。

## 📡 プロトコルサポート

| | |
|---|---|
| トランスポート | stdio ✅ · Streamable HTTP ✅ |
| サーフェス | tools ✅ · resources ✅ · prompts ✅ — 双方向の capability 認識 |
| 現代世代 `2026-07-28`（`server/discover`、ステートレス `_meta`） | ✅ 自動検出 — `--era auto\|modern\|legacy` |
| Legacy 世代（initialize ハンドシェイク、`2024-11-05` → `2025-11-25`） | ✅ 全レーン |
| 回帰レーン | ✅ 両世代 — SDK セッション（legacy）· プローブセッション（modern） |

**どの言語**で書かれたサーバーにも使えます — mcp-proof が対話するのはプロセス（または URL）であり、コードベースではありません。

## ⚙️ ワンステップ CI

```yaml
- uses: YuCPbit/mcp-proof@v0.8.0
  with:
    server-command: python my_server.py
    fixtures: fixtures/
```

サーバーが ship-ready でなければジョブは失敗し、`mcp-proof-report.html` / `.json` / `.junit.xml` / `.sarif` をアップロード用に残します。

## 🏗️ 監査クリーンなテンプレートから始める

監査ではなくサーバーを作る側なら、[`templates/server-starter/`](templates/server-starter/) は最初からこの監査に合格します — 各プラクティスに、それが満たすチェック ID が注釈されています。

## 🗺️ ロードマップ

| | |
|---|---|
| **現在 — v0.8.0** | 効果認識研究レーン：帯域外の効果観測、プローブによる権限分類、残存権限の測定（`mcp-proof effects`、[`experiments/`](experiments/)、[ドキュメント](docs/effect-aware-conformance.md)）。アノテーション信頼の是正。刷新された[評価サイト](https://yucpbit.github.io/mcp-proof/evaluation/) |
| **v0.7.2** | 真実性パッチ：全文書フィンガープリント、フィクスチャのハッシュ剥離は改竄扱い、統一された終了コード分類 |
| **次** | 2026-07-28 の深化（MRTR `input_required` ラウンドトリップ）· CI での公式スイートとのクロス検証 · 実プロバイダー向け効果オブザーバーアダプター |
| **その後** | 署名付き証拠バンドル（attestation）· オプトインの意味論レーン — 決定的コアの完成まで保留 |

リリース履歴は [CHANGELOG.md](CHANGELOG.md) に。

## 🔍 限界

mcp-proof は決定的に証明できるものだけを証明し、その境界を明示します：

- セキュリティチェックは観測可能なプロトコルとメタデータ面を対象とします。デプロイ・ソース・プロセスの証拠を要する MSSS コントロールは常に **manual review** — 合格と見なされることはありません。
- **認可フローは納品レポートの範囲外**です（公式スイートが auth シナリオを扱います）。効果レーンが扱うのは authority-bearing な*オブジェクト*であり、統制されたテストベッド上でのこと — 本番の OAuth 環境を監査するものではありません。
- **効果レーンは測定器であり、ブラックボックスのレーンではありません。** 観測チャネル（SQLite ストア、jail ディレクトリ）が必要で、観測できないものは `unknown`/SKIP と報告され、存在しないとは決して仮定されません。数値はテストベッドでの検出性能であり、本番の有病率ではありません（[詳細](docs/effect-aware-conformance.md)）。
- 自動ベースラインは保守的な名前ヒューリスティックを使います。v0.8 以降、未検証の `readOnlyHint` はこれを上書きしません。本番サーバーでベースラインを記録する前にスキップ一覧を確認してください。
- 意味的正しさ（答えの*意味*が正しいか）は、設計上、決定的コアの外にあります。

## 📄 ライセンス

MIT — MSSS 準拠セクションの分類は [MCP Server Security Standard](https://mcp-security-standard.org)（CC BY-SA 4.0）に従います。
