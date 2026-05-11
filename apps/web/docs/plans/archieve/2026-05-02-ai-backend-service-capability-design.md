# AI 后端服务完整能力规划

> 日期: 2026-05-02
> 状态: Draft v1
> 上游: `docs/plans/2026-05-01-ai-capability-enhancement-design.md`
> 前端配套: `docs/plans/2026-05-02-ai-feature-page-design.md`
> 范围: 后端 AI 服务项目需要承接的 Agent Runtime、工具层、量化研发、回测、调度、安全、观测、评测和 API/SSE 契约
> 非范围: 本前端仓库内的 UI 实现、React 组件、MSW mock、页面视觉细节

---

## 0. 结论

后端服务的目标不是做一个聊天接口，而是建设 Ditto 的量化 Agent 操作系统。它需要把前端定义的页面能力背后的真实执行层补齐:

- Agent 能计划、运行、暂停、取消、恢复、失败重试。
- 每个结论都能追溯到工具调用、数据快照、参数、artifact 和审批记录。
- 因子发现、策略构建、策略维护必须进入可复现的实验闭环。
- 交易相关动作必须经过风控和人工审批，不能被 LLM 直接执行。
- 所有长任务必须通过事件流向前端增量推送状态、工具调用、artifact 和 Finding。
- 所有 Agent 配置、prompt、工具集合和模型版本必须可评测、可回归比较。

一句话: 后端要提供一个可审计、可复现、可评测、可控权的量化 AI 运行平台。

---

## 1. 设计原则

| 原则 | 后端要求 |
|------|----------|
| Deterministic Core | 回测、风控、编译、审批、权限必须确定性执行，LLM 只能提出候选和解释 |
| Human Approval | 因子入库、策略采纳、优化应用、交易下单都需要审批令牌 |
| Trace Everything | run、tool call、guardrail、artifact、approval、data snapshot 都要有 trace id |
| Schema First | Agent 输出必须经过 schema validation，拒绝自由文本直接落库 |
| Replayable Research | 因子和策略实验必须可重跑，包含数据版本、代码版本、参数和环境 |
| Budget Bounded | 每个 run 有 token、工具调用、回测次数、耗时和资金风险预算 |
| Least Privilege | 工具权限按 agent、计划、用户、数据源、动作粒度控制 |
| Failure Visible | 失败是业务对象，不是日志尾巴；前端能看到原因、恢复动作和影响范围 |
| Eval Driven | Agent 质量必须用固定任务集持续评测，不能只靠主观感觉 |

---

## 2. 业界基线

| 参考 | 后端启发 |
|------|----------|
| OpenAI Agents SDK | Agent 需要工具调用、handoff、streaming、guardrails 和完整 trace |
| MCP | 工具、数据和 prompts 应该标准化暴露，但必须配套权限与审计 |
| MCP Security Best Practices | 重点防 session hijack、prompt injection、宽 token、工具越权和敏感数据泄露 |
| Google A2A | 长任务应有 Task / Message / Artifact / Agent Card，支持 streaming、断线恢复和能力发现 |
| Microsoft R&D-Agent(Q) | 量化研发应拆成 Research / Development 循环，围绕因子和模型做协同优化 |
| TradingAgents | 多 Agent 角色和 Bull/Bear debate 对交易判断有价值，但最终必须经过 Risk / PM gate |
| QuantConnect MCP | AI 可辅助写策略、回测、优化和部署，但每一步都要落在平台 API 与权限边界内 |

---

## 3. 总体架构

