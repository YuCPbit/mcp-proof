<div align="center">

# 🧾 mcp-proof

### MCP サーバーを、「レシート」付きで納品する。

**MCP サーバーをワイヤレベルで監査する。プロトコル準拠・セキュリティ・回帰 — そして効果 — の証拠を、再現可能でオフライン検証可能な 1 通の納品レポートに。**

**v0.8 は準拠監査を応答境界の下まで拡張します —— ツールは `readOnlyHint: true` を宣言し、ごく普通の応答を返しながら、それを承認した grant の失効後も使える資格情報を鋳造できてしまうからです。** 帯域外オブザーバーが実際の外部効果を読み、プローブがツールの生成物の権限を実際に行使します。**[→ 研究レーン](docs/effect-aware-conformance.md)**

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

終了コードがそのままゲートです。**`0`** — すべての MUST チェックに合格、ブロッキングなセキュリティ所見なし（勧告は残ってよい）、挙動ドリフトなし。**`1`** — 監査は完了し、サーバーが不合格。**`2`** — 監査自体が完了せず（ベースライン欠落、監査器の内部エラー）、どちらの方向にもサーバーの証拠にはならない。

```bash
mcp-proof plan python my_server.py                             # 自動ベースラインが何を・なぜ呼ぶか
mcp-proof record python my_server.py --fixtures fixtures/      # 挙動契約を凍結
mcp-proof replay --fixtures fixtures/ -- python my_server.py   # ドリフトがあれば失敗
mcp-proof inspect python my_server.py --out baseline.json      # 契約面を凍結
mcp-proof diff baseline.json current.json                      # BREAKING / ADDITIVE / METADATA、breaking で exit 1
mcp-proof verify report.json                                   # レポート内部のフィンガープリントをオフライン再検証
mcp-proof effects --sqlite state.db -- python my_server.py     # 宣言された効果 vs 観測された外部効果（v0.8）
mcp-proof effects --fs-root data/ -- python my_server.py       # 同じレーン、ディレクトリバックエンドのサーバー向け
```

組み込みのデモペア（クリーンなサーバーと、9 件の違反を仕込んだサーバー）で 60 秒で違いを確認：

```bash
mcp-proof run python demo/good_server.py --fixtures demo/fixtures-good --out report-good.html   # → SHIP-READY
mcp-proof run python demo/bad_server.py --out report-bad.html                                    # → MUST 失敗 5 件、セキュリティ所見 3 件
```

## 🔬 4 つのレーン

| レーン | 証明すること | 方法 |
|---|---|---|
| **プロトコル準拠** | サーバーがワイヤ上で MCP を正しく実装している — 世代ネゴシエーション、JSON-RPC エラー意味論、tool/resource/prompt の各サーフェス、出力スキーマ、capability 整合性、ページネーション、stdout 衛生 | 手書き JSON-RPC プローブが生のバイトストリームを観察するため、SDK に均されるものが何もない |
| **セキュリティと衛生** | ツールメタデータがクリーンである：注入指示、不可視 Unicode、漏洩シークレット、無制約の実行面がない | 決定的静的解析。各所見が対応する MSSS コントロール ID を携行 |
| **挙動回帰** | サーバーが納品時と厳密に同じ挙動をしている | 来歴フィンガープリント付きゴールデンフィクスチャの記録/リプレイ、ドリフトを重大度で分類 |
| **効果準拠**（v0.8、研究レーン） | ツールが外部状態に及ぼした観測効果が宣言アノテーションと一致する。生成物は名前ではなくプローブで分類される | 帯域外オブザーバーが各呼び出しの前後でサーバーの状態ストアをスナップショットし、プローブが生成物を行使する — 観測チャネル（`--sqlite` / `--fs-root`）が必要、下記参照。自作テストベッドだけでなく、3 つのサードパーティサーバーで実証済み |

全レーンが 1 通のレポートに集約され、レポートは優先度順の修正リストで終わるため、そのまま是正計画として使えます。

## ✅ 検証

監査ツールは、監査対象よりも多くの信頼を稼がなければなりません。各リリースの背後にあるもの：

