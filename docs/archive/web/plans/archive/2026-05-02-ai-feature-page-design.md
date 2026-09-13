# AI 功能页面统一拆分规划

> 日期: 2026-05-02
> 状态: Draft v2
> 上游: `docs/plans/2026-05-01-ai-capability-enhancement-design.md`
> 范围: Ditto 前端项目内的 AI 产品能力、页面信息架构、交互状态、mock 数据、类型契约与后端交接边界
> 非范围: Agent Runtime、真实模型调用、数据工具、回测引擎、调度器、权限系统的后端实现

---

## 0. 结论

本项目的 AI 工作重点不是实现后端 Agent，而是先把顶尖量化 AI 工作站的前端产品形态定义完整。后端服务项目后续承接运行时、工具、数据、回测、调度和安全执行。

前端规划采用以下定位:

- AI 不再是独立一级域。既有规范已明确: Copilot 是全局 Sidecar，Agent Console 归入 Platform，AI 能力嵌入业务域页面。
- 本规划只新增一个业务域页面: `/research/alpha`。它属于 Research，不是 AI 域。
- Agent Console 是所有长任务、审批、Trace、Finding、AutoResearch Run 的统一控制台。
- Copilot 是跨域辅助层，负责解释、生成、发送到工作区，不承载独立产品路由。
- 后端能力先以 typed contract、mock fixture、SSE event shape、状态机和 artifact schema 表达。

---

## 1. 设计原则

| 原则 | 前端含义 | 后端交接含义 |
|------|----------|--------------|
| 工作流优先 | AI 出现在 Observe / Research / Validate / Execute / Monitor 的真实页面中 | 服务按业务动作暴露，不按聊天意图散落 |
| 结构化优先 | Finding、Proposal、Trace、Artifact 必须有专用 UI，不只显示文本 | 所有 AI 输出返回可验证 schema |
| 审批门控 | 交易、策略采纳、因子入库、策略优化必须显式审批 | 后端执行 destructive action 前等待 approval token |
| 可追溯 | 每条结论都能追到数据、工具、参数、版本、时间、artifact | 后端保存 trace、tool call、artifact、data snapshot |
| 可复现 | 因子和策略发现必须能重跑、比较、回滚 | 后端提供 run replay、experiment id、artifact download |
| 可评测 | Agent/prompt/tool 组合要能被固定任务集评估 | 后端提供 eval run 和 score event |
| 安全最小化 | 前端表达权限、预算、可执行动作边界 | 后端实现权限、guardrail、tool policy |

---

## 2. 业界能力基线与 Ditto 映射

| 参考方向 | 业界能力 | Ditto 前端应该表达的能力 |
|----------|----------|--------------------------|
| R&D-Agent(Q) | 量化研发拆成 Research / Development 循环，围绕因子和模型做假设、实现、回测、反馈 | Alpha Explorer + Experiment Graph + Artifact Replay |
| TradingAgents | 多角色交易公司模拟: 分析师、Bull/Bear 研究员、交易员、风控、PM | Agent Console 的 pipeline timeline、debate panel、Risk Officer gate |
| OpenBB / MCP | 金融数据工具标准化，数据源可被 AI Agent 统一消费 | Tool Registry UI、Tool Trace、Data Source Evidence |
| QuantConnect MCP | AI 可创建项目、写策略、回测、优化、部署，但每步有平台约束 | Strategy Spec DSL、Backtest handoff、Deployment approval placeholder |
| OpenAI Agents SDK | 工具调用、handoff、guardrails、streaming、trace 是生产级 Agent 底座 | Agent Event Stream、Guardrail Result、Trace Drawer、Eval Lab |
| Google A2A | 长任务、Agent Card、SSE、artifact、断线续连和跨 Agent 协作协议 | Run lifecycle、Agent capability card、artifact viewer、resume state |
| MCP Security | 工具权限、prompt injection、token 最小权限、审计日志 | AI Policy Settings、Tool Permission Matrix、Security Finding |

前端不复制这些框架的后端实现，但必须把用户需要看到、审批、追溯和比较的对象先定义出来。

---

## 3. 能力地图

### 3.1 核心能力域