```
Frontend
  ├── Copilot Sidecar
  ├── Agent Console
  ├── Alpha Explorer
  ├── Strategy Studio
  ├── Signals Inbox
  └── Home Daily Brief
        │ REST + SSE
        ▼
AI Service Backend
  ├── API Layer
  │   ├── REST resources
  │   ├── SSE event streams
  │   └── auth / rate limit / request validation
  │
  ├── Agent Runtime
  │   ├── Orchestrator
  │   ├── Run state machine
  │   ├── Planner / Router / Handoff
  │   ├── Guardrail engine
  │   ├── Budget manager
  │   └── Event publisher
  │
  ├── Tool Platform
  │   ├── Tool Registry
  │   ├── Tool Permission Engine
  │   ├── MCP adapters
  │   ├── Data tools
  │   ├── Quant tools
  │   ├── Backtest tools
  │   └── Trading/risk tools
  │
  ├── Quant Research Services
  │   ├── Factor Engine
  │   ├── Alpha Factory
  │   ├── Experiment Graph
  │   ├── Strategy Spec Compiler
  │   ├── Backtest / Simulation
  │   └── Strategy Maintenance
  │
  ├── Governance Services
  │   ├── Approval service
  │   ├── Policy service
  │   ├── Audit log
  │   ├── Evaluation service
  │   └── Observability
  │
  └── Storage
      ├── relational metadata
      ├── artifact store
      ├── vector / retrieval index
      ├── time-series snapshots
      └── trace / event log
```

---

## 4. 服务边界

| 服务 | 职责 | 不负责 |
|------|------|--------|
| API Gateway | 鉴权、限流、schema validation、REST/SSE 出口 | Agent 决策 |
| Agent Runtime | 计划编排、运行状态、事件流、handoff、guardrail | 具体金融计算 |
| Tool Registry | 工具注册、权限、输入输出 schema、调用审计 | 业务 UI |
| Copilot Service | 会话、上下文构建、结构化输出、工作区动作草案 | 自动执行交易 |
| Alpha Factory | 因子生成、评估、去重、样本外验证、采纳候选 | 直接修改生产策略 |
| Strategy Service | StrategySpec、编译、校验、候选策略、版本 | 真实下单 |
| Backtest Service | 回测、成本、滑点、walk-forward、压力测试 | LLM 推理 |
| Risk Service | 风控规则、阻断、风险解释、交易前检查 | 自动绕过审批 |
| Scheduler | 定时/事件驱动任务、重试、补偿 | 决策质量评估 |
| Artifact Service | 报告、因子、策略、数据集、图表、trace 存取 | 业务决策 |
| Evaluation Service | Agent/prompt/tool/model 评测与回归 | 线上交易执行 |
| Policy Service | 模型、工具、数据、预算、审批策略 | 绕过审计 |

---

## 5. 核心领域模型

### 5.1 AgentPlan

AgentPlan 是可重复执行的任务模板。

关键字段:

- `id`
- `kind`: daily-brief / alpha-discovery / strategy-build / strategy-maintenance / position-review / risk-review / data-health / agent-evaluation
- `objective`
- `scope`
- `constraints`
- `agent_profile`
- `tool_policy_id`
- `budget_policy_id`
- `approval_policy_id`
- `schedule`
- `created_by`
- `status`

### 5.2 AgentRun

AgentRun 是 Plan 的一次执行。

状态:

- queued
- running
- partial
- blocked
- waiting-approval
- failed
- completed
- cancelled

关键字段:

- `id`
- `plan_id`
- `kind`
- `trace_id`
- `status`
- `current_stage`
- `progress`
- `budget_used`
- `started_at`
- `updated_at`
- `completed_at`
- `failure_reason`
- `artifact_ids`
- `finding_ids`

### 5.3 ToolInvocation

工具调用必须是一等对象。

关键字段:

- `id`
- `run_id`
- `trace_id`
- `tool_name`
- `tool_version`
- `permission_scope`
- `input_schema_version`
- `input_summary`
- `output_summary`
- `artifact_ids`
- `status`
- `duration_ms`
- `error_code`
- `created_at`

### 5.4 Finding

Finding 是 Agent 运行产出的可审查结论，不是普通消息。

类型:

