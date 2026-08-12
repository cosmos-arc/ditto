# AI/Agent 能力平面设计

> **归档说明（2026-08-12）**：本文已被 [R5 治理型量化研究 Agent 设计](../2026-08-12-r5-governed-quant-research-agent-design.md) 取代，仅保留为历史决策记录。新的权威设计修正了 Agent/application 依赖方向、取消通用 Platform LLM Gateway 与强制 Langfuse、采用单 Agent 确定性运行时，并加入自主研究 Campaign、PIT、隐藏 holdout、OCI 沙箱和模型风险控制。请勿按本文实施。

> **日期**：2026-08-04
> **状态**：设计稿（待评审）
> **关联**：定位纠偏见 [2026-08-04-comprehensive-architecture-audit.md](../../reviews/2026-08-04-comprehensive-architecture-audit.md) §定位校准；架构边界见 [boundaries-and-abstraction-standards.md](../../architecture/boundaries-and-abstraction-standards.md)
> **决策（已敲定）**：① Agent runtime + tool 层 → 新增 `ditto_agent` 包（application 编排层 peer）；② Provider = **OpenAI**；③ Runtime = **OpenAI Agents SDK**（非自造 loop）；④ Trace = **OTel GenAI 语义约定 + 自托管 Langfuse**；⑤ 同步（对话）/异步（长任务）双模。详情见 §6（新依赖 `openai-agents` / `langfuse` **已批准 2026-08-04**）

---

## 1. 背景与定位

本项目北极星经用户纠偏后明确为：**当下 A 股 ETF + 个股 + 选股，目标全资产标的 + AI/Agent 现代化量化平台**。AI/Agent 是定位支柱之一，当前能力 **0★**（战略级头号缺口，非推迟项）。

目标 AI 能力四类（用户全选）：

1. **研究 Copilot** — LLM 对话式查询研究/回测/因子诊断、生成报告
2. **NL 策略/因子创作** — LLM 协同现有 features DSL 写因子表达式、协同 alpha pipeline 写策略
3. **Agentic Alpha 发现** — LLM 闭环提假设→生成因子→跑回测/IC→筛选→入库
4. **决策回路 Agent** — LLM 嵌入日级决策：总结 regime、解释持仓偏离、给调整建议

**核心判断**：四类不是四个独立 agent，而是**一个横切「Agent 能力平面」的四种用法**。分头建会得到四套重复的 LLM 客户端 / prompt / trace / 治理胶水。本设计提供一个共享基建 + 四种用法。

**平台已有的两块 AI 接缝资产（无需新建）**：
- **features 表达式 DSL**（lexer→parser→compiler→codegen + governed 校验）——封闭语法、编译期校验，是 NL→因子创作的天然靶点，LLM 产出错了即 fail-closed。
- **R3 研究治理**（11 hard-gate + ReviewPacket + evidence hash + promotion 三层 identity binding）——是 Agent 闭环的天然护栏，**Agent 无法自造通过**。多数平台要为 AI 单独造治理，本项目已有。

---

## 2. 设计原则

1. **零新业务逻辑** — Agent 不重新实现策略/评估/回测；所有计算经 Tool 层委托给既有 application facades。
2. **Agent 不能直写生产** — 每个 agent 写操作走既有 application command → R3 治理门禁。Agent 可提议、可实验，但 promotion 需同一套 human/governance gate。
3. **基建一次、四用法复用** — LLM gateway、Tool 层、trace、治理钩子只建一套。
4. **最小边界变更** — 仅新增一个 application 编排层包 `ditto_agent`；capability 包零改动。
5. **渐进、可独立交付** — Copilot → NL 创作 → Agentic 发现 → 决策回路，每相独立可上线。

---

## 3. 架构

### 3.1 三层模型