| 能力域 | 用户问题 | 前端入口 | 关键产物 |
|--------|----------|----------|----------|
| Context Copilot | 这个页面说明了什么，下一步能做什么 | 全局 Copilot Sidecar | ConversationBlock、StructuredOutput、WorkspaceAction |
| Agent Operations | 哪些 Agent 在跑，产出了什么，是否需要我批准 | `/platform/agents` | Plan、Run、Finding、Approval、Trace、Artifact |
| Alpha Discovery | 有没有新因子，质量如何，能否入库 | `/research/alpha` | FactorCandidate、Experiment、ParetoFrontier |
| Strategy Construction | 如何从目标生成可验证策略 | `/research/strategies/[id]/studio` | StrategySpec、BacktestDraft、RiskCheck |
| Strategy Maintenance | 策略是否衰减，如何修复 | `/research/strategies/[id]` 优化 tab | OptimizationProposal、Simulation |
| Trading AI Review | 信号为什么来，能不能下单 | `/trading/signals` | SignalInterpretation、RiskOfficerDecision |
| Daily Quant Brief | 今天需要关注什么 | Home | DailyBrief、PriorityFinding、DataHealth |
| Agent Quality | 哪套 Agent/prompt/tool 更可靠 | `/platform/agents` Quality tab | EvalRun、ScoreCard、RegressionSet |
| AI Governance | 哪些工具能用，预算和审批规则是什么 | `/platform/settings` AI section | ToolPolicy、BudgetPolicy、ModelPolicy |

### 3.2 前端交付对象

前端项目需要交付以下内容:

- 页面蓝图: 页面、slot、tab、overlay、状态、响应式行为。
- 组件规范: Finding 卡片、Trace Drawer、Artifact Viewer、Approval Panel、Agent Timeline。
- 类型契约: TypeScript discriminated union，不使用 `any`。
- mock 数据: MSW fixture 覆盖 default/loading/empty/failed/running/waiting-approval/blocked。
- API/SSE 形状: 只定义 contract 和 adapter，不在本项目实现后端。
- 验收测试: RTL 组件测试、状态矩阵测试、路由/契约测试。

---

## 4. IA 与页面组合

### 4.1 决策记录

| 决策点 | 结论 | 原因 |
|--------|------|------|
| AI 域是否恢复 | 不恢复 | 既有规范已废弃 `/ai`，AI 必须嵌入业务域与 Platform |
| Alpha Explorer 归属 | 新增 `/research/alpha` | 它是 Research 域的独立工作流，不是独立 AI 域 |
| AutoResearch Dashboard 归属 | `/platform/agents` + `/research/alpha` 深链 | Console 负责任务治理，Alpha 页面负责因子研究体验 |
| Copilot 形态 | 全局 Sidecar | 不再创建 `/ai/copilot` 路由 |
| Strategy AI 模式 | Strategy Studio 内建 | Guided / Agent 是 Manual 的同级构建方式 |
| Agent 质量评测 | Agent Console Quality tab | 评测是 Agent 运维的一部分 |
| AI 设置 | Platform Settings AI section | 模型、工具权限、预算、审批策略属于平台配置 |

### 4.2 页面清单

| 页面/组件 | 路由 | 类型 | 优先级 | 说明 |
|-----------|------|------|--------|------|
| Global Copilot Sidecar | 全局组件 | 增强 | P0 | 上下文感知、结构化输出、发送到工作区 |
| Agent Console V2 | `/platform/agents` | 增强 | P0 | Plans/Runs/Findings/Approvals/AutoResearch/Quality/Trace |
| AI Policy Settings | `/platform/settings` | 增强 | P0 | 模型偏好、工具权限、预算、审批规则 |
| Home Daily Brief | `/` | 增强 | P1 | 每日摘要、优先级队列、结构化 Finding |
| Alpha Explorer | `/research/alpha` | 新增 | P1 | 因子发现、探索流、评估、采纳 |
| Strategy Studio AI Modes | `/research/strategies/[id]/studio` | 增强 | P1 | Manual / Guided / Agent |
| Signals AI Review | `/trading/signals` | 增强 | P1 | AI 解读、风控门控、证据链 |
| Strategy Optimization | `/research/strategies/[id]` | 增强 | P2 | 策略自优化、模拟回测、采纳 |
| Research/Regime AI | `/research/regime` | 增强 | P2 | Regime 变化触发、策略影响、因子适配 |
| Agent Evaluation Lab | `/platform/agents` Quality tab | 增强 | P2 | Agent 配置评测和回归测试 |

### 4.3 路由清理

