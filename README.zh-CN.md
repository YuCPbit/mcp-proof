<div align="center">

# 🧾 mcp-proof

### 交付 MCP server，附上一张"收据"。

**从 wire 层审计 MCP server：协议一致性、安全、行为回归——以及效果——证据汇成一份可复现、可离线验证的交付报告。**

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

退出码即门禁：**`0`** — 所有 MUST 检查通过、无阻断级安全发现（建议级可以保留）、无行为漂移。**`1`** — 审计完成且 server 未通过。**`2`** — 审计未完成（缺基线、审计器内部错误），对 server 不构成任何方向的证据。

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

| 通道 | 证明什么 | 方式 |
|---|---|---|
| **协议一致性** | server 在 wire 层正确实现了 MCP —— 时代协商、JSON-RPC 错误语义、tool/resource/prompt 三个 surface、输出 schema、能力一致性、分页、stdout 卫生 | 手写 JSON-RPC 探针直接观察原始字节流，没有任何东西被 SDK 抹平 |
| **安全与卫生** | 工具元数据干净：没有注入指令、隐形 Unicode、泄漏的密钥、无约束的执行面 | 确定性静态分析，每条发现携带对应的 MSSS 控制 ID |
| **行为回归** | server 的行为与交付时完全一致 | 带来源指纹的黄金 fixture 录制/重放，漂移按严重度分级 |
| **效果一致性**（v0.8，研究通道） | 工具对外部状态的实际效果与其声明的 annotation 相符；创建出的对象靠探针分类，而不是靠名字 | 带外观测器在每次调用前后快照 server 的状态存储；探针实际行使创建出的对象 —— 需要观测信道，见下文 |

四条通道汇入同一份报告，报告以按优先级排序的修复清单收尾，可以直接当整改计划用。

## ✅ 验证

审计工具必须比它审计的东西赢得更多信任。每个版本背后有：

- **151 个测试**，含攻击审计器自身的对抗套件：藏在分页列表第 2 页的违规、被篡改的 fixture 与 manifest、剥离哈希的降级尝试、改写过结论横幅的报告、曾经漏网的漂移类别、不合法的合成基线 —— 效果通道也有自己的对抗集：一个标注只读却铸出凭证、只有带外才能发现的工具；一个绝不能被判为 authority-bearing 的持久对象；以及一次无探针审计，其权威结论必须退化为 `unknown`/SKIP 而不是通过。
- **Linux、macOS、Windows × Python 3.11 / 3.12 / 3.13 的 CI**，外加一个打包任务：构建 wheel、全新安装、对真实 server 跑一次完整审计，然后才允许发布。
- **与官方 v2 SDK 双向交叉验证**：官方客户端通过 `server/discover` 接纳 mcp-proof 手写的现代测试 server，mcp-proof 对官方 v2 SDK server 在两种传输上全绿（`scripts/crosscheck_modern_server.py`）。
- **设计上 fail-closed**：分页中断、fixture 被篡改或无法验证、基线缺失、审计器内部错误 —— 每一种都大声中止审计；所有命令用同一套分类回答：exit `2` 加一行稳定输出，从无 traceback，从不悄悄缩小审计范围，也从不构成对目标的指控。
- **可离线验证的报告**：`mcp-proof verify report.json` 用报告自身字段重算两枚指纹；文档指纹覆盖读者看到的一切 —— 结论横幅、审计状态、汇总计数、MSSS 表、后续步骤 —— 任何事后编辑都会破坏它。这是内部一致性证明，不是签名（attestation 在路线图上）。

## ✨ 内部机制

