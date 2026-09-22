<div align="center">

# 🧾 mcp-proof

### 交付 MCP server，附上一张"收据"。

**从 wire 层审计 MCP server：协议一致性、安全、行为回归——以及效果——四类证据，汇成一份可复现、可离线验证的交付报告。**

`stdio + Streamable HTTP · 2026-07-28 与 legacy 双协议时代 · HTML / JSON / JUnit / SARIF`

[![ci](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml/badge.svg)](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11+-blue)](pyproject.toml)
[![checks](https://img.shields.io/badge/checks-32_modern_·_27_legacy_·_6_security_·_4_effect-6a5acd)](src/mcpproof/checks/)
[![transports](https://img.shields.io/badge/transports-stdio_·_HTTP-informational)](src/mcpproof/client_http.py)
[![license](https://img.shields.io/badge/license-MIT-black)](LICENSE)

[English](README.md) · **简体中文** · [日本語](README.ja.md) · [한국어](README.ko.md) · [Français](README.fr.md)

<a href="https://yucpbit.github.io/mcp-proof/report-filesystem.html"><img src="demo/report-filesystem.png" width="760" alt="mcp-proof 对官方 MCP filesystem server 的交付报告 — SHIP-READY，11/11 MUST 检查通过，完整 MSSS 合规表，34/34 重放干净"></a>

**[查看在线报告 →](https://yucpbit.github.io/mcp-proof/)** · **[效果感知评测 →](https://yucpbit.github.io/mcp-proof/evaluation/)**

*对官方 MCP filesystem server 的真实审计：27 项一致性检查、MSSS 合规表、34 次回归重放 — ship-ready，一条建议级发现。*

</div>

---

## 🚀 快速开始

```bash
pip install git+https://github.com/YuCPbit/mcp-proof
mcp-proof run python my_server.py --fixtures fixtures/ --record-if-missing --out report.html
```

审计运行中的 HTTP server：`mcp-proof run --url http://localhost:8000/mcp --out report.html`

退出码即门禁：**`0`** — 所有 MUST 检查通过、无阻断级安全发现、无行为漂移。**`1`** — 审计完成且目标未通过。**`2`** — 审计未完成，对目标不构成任何方向的证据。

```bash
mcp-proof plan python my_server.py                             # 自动基线会调用哪些工具、依据是什么
mcp-proof record python my_server.py --fixtures fixtures/      # 冻结行为契约
mcp-proof replay --fixtures fixtures/ -- python my_server.py   # 任何漂移即失败
mcp-proof inspect python my_server.py --out baseline.json      # 冻结契约面
mcp-proof diff baseline.json current.json                      # BREAKING / ADDITIVE / METADATA，breaking 时 exit 1
mcp-proof verify report.json                                   # 离线复核报告内部指纹
mcp-proof effects --sqlite state.db -- python my_server.py     # 声明效果 vs 观测到的外部效果（v0.8）
```

用内置的 demo 对照组 60 秒看出差别 —— 一个干净的 server 和一个埋了九处违规的 server：

```bash
mcp-proof run python demo/good_server.py --fixtures demo/fixtures-good --out report-good.html   # → SHIP-READY
mcp-proof run python demo/bad_server.py --out report-bad.html                                    # → 5 项 MUST 失败，3 条安全发现
```

## 🔬 四条审计通道

| 通道 | 回答的问题 | 方式 |
|---|---|---|
| **协议一致性** | server 在 wire 层是否正确实现了 MCP？ | 手写 JSON-RPC 探针直接观察原始字节流 —— 时代协商、错误语义、三个 surface、分页、stdout 卫生、经验证的否定探针 |
| **安全与卫生** | 对外声明的工具元数据是否干净？ | 确定性静态分析 —— 注入指令、隐形 Unicode、泄漏密钥、无约束执行面 —— 每条发现映射到 MSSS 控制 ID |
| **行为回归** | server 是否仍与交付时行为完全一致？ | 带 SHA-256 指纹的黄金 fixture 录制/重放，重放前先过 fail-closed 完整性门，漂移按严重度分级 |
| **效果一致性**（v0.8，研究向） | 工具对世界的实际效果是否与声明相符？ | 带外观测器在每次调用前后 diff 外部状态；探针实际行使创建出的对象 —— 见[评测站](https://yucpbit.github.io/mcp-proof/evaluation/) |

四条通道汇入同一份报告，报告以按优先级排序的修复清单收尾，可直接当整改计划用。

## ✨ 内部机制

- **wire 层检查覆盖每个 surface、每一页、两个协议时代。** 现代时代（2026-07-28：`server/discover`、`_meta` envelope、`resultType`、`ttlMs`/`cacheScope`、`-32022`、路由头）32 项，legacy 时代 27 项；所有通道共用一个分页收集器，藏在第 2 页的违规和第 1 页被同样审计。
- **经验证的否定探针。** TOOL-07 发送*可证明*违反声明 schema 的输入（schema 合法的基线上恰好变异一个字段，两端都用 `jsonschema` 证明）；正常应答者被标记，挂起本身是独立发现 —— 从不算作拒绝。
- **挂靠公开标准的安全检查。** 对每个声明工具做六类确定性扫描，schema walker 能穿透 `$ref`/`allOf`/嵌套 —— 映射到 [MCP Server Security Standard](https://mcp-security-standard.org) 的 24 项控制矩阵，结论从不超出证据：**met** / **partial** / **gap** / **manual review**。
- **先自证完整、再评判他人的回归套件。** fixture 携带逐合约 SHA-256 和顺序敏感的 manifest 指纹；篡改、缺失、重复 —— 甚至删掉哈希本身 —— 都会中止重放。任何结构化/JSON 值变化至少判 `VALUE` 级漂移；`"approved"→"denied"` 永远不可能混过 cosmetic。
- **两枚职责分明的指纹。** `behavior_sha256` 只覆盖 server 行为（跨机器可复现）；`run_hash` 用"做减法"封存整份文档。`mcp-proof verify` 离线复核两者 —— 这是内部一致性证明，不是签名。
- **保守的调用规划。** 自动基线跳过名字像变更操作的工具；自 v0.8 起 MCP annotation 只能*增加*谨慎 —— 未经验证的 `readOnlyHint` 不再让工具获得自动调用资格，与规范"annotation 不可信"的立场一致。
- **给 CI 用的契约 diff。** `inspect` 把完整分页后的服务面冻结成带指纹的 manifest（拒绝冻结半个面）；`diff` 分类 `BREAKING` / `ADDITIVE` / `METADATA` —— schema 收紧、enum 收窄、可选转必填、安全 annotation 被削弱都算 breaking。
- **可复现是设计出来的。** 零 LLM 调用、零 API key、确定性参数合成；相同的 server 行为在任何机器上产生相同指纹。

## 🧪 效果感知研究通道（v0.8）

协议一致性问的是 server 有没有把 MCP *说*对。效果通道问的是工具**对世界的效果**是否与声明相符 —— 通过带外读取外部状态（绝不读工具自己的响应），并**实际行使**创建出的对象，而不是相信名字或持久性。

```bash
python experiments/run_all.py         # 从干净状态跑 E1–E3 → experiments/results/index.html
python experiments/make_report.py     # 旗舰效果证据报告
```

在带外真值的受控合成 testbed 上测得（是对植入不一致的检测表现 —— **不是**生产环境流行度）：

| 性质 | 探针 / 效果观测 | 最好的 baseline |
|---|---|---|
| annotation 谎言检出（含 3 个响应不可见谎言） | precision / recall **1.000 / 1.000** | 1.000 / 0.333 |
| authority-bearing vs 仅仅持久 | 准确率 **1.000** | 0.875（名字）· 0.625（持久性） |
| 生命周期事件后：有效 vs 仅仅仍被列出 | 准确率 **1.000**，残留权威漏检 0 | 0.500 · 0.333，漏检 1 |

两个普通审计器看不见的发现：一个 `readOnlyHint: true` 的工具偷偷铸出 API key —— 响应看起来是普通读取，状态 diff 抓住了它；一个 API key 在**授权它的 grant 被撤销后仍然有效** —— 残留权威由行使探针测得，而不是从"对象还在"推断。

完整方法论、oracle、baseline 与局限：[docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) · 在线结果：[评测站](https://yucpbit.github.io/mcp-proof/evaluation/)。

## ✅ 验证

- **151 个测试**，含攻击审计器自身的对抗套件：藏在第 2 页的违规、被篡改的 fixture 与 manifest、剥离哈希的降级攻击、被改写的报告结论 —— 加上效果通道自己的对抗集（响应不可见的谎言只有带外能抓、持久 ≠ 权威、无探针 → `unknown` → SKIP）。
- **Linux、macOS、Windows × Python 3.11–3.13 的 CI**，外加全新安装打包任务，端到端审计真实 server。
- **与官方 v2 SDK 双向交叉验证**（`scripts/crosscheck_modern_server.py`）。
- **处处 fail-closed**：审计无法证明的一切都以 exit `2` 加一行稳定输出收场 —— 从无 traceback、从不悄悄缩小审计范围、从不构成对目标的指控。

## 📊 真实审计，真实报告

| 目标 | 结论 | 报告 |
|---|---|---|
| **官方 filesystem server** | ✅ SHIP-READY — 11/11 MUST，34/34 重放干净，4 个写类工具被自动跳过 | [在线报告](https://yucpbit.github.io/mcp-proof/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| **官方 "everything" server** | ✅ SHIP-READY — 20/20 MUST + 7/7 SHOULD，13 个工具 0 安全发现（刻意跳过录制：其 `get-env` 工具会倾倒环境变量） | [在线报告](https://yucpbit.github.io/mcp-proof/report-everything.html) |
| **官方 memory server** | ✅ SHIP-READY — 16/16 MUST，4/4 重放，一条建议级发现（无约束的 `search_nodes.query`） | [在线报告](https://yucpbit.github.io/mcp-proof/report-memory.html) |
| **官方 sequential-thinking server** | ✅ SHIP-READY — 11/11 MUST；追查其诚实的 TOOL-08 SKIP 时发现 served inputSchema 漏掉了一个运行时必需字段 | [在线报告](https://yucpbit.github.io/mcp-proof/report-sequential-thinking.html) |
| **2026-07-28 现代时代 server**（零依赖，经 SDK 交叉验证） | ✅ SHIP-READY — 时代自动探测，23/23 MUST 含否定探针 | [在线报告](https://yucpbit.github.io/mcp-proof/report-modern.html) |
| 埋有 **9 处违规**的 demo server | ❌ NOT SHIP-READY — 5 项 MUST 失败 + 5 条安全发现，每条都带证据被抓获 | [在线报告](https://yucpbit.github.io/mcp-proof/report-bad.html) |
| **效果 testbed 的 `silent-keymint` 变体** | ❌ EFF-01 FAIL — 标注只读的工具铸出 API key；被带外抓获 | [效果证据](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-silent-keymint.html) |

## 🧭 与官方 conformance 套件的关系

MCP 项目维护着 [`modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance) —— 覆盖协议行为（含 auth 流程）的场景测试。用它证明协议。mcp-proof 做的是它不做的那一半：**交付证据** —— 客户可留存的带指纹、可离线验证的报告，MSSS 映射，fail-closed 行为回归，作为 CI 门禁的契约 diff，SARIF/JUnit 产物，以及效果一致性研究通道。两者互补。

## 📡 协议支持

| | |
|---|---|
| 传输 | stdio ✅ · Streamable HTTP ✅ |
| Surface | tools ✅ · resources ✅ · prompts ✅ —— 双向能力感知 |
| 现代时代 `2026-07-28`（`server/discover`、无状态 `_meta`） | ✅ 自动探测 —— `--era auto\|modern\|legacy` |
| Legacy 时代（initialize 握手，`2024-11-05` → `2025-11-25`） | ✅ 全部通道 |
| 回归通道 | ✅ 双时代 —— SDK 会话（legacy）· 探针会话（modern） |

适用于**任何语言**编写的 server —— mcp-proof 对话的是进程（或 URL），不是你的代码库。

## ⚙️ 一步接入 CI

```yaml
- uses: YuCPbit/mcp-proof@v0.8.0
  with:
    server-command: python my_server.py
    fixtures: fixtures/
```

server 不达 ship-ready 则任务失败，并留下 `mcp-proof-report.html` / `.json` / `.junit.xml` / `.sarif` 供上传。

## 🏗️ 从审计洁净的模板起步

在写 server 而不是审计 server？[`templates/server-starter/`](templates/server-starter/) 开箱即通过本审计 —— 每条实践都标注了它满足的检查 ID。

## 🗺️ 路线图

| | |
|---|---|
| **当前 — v0.8.0** | 效果感知研究通道：带外效果观测、探针化权威分类、残留权威测量（`mcp-proof effects`、[`experiments/`](experiments/)、[文档](docs/effect-aware-conformance.md)）；annotation 信任修正；重设计的[评测站](https://yucpbit.github.io/mcp-proof/evaluation/) |
| **v0.7.2** | 真实性补丁：全文档指纹、剥离 fixture 哈希视同篡改、统一退出码分类 |
| **下一步** | 2026-07-28 深化（MRTR `input_required` 往返）· CI 内与官方套件交叉验证 · 真实 provider 的效果观测适配器 |
| **之后** | 签名证据包（attestation）· 可选语义通道 —— 在确定性内核完成前搁置 |

版本历史见 [CHANGELOG.md](CHANGELOG.md)。

## 🔍 局限

mcp-proof 只证明可被确定性证明的东西，并明确说出边界在哪：

- 安全检查覆盖可观测的协议与元数据面；需要部署、源码或流程证据的 MSSS 控制永远标 **manual review** —— 绝不默认通过。
- **授权流程不在交付报告范围内**（官方套件覆盖 auth 场景）。效果通道推理的是 authority-bearing 的*对象*，在受控 testbed 上 —— 它不审计生产 OAuth 部署。
- **效果通道是测量仪器，不是黑盒通道。** 它需要观测信道（SQLite 存储、jail 目录）；观测不到的报 `unknown`/SKIP，绝不假设为无。其数字是 testbed 检测表现，不是生产流行度（[详情](docs/effect-aware-conformance.md)）。
- 自动基线用保守的名字启发式；自 v0.8 起未经验证的 `readOnlyHint` 不再覆盖它。对生产 server 录制基线前请先审阅跳过清单。
- 语义正确性（答案的*含义*对不对）有意置于确定性内核之外。

## 📄 许可

MIT —— MSSS 合规节的分类学遵循 [MCP Server Security Standard](https://mcp-security-standard.org)（CC BY-SA 4.0）。