现有组件中仍有 `/ai/agents`、`/ai/copilot` 的残留链接。规划实施时应统一:

| 残留 | 替换 |
|------|------|
| `/ai/agents` | `/platform/agents` |
| `/ai/copilot` | 打开全局 Copilot Sidecar |
| AI Overview 页面 | Home + Platform/Agents + Sidecar 能力拆分 |

---

## 5. 核心前端类型契约

### 5.1 Agent Run

```typescript
export type AgentRunStatus =
	| "queued"
	| "running"
	| "partial"
	| "blocked"
	| "waiting-approval"
	| "failed"
	| "completed"
	| "cancelled";

export type AgentRunKind =
	| "daily-brief"
	| "alpha-discovery"
	| "strategy-build"
	| "strategy-maintenance"
	| "position-review"
	| "risk-review"
	| "data-health"
	| "agent-evaluation";

export type AgentRunView = {
	readonly id: string;
	readonly kind: AgentRunKind;
	readonly title: string;
	readonly status: AgentRunStatus;
	readonly progress?: number;
	readonly startedAt?: string;
	readonly updatedAt: string;
	readonly objective: string;
	readonly budget: AgentRunBudget;
	readonly artifactIds: readonly string[];
	readonly findingIds: readonly string[];
};
```

### 5.2 Finding Union

```typescript
export type AgentFindingBase = {
	readonly id: string;
	readonly runId: string;
	readonly title: string;
	readonly summary: string;
	readonly confidence: number;
	readonly status: "pending" | "approved" | "rejected" | "expired";
	readonly severity: "info" | "warning" | "critical";
	readonly evidence: readonly EvidenceRef[];
	readonly createdAt: string;
};

export type AgentFinding =
	| TextFinding
	| FactorCandidateFinding
	| StrategyProposalFinding
	| OptimizationProposalFinding
	| RiskAlertFinding
	| DataQualityFinding
	| EvaluationFinding;
```

### 5.3 Artifact

```typescript
export type AiArtifact =
	| ReportArtifact
	| FactorArtifact
	| StrategySpecArtifact
	| BacktestArtifact
	| DatasetArtifact
	| ChartArtifact
	| TraceArtifact
	| EvalArtifact;
```

### 5.4 Event Stream

```typescript
export type AgentStreamEvent =
	| { readonly type: "run.started"; readonly run: AgentRunView }
	| { readonly type: "run.progress"; readonly runId: string; readonly progress: number; readonly stage: string }
	| { readonly type: "tool.started"; readonly call: ToolInvocation }
	| { readonly type: "tool.completed"; readonly call: ToolInvocationResult }
	| { readonly type: "artifact.created"; readonly artifact: AiArtifact }
	| { readonly type: "finding.created"; readonly finding: AgentFinding }
	| { readonly type: "approval.requested"; readonly approval: ApprovalRequest }
	| { readonly type: "guardrail.blocked"; readonly result: GuardrailResult }
	| { readonly type: "run.failed"; readonly runId: string; readonly error: AgentError }
	| { readonly type: "run.completed"; readonly runId: string; readonly artifactIds: readonly string[] };
```

### 5.5 Transport Adapter

当前 `package.json` 没有 `ai` 依赖，且新增依赖需单独批准。因此前端先定义 adapter，不默认引入 Vercel AI SDK:

```typescript
export interface AiStreamTransport {
	readonly subscribeRun: (runId: string) => AsyncIterable<AgentStreamEvent>;
	readonly sendCopilotMessage: (request: CopilotMessageRequest) => AsyncIterable<CopilotStreamEvent>;
	readonly cancelRun: (runId: string) => Promise<void>;
}
```

后续后端协议稳定后，可在不影响 UI 契约的前提下选择 native `EventSource`、fetch streaming 或第三方 SDK。

---

## 6. 页面拆分

## 6.1 Global Copilot Sidecar

### 页面角色

跨域上下文助手。它不是聊天产品，而是当前页面的解释、生成、转化和发送到工作区层。

### 上下文模式