- TextFinding
- FactorCandidateFinding
- StrategyProposalFinding
- OptimizationProposalFinding
- RiskAlertFinding
- DataQualityFinding
- EvaluationFinding
- SecurityFinding

共用字段:

- `id`
- `run_id`
- `schema_version`
- `title`
- `summary`
- `confidence`
- `severity`
- `status`
- `evidence_refs`
- `artifact_refs`
- `approval_required`
- `created_at`

### 5.5 Artifact

Artifact 是所有可复现结果的统一容器。

类型:

- report
- factor
- strategy_spec
- backtest
- dataset_snapshot
- chart
- trace
- eval_result
- approval_record

关键字段:

- `id`
- `type`
- `schema_version`
- `run_id`
- `source_tool_call_id`
- `storage_uri`
- `content_hash`
- `metadata`
- `created_at`

### 5.6 EvidenceRef

EvidenceRef 用于把结论追溯到数据和工具。

来源类型:

- data_snapshot
- tool_invocation
- artifact
- backtest_run
- factor_result
- risk_check
- market_event
- user_note

---

## 6. Agent Runtime

### 6.1 Orchestrator

职责:

- 根据 Plan kind 选择 workflow。
- 根据上下文选择 Agent profile 和 tools。
- 管理多 Agent handoff。
- 发布 run events。
- 处理中断、取消、恢复和重试。

### 6.2 Workflow 模板

| Workflow | 阶段 |
|----------|------|
| Daily Brief | data health -> market scan -> risk scan -> priority findings -> report |
| Alpha Discovery | hypothesis -> factor expression -> factor compute -> validation -> novelty check -> finding |
| Strategy Build | goal parse -> strategy spec draft -> compile -> backtest -> risk check -> proposal |
| Strategy Maintenance | health scan -> drift detection -> proposal -> simulation -> approval request |
| Signal Review | signal context -> risk check -> evidence build -> interpretation -> approval request |
| Data Health | source checks -> gap detection -> impact analysis -> repair suggestion |
| Agent Evaluation | task set load -> candidate run -> scoring -> regression compare -> eval artifact |

### 6.3 Agent 角色

| 角色 | 职责 | 可用工具 |
|------|------|----------|
| FundamentalAnalyst | 财务、估值、基本面解释 | financials、factor、report tools |
| TechnicalAnalyst | K 线、趋势、波动、成交 | market data、indicator tools |
| SentimentAnalyst | 新闻、公告、舆情 | news、announcement、sentiment tools |
| QuantResearcher | 因子假设、实验设计 | factor engine、experiment graph |
| BullResearcher | 看多论据与正向假设 | evidence、market、backtest tools |
| BearResearcher | 看空论据、反证和风险 | risk、drawdown、correlation tools |
| TraderAgent | 生成信号或策略提案 | strategy、signal、portfolio tools |
| RiskOfficer | 风险检查、阻断、限制条件 | risk engine、portfolio、rules |
| PMAgent | 最终建议、审批请求整理 | artifact、approval、summary tools |
| DataSteward | 数据质量与修复建议 | data source、lineage、health tools |

### 6.4 Run 生命周期

```
created
  -> queued
  -> running
  -> partial
  -> waiting-approval
  -> completed

running
  -> blocked
  -> failed
  -> cancelled

blocked
  -> waiting-approval
  -> failed
  -> cancelled

failed
  -> queued (rerun)
```

### 6.5 Budget Manager

每个 run 必须支持:

- token 上限
- LLM 调用次数上限
- tool 调用次数上限
- 回测次数上限
- wall-clock 时间上限
- artifact 存储上限
- 风险动作上限

预算超限时进入 `blocked` 或 `waiting-approval`。

---

## 7. Tool Platform

### 7.1 Tool Registry

每个 tool 必须注册:

- name
- version
- description
- input schema
- output schema
- permission scope
- side_effect level: read / write / trade / destructive
- timeout
- retry policy
- owner service
- audit level