- **160 テスト**。監査器自身を攻撃する敵対的スイートを含みます：ページネーションの 2 ページ目に隠した違反、改竄されたフィクスチャとマニフェスト、ハッシュ剥離によるダウングレード試行、判定バナーを書き換えたレポート、かつて擦り抜けていたドリフト類、無効な合成ベースライン — 効果レーンにも独自の敵対セットがあります：帯域外でしか検出できない、読み取り専用と注釈されつつ資格情報を鋳造するツール；authority-bearing と分類されてはならない永続オブジェクト；プローブなしの監査では権限判定が合格ではなく `unknown`/SKIP に退化すること；そして create+delete を同時に行う呼び出しがヘッドライン効果の陰に削除を隠せないこと。
- **Linux・macOS・Windows × Python 3.11 / 3.12 / 3.13 の CI**。加えてパッケージングジョブが wheel をビルドし、まっさらな環境にインストールし、実サーバーへの実監査を走らせてからでないと何も出荷されません — さらに **experiments ジョブが E1–E3 をゼロから再実行し、出力がコミット済み結果とバイト単位で一致しなければ失敗します**：再現性の主張は口約束ではなく CI が強制します。
- **自作ではないサーバーで実証済み**：公開されているサードパーティ MCP サーバー 3 つ（公式リファレンスサーバー 2 つとコミュニティ製 1 つ — 3 種類のストア、アノテーション有り / 無しの両方）へのケーススタディ監査。証拠はコミット済み — 下記の効果レーンの節を参照。
- **公式 v2 SDK と双方向のクロス検証**：公式クライアントは `server/discover` 経由で mcp-proof の手書きモダンテストサーバーを受け入れ、mcp-proof は公式 v2 SDK サーバーに対して両トランスポートで全緑（`scripts/crosscheck_modern_server.py`）。
- **設計としての fail-closed**：壊れたページネーション、改竄または検証不能なフィクスチャ、欠落したベースライン、監査器の内部エラー — どれも監査を声高に停止させます。すべてのコマンドが同じ分類で答えます：exit `2` と安定した 1 行。トレースバックなし、黙って縮小される監査なし、対象への不利な証拠になることもなし。
- **オフライン検証可能なレポート**：`mcp-proof verify report.json` はレポート自身のフィールドから両フィンガープリントを再計算します。文書フィンガープリントは読者の目に入るすべて — 判定バナー、監査ステータス、集計カウンター、MSSS 表、次のステップ — を覆うため、事後の編集はどれも検証を壊します。これは内部一貫性の証明であり、署名ではありません（attestation はロードマップ上）。

## ✨ 内部のしくみ