| 模式 | 触发页面 | 结构化输出 |
|------|----------|------------|
| Market Analysis | Markets / Intelligence | MarketBrief、MacroDriver、WatchlistAction |
| Instrument Review | Instrument Hub | InstrumentThesis、RiskNote、SignalDraft |
| Factor Discovery | Factor Analysis / Alpha Explorer | FactorHypothesis、FactorCandidate |
| Strategy Draft | Strategy Studio | StrategySpecDraft、RiskRuleDraft |
| Backtest Review | Backtest Result | BacktestDiagnosis、OptimizationHint |
| Signal Review | Signals Inbox | SignalInterpretation、RiskOfficerDecision |
| Agent Run Assist | Agent Console | RunSummary、TraceExplanation、ApprovalAdvice |

### 必备组件

- Context Header: 当前页面对象、数据时间、来源状态。
- Conversation Blocks: 非气泡式结构块，区分用户输入、AI 解释、工具结果、结构化产物。
- Structured Output Shelf: 因子、策略、信号、笔记、报告等可发送对象。
- Workspace Actions: 发送到 Factor Analysis / Strategy Studio / Backtest / Watchlist / Agent Console。
- Evidence Drawer: 展示证据链、引用对象、数据版本、工具调用。
- Failure Recovery: 断流重连、消息重试、降级为只读解释。

### 状态矩阵

| 组件 | default | loading | empty | failed | streaming | blocked |
|------|---------|---------|-------|--------|-----------|---------|
| Context Header | 当前对象摘要 | skeleton | 无上下文提示 | 上下文读取失败 | 数据时间实时更新 | 权限不足 |
| Conversation Blocks | 历史块 | 消息骨架 | 引导输入 | 发送失败 + 重试 | 增量输出 | guardrail 提示 |
| Structured Output Shelf | 产物列表 | 骨架 | 暂无产物 | 渲染失败 | 新产物插入 | 产物需审批 |
| Workspace Actions | 动作按钮 | disabled | disabled | disabled | 可部分禁用 | 展示原因 |

---

## 6.2 Agent Console V2

### 页面角色

Agent Console 是 AI 长任务和审批治理中心。用户在这里看计划、运行、发现、审批、工具追踪、产物和质量评测。

### Tab 结构

| Tab | 角色 | 优先级 |
|-----|------|--------|
| Plans | 创建和管理 Agent Plan | P0 |
| Runs | 运行队列、状态、失败恢复 | P0 |
| Findings | 所有结构化发现 | P0 |
| Approvals | 需要人工处理的审批 | P0 |
| AutoResearch | 自主研究运行总览 | P1 |
| Artifacts | 报告、策略、因子、回测、数据集 | P1 |
| Quality | Agent/prompt/tool 评测 | P2 |
| Policies | 当前计划使用的权限和预算摘要 | P2 |

### 核心布局

- 左: Plan/Run/Filter 列表。
- 中: Timeline / Finding table / AutoResearch dashboard / Quality dashboard。
- 右: Inspector，承载 Run detail、Trace、Evidence、Artifacts、Approval。

### 结构化 Finding 卡片

| 类型 | UI 重点 | 主动作 |
|------|---------|--------|
| TextFinding | 摘要、置信度、证据 | 查看详情 |
| FactorCandidateFinding | 公式、IC、ICIR、换手、相关性、新颖度 | 发送 Alpha / Factor Analysis |
| StrategyProposalFinding | StrategySpec、回测摘要、风险摘要 | 进入 Studio / 提交回测 |
| OptimizationProposalFinding | 权重 diff、预测影响、模拟状态 | 模拟回测 / 采纳 |
| RiskAlertFinding | 严重度、影响范围、阻断原因 | 查看受影响对象 / 启动修复 |
| DataQualityFinding | 数据源、缺口、延迟、影响页面 | 查看数据健康 / 重新同步 |
| EvaluationFinding | Agent 配置、任务集、得分变化 | 查看 Quality tab |

### Inspector 区块

| 区块 | 内容 |
|------|------|
| Run Summary | 目标、状态、预算、开始时间、最后更新时间 |
| Agent Pipeline | Analyst / Researcher / Trader / Risk / PM 阶段状态 |
| Activity Stream | 实时事件流，按 run event 分组 |
| Tool Trace | 工具名、输入摘要、输出摘要、耗时、状态、重试 |
| Evidence Chain | 数据来源、对象链接、样本区间、版本 |
| Artifact Viewer | 报告、因子、策略、回测、数据集、图表 |
| Approval Panel | Approve / Reject / Comment / Request changes |
| Guardrail Result | 被阻断的动作、原因、可恢复建议 |
| Cost & Budget | token、工具调用数、耗时、估算成本、预算剩余 |