### 7.2 工具分类

| 分类 | 工具示例 |
|------|----------|
| Market Data | get_quotes、get_kline、get_order_book、get_market_calendar |
| Fundamentals | get_financials、get_valuation、get_earnings_calendar |
| News/Event | get_news、get_announcements、get_macro_events |
| Factor | compute_factor、calc_ic、calc_icir、factor_decay、factor_correlation |
| Strategy | compile_strategy_spec、validate_strategy、generate_strategy_variant |
| Backtest | run_backtest、run_walk_forward、run_stress_test、compare_backtests |
| Risk | check_position_limit、check_sector_exposure、check_liquidity、check_var |
| Trading | create_signal、dry_run_order、submit_order_pending_approval |
| Artifact | create_report、create_chart、save_dataset_snapshot |
| Eval | run_eval_task、score_agent_output、compare_eval_runs |

### 7.3 权限策略

| side_effect | 说明 | 默认审批 |
|-------------|------|----------|
| read | 读取数据 | 不需要 |
| write | 写入研究对象、草稿、artifact | 视对象而定 |
| trade | 生成信号、订单草案 | 必须审批 |
| destructive | 删除、覆盖、下单、修改生产策略 | 必须审批 + 二次确认 |

### 7.4 MCP / 外部工具适配

后端可支持 MCP 风格的工具接入，但必须通过本地 Tool Registry 包装:

- 不直接把外部 tool 暴露给 Agent。
- 每个外部 tool 映射成本地 schema。
- 每次调用检查 tool policy。
- 输出先落 artifact，再进入 Agent 上下文。
- 对 tool metadata 做可信源校验，避免 tool poisoning。

---

## 8. 数据服务

### 8.1 数据源

| 数据源 | 用途 | 后端要求 |
|--------|------|----------|
| tushare | A 股历史行情、财务、基础数据 | 快照、补全、质量检查 |
| MiniQMT | 实时行情、持仓、交易通道 | 低延迟、连接健康、交易前门控 |
| 通达信 | 辅助行情和交叉验证 | 差异检测 |
| FRED | 宏观数据 | 频率对齐、版本化 |
| News/公告 | 事件和情绪 | 来源、时间、去重、引用 |
| User Research | 用户笔记和策略假设 | 权限和上下文检索 |

### 8.2 Data Snapshot

所有实验必须引用数据快照:

- universe membership
- price data interval
- adjusted/unadjusted flag
- corporate action version
- financial report version
- trading calendar
- data source version
- retrieval timestamp

### 8.3 Data Health

数据健康检查:

- 延迟
- 缺口
- 异常值
- 停牌/涨跌停状态缺失
- 复权不一致
- 多数据源差异
- MiniQMT 连接状态
- 对页面、策略、回测和交易的影响范围

---

## 9. Quant Research Services

## 9.1 Factor Engine

能力:

- 因子表达式解析
- 因子计算
- 缺失值处理
- winsorize / zscore / neutralize
- IC / RankIC / ICIR
- 分层收益
- 换手
- 覆盖率
- 容量估计
- 行业和风格暴露
- 与现有因子相关性
- 衰减检测
- 样本外验证
- regime 分段表现

### 9.2 Alpha Factory

能力:

- 从自然语言目标生成因子假设。
- 从假设生成表达式候选。
- 对候选做快速筛选。
- 对有效候选做深度验证。
- 生成相似因子去重。
- 维护 Pareto frontier。
- 记录探索路线图和转向原因。
- 输出 FactorCandidateFinding。

### 9.3 Experiment Graph

每个研究对象进入图谱:

```
Hypothesis
  -> CandidateExpression
  -> FactorRun
  -> ValidationResult
  -> BacktestResult
  -> Finding
  -> Approval
  -> FactorArtifact
```

图谱必须支持:

- lineage 查询
- 重跑
- 对比
- 继承关系
- 失败原因聚合
- artifact 下载

### 9.4 过拟合防护

后端必须提供:

- 样本内 / 样本外切分
- walk-forward
- regime split
- 多 universe 验证
- 多时间段稳定性
- 相关性去重
- turnover/cost 惩罚
- p-hacking 风险提示
- 过高复杂度惩罚

---

## 10. Strategy Services

### 10.1 StrategySpec DSL

策略必须落为确定性规格:

- universe
- alpha signal
- ranking
- weighting
- rebalance
- risk rules
- execution assumptions
- cost model
- constraints

LLM 可以生成 draft，但必须通过 compiler。

### 10.2 Compiler

职责:

- schema validation
- 引用校验
- 因子存在性校验
- A 股规则校验
- 风控规则完整性
- cost model 校验
- 生成可回测配置

### 10.3 Strategy Builder Agent

流程:

1. 解析用户目标。
2. 生成 StrategySpec draft。
3. 编译校验。
4. 回测。
5. 风险检查。
6. 生成候选策略。
7. 请求审批或返回修改建议。

### 10.4 Strategy Maintenance

能力:

- 实际表现 vs 预期表现
- 因子贡献漂移
- 回撤异常
- regime fit
- 成本漂移
- 交易频率异常
- 优化提案
- 模拟回测
- 版本化采纳

---

## 11. Backtest / Simulation

### 11.1 回测能力

- 日频/分钟频，按阶段扩展。
- A 股 T+1、涨跌停、停牌、交易日历。
- 手续费、印花税、滑点。
- 成交量和容量约束。
- 调仓规则。
- 行业和风格暴露。
- benchmark 对比。
- 分期表现。
- 交易明细。
- 风险指标。

### 11.2 Walk-forward

必须支持:

- rolling train/test
- expanding window
- regime-aware split
- 参数稳定性分析
- 多窗口结果聚合

### 11.3 Simulation for Approval

采纳前模拟用于:

- OptimizationProposalFinding
- StrategyProposalFinding
- Signal AI Review
- 风控规则变更

模拟结果必须生成 artifact，并绑定审批。

---

## 12. Trading / Risk

### 12.1 Signal AI Review

能力:

- 解释信号来源。
- 汇总策略、因子、行情和持仓背景。
- 检查冲突证据。
- 调用 Risk Officer。
- 生成 SignalInterpretation artifact。

### 12.2 Risk Officer

检查:

- 单票集中度
- 行业暴露
- 风格暴露
- 流动性
- VaR
- 回撤风险
- 相关性上升
- T+1 约束
- 涨跌停 / 停牌
- 数据过期
- 账户连接状态

输出:

- PASS
- WARN
- BLOCK

BLOCK 必须阻止交易动作。

### 12.3 Execution Boundary

后端可以生成:

- signal draft
- order draft
- dry-run result
- risk checked order proposal

后端不能在无审批情况下:

- 提交真实订单
- 修改生产策略
- 调整账户配置
- 删除审计记录

---

## 13. Scheduler / Automation

### 13.1 调度类型

| 类型 | 示例 |
|------|------|
| fixed time | 每日 06:00 数据健康 |
| market time | 开盘前、午间、收盘后 |
| event driven | regime 变化、因子退化、财报披露 |
| manual | 用户从 Agent Console 启动 |
| dependency | 数据同步完成后触发 |

### 13.2 每日流程

| 时间 | 任务 | 输出 |
|------|------|------|
| 06:00 | 数据健康巡检 | DataQualityFinding |
| 07:00 | 因子健康巡检 | RiskAlertFinding |
| 08:00 | 持仓分析 | TextFinding / RiskAlertFinding |
| 12:00 | 午间回顾 | ReportArtifact |
| 15:00 | 收盘总结 | ReportArtifact |
| 20:00 | 策略自优化 | OptimizationProposalFinding |
| 22:00 | Alpha 深度挖掘 | FactorCandidateFinding |

