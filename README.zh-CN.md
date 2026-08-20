<div align="center">

# 🧾 mcp-proof

### 交付 MCP 服务器，附带一张「收据」。

**一条命令审计任意 MCP 服务器——tools、resources、prompts 三个面，两个协议时代，stdio 或 Streamable HTTP——交给客户一份带指纹、可复现的交付报告，外加一套留在客户仓库里持续把关的 CI 回归套件。**

[![ci](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml/badge.svg)](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11+-blue)](pyproject.toml)
[![checks](https://img.shields.io/badge/checks-30_modern_·_25_legacy_·_6_security-6a5acd)](src/mcpproof/checks/)
[![transports](https://img.shields.io/badge/transports-stdio_·_HTTP-informational)](src/mcpproof/client_http.py)
[![license](https://img.shields.io/badge/license-MIT-black)](LICENSE)

[English](README.md) · [简体中文](README.zh-CN.md)

<img src="demo/report-filesystem.png" width="760" alt="mcp-proof 对官方 MCP filesystem 服务器的交付报告——SHIP-READY，11/11 MUST 检查通过，完整 MSSS 合规表，34/34 回归全清">

*对官方 MCP filesystem 服务器的真实审计：25 项协议检查、MSSS 合规表、34 个回归 fixtures——全绿。*

</div>

---

## ✨ 你得到什么

- 🔍 **覆盖全部面与两个时代的线级检查** —— mcp-proof 直接对服务器说原始 JSON-RPC 并自动识别其时代：2026-07-28 现代时代 30 项（`server/discover`、`_meta` envelope 强制、`resultType`、所有可缓存结果的 `ttlMs`/`cacheScope`、-32022 版本拒绝、HTTP 路由 header 强制），initialize 握手时代 25 项——精确错误码、schema 合法性、结构化输出、stdout 卫生、分页安全、专门的 resources 与 prompts 车道，以及**验证过的负向探测**：TOOL-07 发送可证明违反 inputSchema 的输入，服务器若正常应答即告警并附最小复现输入。双向能力感知：未声明的面跳过，声明了的面必须能用。
- 🛡️ **挂靠公开标准的安全审计** —— 6 项确定性检查（工具描述投毒、隐形/双向字符、凭据泄漏、无约束注入面、暴露任意执行），每项映射到 24 控制项的 [MCP Server Security Standard](https://mcp-security-standard.org) 的规范控制 ID，每份报告内置完整合规表。
- 📼 **留给客户的回归套件** —— 两个协议时代都能录制；带 SHA-256 溯源的黄金 fixtures 冻结服务器行为；重放按严重度给漂移分级（`BREAKING` / `VALUE` / `COSMETIC` / `LATENCY`），理解结构化输出，保持有状态调用顺序，并附带可直接粘贴的 GitHub Actions 门禁。
- 📄 **人和机器都能读的报告** —— 自包含 HTML：吸顶导航、逐检查锚点（`report.html#SEC-03`）、关注/通过过滤器、可折叠 MSSS 矩阵；`--pdf` 供打印。同一份版本化模型可输出 `--json`（schema v1）、`--junit`（任意 CI）、`--sarif`（GitHub Security 页签）。
- 🔁 **可复现是设计出来的** —— 零 LLM 调用、零 API key。所有哈希只依赖行为本身——时间戳与延迟放在独立、不进哈希的 observation 层——因此相同的服务器行为产生相同的报告指纹：验收靠验证，不靠信任。
- 🧯 **annotations 优先的调用规划** —— MCP 工具注解双向覆盖名称启发式：`readOnlyHint` 救回会被正则误拦的只读工具，`destructiveHint` 抓住正则漏掉的写型工具；无注解才回退保守启发式。`mcp-proof plan` 在碰生产环境之前就告诉你自动基线会调用什么、依据是什么；`--include-destructive` 与 `--edge-cases` 按需放行更多。
- 📋 **给 CI 的契约 diff** —— `mcp-proof inspect` 把服务面（capabilities + tools + resources + prompts，翻页收齐）冻结成带指纹的 manifest；`mcp-proof diff` 把每处变化归为 `BREAKING` / `ADDITIVE` / `METADATA`，出现破坏性变化即非零退出——schema 收紧、enum 收窄、optional 变 required、输出字段消失、安全注解弱化都算数。

## 🚀 快速开始

```bash
pip install git+https://github.com/YuCPbit/mcp-proof
mcp-proof run python my_server.py --fixtures fixtures/ --out report.html
```

审计一个运行中的 HTTP 服务器？`mcp-proof run --url http://localhost:8000/mcp --out report.html`

退出码为 `0` 意味着：所有 MUST 检查通过、零安全发现、零行为漂移——天然的单行 CI 门禁。

```bash
mcp-proof record python my_server.py --fixtures fixtures/    # 冻结行为契约
mcp-proof replay --fixtures fixtures/ -- python my_server.py  # 任何漂移即失败
```

用内置的对照演示 60 秒看懂差别——一个干净的服务器 vs 一个埋了九处违规的服务器：

```bash
mcp-proof run python demo/good_server.py --fixtures demo/fixtures-good --out report-good.html   # → SHIP-READY
mcp-proof run python demo/bad_server.py --out report-bad.html                                    # → 5 项 MUST 失败，3 项安全发现
```

## 📊 真实案例，真实报告

| 审计对象 | 判定 | 报告 |
|---|---|---|
| **官方 MCP filesystem 服务器**（`@modelcontextprotocol/server-filesystem`） | ✅ SHIP-READY —— 11/11 MUST 检查通过，34/34 回归全清，4 个写型工具自动跳过 | [HTML](demo/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| **2026-07-28 现代时代服务器**（零依赖，与官方 v2 SDK 交叉互验） | ✅ SHIP-READY —— `server/discover` 自动识别时代，21/21 MUST 含负向探测，2/2 回归全清 | [HTML](demo/report-modern.html) |
| 埋了 **9 处违规**的演示服务器 | ❌ NOT SHIP-READY —— 5 项 MUST 失败 + 3 项安全发现，逐一带证据抓出 | [HTML](demo/report-bad.html) |
| 行为规范的演示服务器 | ✅ SHIP-READY —— 16/16 MUST，三车道全过，含回归基线 | [HTML](demo/report-good.html) |

## 🔬 三条审计车道

| 车道 | 证明什么 | 怎么做 |
|---|---|---|
| **协议一致性** | 服务器在线级正确实现了 MCP——握手、JSON-RPC 错误语义、工具与输出 schema、能力一致性、分页、stdout 卫生 | 手写 JSON-RPC 探针直接观测原始字节流，任何瑕疵无处藏身 |
| **安全与卫生** | 工具元数据干净：没有注入指令、隐藏 Unicode、泄漏的密钥或无约束的执行面 | 确定性静态分析，每项发现携带 MSSS 控制 ID |
| **行为回归** | 服务器的行为和交付那天一模一样 | 溯源指纹化黄金 fixtures 的录制/重放，漂移按严重度分级 |

三条车道汇入一份报告——报告以按优先级排序的修复清单收尾，天然兼任整改方案。

## 📡 协议支持

| | |
|---|---|
| 传输层 | stdio ✅ · Streamable HTTP ✅ |
| 服务面 | tools ✅ · resources ✅ · prompts ✅ ——双向能力感知 |
| 现代时代 `2026-07-28`（`server/discover`、无状态 `_meta`） | ✅ 一致性车道，自动识别——`--era auto\|modern\|legacy` |
| Legacy 时代（initialize 握手，`2024-11-05` → `2025-11-25`） | ✅ 全部车道 |
| 回归车道 | ✅ 双时代——SDK 会话（legacy）· 探针会话（modern） |

现代车道与官方 v2 SDK **双向互验**：官方客户端通过 `server/discover` 接纳 mcp-proof 手写的现代测试服务器；mcp-proof 对官方 v2 SDK 服务器在**两种传输**上（stdio 与带 SSE 响应的 Streamable HTTP）三车道全绿（`scripts/crosscheck_modern_server.py`）。

支持**任何语言**编写的服务器——mcp-proof 对话的是进程（或 URL），不是你的代码库。

## ⚙️ 一步接入 CI

```yaml
- uses: YuCPbit/mcp-proof@v0.5.0
  with:
    server-command: python my_server.py
    fixtures: fixtures/
```

服务器不达 ship-ready 即失败，并留下 `mcp-proof-report.html` / `.json` / `.junit.xml` / `.sarif` 供上传。

## 🏗️ 从审计全绿的模板起步

要建服务器而不是审计？[`templates/server-starter/`](templates/server-starter/) 是一个出厂即通过全部审计的 fastmcp 服务器模板——约束好的输入 schema、规范的错误语义、结构化输出，每个最佳实践都标注了它满足的检查 ID。复制、实现你的工具、审计、连报告一起交付。

## 🖥️ 平台

| | |
|---|---|
| macOS | ✅ 开发与完整验证平台 |
| Linux | ✅ CI 覆盖 |
| Windows | ✅ CI 覆盖 |

## 🗺️ 路线图

| 版本 | 主线 |
|---|---|
| v0.3 | ✅ 双时代协议支持已落地 main——时代自动识别、19 项现代检查、双时代回归会话，对官方 v2 SDK 双传输实测全绿 |
| v0.4 | ✅ 能力感知的 resources / prompts 车道 · 契约清单 `inspect` / `diff` 破坏性变化门禁 · annotations 优先调用规划 |
| v0.5 | ✅ 版本化 JSON 报告模型 · JUnit 与 SARIF 输出 · 可复用 GitHub Action（`uses: YuCPbit/mcp-proof@v0.5.0`）· 报告 UI：吸顶导航、锚点、过滤器 |
| v0.6 | ✅ 两阶段参数合成（`$ref` / `allOf` / `const` / `pattern` / `format` / 边界 / `multipleOf`）· 验证过的负向探测（TOOL-07）附最小复现输入 |
| 更远 | 可选语义车道（LLM 评分断言）——等确定性核心完工后再排期 |

## 🔍 边界与承诺

mcp-proof 只声称能被确定性证明的结论，并明确标注哪些不是：

- 安全检查覆盖可观测的协议与元数据面。需要部署、源码或流程证据的 MSSS 控制项一律标注**人工复核**——绝不冒充"已通过"。
- 自动基线依据保守的名称/描述启发式分类工具。对生产服务器录制基线前，请先复核 manifest 里的跳过清单。
- 语义正确性（答案的*含义*对不对）在确定性核心之外，这是设计使然。

## 📄 许可证

MIT —— MSSS 合规部分的分类体系来自 [MCP Server Security Standard](https://mcp-security-standard.org)（CC BY-SA 4.0）。