### Overlay Registry

| Overlay | 类型 | 触发 | 内容 |
|---------|------|------|------|
| Plan Create | Sheet | 新建计划 | 类型、目标、范围、约束、触发方式、预算 |
| Run Rerun | Sheet | 重跑 | 使用原参数 / 修改参数 / 跳过已成功阶段 |
| Approval Confirm | Modal | 审批动作 | 变更摘要、风险摘要、确认 |
| Tool Trace Detail | Drawer | 点击工具调用 | input/output、耗时、错误、artifact |
| Artifact Preview | Drawer | 点击产物 | 结构化预览、复制引用、发送工作区 |
| Guardrail Detail | Drawer | 被阻断 | policy、原因、申请权限入口 |
| Quality Run Create | Sheet | 新建评测 | 任务集、Agent 配置、预算 |

---

## 6.3 Alpha Explorer

### 基本信息

| 字段 | 值 |
|------|----|
| 路由 | `/research/alpha` |
| 域 | Research |
| shellFamily | `studio` |
| pagePattern | `studio-builder` |
| 页面目标 | 因子发现、评估、采纳和实验追踪 |

### 模式

| 模式 | 用户参与 | 入口 | 产出 |
|------|----------|------|------|
| Copilot Explore | 高 | 用户配置约束并对话引导 | FactorCandidate、ExperimentDraft |
| AutoResearch Review | 中 | 从 Agent Console 深链进入 Run | Run Roadmap、Discovery List |
| Factor Lab | 高 | 对候选因子做手动诊断 | FactorArtifact、BacktestArtifact |

### 核心区块

- Search Space Config: universe、数据字段、算子族、排除项。
- Constraint Panel: min IC、max turnover、correlation cap、coverage、capacity、regime。
- Exploration Stream: 候选因子增量流，显示公式、指标、发现原因。
- Pareto Frontier: IC vs turnover / ICIR vs correlation / novelty vs stability。
- Candidate Inspector: 公式、解释、样本外、分层收益、行业暴露、相似因子。
- Experiment Graph: 从假设到候选、优化、回测、采纳的 lineage。
- Adoption Queue: 待采纳、待补测、已拒绝。

### 主流程

1. 用户选择 universe、搜索空间和约束。
2. Copilot 生成或解释探索目标。
3. Exploration Stream 推送候选因子。
4. 用户对候选因子执行深入、变体、排除、采纳。
5. 采纳前必须展示样本外、相关性、换手、容量、行业暴露和过拟合警告。
6. 采纳后生成 FactorArtifact，并发送到 Factor Analysis / Experiment List。

### 状态矩阵

| 组件 | default | loading | empty | failed | running | partial | blocked |
|------|---------|---------|-------|--------|---------|---------|---------|
| Config | 表单 | 字段骨架 | 默认模板 | 因子库加载失败 | disabled | — | 权限不足 |
| Exploration Stream | 候选卡片 | 骨架 | 配置后开始探索 | Agent 异常 | 新卡片流入 | 部分指标待算 | 预算不足 |
| Pareto Frontier | 散点图 | 图表骨架 | 空坐标 | 渲染失败 | 实时点位 | 部分点灰态 | — |
| Candidate Inspector | 详情 | 骨架 | 未选中 | 加载失败 | 指标刷新 | 部分诊断可见 | 采纳被阻断 |
| Experiment Graph | lineage | 骨架 | 无实验 | 加载失败 | 节点增加 | 部分 artifact 待生成 | — |

---

## 6.4 Strategy Studio AI Modes

### 模式切换

现有模式从 `Form | Code` 升级为:

| 模式 | 定位 |
|------|------|
| Manual | 专业用户手动配置。内部可保留 Form / Code 子切换 |
| Guided | Copilot 引导构建，用户逐步确认 |
| Agent | 用户给目标，Agent 自主生成候选策略并回测 |

### Guided 模式

核心布局:

- 左: Guided Conversation，按步骤收集目标、universe、因子偏好、风控约束。
- 中: Strategy Inspector，实时展示 StrategySpec、因子权重、IC 预测、风险检查。
- 右: Progress / Decisions，展示已确认和待确认步骤。

必备动作:

- 应用建议到当前策略。
- 对比 Manual 当前配置。
- 发送到 Backtest。
- 保存为 draft。
- 进入 Manual 精调。