- 🔍 **ワイヤレベルのプロトコルチェックを、全サーフェス・全ページ・両世代で** — mcp-proof はサーバーに生の JSON-RPC で話しかけ、世代を自動検出します：2026-07-28 モダン世代に 32 チェック（`server/discover`、`_meta` エンベロープ強制、`resultType`、キャッシュ可能な全結果の `ttlMs`/`cacheScope`、`-32022` バージョン拒否、HTTP ルーティングヘッダー強制）、initialize ハンドシェイク世代に 27 チェック — 正確なエラーコード、スキーマ妥当性、構造化出力、stdout 衛生、3 つのリストサーフェスのページネーション安全性、専用の resources / prompts レーン、そして**検証済みネガティブプローブ**：TOOL-07 は宣言 inputSchema に証明可能に違反する入力（スキーマ有効なベースラインの 1 フィールドだけを変異）を送り、サーバーが平然と応答すれば警告します — ハングはそれ自体が所見で、拒否と数えられることは決してありません。ページネーション収集器は全レーンで 1 つに統一され、2 ページ目に隠れたツールも 1 ページ目と同様に監査されます。
- 🛡️ **公開標準に紐づくセキュリティ監査** — 全ページの全公開ツールに 6 種の決定的チェック（ツール説明のポイズニング、不可視/bidi 文字、漏洩資格情報、無制約の注入面、公言されたシェル実行）。スキーマウォーカーは `$ref`/`allOf`/ネスト/配列要素を見通します — `config.shell.command` は一段下にも隠れられません。各チェックは [MCP Server Security Standard](https://mcp-security-standard.org) の 24 コントロール行列（完全文書化 23 + 将来コントロール `MCP-DEPLOY-04` のプレースホルダー）の正規コントロール ID に対応し、判定が証拠を超えない準拠表として描画されます：完全な直接証拠は **met**、クリーンだが間接的な証拠は **partial**、チェックの見えないコントロールは **manual review**。
- 🧪 **応答ではなく世界を読む効果チェック（v0.8）** — 観測チャネルを設定すると（SQLite バックエンドのサーバーには `--sqlite`、ディレクトリバックエンドには `--fs-root`）、効果レーンは各呼び出しの前後で外部状態をスナップショットし、オブジェクトごとの create/update/delete 効果に diff して、原因となった呼び出しに帰属させます（op はターゲットごとに記録されるため、move が create の陰に delete を隠すことはできません）。4 つのチェックがそれを宣言アノテーションと突き合わせます。仕様のセマンティクスに厳密に従い — 既定値は悲観的なので、*欠落した* ヒントが咎められることはなく、観測効果が反証する明示的な主張だけが対象です：EFF-01（`readOnlyHint: true` のツールが観測可能な書き込みを起こしていない）、EFF-02（明示的な `destructiveHint: false` の下で観測される削除がない）、EFF-03（`idempotentHint` ツールの同一引数の再呼び出しが無操作）、EFF-06（生成された資格情報の有効性が、それを承認した grant に依然として依存している — 候補依存を帯域外で失効させ、オブジェクトを再行使し、元に戻すことで確立）。効果レコードの全フィールドは知られ方 — `declared` / `observed` / `probed` / `unknown` — を携行し、チャネルのない次元は合格ではなく SKIP します。
- 📼 **クライアントの手元に残り、他者を裁く前に自らを検証する回帰スイート** — 両世代で記録可能。ゴールデンフィクスチャは SHA-256 来歴でサーバー挙動を凍結し、あらゆるコンテンツ型を含みます（バイナリはダイジェスト化されるため、すり替えた画像が OK としてリプレイされることはない）。リプレイ前に完全性ゲートが全契約ハッシュとマニフェスト指紋を再計算します：欠落・改竄・重複・陳腐化したフィクスチャは黙ってスキップされるのではなくリプレイを中止させます — フィクスチャの保存ハッシュを削除するのは旧スキーマではなく改竄と数えられ、契約ハッシュ以前のベースラインは `--allow-legacy-fixtures` の明示オプトインなしには拒否されます。リプレイはあらゆるドリフトを分類し（`BREAKING` / `VALUE` / `COSMETIC` / `LATENCY`）— 構造化/JSON 値の変化は最低でも `VALUE`、反転した `"approved"→"denied"` が cosmetic として通ることはない — ステートフルな呼び出し順序を保持します（連番フィクスチャ、順序依存フィンガープリント）。ベースラインが暗黙に作られることはありません：フィクスチャが無ければ `run` は fail-closed し、`--record-if-missing` で明示的にオプトインしたときのみ記録します。
- 📄 **人と機械の両方のためのレポート** — 自己完結 HTML：スティッキーナビゲーション、チェック別アンカー（`report.html#SEC-03`）、attention/passed フィルター、証拠範囲カード、折りたたみ式 MSSS 行列。印刷には `--pdf`。同じバージョン付きモデルが `--json`（スキーマ v3）、任意の CI 向け `--junit`、GitHub Security タブ向け `--sarif` としても出力されます。効果レーンは独自の証拠ページを描画します：宣言アノテーションと観測効果を並置し、応答しか見ない監査器が読んだはずの内容、生成されたオブジェクト、プローブの権限/依存判定を、各値の知られ方タグ付きで示します。
- 🔁 **設計としての再現性** — LLM 呼び出しゼロ、API キーゼロ。役割を正直に分けた 2 つのフィンガープリント：`behavior_sha256` はサーバー挙動のみから計算され（チェック判定、リプレイ判定、プロトコル事実 — タイムスタンプ、レイテンシ、起動コマンド、監査器バージョンは決して含まない）、同一のサーバー挙動はどのマシンでも同一に指紋化されます。`run_hash` はレポート文書全体 — 証拠、判定バナー、監査ステータス、集計、MSSS 表 — を揮発性のタイムスタンプブロックだけを除いて凍結します。`mcp-proof verify` は両方をオフラインで再検証：事後編集をすべて壊す内部一貫性の証明であって、署名ではありません。受け入れは信頼ではなく検証です。
- 🧯 **保守的な呼び出し計画と、v0.8 の信頼是正** — 自動ベースラインは保守的な名前/説明ヒューリスティックでツールを分類し、`mcp-proof plan` は本番に触れる前に、何が・どんな根拠で呼ばれるかを正確に表示します。v0.8 以降、MCP アノテーションは注意を*加える*ことしかできません：`destructiveHint: true` は引き続きスキップを強制しますが、未検証の `readOnlyHint: true` が変更系に見えるツールを自動呼び出し集合に救い上げることはもうありません — 仕様はクライアントにアノテーションを信頼するなと命じており、効果レーンが存在する理由はまさに「読み取り専用」ツールでも資格情報を鋳造できるからです。`--include-destructive` と `--edge-cases` で明示的に範囲を広げられます。
- 📋 **CI のための契約 diff** — `mcp-proof inspect` は提供面（capabilities + tools + resources + prompts、完全ページネーション、「不在」と「空」を区別して記録）を指紋付きマニフェストに凍結します — ページネーションが完走できない場合は書き込み自体を拒否します。半分だけの面を「ベースライン」として凍結すれば、欠けた半分に対する以後のすべての diff が不可視になるからです。揮発性のワイヤメタデータはキー名ではなく位置で除去されるため、たまたま `ttlMs` や `nextCursor` という名のユーザースキーマプロパティは契約に残ります。`mcp-proof diff` はすべての変更を `BREAKING` / `ADDITIVE` / `METADATA` に分類し、breaking で非ゼロ終了します — スキーマの厳格化、enum の縮小、任意→必須の反転、出力フィールドの削除、安全アノテーションの弱体化はすべて breaking です。

## 📊 実監査・実レポート

| 対象 | 判定 | レポート |
|---|---|---|
| **公式 filesystem サーバー**（`@modelcontextprotocol/server-filesystem`） | ✅ SHIP-READY — 11/11 MUST、34/34 リプレイクリーン、書き込み系ツール 4 つを自動スキップ | [ライブ](https://yucpbit.github.io/mcp-proof/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| **公式 "everything" リファレンスサーバー**（`@modelcontextprotocol/server-everything`） | ✅ SHIP-READY — 20/20 MUST + 7/7 SHOULD、13 ツールでセキュリティ所見 0。プロトコル + セキュリティレーン。記録は意図的にスキップ — `get-env` ツールが環境変数をダンプするため | [ライブ](https://yucpbit.github.io/mcp-proof/report-everything.html) |
| **公式 memory サーバー**（`@modelcontextprotocol/server-memory`） | ✅ SHIP-READY — 16/16 MUST、4/4 リプレイクリーン、書き込み/削除系 5 ツールを自動スキップ、勧告 1 件：無制約の `search_nodes.query`（SEC-04） | [ライブ](https://yucpbit.github.io/mcp-proof/report-memory.html) |
| **公式 sequential-thinking サーバー**（`@modelcontextprotocol/server-sequential-thinking`） | ✅ SHIP-READY — 11/11 MUST、1/1 リプレイクリーン、勧告 1 件（2,781 文字のツール説明、SEC-05）。誠実な TOOL-08 SKIP を調査したところ、提供 inputSchema が実行時必須フィールドを欠いていることが判明 | [ライブ](https://yucpbit.github.io/mcp-proof/report-sequential-thinking.html) |
| **2026-07-28 モダン世代サーバー**（依存ゼロ、公式 v2 SDK とクロス検証） | ✅ SHIP-READY — `server/discover` で世代自動検出、ネガティブプローブ込みで 23/23 MUST、2/2 リプレイ | [ライブ](https://yucpbit.github.io/mcp-proof/report-modern.html) |
| **9 件の違反**を仕込んだデモサーバー | ❌ NOT SHIP-READY — MUST 失敗 5 件 + セキュリティ所見 5 件（ブロッキング 3、勧告 2）、すべて証拠付きで捕捉 | [ライブ](https://yucpbit.github.io/mcp-proof/report-bad.html) |
| 行儀のよいデモサーバー | ✅ SHIP-READY — 18/18 MUST、回帰ベースライン込みの全レーン合格 | [ライブ](https://yucpbit.github.io/mcp-proof/report-good.html) |
| **効果テストベッド `silent-keymint` 変異体** | ❌ EFF-01 FAIL — `readOnlyHint: true` と注釈されたツールが普通の読み取り応答を返しつつ `api_keys` テーブルに行を挿入。帯域外の状態 diff がその書き込みを当該呼び出しに帰属させる | [効果証拠](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-silent-keymint.html) |
| **効果ケーススタディ：公式 memory サーバー**（JSONL ストア、全ツールにアノテーション） | ✅ EFF-01/02/03 PASS — readOnly 宣言・destructive 宣言・冪等性宣言のすべてが帯域外観測の下で成立。`delete_entities` の再呼び出しも含む。権限次元は正直に SKIP（プローブチャネルなし） | [効果証拠](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-case-memory.html) |
| **効果ケーススタディ：公式 filesystem サーバー**（隔離ディレクトリ、標準オブザーバー） | ✅ EFF-01/02/03 PASS — 10 の readOnly ツールは何も書かず、`move_file` の観測された削除はその `destructiveHint` に覆われる — この呼び出しが EFF-02 のヘッドラインのみを見る盲点を露呈させ（そして修正させ）た | [効果証拠](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-case-filesystem.html) |
| **効果ケーススタディ：コミュニティ SQLite サーバー**（`@executeautomation/database-server`、アノテーションなし） | ✅ 正直な退化 — 何も宣言されていないため EFF-01/03 は SKIP。観測された `DELETE` は仕様の悲観的既定値と整合。標準の `--sqlite` チャネルで効果は行単位で帰属されたまま | [効果証拠](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-case-sqlite.html) |

## 🧪 効果認識研究レーン（v0.8）

3 つの納品レーンはワイヤで止まります：それらの「挙動」の定義は応答のバイトストリームです。効果レーンは同じ「宣言 vs 観測」の方法を一段深く延長します。構成要素を具体的に：

- **オブザーバー**（`effects/observe.py`）：各ツール呼び出しの前後で外部状態 — ファイルを直接読む SQLite ストア、またはディレクトリツリー — をスナップショットし、2 つのスナップショットをオブジェクトごとの create/update/delete 差分に diff します。何が変わったかをツールに尋ねることは決してないため、応答が言及しようがしまいが効果は見えます。
- **プローブ**（`effects/probes.py`）：生成されたオブジェクトを資格情報として、サービスの実際の認可規則に対して*実際に使おうと*試みます。したがって「authority-bearing」は観測された結果（そのオブジェクトがある操作を認可した）であり、フィールド名からの推測ではありません。「まだ有効」とはプローブがいま成功することであり、オブジェクトがまだ列挙されていることではありません。
- **系譜は 3 つの独立フィールドのまま**：`created_via`（どの呼び出しがオブジェクトを産んだか — 観測）、`authorized_by`（セッションがどの grant の下で走ったか — 宣言）、`depends_on`（継続的な有効性が実際に何を要するか — 各候補を帯域外で失効させ、再行使し、復元することで確立）。この区別こそが要点です：ある grant に `authorized_by` されつつ `depends_on` にその grant を含まない API キーは、grant の失効を生き延びます。
- **テストベッド**（`testbed/`）：決定的な SQLite バックエンドの MCP サーバー。普通の永続オブジェクト（ノート）と資格情報オブジェクト（API キー、webhook、共有リンク）、1 ビットの grant、ライフサイクルツール、そして 1 回につき正確に 1 つのアノテーション虚偽を植える変異フラグを持ちます — 文書化された実際のインシデントパターン（権限を鋳造する読み取りパス、カスケードしない失効）をモデルにしています。グラウンドトゥルースは `testbed/saas_oracle.py` が帯域外で読み、監査対象の MCP サーフェスを決して経由しません。

3 つの実験がそれに対して走ります（`python experiments/run_all.py` — 決定的パイプラインで、CI が再実行してバイト単位の一致を強制します）。3 つは役割が異なります — E1 は検出実験、E2 は構成概念の妥当性検証（persistence と authority の区別が運用上実在すること）、E3 はライフサイクル測定（存在 ≠ 現在の有効性）。数値はこの統制環境での、仕込んだ不一致に対する検出性能です — **本番の有病率ではありません**：

| 実験 | プローブ / 効果観測 | ベースライン |
|---|---|---|
| **E1 · 検出** — 宣言効果 vs 観測効果。正直なサーバー + 単一虚偽の 6 変異体。オラクル = 変異台帳 | precision / recall **1.000 / 1.000** | 応答レベル 1.000 / 0.333 · 名前ヒューリスティック 1.000 / 0.333 |
| **E2 · 構成概念の検証** — authority-bearing か単なる永続か。`api_key_backup` という名の囮ノートと、永続しなかった資格情報を含む 8 オブジェクトコーパス。オラクル = 構成上の権限ラベル | 両シグナルを分離するために構築したコーパス上で精度 **1.000** | 名前キーワード 0.875 · 永続⇒権限 0.625 |
| **E3 · ライフサイクル測定** — 存在 vs 現在の有効性。6 つのライフサイクルシナリオ（grant 失効、キー失効、キー削除、TTL 満了、カスケード）。オラクル = シナリオごとの意図された有効性 | 精度 **1.000**、偽無効 0 | 存在 0.500 · grant 状態 0.333、偽無効 1 |

このレーンを動機づける 2 つの結果：E1 では、効果が応答に一切現れない 3 つの虚偽（`silent-keymint`、`shadow-webhook`、`phantom-write`）は状態 diff だけが捕捉します — 応答レベルの監査器はそれらに対して構造的に盲目であり、これが両ベースラインの再現率が 0.333 にとどまる理由です。E3 の `grant_revoked` シナリオでは、grant の下で生成されたキーが grant 失効後も有効なままです（テストベッドの認可規則はキー自身の行を見て grant を見ません — 文書化された OAuth アプリ残存インシデントと同じ形）。grant 状態というプロキシはそれを無効化済みと報告し、それが表の中の唯一の危険な偽無効です — `authorized_by` を `depends_on` であるかのように読んでしまった結果です。

**テストベッドの外でも**：3 つのケーススタディが同じ計測器を公開サードパーティサーバーに向けます — 公式 memory サーバー（JSONL ストア、全アノテーション）、公式 filesystem サーバー（隔離ディレクトリ、標準オブザーバー、全アノテーション）、コミュニティ SQLite サーバー（アノテーション皆無）。検証可能な宣言はすべて成立し、何も宣言されていない箇所ではチェックが判定を捏造せず SKIP しました。さらに filesystem の実行は EFF-02 初版実装の実在する盲点（create+delete を同時に行う呼び出しのヘッドライン効果が削除を隠す）を露呈させ、これは修正済みでテストに固定されています。プローブ側は終始正直に `unknown` のままでした — これらのサービスは行使可能な資格情報を鋳造しないためです — したがってプローブによる権限判定はテストベッド検証のままです。証拠：[評価サイトのケーススタディ](https://yucpbit.github.io/mcp-proof/evaluation/#cases)。

方法論、オラクル設計、ベースライン、関連研究、限界：[docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) · 生の証拠付き結果：[評価サイト](https://yucpbit.github.io/mcp-proof/evaluation/) · 再現手順：[experiments/README.md](experiments/README.md)。

## 🧭 公式 conformance スイートとの関係

MCP プロジェクトは [`modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance) — auth フローを含む、サーバーとクライアントのプロトコル挙動を検証するシナリオテスト — を保守しています。プロトコル正しさのベースラインが必要ならそれを走らせてください。mcp-proof の準拠レーンは独自のワイヤレベルプローブから重なる領域をカバーします。

mcp-proof は公式スイートがやらない残り半分 — **納品証拠** — のために存在します。クライアントが保管できる指紋付きオフライン検証可能レポート、MSSS セキュリティ対応付け、fail-closed の完全性ゲートを備えたゴールデン挙動回帰、CI ゲートとしての契約スナップショット/diff、SARIF/JUnit 成果物、そして効果準拠の研究レーン。公式スイートでプロトコルを証明し、mcp-proof で納品を証明する — 両者は組み合わさり、公式スイートとのクロス検証はロードマップ上にあります。

## 📡 プロトコルサポート

| | |
|---|---|
| トランスポート | stdio ✅ · Streamable HTTP ✅ |
| サーフェス | tools ✅ · resources ✅ · prompts ✅ — 双方向の capability 認識 |
| モダン世代 `2026-07-28`（`server/discover`、ステートレス `_meta`） | ✅ 準拠レーン、自動検出 — `--era auto\|modern\|legacy` |
| Legacy 世代（initialize ハンドシェイク、`2024-11-05` → `2025-11-25`） | ✅ 全レーン |
| 回帰レーン | ✅ 両世代 — SDK セッション（legacy）· プローブセッション（modern） |

**どの言語**で書かれたサーバーにも使えます — mcp-proof が話す相手はプロセス（または URL）であって、コードベースではありません。

## ⚙️ ワンステップ CI

```yaml
- uses: YuCPbit/mcp-proof@v0.8.1
  with:
    server-command: python my_server.py
    fixtures: fixtures/
```

サーバーが ship-ready でなければジョブは失敗し、アップロード用に `mcp-proof-report.html` / `.json` / `.junit.xml` / `.sarif` を残します。生のコマンドが好みなら、`mcp-proof run … --junit r.xml --sarif r.sarif` に `mcp-proof diff` を足せば同じゲートです。

## 🏗️ 監査クリーンなテンプレートから始める

監査ではなくサーバーを作る側なら、[`templates/server-starter/`](templates/server-starter/) は最初からこの監査に合格する fastmcp サーバーです — 制約付き入力スキーマ、正しいエラー意味論、構造化出力、各プラクティスにそれが満たすチェック ID が注釈されています。コピーし、ツールを実装し、監査し、レポートとともに納品を。

## 🖥️ プラットフォーム

| | |
|---|---|
| macOS | ✅ 開発・完全検証環境 |
| Linux | ✅ CI で実行 |
| Windows | ✅ CI で実行（`--pdf` には Chrome/Chromium が必要） |

## 🗺️ ロードマップ

| | |
|---|---|
| **現在 — v0.8.1** | 研究の強化：コミット済み証拠付きのサードパーティケーススタディ 3 件（公式 memory + filesystem サーバー、コミュニティ SQLite サーバー）。効果チェックは仕様のアノテーション既定値に厳密準拠（ヒントの欠落は決して咎めない）。ターゲット単位の削除帰属（create+delete でも削除は隠せない）。`--fs-root` 観測チャネル。CI 強制のバイト単位実験再現 |
| **v0.8.0** | 効果認識研究レーン：帯域外の効果観測、プローブによる権限分類、残存権限の測定（`mcp-proof effects`、[`experiments/`](experiments/)、[ドキュメント](docs/effect-aware-conformance.md)）。アノテーション信頼の是正。[評価サイト](https://yucpbit.github.io/mcp-proof/evaluation/) |
| **v0.7.2** | 真実性パッチ：`verify` が文書全体を指紋化（レポートスキーマ v3）、フィクスチャのハッシュ剥離は改竄扱い、legacy ベースラインは fail-closed、全コマンド統一の終了コード分類 |
| **次** | 2026-07-28 の深化：MRTR `input_required` ラウンドトリップ · CI での公式スイートとのクロス検証 · 実プロバイダー向け**プローブ**アダプター — 生成された資格情報を実プロバイダーに対して行使する。観測側はサードパーティサーバーで実証済み |
| **その後** | 署名付き証拠バンドル（attestation）· オプトインの意味論レーン（LLM 採点アサーション）— 決定的コアの完成まで保留 |

リリース履歴は [CHANGELOG.md](CHANGELOG.md) にあります。

## 🔍 限界

mcp-proof は決定的に証明できるものだけを証明し、どれがどれかを明言します：

- セキュリティチェックは観測可能なプロトコルとメタデータ面を対象とします。デプロイ・ソース・プロセスの証拠を要する MSSS コントロールは常に **manual review** と報告され、合格と見なされることはありません。
- **認可フローは納品レポートの範囲外**です：OAuth ハンドシェイクは監査しません（公式スイートが auth シナリオを扱います）。効果レーンが推論するのはツールが生成する *authority-bearing オブジェクト*であり、帯域外オブザーバーを備えた統制テストベッド上でのことです — 本番の OAuth 環境を監査するものではありません。
- **効果レーンは測定器であり、ブラックボックスのレーンではありません。** 観測チャネル（`--sqlite`、`--fs-root`）が必要で、観測できないシステムへの効果は `unknown`/SKIP と報告されるだけで、存在しないとは決して仮定されません。定量結果は合成テストベッドでの検出性能です — ケーススタディは計測器がサードパーティサーバーで動くことを示しますが、検証されたのは観測側だけであり、プローブによる権限 / 有効性判定はテストベッド検証のままです。[docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) §8 参照。
- 自動ベースラインは保守的な名前/説明ヒューリスティックでツールを分類します。v0.8 以降、未検証の `readOnlyHint` はこれを上書きしません。本番サーバーに対して記録されたベースラインを信頼する前に、fixtures マニフェストのスキップ一覧を確認してください。
- 意味的正しさ（答えの*意味*が正しいか）は、設計上、決定的コアの外にあります。

## 📄 ライセンス

MIT — MSSS 準拠セクションの分類は [MCP Server Security Standard](https://mcp-security-standard.org)（CC BY-SA 4.0）に従います。
