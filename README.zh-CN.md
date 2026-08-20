<div align="center">

# 🧾 mcp-proof

### 交付 MCP 服务器，附带一张「收据」。

**一条命令审计 stdio 或 Streamable HTTP 上的 MCP 服务器——交给客户一份带指纹、可复现的交付报告，外加一套留在客户仓库里持续把关的 CI 回归套件。**

[![ci](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml/badge.svg)](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11+-blue)](pyproject.toml)
[![checks](https://img.shields.io/badge/checks-15_conformance_·_6_security-6a5acd)](src/mcpproof/checks/)
[![transports](https://img.shields.io/badge/transports-stdio_·_HTTP-informational)](src/mcpproof/client_http.py)
[![license](https://img.shields.io/badge/license-MIT-black)](LICENSE)

[English](README.md) · [简体中文](README.zh-CN.md)

<img src="demo/report-filesystem.png" width="760" alt="mcp-proof 对官方 MCP filesystem 服务器的交付报告——SHIP-READY，11/11 MUST 检查通过，完整 MSSS 合规表，34/34 回归全清">

*对官方 MCP filesystem 服务器的真实审计：15 项协议检查、MSSS 合规表、34 个回归 fixtures——全绿。*

</div>

---

## ✨ 你得到什么

- 🔍 **15 项线级协议检查** —— mcp-proof 直接对服务器说原始 JSON-RPC，验证的是真正走线的内容：握手完整性、精确错误码、工具 schema 合法性、结构化输出正确性、stdout 卫生、分页安全，以及协议版本如实上报。能力感知：只提供 resources 或 prompts 的服务器绝不会因为没有 tools 而被判失败。
- 🛡️ **挂靠公开标准的安全审计** —— 6 项确定性检查（工具描述投毒、隐形/双向字符、凭据泄漏、无约束注入面、暴露任意执行），每项映射到 24 控制项的 [MCP Server Security Standard](https://mcp-security-standard.org) 的规范控制 ID，每份报告内置完整合规表。
- 📼 **留给客户的回归套件** —— 带 SHA-256 溯源的黄金 fixtures 冻结服务器行为；重放按严重度给漂移分级（`BREAKING` / `VALUE` / `COSMETIC` / `LATENCY`），理解结构化输出，保持有状态调用顺序，并附带可直接粘贴的 GitHub Actions 门禁。
- 📄 **非工程师也能读的报告** —— 判定横幅、分数卡、逐项证据与修复建议、MSSS 合规表，以及按优先级排序的**下一步行动清单**。自包含 HTML；加 `--pdf` 直接出 PDF。
- 🔁 **可复现是设计出来的** —— 零 LLM 调用、零 API key。所有哈希只依赖行为本身——时间戳与延迟放在独立、不进哈希的 observation 层——因此相同的服务器行为产生相同的报告指纹：验收靠验证，不靠信任。
- 🧯 **保守的自动基线** —— 疑似写型工具（`write_*`、`delete_*`、`exec` 等）默认跳过并列入 manifest 供人工复核；需要时用 `--include-destructive` 显式放行。`--edge-cases` 额外把超长、空串、注入形态的输入也纳入基线。

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
| **官方 MCP filesystem 服务器**（`@modelcontextprotocol/server-filesystem`） | ✅ SHIP-READY —— 11/11 MUST 检查通过，34/34 回归全清 | [HTML](demo/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| 埋了 **9 处违规**的演示服务器 | ❌ NOT SHIP-READY —— 5 项 MUST 失败 + 3 项安全发现，逐一带证据抓出 | [HTML](demo/report-bad.html) |
| 行为规范的演示服务器 | ✅ SHIP-READY —— 三车道全过，含回归基线 | [HTML](demo/report-good.html) |

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
| 协议版本 | initialize 握手时代的全部版本，`2024-11-05` → `2025-11-25` ✅ |
| `2026-07-28` 现代时代（`server/discover`） | v0.3——见路线图 |

支持**任何语言**编写的服务器——mcp-proof 对话的是进程（或 URL），不是你的代码库。

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
| v0.3 | 双时代协议支持——`server/discover` + `_meta`（2026-07-28 现代时代）与 legacy 握手并存，`--era auto\|modern\|legacy` |
| v0.4 | 能力感知的 resources / prompts 车道 · 契约清单 `inspect` / `diff` / `assert-no-breaking` |
| v0.5 | JSON / JUnit / SARIF 输出 · 可复用的 GitHub Action |
| v0.6 | Schema 驱动的边界与负向测试生成 |
| 更远 | 可选语义车道（LLM 评分断言）——等确定性核心完工后再排期 |

## 🔍 边界与承诺

mcp-proof 只声称能被确定性证明的结论，并明确标注哪些不是：

- 安全检查覆盖可观测的协议与元数据面。需要部署、源码或流程证据的 MSSS 控制项一律标注**人工复核**——绝不冒充"已通过"。
- 自动基线依据保守的名称/描述启发式分类工具。对生产服务器录制基线前，请先复核 manifest 里的跳过清单。
- 语义正确性（答案的*含义*对不对）在确定性核心之外，这是设计使然。

## 📄 许可证

MIT —— MSSS 合规部分的分类体系来自 [MCP Server Security Standard](https://mcp-security-standard.org)（CC BY-SA 4.0）。