### Agent 模式

核心布局:

- Goal Card: 年化、MDD、换手、universe、实验预算、可用因子。
- Activity Stream: 选基线、回测、评估、调整、再回测。
- Candidate Strategy Board: 多个候选策略并排比较。
- Strategy Output Card: Config / Backtest / Decision Log / Risk。
- Approval Bar: 采纳、拒绝、提交回测、进入 Manual。

### StrategySpec 前端契约

```typescript
export type StrategySpecDraft = {
	readonly id: string;
	readonly universeId: string;
	readonly factors: readonly StrategyFactorWeight[];
	readonly weighting: "equal" | "ic-weighted" | "risk-budget" | "manual";
	readonly rebalance: RebalanceRule;
	readonly riskRules: readonly StrategyRiskRule[];
	readonly costModelId: string;
	readonly constraints: readonly StrategyConstraint[];
	readonly source: "manual" | "copilot" | "agent";
};
```

---

## 6.5 Strategy Detail Optimization

### Tab 变更

Strategy Detail tab 增加 `优化`:

```
概览 | 配置 | 因子 | 回测历史 | 信号 | 优化 | 版本
```

### 核心区块

- Health Monitor: 实际 Sharpe vs 预期、回撤漂移、换手漂移。
- Factor Contribution Drift: 因子贡献、IC 衰减、相关性变化。
- Regime Fit: 当前 regime 与策略设计假设的匹配度。
- Optimization Proposal List: 调权、换因子、加风控、加择时、暂停策略。
- Simulation Drawer: 采纳前模拟回测。
- Change Diff: 策略配置变更前后对比。

### 提案状态

| 状态 | UI 表达 |
|------|---------|
| pending | 待审，显示预测影响 |
| simulating | 进度条和部分结果 |
| simulated | 显示模拟回测结果 |
| approved | 标记已采纳并链接版本 |
| rejected | 保留原因 |
| expired | 提案过期，不可操作 |

---

## 6.6 Signals AI Review

### 页面角色

Signals Inbox 是交易执行前的最后人工复核点。AI 只能解释和预筛选，不能绕过审批。

### 增强区块

| 区块 | 内容 |
|------|------|
| AI Interpretation | 信号来源、市场背景、因子贡献、冲突证据 |
| Risk Officer Decision | PASS / WARN / BLOCK，说明仓位、流动性、相关性、T+1、涨跌停 |
| Execution Preview | 预计订单、滑点、成交风险、资金占用 |
| Evidence Chain | 策略、回测、行情、持仓、风控规则 |
| Approval Actions | approve、reject、request changes、send to order |

### 风控阻断场景

- 单票集中度超限。
- 行业暴露偏离超限。
- 涨跌停或停牌导致不可交易。
- T+1 规则导致卖出不可执行。
- 数据过期或行情延迟。
- 策略版本已 stale。

---

## 6.7 Home Daily Quant Brief

### 页面角色

Home 是 5 秒态势感知入口。AI 不做大段叙述，只展示今天需要处理的工作队列。

### 区块

| 区块 | 内容 |
|------|------|
| Daily Brief Strip | 盘前/盘中/盘后摘要，显示时间和数据新鲜度 |
| Priority Findings | 结构化 Finding 前 5 条，按风险和时效排序 |
| Pending Approvals | 需要用户处理的 Agent/Signal/Strategy 审批 |
| Data Health | 数据源延迟、缺口、失败任务 |
| Research Queue | Alpha / Strategy / Optimization 的待处理产物 |

### Finding 卡片简化规则

Home 只展示结论摘要、严重度、关键指标和主动作。完整 Trace 必须跳转 Agent Console。

---

## 6.8 Platform Settings AI Section

### 页面角色

AI 设置不是模型偏好面板，而是 Agent 能力的治理面板。

### 配置项

| 配置 | 内容 |
|------|------|
| Model Policy | 默认模型、fallback、成本等级、禁用场景 |
| Tool Permission | 工具白名单、危险工具审批、只读/可写/可交易 |
| Budget Policy | 单次 run token、工具调用、时间、回测次数上限 |
| Approval Policy | 哪些 Finding 可自动通过，哪些必须人工审批 |
| Data Policy | 可访问数据源、敏感字段、脱敏规则 |
| Guardrails | prompt injection、越权工具、交易动作阻断规则 |
| Audit Retention | trace、artifact、approval log 保存时长 |