- 🔍 **wire 层协议检查覆盖每个 surface、每一页、两个时代** —— mcp-proof 对 server 直接说原始 JSON-RPC 并自动探测其时代：2026-07-28 现代时代 32 项检查（`server/discover`、`_meta` envelope 强制、`resultType`、每个可缓存结果上的 `ttlMs`/`cacheScope`、`-32022` 版本拒绝、HTTP 路由头强制），initialize 握手时代 27 项 —— 精确错误码、schema 合法性、结构化输出、stdout 卫生、三个列表 surface 的分页安全、专门的 resources 与 prompts 通道，以及**经验证的否定探针**：TOOL-07 发送可证明违反声明 inputSchema 的输入（schema 合法的基线上恰好变异一个字段），server 正常应答则告警 —— 挂起被当作独立发现，绝不算作拒绝。所有通道共用一个分页收集器，藏在第 2 页的工具和第 1 页被同样审计。
- 🛡️ **挂靠公开标准的安全审计** —— 对每一页上的每个声明工具做 6 项确定性检查（工具描述投毒、隐形/bidi 字符、泄漏凭证、无约束注入面、声明的 shell 执行），schema walker 能穿透 `$ref`/`allOf`/嵌套/数组项 —— `config.shell.command` 藏在一层之下也躲不掉。每项检查映射到 [MCP Server Security Standard](https://mcp-security-standard.org) 24 项控制矩阵的规范控制 ID（23 项有完整文档，外加 `MCP-DEPLOY-04` 未来控制占位），渲染为一张结论从不超出证据的合规表：完整直接证据是 **met**，干净但间接的证据是 **partial**，检查看不到的控制是 **manual review**。
- 🧪 **读世界、不读响应的效果检查（v0.8）** —— 配置好观测信道后（SQLite 后端 server 用 `--sqlite`；jail 目录另有文件系统观测器），效果通道在每次调用前后快照外部状态，diff 成逐对象的 create/update/delete 效果并归因到引发它的那次调用。四项检查将其与声明的 annotation 对照：EFF-01（`readOnlyHint: true` 的工具未引发任何观测到的写入）、EFF-02（观测到的删除来自带 `destructiveHint` 的工具）、EFF-03（`idempotentHint` 工具的重复同参调用是无操作）、EFF-06（创建出的凭证的持续有效性仍依赖授权它的 grant —— 做法是带外撤销每个候选依赖、重新行使对象、再恢复）。效果记录的每个字段都标明来历 —— `declared`、`observed`、`probed` 或 `unknown` —— 没有信道的维度报 SKIP 而不是通过。
- 📼 **client 可以留存、且先自证完整再评判他人的回归套件** —— 两个协议时代都能录制；黄金 fixture 用 SHA-256 来源指纹冻结 server 行为，覆盖每种内容类型（二进制载荷存摘要，换掉的图片不可能重放成 OK）。重放前有完整性门：重算每个合约哈希和 manifest 指纹 —— 缺失、篡改、重复、过期的 fixture 都会中止重放而不是被静默跳过；删掉 fixture 存储的哈希算作篡改而不是旧格式，早于合约哈希的基线除非用 `--allow-legacy-fixtures` 显式豁免否则被拒绝。重放对每条漂移分级（`BREAKING` / `VALUE` / `COSMETIC` / `LATENCY`）—— 任何结构化或 JSON 值变化至少是 `VALUE`，翻转的 `"approved"→"denied"` 不可能混过 cosmetic —— 并保持有状态调用顺序（fixture 带序号、指纹对顺序敏感）。基线从不被隐式创建：fixture 缺失时 `run` fail-closed，除非用 `--record-if-missing` 显式豁免。
- 📄 **同时给人和机器看的报告** —— 自包含 HTML：粘性导航、逐检查锚点（`report.html#SEC-03`）、attention/passed 过滤器、证据范围卡、可折叠 MSSS 矩阵；`--pdf` 供打印。同一份带版本的模型输出为 `--json`（schema v3）、给任意 CI 的 `--junit`、给 GitHub Security 标签页的 `--sarif`。效果通道有自己的证据页：声明的 annotation 与观测到的效果并排、只看响应的审计器会读到什么、产生了哪些对象、探针的权威/依赖结论，每个值都带着来历标记。
- 🔁 **可复现是设计出来的** —— 零 LLM 调用、零 API key。两枚职责分明的指纹：`behavior_sha256` 只由 server 行为计算（检查结论、重放结论、协议事实 —— 从不含时间戳、延迟、启动命令或审计器版本），相同的 server 行为在任何机器上指纹相同；`run_hash` 冻结整份报告文档 —— 证据、结论横幅、审计状态、汇总、MSSS 表 —— 只减去易变的时间戳块。`mcp-proof verify` 离线复核两者：任何事后编辑都会破坏的内部一致性证明，不是签名。验收靠验证，不靠信任。
- 🧯 **保守的调用规划，以及 v0.8 的信任修正** —— 自动基线用保守的名字/描述启发式给工具分类，`mcp-proof plan` 在任何东西碰到生产环境之前展示会调用什么、依据是什么。自 v0.8 起 MCP annotation 只能*增加*谨慎：`destructiveHint: true` 仍强制跳过，但未经验证的 `readOnlyHint: true` 不再把一个名字像变更操作的工具捞回自动调用集合 —— 规范写明 client 必须把 annotation 当作不可信，而效果通道存在的原因恰恰是"只读"工具也能铸凭证。`--include-destructive` 和 `--edge-cases` 显式豁免更多。
- 📋 **给 CI 用的契约 diff** —— `mcp-proof inspect` 把服务面（capabilities + tools + resources + prompts，完整分页，"缺席"与"为空"分开记录）冻结成带指纹的 manifest —— 任何分页走不完就拒绝写入，因为把半个面冻结成"基线"会让此后针对缺失那半的所有 diff 都不可见。易变的 wire 元数据按位置剥除、从不按键名剥除，恰好叫 `ttlMs` 或 `nextCursor` 的用户 schema 属性仍属于契约。`mcp-proof diff` 把每处变更分类为 `BREAKING` / `ADDITIVE` / `METADATA`，breaking 时退出码非零 —— schema 收紧、enum 收窄、可选转必填、移除输出字段、削弱安全 annotation 都算 breaking。

## 📊 真实审计，真实报告

| 目标 | 结论 | 报告 |
|---|---|---|
| **官方 filesystem server**（`@modelcontextprotocol/server-filesystem`） | ✅ SHIP-READY — 11/11 MUST，34/34 重放干净，4 个写类工具被自动跳过 | [在线报告](https://yucpbit.github.io/mcp-proof/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| **官方 "everything" 参考 server**（`@modelcontextprotocol/server-everything`） | ✅ SHIP-READY — 20/20 MUST + 7/7 SHOULD，13 个工具 0 安全发现。协议 + 安全通道；录制被刻意跳过 —— 其 `get-env` 工具会倾倒环境变量 | [在线报告](https://yucpbit.github.io/mcp-proof/report-everything.html) |
| **官方 memory server**（`@modelcontextprotocol/server-memory`） | ✅ SHIP-READY — 16/16 MUST，4/4 重放干净，5 个写/删工具被自动跳过，一条建议：无约束的 `search_nodes.query`（SEC-04） | [在线报告](https://yucpbit.github.io/mcp-proof/report-memory.html) |
| **官方 sequential-thinking server**（`@modelcontextprotocol/server-sequential-thinking`） | ✅ SHIP-READY — 11/11 MUST，1/1 重放干净，一条建议（工具描述 2,781 字符，SEC-05）；追查其诚实的 TOOL-08 SKIP 时发现 served inputSchema 漏掉了一个运行时必需字段 | [在线报告](https://yucpbit.github.io/mcp-proof/report-sequential-thinking.html) |
| **2026-07-28 现代时代 server**（零依赖，与官方 v2 SDK 交叉验证） | ✅ SHIP-READY — 经 `server/discover` 自动探测时代，23/23 MUST 含否定探针，2/2 重放 | [在线报告](https://yucpbit.github.io/mcp-proof/report-modern.html) |
| 埋有 **9 处违规**的 demo server | ❌ NOT SHIP-READY — 5 项 MUST 失败 + 5 条安全发现（3 阻断、2 建议），每条都带证据被抓获 | [在线报告](https://yucpbit.github.io/mcp-proof/report-bad.html) |
| 行为良好的 demo server | ✅ SHIP-READY — 18/18 MUST，三通道全过，含回归基线 | [在线报告](https://yucpbit.github.io/mcp-proof/report-good.html) |
| **效果 testbed 的 `silent-keymint` 变体** | ❌ EFF-01 FAIL — 一个标注 `readOnlyHint: true` 的工具返回正常的读取响应，同时向 `api_keys` 表插入一行；带外状态 diff 把这次写入归因到该调用 | [效果证据](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-silent-keymint.html) |

## 🧪 效果感知研究通道（v0.8）

三条交付通道止步于 wire：它们对"行为"的定义是响应字节流。效果通道把同一套"声明 vs 观测"方法往下推一层。它的组成，具体说：

- **观测器**（`effects/observe.py`）：在每次工具调用前后快照外部状态 —— 直接读文件的 SQLite 存储，或一棵目录树 —— 并把两份快照 diff 成逐对象的 create/update/delete 增量。它从不去问工具改了什么，所以无论响应提不提，效果都会被看到。
- **探针**（`effects/probes.py`）：尝试把创建出的对象当作凭证，*实际使用*它去通过服务的真实授权规则。于是 "authority-bearing" 是一个观测结果（这个对象授权了一个动作），不是从字段名猜出来的；"仍然有效"是探针此刻成功，不是对象仍被列出。
- **谱系，保持为三个独立字段**：`created_via`（哪次调用产出了对象 —— 观测所得）、`authorized_by`（会话运行在哪个 grant 之下 —— 声明所得）、`depends_on`（持续有效性实际需要什么 —— 通过带外撤销每个候选、重新行使、再恢复而确立）。区分本身就是要点：一个 `authorized_by` 某 grant、而 `depends_on` 不含该 grant 的 API key，会在 grant 被撤销后存活。
- **testbed**（`testbed/`）：确定性的 SQLite 后端 MCP server，有普通持久对象（笔记）和凭证对象（API key、webhook、分享链接）、一比特 grant、生命周期工具，以及每次恰好植入一个 annotation 谎言的变异开关 —— 建模自有文档的真实事故模式（读路径铸出权威；撤销不级联）。地面真值由 `testbed/saas_oracle.py` 带外读取，从不经过被审计的 MCP surface。

三个实验对着它运行（`python experiments/run_all.py`，确定性，两次运行的 JSON 逐字节相同）。这些数字是此受控环境中对植入不一致的检测表现 —— **不是生产环境流行度**：

| 实验 | 探针 / 效果观测 | baseline |
|---|---|---|
| **E1** — 声明效果 vs 观测效果，诚实 server + 6 个单谎言变体；oracle = 变异台账 | precision / recall **1.000 / 1.000** | 响应级 1.000 / 0.333 · 名字启发式 1.000 / 0.333 |
| **E2** — authority-bearing vs 仅仅持久，8 对象语料，含名为 `api_key_backup` 的诱饵笔记和一个从未持久化的凭证；oracle = 构造即得的权威标签 | 准确率 **1.000** | 名字关键词 0.875 · 持久即权威 0.625 |
| **E3** — 存在性 vs 当前有效性，6 个生命周期场景（撤 grant、撤 key、删 key、TTL 过期、级联）；oracle = 每场景的应然有效性 | 准确率 **1.000**，0 次假失效 | 存在性 0.500 · grant 状态 0.333，1 次假失效 |

支撑这条通道的两个结果：E1 里效果从不出现在响应中的三个谎言（`silent-keymint`、`shadow-webhook`、`phantom-write`）只有状态 diff 能抓到 —— 只看响应的审计器对它们结构性失明，这正是两个 baseline 召回率都是 0.333 的原因。E3 的 `grant_revoked` 场景里，grant 之下创建的 key 在 grant 被撤销后仍然有效（testbed 的授权规则查的是 key 自己那一行，不查 grant —— 与有文档记录的 OAuth 应用持久化事故同构）；grant 状态这个代理判它已失效，就是表里那一次危险的假失效。

方法论、oracle 设计、baseline、相关工作与局限：[docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) · 带原始证据的结果：[评测站](https://yucpbit.github.io/mcp-proof/evaluation/) · 复现：[experiments/README.md](experiments/README.md)。

## 🧭 与官方 conformance 套件的关系

MCP 项目维护着 [`modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance) —— 验证 server 与 client 协议行为（含 auth 流程）的场景测试。需要协议正确性基线就跑它；mcp-proof 的一致性通道从自己的 wire 层探针覆盖了重叠的地带。

mcp-proof 为官方套件不做的那一半而存在：**交付证据**。client 可留存的带指纹、可离线验证的报告；MSSS 安全映射；带 fail-closed 完整性门的黄金行为回归；作为 CI 门禁的契约快照/diff；SARIF/JUnit 产物；以及效果一致性研究通道。用官方套件证明协议，用 mcp-proof 证明交付 —— 两者互补，与官方套件的交叉验证在路线图上。

## 📡 协议支持

| | |
|---|---|
| 传输 | stdio ✅ · Streamable HTTP ✅ |
| Surface | tools ✅ · resources ✅ · prompts ✅ —— 双向能力感知 |
| 现代时代 `2026-07-28`（`server/discover`、无状态 `_meta`） | ✅ 一致性通道，自动探测 —— `--era auto\|modern\|legacy` |
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

server 不达 ship-ready 则任务失败，并留下 `mcp-proof-report.html` / `.json` / `.junit.xml` / `.sarif` 供上传。想用原始命令？`mcp-proof run … --junit r.xml --sarif r.sarif` 加 `mcp-proof diff` 是同一道门。

## 🏗️ 从审计洁净的模板起步

在写 server 而不是审计 server？[`templates/server-starter/`](templates/server-starter/) 是一个开箱即通过本审计的 fastmcp server —— 受约束的输入 schema、正确的错误语义、结构化输出，每条实践都标注了它满足的检查 ID。复制、实现你的工具、审计、带着报告交付。

## 🖥️ 平台

| | |
|---|---|
| macOS | ✅ 开发与完整验证平台 |
| Linux | ✅ CI 覆盖 |
| Windows | ✅ CI 覆盖（`--pdf` 需要安装 Chrome/Chromium） |

## 🗺️ 路线图

| | |
|---|---|
| **当前 — v0.8.0** | 效果感知研究通道：带外效果观测、探针化权威分类、残留权威测量（`mcp-proof effects`、[`experiments/`](experiments/)、[文档](docs/effect-aware-conformance.md)）；annotation 信任修正；[评测站](https://yucpbit.github.io/mcp-proof/evaluation/) |
| **v0.7.2** | 真实性补丁：`verify` 指纹覆盖全文档（报告 schema v3）、剥离 fixture 哈希视同篡改、legacy 基线 fail-closed、全命令统一退出码分类 |
| **下一步** | 2026-07-28 深化：MRTR `input_required` 往返 · CI 内与官方套件交叉验证 · 真实 provider 的效果观测适配器（效果通道的 `Observer` 接口已为此留好） |
| **之后** | 签名证据包（attestation）· 可选语义通道（LLM 评分断言）—— 在确定性内核完成前搁置 |

版本历史见 [CHANGELOG.md](CHANGELOG.md)。

## 🔍 局限

mcp-proof 只证明可被确定性证明的东西，并明确说出哪些是哪些：

- 安全检查覆盖可观测的协议与元数据面。需要部署、源码或流程证据的 MSSS 控制永远标 **manual review** —— 绝不默认通过。
- **授权流程不在交付报告范围内**：不审计 OAuth 握手（官方套件覆盖 auth 场景）。效果通道推理的是工具创建的 *authority-bearing 对象*，在带外观测器的受控 testbed 上 —— 它不审计生产 OAuth 部署。
- **效果通道是测量仪器，不是黑盒通道。** 它需要观测信道（SQLite 存储、jail 目录）；观测不到的系统的效果报 `unknown`/SKIP，绝不假设为无。它的数字是合成 testbed 上的检测表现，不是生产流行度。见 [docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) §7。
- 自动基线用保守的名字/描述启发式分类工具；自 v0.8 起未经验证的 `readOnlyHint` 不再覆盖它。对生产 server 信任一份录制基线之前，请先审阅 fixtures manifest 里的跳过清单。
- 语义正确性（答案的*含义*对不对）有意置于确定性内核之外。

## 📄 许可

MIT —— MSSS 合规节的分类学遵循 [MCP Server Security Standard](https://mcp-security-standard.org)（CC BY-SA 4.0）。