### 13.3 调度可靠性

- 去重
- 锁
- 超时
- retry
- dead letter
- 补跑
- 幂等 run key
- 失败通知

---

## 14. Artifact / Trace / Evidence

### 14.1 Trace

Trace 覆盖:

- Agent run
- LLM call
- tool call
- handoff
- guardrail
- approval
- artifact creation
- error

### 14.2 Artifact Store

存储:

- JSON structured artifact
- report markdown/html
- chart data
- dataset snapshot
- backtest result
- strategy spec
- factor expression

必须有:

- content hash
- schema version
- created by
- source run
- source tool
- retention policy

### 14.3 Evidence Builder

每个 Finding 的 evidence chain 必须自动生成:

- 关键数据引用
- 工具调用引用
- 指标引用
- 样本区间
- 数据源版本
- artifact 链接

---

## 15. Copilot Service

### 15.1 会话

能力:

- 创建会话。
- 接收页面上下文。
- 检索相关对象。
- 调用只读工具。
- 返回流式文本和结构化输出。
- 保存 note。
- 生成 workspace action draft。

### 15.2 Context Builder

上下文来源:

- 当前页面对象
- selected row / selected run / selected strategy
- 用户权限
- 数据时间戳
- 最近 artifacts
- 相关 findings
- 用户笔记

### 15.3 Structured Output

输出类型:

- FactorHypothesis
- FactorCandidateDraft
- StrategySpecDraft
- BacktestDiagnosis
- SignalInterpretation
- ResearchNote
- WorkspaceActionDraft

所有结构化输出必须 schema validate。

---

## 16. Evaluation Service

### 16.1 Eval Task Set

任务类型:

- 因子衰减诊断
- 数据异常定位
- 策略优化建议
- 信号解释
- 风控阻断判断
- backtest 结果诊断
- hallucination trap
- tool permission trap

### 16.2 Score

评分维度:

- correctness
- evidence coverage
- executable output
- risk awareness
- overfit awareness
- schema validity
- cost
- latency
- human approval acceptance rate

### 16.3 Regression

必须支持:

- agent profile 对比
- prompt 版本对比
- model 版本对比
- tool set 对比
- 历史趋势
- 失败案例库

---

## 17. Governance / Security

### 17.1 Auth / RBAC

权限粒度:

- 页面读取
- 数据源读取
- tool read
- tool write
- strategy write
- signal approve
- order submit
- policy edit
- audit read

### 17.2 Guardrails

类型:

- input guardrail
- output guardrail
- tool guardrail
- trading guardrail
- data leakage guardrail
- prompt injection guardrail
- budget guardrail

工具级 guardrail 必须覆盖每次 tool call，不能只在最终输出检查。

### 17.3 Secrets

要求:

- LLM provider key 不进入 trace 明文。
- 券商凭证不进入 prompt。
- 敏感账户字段默认脱敏。
- 本地工具和外部 MCP 工具分离权限。

### 17.4 Audit

所有高风险动作记录:

- who
- when
- what
- before/after
- approval id
- trace id
- source artifact
- risk result

---

## 18. Observability

### 18.1 Metrics

- run count
- success rate
- failure rate
- average latency
- token usage
- tool call count
- tool failure rate
- approval acceptance rate
- finding rejection rate
- backtest queue time
- data health score

### 18.2 Logs

结构化日志字段:

- trace_id
- run_id
- user_id
- plan_id
- tool_name
- status
- error_code
- duration_ms

### 18.3 Alerts

触发:

- data source down
- MiniQMT disconnected
- tool error spike
- guardrail block spike
- budget overrun
- eval score regression
- high severity risk finding
- scheduler missed run

---

## 19. API 契约

### 19.1 Agent