---

## 6.9 Agent Evaluation Lab

### 页面角色

顶尖 Agent 产品必须能评测自己。Quality tab 用来比较 Agent 配置、prompt、工具集合和模型版本。

### 核心区块

- Eval Task Set: 因子衰减诊断、信号解释、策略优化、数据异常定位等固定任务。
- Candidate Configs: Agent 配置、模型、prompt、工具权限。
- Score Board: 正确性、可执行性、证据完整度、过拟合风险、成本、耗时。
- Regression History: 版本间得分变化。
- Failure Gallery: 错误案例、幻觉、证据不足、工具失败、过度交易建议。

### 前端价值

即使后端暂未实现，前端也要先定义质量仪表盘和 mock 数据，因为它决定了 Ditto 对 AI 的信任边界。

---

## 7. 统一组件清单

| 组件 | 复用页面 | 优先级 |
|------|----------|--------|
| AgentRunTimeline | Agent Console、Strategy Studio、Alpha Explorer | P0 |
| ToolTraceList | Agent Console、Copilot Evidence、Signals | P0 |
| EvidenceChain | Copilot、Findings、Signals、Strategy | P0 |
| ArtifactViewer | Agent Console、Alpha Explorer、Strategy Studio | P0 |
| ApprovalPanel | Agent Console、Signals、Strategy Detail | P0 |
| FindingCard | Home、Agent Console、Platform | P0 |
| GuardrailBlock | Agent Console、Signals、Copilot | P0 |
| BudgetMeter | Agent Console、Alpha Explorer、Strategy Agent | P1 |
| ParetoFrontierChart | Alpha Explorer | P1 |
| StrategySpecPreview | Strategy Studio、Agent Console | P1 |
| OptimizationDiff | Strategy Detail、Agent Console | P2 |
| EvalScoreCard | Agent Console Quality | P2 |

---

## 8. 统一状态模型

| 状态 | 适用场景 | UI 表达 |
|------|----------|---------|
| loading | 首次加载 | skeleton |
| empty | 无业务对象 | 空态 + CTA |
| failed | 请求失败 | 错误说明 + retry |
| stale | 数据过期 | 时间戳 + 黄色提示 |
| queued | Agent/Backtest 排队 | 队列位置 |
| running | 长任务运行 | 脉冲、活动流、可取消 |
| streaming | 文本/事件流 | 增量插入 |
| partial | 部分 artifact 可见 | 已完成部分正常展示，待完成灰态 |
| blocked | guardrail 或权限阻断 | 红色阻断块 + 原因 |
| waiting-approval | 需要人工审批 | ApprovalPanel 自动露出 |
| budget-exceeded | 超预算 | 预算块 + 调整入口 |
| data-missing | 数据缺失 | 缺口说明 + 数据健康链接 |
| tool-error | 工具调用失败 | Tool Trace 中标红 |
| cancelled | 用户或系统取消 | 终态说明 |
| completed | 成功完成 | artifact / finding / next action |

---

## 9. 后端交接边界

本项目只定义以下 contract，后端服务项目实现:

### 9.1 REST 占位

| API | 用途 |
|-----|------|
| `GET /api/ai/agents/plans` | Plan 列表 |
| `POST /api/ai/agents/plans` | 创建 Plan |
| `GET /api/ai/agents/runs` | Run 列表 |
| `GET /api/ai/agents/runs/:id` | Run 详情 |
| `POST /api/ai/agents/runs/:id/rerun` | 重跑 |
| `POST /api/ai/agents/runs/:id/cancel` | 取消 |
| `GET /api/ai/agents/findings` | Finding 列表 |
| `GET /api/ai/agents/findings/:id/trace` | Trace 详情 |
| `POST /api/ai/agents/findings/:id/approve` | 审批 |
| `POST /api/ai/agents/findings/:id/reject` | 拒绝 |
| `GET /api/ai/artifacts/:id` | Artifact 详情 |
| `POST /api/ai/copilot/messages` | Copilot 消息 |
| `GET /api/ai/evals/runs` | Eval Run 列表 |
| `POST /api/ai/evals/runs` | 启动评测 |

### 9.2 Streaming 占位