```
┌─────────────────────────────────────────────────────────────┐
│  apps 层（entry）                                            │
│   chat / CLI / API surface · 决策回路挂 EOD                  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  ditto_agent（application 编排层 peer — 新增）              │
│   ┌──────────────┐  ┌──────────────────────────────────────┐│
│   │ Agent runtime│  │ Tool 层（facade 薄适配器）            ││
│   │ loop/trace/  │→ │  read tools / write tools / 角色白名单││
│   │ 预算/速率     │  └──────────────┬───────────────────────┘│
│   └──────────────┘                 │                        │
└────────────────────────────────────┼────────────────────────┘
                                     │ 调既有 facades/queries/commands
              ┌──────────────────────▼───────────────────────┐
              │ application（queries / commands / processes）│
              │  → capabilities + data + R3 governance       │
              └──────────────────────────────────────────────┘
                                     ▲
┌────────────────────────────────────┼────────────────────────┐
│  platform — LLM gateway（新增横切基建）                      │
│   model client / prompt 模板 / token-成本计量 /             │
│   function-calling 管线 / tenacity 重试 / OTel trace         │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 依赖方向（layering 规则变更）

**现状**：
```
apps → {application} → capabilities + data + platform
apps → platform
capability 包 → 仅 kernel + platform（禁依赖 application）
```

**变更后**：引入"application 编排层"概念，成员 = `{application, ditto_agent}`：
```
apps → {application, ditto_agent} → capabilities + data + platform
ditto_agent → application + platform          （用 application facades 作 tool）
ditto_agent ↛ capability 包直接实现           （与 apps 非 registry 代码同纪律）
application ↛ ditto_agent                      （application 不反向依赖 agent）
capability 包 → 仍仅 kernel + platform（零改动）
```

**需新增/修改的 importlinter 契约**：
- `ditto_agent must not import ditto_{strategy,portfolio,risk,execution,backtest,features,data,analysis}` 直接实现（须经 application facade / read-model）
- `application must not import ditto_agent`（防反向依赖）
- `ditto_agent must not import ditto_platform.config`（与 application 同纪律，settings 经 dishka 注入）
- 更新 [boundaries-and-abstraction-standards.md](../../architecture/boundaries-and-abstraction-standards.md) 编排层章节

> 这是对"capability 包禁依赖 application"规则的**补充而非破坏**：ditto_agent 不是 capability 包，而是 application 的编排层 peer（与 apps 同级消费 application 输出）。

---

## 4. Tool 层（核心设计）

Tool = function-calling JSON schema + 一个委托既有 facade 的 handler。**每个 tool 是一个薄 pass-through，零业务逻辑。**

### 4.1 Tool 形态

```python
# packages/agent/src/ditto_agent/tools/factor.py（示意）
from ditto_agent.tools.protocol import tool
from ditto_application.queries.factor_evaluation import FactorEvaluationFacade

@tool(allowlist="read")
def factor_ic(factor_id: str, start: str, end: str) -> FactorICReport:
    """查询某因子的 IC/ICIR/分层/多空/换手成本报告。"""
    return _facade.run_ic(factor_id, start, end)   # 既有 facade，零新逻辑