| API | 说明 |
|-----|------|
| `GET /api/ai/agents/plans` | Plan 列表 |
| `POST /api/ai/agents/plans` | 创建 Plan |
| `GET /api/ai/agents/plans/:id` | Plan 详情 |
| `GET /api/ai/agents/runs` | Run 列表 |
| `POST /api/ai/agents/runs` | 手动启动 Run |
| `GET /api/ai/agents/runs/:id` | Run 详情 |
| `POST /api/ai/agents/runs/:id/cancel` | 取消 Run |
| `POST /api/ai/agents/runs/:id/rerun` | 重跑 Run |
| `GET /api/ai/agents/runs/:id/events` | SSE 事件流 |

### 19.2 Finding / Approval

| API | 说明 |
|-----|------|
| `GET /api/ai/agents/findings` | Finding 列表 |
| `GET /api/ai/agents/findings/:id` | Finding 详情 |
| `GET /api/ai/agents/findings/:id/trace` | Trace |
| `POST /api/ai/agents/findings/:id/approve` | 审批 |
| `POST /api/ai/agents/findings/:id/reject` | 拒绝 |
| `POST /api/ai/approvals/:id/comment` | 审批评论 |

### 19.3 Artifact

| API | 说明 |
|-----|------|
| `GET /api/ai/artifacts` | Artifact 列表 |
| `GET /api/ai/artifacts/:id` | Artifact 详情 |
| `GET /api/ai/artifacts/:id/download` | 下载 |
| `GET /api/ai/artifacts/:id/lineage` | lineage |

### 19.4 Copilot

| API | 说明 |
|-----|------|
| `GET /api/ai/copilot/sessions` | 会话列表 |
| `POST /api/ai/copilot/sessions` | 创建会话 |
| `POST /api/ai/copilot/sessions/:id/messages` | 发送消息 |
| `GET /api/ai/copilot/sessions/:id/events` | 流式响应 |
| `POST /api/ai/copilot/workspace-actions` | 创建工作区动作草案 |

### 19.5 Quant Research

| API | 说明 |
|-----|------|
| `POST /api/ai/alpha/runs` | 启动 Alpha 探索 |
| `GET /api/ai/alpha/runs/:id` | Alpha Run |
| `GET /api/ai/alpha/runs/:id/events` | Alpha SSE |
| `POST /api/ai/factors/:id/adopt` | 采纳候选因子 |
| `GET /api/ai/experiments/:id/graph` | Experiment Graph |

### 19.6 Strategy / Backtest

| API | 说明 |
|-----|------|
| `POST /api/ai/strategy/build-runs` | 启动策略构建 |
| `GET /api/ai/strategy/build-runs/:id/events` | 策略构建 SSE |
| `POST /api/ai/strategy/specs/validate` | 校验 StrategySpec |
| `POST /api/ai/backtests/simulate` | 模拟回测 |
| `POST /api/ai/strategy/optimizations/:id/approve` | 采纳优化 |

### 19.7 Evaluation / Policy

| API | 说明 |
|-----|------|
| `GET /api/ai/evals/task-sets` | 任务集 |
| `POST /api/ai/evals/runs` | 启动评测 |
| `GET /api/ai/evals/runs/:id` | 评测详情 |
| `GET /api/ai/evals/runs/:id/events` | 评测 SSE |
| `GET /api/ai/policies` | 策略配置 |
| `PUT /api/ai/policies/:id` | 更新策略 |

---

## 20. SSE 事件

```typescript
type AgentStreamEvent =
  | RunStartedEvent
  | RunProgressEvent
  | AgentHandoffEvent
  | ToolStartedEvent
  | ToolCompletedEvent
  | ArtifactCreatedEvent
  | FindingCreatedEvent
  | ApprovalRequestedEvent
  | GuardrailBlockedEvent
  | BudgetUpdatedEvent
  | RunFailedEvent
  | RunCompletedEvent;
```

事件要求:

- 每个 event 有 `id`、`type`、`run_id`、`trace_id`、`created_at`。
- 支持 Last-Event-ID 断线续连。
- 不在 event 中塞完整大对象，大对象通过 artifact API 获取。
- event payload 必须有 schema version。

---

## 21. 存储建议

| 存储 | 用途 |
|------|------|
| Postgres | Plan、Run、Finding、Approval、Policy、metadata |
| Object Storage | Artifact、报告、数据集快照、大型图表数据 |
| Time-series / Parquet | 行情、因子矩阵、回测序列 |
| Vector Index | 文档、笔记、报告、工具说明检索 |
| Event Log | run events、tool calls、audit |
| Cache | 行情快照、会话上下文、常用计算结果 |

---

## 22. 实施阶段

### B0: Contract Foundation

- 定义 OpenAPI / schema。
- 定义 SSE event schema。
- 定义 AgentRun / Finding / Artifact / Approval 表。
- 建立 trace id、event id、schema version 规范。

### B1: Runtime MVP

- AgentPlan / AgentRun CRUD。
- Run state machine。
- Event publisher。
- Tool Registry MVP。
- 只读数据工具 3 个。
- TextFinding + ToolTrace。

### B2: Governance MVP

- Approval service。
- Tool permission。
- Budget manager。
- Guardrail engine。
- Audit log。

### B3: Quant Research MVP

- Factor Engine。
- Alpha discovery run。
- IC / ICIR / turnover / correlation。
- FactorCandidateFinding。
- Experiment Graph MVP。

### B4: Strategy / Backtest

- StrategySpec DSL。
- Compiler。
- Backtest service。
- StrategyProposalFinding。
- OptimizationProposalFinding。

### B5: Trading / Risk

- Signal AI Review。
- Risk Officer。
- Dry-run order。
- Approval-gated order proposal。

### B6: Evaluation / Automation

- Scheduler。
- Daily Brief。
- Agent Evaluation。
- Regression dashboard data。
- Failure gallery。

---

## 23. 验收标准

| 类别 | 标准 |
|------|------|
| Runtime | Run 可启动、暂停、取消、重跑、失败恢复 |
| Stream | 前端能收到阶段、工具、artifact、finding、approval 事件 |
| Trace | 任意 Finding 能追到 tool call、data snapshot、artifact |
| Approval | 高风险动作无审批不能执行 |
| Quant | 因子候选有 IC、ICIR、换手、相关性、样本外 |
| Backtest | 策略提案必须有可复现回测 artifact |
| Risk | Signal / Order proposal 必须经过 Risk Officer |
| Security | 工具权限、预算、prompt injection、敏感字段脱敏生效 |
| Eval | Agent 配置可在固定任务集上跑分 |
| Observability | 有 metrics、structured logs、alerts |

---

## 24. 参考资料

- OpenAI Agents SDK: https://platform.openai.com/docs/guides/agents-sdk/
- OpenAI Agents SDK Guardrails: https://openai.github.io/openai-agents-python/guardrails/
- Model Context Protocol Security Best Practices: https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices
- Google A2A Specification: https://google-a2a.github.io/A2A/specification/
- Google A2A Announcement: https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/
- Microsoft R&D-Agent-Quant: https://www.microsoft.com/en-us/research/articles/rd-agent-quant/
- TradingAgents: https://tauricresearch.github.io/TradingAgents-AI.github.io/
- QuantConnect MCP Server: https://www.quantconnect.com/docs/v2/ai-assistance/mcp-server

---

## 25. Changelog

### 2026-05-02 — v1

- 新增后端服务完整能力规划。
- 与前端 `2026-05-02-ai-feature-page-design.md` 分离。
- 覆盖 Agent Runtime、Tool Platform、Data、Quant Research、Strategy、Backtest、Trading/Risk、Scheduler、Trace、Copilot、Evaluation、Governance、API/SSE、Storage 和实施阶段。