| Stream | 用途 |
|--------|------|
| `/api/ai/agents/runs/:id/events` | Agent run event stream |
| `/api/ai/copilot/sessions/:id/events` | Copilot response stream |
| `/api/ai/alpha/runs/:id/events` | Alpha exploration stream |
| `/api/ai/strategy/runs/:id/events` | Strategy build stream |
| `/api/ai/evals/runs/:id/events` | Evaluation stream |

### 9.3 后端必须保证

- 所有 destructive action 需要 approval id。
- 所有 AI 输出返回 schema version。
- 所有 tool call 有 input/output 摘要、耗时、状态和 artifact link。
- 所有 Run 可恢复、可取消、可失败重试。
- 所有 Artifact 可追溯到 run、tool、data snapshot。
- 所有 Finding 可被拒绝并保留原因。

---

## 10. 分阶段实施

### M0: 契约与 IA 清理

目标: 让前端 AI 能力边界清楚，避免 `/ai` 路由和 mock 类型继续漂移。

- 更新 AI 类型 union。
- 补齐 AgentRunStatus、AgentEvent、Artifact、Evidence、Approval 类型。
- 清理 `/ai/agents`、`/ai/copilot` 链接。
- 新增/更新 MSW fixture。
- 更新 page contract 和 glossary 增量。

### M1: Agent Console V2

目标: 先把任务治理、Finding、审批、Trace 做成核心工作台。

- Plans/Runs/Findings/Approvals tab。
- 结构化 FindingCard。
- Inspector: Activity、Tool Trace、Evidence、Artifact、Approval。
- Guardrail/blocked/waiting-approval 状态。
- Component tests + contract tests。

### M2: Copilot Sidecar V2

目标: 全局上下文助手不再只是会话面板，而是可输出结构化工作对象。

- Context Header。
- Conversation Block。
- Structured Output Shelf。
- Workspace Actions。
- Evidence Drawer。
- Transport adapter mock。

### M3: Alpha Explorer

目标: 建立因子发现工作台。

- `/research/alpha` route。
- Config / Exploration Stream / Pareto Frontier / Candidate Inspector。
- Experiment Graph。
- Adoption Queue。
- AutoResearch deep link。

### M4: Strategy AI

目标: 把自然语言目标转成可验证策略草稿。

- Strategy Studio Manual/Guided/Agent 模式。
- StrategySpecPreview。
- Agent Activity Stream。
- Candidate Strategy Board。
- Backtest handoff mock。

### M5: Trading / Maintenance / Quality

目标: 完成闭环，让 AI 进入执行、维护和自我评测。

- Signals AI Review + Risk Officer。
- Strategy Detail Optimization tab。
- Home Daily Quant Brief。
- Platform Settings AI section。
- Agent Console Quality tab。

---

## 11. 验收标准

| 类别 | 标准 |
|------|------|
| IA | 不恢复 AI 一级域；新增路由仅 `/research/alpha` |
| 类型 | 所有 AI 输出使用 discriminated union，不使用 `any` |
| 状态 | loading/empty/failed/stale/running/blocked/waiting-approval 覆盖 |
| 审批 | 采纳因子、策略、优化、交易动作都有审批 UI |
| Trace | Finding 和 Artifact 都能打开 Evidence/Tool Trace |
| Mock | 每个页面有 default、empty、failed、running 样本 |
| 测试 | 新增组件测试和契约测试 |
| 视觉 | 服从现有 shell、density、panel、status 规范 |
| 后端交接 | API/stream/artifact/approval contract 清晰 |

---

## 12. Changelog

### 2026-05-02 — v2

- 将初稿升级为前端统一功能拆分规划。
- 明确前端项目范围: UI、契约、状态、mock、交互，不实现后端 Agent Runtime。
- 对齐既有 IA: AI 域废弃，Copilot 为全局 Sidecar，Agent Console 属于 Platform。
- 保留并重组 Alpha Explorer、Strategy Studio、Agent Console、Strategy Detail、Copilot、Home。
- 新增 Signals AI Review、AI Policy Settings、Agent Evaluation Lab、Artifact / Trace / Guardrail 能力。
- 修正 Vercel AI SDK 默认引入问题: 当前项目无 `ai` 依赖，先定义 transport adapter。

### 2026-05-02 — v1

- 初始设计方案。
- 基于 `2026-05-01-ai-capability-enhancement-design.md`。
- 提出 Alpha Explorer 新路由、Strategy Studio AI 模式、Agent Console AutoResearch tab。