```

- `@tool` 装饰器从类型注解 + docstring 生成 function-calling schema；handler 是单行委托。
- `allowlist` 标注工具的角色可见性（read / authoring / experiment / advisory）。
- 返回值是既有 application read-model（已 orjson 序列化友好）。

### 4.2 Tool 目录（按支柱）

| 支柱 | 复用既有接缝 | Tool（示例） |
|------|-------------|-------------|
| **Copilot / 决策回路（读）** | application queries/read-models | `factor_ic`、`experiment_summary`、`review_packet`、`backtest_result`、`regime_summary`、`position_deviation`、`dataset_maturity`、`render_report` |
| **NL 创作（写，经治理）** | features DSL compiler + StrategySpec validate/diff | `validate_expression`、`compile_factor`、`diff_strategy_version`、`submit_strategy_for_review`（**不 publish**） |
| **Agentic 发现（写，经治理）** | FactorEvaluationFacade + experiment launch | `propose_factor`、`launch_experiment`、`evaluate_candidate`、`submit_for_review` |

### 4.3 为什么是薄适配器而非新逻辑

- 所有计算、校验、PIT、治理已在 application/capabilities 内沉淀并测试。
- Tool 层只需保证 **schema ↔ facade 签名一致**（加一条契约测试即可）。
- LLM 选错 tool / 参数非法 → facade 抛 typed error → agent runtime 把错误回喂 LLM 重试（bounded）。

---

## 5. 治理与安全（护城河）

### 5.1 Agent 不能直写生产

每个 write tool 包一个 application command，该 command 已走：
- 策略：`StrategySpec validate` → `ReviewPacket`（11 gate）→ review → publish → governance promote（三层 identity binding）
- 实验：launch → `ReviewPacket` → review → publish

**Agent 可提议、编译、校验、甚至跑实验，但 promotion 到生产需同一 human/governance gate。** 这由既有 R3 架构强制，非新代码。

### 5.2 角色工具白名单

| Agent 角色 | 可见 tool 集 | 能否触达生产 |
|-----------|-------------|:---:|
| Copilot | read-only | 否 |
| Author | read + validate + compile + submit-for-review | 否（仅提交审查） |
| Researcher（agentic） | read + launch-experiment + evaluate | 否（仅实验） |
| Advisor（决策回路） | read + daily-decision-suggest（纯建议） | 否 |
| 发布/Promotion | **无 agent 角色** — 仅人工经 governance | — |

### 5.3 纵深防御

- **Prompt 注入**：write tool 参数经 facade 的既有输入校验（StrategySpec validate / canonical hash）；LLM 产出不绕过 schema。
- **速率/预算**：每 agent 每会话的 write 次数 + token/成本上限（LLM gateway 计量）。
- **人在回路**：生产影响的 write（submit-for-review / launch）需人工确认或已在 governance 流程内。
- **可审计**：每个 agent action 落 OTel span + agent trace artifact（谁/何时/用了哪个 tool/结果/成本）。

---

## 6. LLM Gateway（platform 横切基建）

> **2026-08-04 调研后决策（基于 OpenAI Agents SDK 官方文档 + OTel GenAI 2026 实践）**：
> - **Provider = OpenAI**；**Runtime 采用 OpenAI Agents SDK（不自造 loop）**——`@function_tool` 包 Ditto facade（零新业务逻辑）、input/output **guardrails** + tool **approval**（pause/resume）接 R3 治理、`Runner.run_sync()`/`run_streamed()` 同步对话、`Runner.run()` async + **Temporal/DBOS/Restate** 持久化长任务（跨重启恢复）、`SQLiteSession` 会话记忆、内置 `max_turns` + error handlers 防失控。
> - **Trace = OTel GenAI 语义约定**（CNCF / OpenLLMetry 已并入，vendor-neutral，与 platform 现有 OTel 同源）+ **自托管 Langfuse** 后端（trace 可视化 / prompt 管理 / eval / 成本 / 回放，OpenAI Agents SDK 一等公民 trace processor）。
> - **隐私**：`set_trace_processors()` **替换** SDK 默认处理器，**禁止 trace 回传 OpenAI**，只发自托管 Langfuse；`trace_include_sensitive_data` 按需关。治理写入的审计仍以既有 R3 governance（durable/immutable）为准，agent trace 为辅助。
> - **新依赖（已批准 2026-08-04）**：`openai-agents`、`langfuse`。Langfuse server 独立部署，不进 Python 依赖树。

填审计 [platform §2.2](../../reviews/2026-08-04-comprehensive-architecture-audit.md) flag 的"缺统一 http client / tenacity / limits 封装"——**LLM 网关就是其第一个正经消费者**。

| 组件 | 职责 |
|------|------|
| **model client** | httpx 单例 + 连接池 + tenacity 重试 + 超时 + W3C TraceContext 注入；provider 可配置（Claude/OpenAI/本地） |
| **prompt 模板** | 版本化 prompt（artifact 化），Jinja2 渲染，回归测试 |
| **function-calling** | 跨 provider 归一化的 tool-call 协议；tool 执行由 ditto_agent runtime 负责 |
| **structured output** | tool 返回 typed 对象（pydantic + orjson），非裸字符串 |
| **token/成本计量** | per-call / per-agent / per-session 预算与计费事件 |
| **限流** | limits 库令牌桶（兑现 CLAUDE.md 已允许依赖） |

**位置**：`packages/platform/src/ditto_platform/services/llm/`（与 notification channels 并列的横切服务）。

---

## 7. 四支柱详细设计

### Phase A — 研究 Copilot（先做，零写风险）
- **范围**：LLM gateway + ditto_agent 骨架 + 只读 tool 层 + chat/CLI 入口。
- **价值**：自然语言查"000001 过去一年 IC 怎样""实验 #42 的 review packet 卡在哪条 gate""生成本周因子诊断 markdown"。
- **风险**：最低（纯读），验证 gateway + tool 层 + 治理读路径。
- **完成定义**：3+ read tool 接通 FactorEvaluationFacade/ReviewPacket query；CLI `ditto ask "..."`；OTel trace 全链路；mock-LLM 金样测试。

### Phase B — NL 策略/因子创作（DSL 接缝）
- **范围**：NL → features 表达式（`validate_expression` + `compile_factor`，compiler fail-closed）；NL → StrategySpec（`diff_strategy_version`）；`submit_strategy_for_review`（不 publish）。
- **价值**："帮我写一个 20 日动量减 5 日反转的横截面因子"→ LLM 产出表达式 → compiler 校验 → 不合法则报错回喂。
- **风险**：中（DSL 封闭语法是天然护栏；产出必须过 validate）。
- **完成定义**：NL→表达式 roundtrip 测试（合法/非法用例）；submit-for-review 经既有 command；角色白名单生效。

### Phase C — Agentic Alpha 发现（治理护栏闭环）
- **范围**：propose→generate→backtest/IC→evaluate→筛选 循环，复用 FactorEvaluationFacade + experiment launch；候选经 R3 review。
- **价值**：Agent 批量假设、自动跑 IC、筛出达标候选提交审查（**不自动上线**）。
- **风险**：高（需 Phase A/B 基建成熟；成本/速率控制关键）。
- **完成定义**：discovery loop 在预算内收敛；候选提交 review_packet；promotion 仍走人工 governance。

### Phase D — 决策回路 Agent（live 接线）
- **范围**：regime 总结 + 持仓偏离解释 + daily-decision 建议工具；挂 EOD flow；纯建议（Advisor 角色）。
- **价值**：每日 EOD 后 LLM 总结"今日 regime 变化、组合偏离、建议动作"供人工决策。
- **风险**：中（紧耦合 daily-decision；需 Phase A/B trace 与可观测成熟）。
- **完成定义**：EOD 产出 agent advisory report；人在回路确认；成本可控。

---

## 8. 可观测性与评估

- **trace**：每个 agent step 一个 OTel span（agent_id / role / tool / model / tokens / cost / latency）。
- **agent trace artifact**：完整 agent 会话落盘（复用 analysis artifact 存储 or 新 namespace），供回放/审计。
- **eval harness**：prompt 回归套件（每个 tool/角色的 golden transcript），防 prompt 漂移；NL 创作用合法/非法表达式用例集。

---

## 9. 测试策略

| 层 | 策略 |
|----|------|
| Tool 层 | 委托既有 facade → 复用 facade 测试；**新增** schema↔signature 一致性契约测试 |
| Agent runtime | mock LLM（确定性）+ loop 边界（预算/速率/重试上限）单测 |
| 端到端 | golden agent transcript（Copilot 查询路径、NL 创作合法/非法路径） |
| 治理 | 断言 write tool 必经 review_packet / governance（无法绕过 promotion） |
| 成本 | 预算上限触发即停的单测 |

---

## 10. 风险与开放问题

| 风险/问题 | 缓解/待决 |
|----------|----------|
| LLM 非确定性 | structured output + tool schema 校验 + golden transcript 回归 |
| 成本失控 | gateway 预算计量 + per-session 上限 + 速率限制 |
| ~~provider 选型~~ | ✅ **OpenAI**（已决） |
| ~~agent trace 存哪~~ | ✅ OTel GenAI span（platform gateway 发）+ **自托管 Langfuse** 后端；治理写入审计仍以 R3 governance 为准 |
| ~~同步 vs 异步 loop~~ | ✅ 双模：对话 `run_sync`/`run_streamed`；长任务 `run` async + Temporal/DBOS 持久化 |
| 模型供应商锁定 | gateway 抽象 provider；现单 OpenAI，SDK 支持非 OpenAI model adapter 作退路 |
| 多用户/多租户 | 待决（当前单租户假设） |
| ~~新依赖批准~~ | ✅ 已批准（`openai-agents` + `langfuse`，2026-08-04） |

---

## 11. 与既有路线图的关系

- **不冲突 R3/R4**：ditto_agent 是 application 同层新包，capability 包零改动；凸优化（R4）等仍按原计划。
- **反哺 application 拆分（ARCH-001）**：ditto_agent 分流一部分编排职责，**减轻**而非加重 god-layer。
- **填补 platform http/retry/ratelimit 缺口**：LLM gateway 直接兑现审计 P1 建议 #6。

---

## 12. 下一步（待评审通过）

1. 评审本设计 → 敲定开放问题（provider 选型、trace 存储、sync/async）。
2. 起 `feat/agent-capability-plane` 分支。
3. 用宿主原生计划能力把 Phase A 拆成原子任务（LLM gateway → ditto_agent 骨架 → 3 个 read tool → CLI `ask` → trace → mock-LLM 测试）。
4. TDD 推进 Phase A，独立可上线后再启 Phase B。

---

## 附录 A：Tool 目录初稿

**read（Copilot/Advisor）**：`factor_ic` · `factor_attribution` · `experiment_summary` · `experiment_list` · `review_packet` · `backtest_result` · `regime_summary` · `position_deviation` · `dataset_maturity` · `render_report`

**authoring（Author）**：`validate_expression` · `compile_factor` · `propose_strategy_spec` · `diff_strategy_version` · `submit_strategy_for_review`

**experiment（Researcher）**：`propose_factor` · `launch_experiment` · `evaluate_candidate` · `submit_for_review`

**advisory（Advisor）**：`daily_decision_suggest` · `explain_deviation`

> 所有 write/advisory tool 经既有 application command；无 tool 直接触达生产 promotion。

## 附录 B：边界契约清单（实施时落入 .importlinter）

```
ditto_agent must not import ditto_strategy / portfolio / risk / execution / backtest / features / data / analysis  （须经 application facade）
application must not import ditto_agent
ditto_agent must not import ditto_platform.config
ditto_agent → ditto_application + ditto_platform  （仅此两项直接依赖）
```
