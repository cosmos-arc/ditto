# R5 治理型量化研究 Agent 设计

> **日期**：2026-08-12
> **状态**：Accepted，R5 设计事实源
> **适用范围**：本机、内部、单操作者的 A 股日频研究与决策辅助
> **取代**：[2026-08-04 AI/Agent 能力平面设计](archive/2026-08-04-ai-agent-capability-plane-design.md) 与 [2026-08-04 Phase A Copilot 计划](archive/2026-08-04-agent-capability-plane-phase-a-copilot.md)
> **实施计划**：[2026-08-12 R5 详细实施计划](2026-08-12-r5-governed-quant-research-agent-implementation-plan.md)
> **上游事实**：[架构快速参考](../architecture/agent-context-pack.md)、[边界与抽象标准](../architecture/boundaries-and-abstraction-standards.md)、[PIT 合同](../../.agents/skills/ditto-pit-safety/references/pit-contract.md)、[R4/G3 执行计划](2026-08-10-r4-portfolio-risk-g3-execution-plan.md)

## 1. 决策摘要

Ditto R5 建设的是**治理型量化研究与决策 Agent**，不是自动交易聊天机器人，也不是让多个 LLM 角色自由辩论后直接给出交易指令。

R5 的生产架构采用：

1. 一个 `ditto_agent` 能力包、一个主 Agent、一个确定性状态机。
2. 模型只负责意图理解、假设提出、受控代码生成、证据归纳与解释。
3. 数据可见性、回测、组合、风险、成本、显著性和执行资格由 Ditto 确定性宿主计算。
4. 读操作自动执行；草案和受控研究写入按权限执行；任何具有外部影响或正式发布含义的写操作由 HITL 审批。
5. R5.3 允许经一次人工审批后运行有预算、有边界、可恢复的自主研究 Campaign；该授权不能扩大到策略发布、实盘路径或券商操作。
6. 多 Agent 只作为离线对照实验。没有量化增益证据前，不进入生产运行时。

当前仓库已经具备 R5 的可靠宿主：R3 experiment/holdout/trial ledger/replay、R4 portfolio/risk/Daily Decision V3，以及 apps composition root。R5 的重点不是再造量化引擎，而是建立受治理的模型运行时、证据协议、研究授权、沙箱和评测体系。

## 2. 当前事实与设计前提

- 当前代码是 12 包 Python 模块化单体；R5 实施后增加第 13 个包 `ditto_agent`。
- R4 与 G3 已由提交 `9ee6c48c`（PR #72）完成；`DailyDecisionV3QueryFacade`、风险投影和持久化 reader 已存在。
- `ditto_analysis.experiments` 已拥有 experiment identity、fold、attempt、holdout、trial ledger、持久化合同和独立研究 SQLite。
- `ditto_application.processes.experiments` 已拥有计划、调度、lease、恢复、walk-forward、holdout 和 evidence 编排。
- `ditto_apps.registry` 是唯一 composition root；普通 API/CLI/Job 不得直接装配能力包实现。
- 当前无 `openai-agents`、Langfuse 或 Agent 业务包生产依赖；OTel 基础已经存在。
- R5 首发仍是本机、内部、单操作者；auth/RBAC、多租户和外部 Beta 属于 G4。

## 3. 业界调研与方向校验

### 3.1 调研方法

调研优先使用项目仓库、官方文档、论文和监管机构原文。项目星数、宣传收益和 demo 结果不作为架构正确性的证据；重点比较运行时结构、研究闭环、数据时间语义、回测权威、沙箱、记忆、审批和发布边界。

以下链接于 **2026-08-12** 复核。

### 3.2 项目证据矩阵

| 项目 | 可验证能力 | 值得采用 | Ditto 不照搬的部分 |
|---|---|---|---|
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | LangGraph 多角色分析、checkpoint resume、结构化输出和决策记忆 | 状态可恢复、角色职责显式、运行记录 | 自由辩论不是收益或安全证据；生产默认不采用多 Agent 投票 |
| [RD-Agent](https://github.com/microsoft/RD-Agent) | 假设提出、代码实现、实验反馈、自演化式数据/模型研发 | 假设→实现→评价→反馈的受控循环 | 不在一次 Campaign 同时优化 factor 与 model；不接受模型自行声明改进 |
| [Qlib](https://github.com/microsoft/qlib) / [PIT 文档](https://qlib.readthedocs.io/en/stable/advanced/PIT.html) | 研究工作流、模型、策略、组合、回测、实验记录和 PIT 数据 | 研究工件化、可复现实验、PIT 数据层 | 不引入第二套量化平台；Ditto 继续由自身数据、回测和风险语义裁决 |
| [QuantaAlpha](https://github.com/QuantaAlpha/QuantaAlpha) | LLM 与演化策略结合的因子挖掘和验证轨迹 | 候选 lineage、演化预算、自动验证 | 不把搜索次数藏在分支中，不让 holdout 形成反馈梯度 |
| [FinMem](https://github.com/pipiku915/FinMem-LLM-StockTrading) | 分层记忆、反馈和交易 Agent 状态 | 结构化、带时间的研究记忆 | 不把模型输出或收益结果自动提升为长期知识；记忆必须有 `known_at` |
| [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | 金融报告、估值、风险分析和多源工具 | 金融任务工具化、报告工件化 | 不让通用数据源和 Agent action 绕过 Ditto 数据许可、PIT 与 application facade |
| [Freqtrade](https://github.com/freqtrade/freqtrade) | backtest、dry-run、lookahead-analysis、recursive-analysis | 先 dry-run、显式检测前视和递归偏差 | R5 不连接交易所或券商，不把 Agent 研究结果直接提升到交易策略 |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | 确定性事件驱动时间、研究—实盘语义一致、适配器隔离 | 确定性时钟、同一宿主语义、清晰 adapter 边界 | 不因 Agent 引入另一套时间或执行模型 |
| [LEAN](https://github.com/QuantConnect/Lean) | 模块化事件驱动研究、回测、优化和实盘 | 策略与宿主职责分离、可插拔执行模型 | R5 生成代码只产出研究分数，不能获得订单和券商能力 |
| [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 多角色股票分析的教育性实现 | 可作为自然语言任务集和 adversarial case 来源 | README 明确非真实交易系统；不作为生产架构或收益证据 |
| [AlphaQuanter](https://aclanthology.org/2026.findings-acl.456/) | 单 Agent、tool-augmented workflow 与强化学习策略研究 | 单 Agent 基线、透明工具轨迹和端到端评测 | 不把交易 RL 或论文收益直接移入产品；必须在 Ditto 自有数据、PIT 和成本约束下重新评估 |

### 3.3 Agent 平台与模型风险证据

- [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents) 支持 code-first Agent、function tools、运行状态、guardrails、审批和自定义存储；官方也明确服务端仍拥有部署、工具实现、状态存储和审批决策。
- [Guardrails 与人工审批](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals) 支持中断并恢复同一运行；tool guardrail 必须放在产生副作用的工具边界，不能只依赖 Agent 首尾 guardrail。
- [Agent evals](https://developers.openai.com/api/docs/guides/agent-evals) 建议先用 trace 定位工作流问题，再以 dataset/eval run 做可重复回归。Ditto 在此基础上增加 PIT、安全和财务结果的确定性 grader。
- [OpenAI 数据控制](https://developers.openai.com/api/docs/guides/your-data) 说明默认 abuse monitoring 和部分 endpoint application state 的保留行为；MAM/ZDR 需要资格与项目配置，`store=false` 也不能替代 endpoint 级核验。
- [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) 与 [NIST Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) 强调持续治理、测量、验证、记录和上下文内解释。
- [Federal Reserve SR 26-2](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm) 强调按模型用途和暴露度实施开发、验证、监控、治理与第三方模型管理。该指引不直接覆盖生成式/agentic AI，但其风险分级、独立验证和 outcome analysis 原则仍适合作为 Ditto 内部控制参考。
- [FINRA Regulatory Notice 24-09](https://www.finra.org/rules-guidance/notices/24-09) 强调使用 GenAI 不免除既有监督、记录、隐私、可靠性和准确性义务。
- [证监会《证券市场程序化交易管理规定（试行）》](https://www.csrc.gov.cn/csrc/c100028/c7480577/content.shtml) 与 [上交所实施细则](https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/c_20250612_10781696.shtml) 强调报告、全程管理、权限/阈值/异常监测、人工干预、测试和记录。R5 不属于获准自动下单系统；该边界必须在产品和代码中同时成立。

### 3.4 调研裁决

**采用：**

- 单 Agent + 确定性工作流作为生产默认。
- function tools 访问受控内部事实，模型不直接访问存储或券商。
- 结构化假设、候选、评价、记忆、Episode 和审计工件。
- 可恢复运行、预算和停止条件。
- 生成代码在无网 OCI 沙箱运行，宿主计算所有财务结果。
- 离线 eval、PIT sentinel、安全攻击和 shadow outcome analysis。

**不采用：**

- 以多 Agent 角色数量代表前沿程度。
- LLM 直接计算收益、风险、权重或订单。
- 首发开放 Web、RAG、MCP、Hosted Code Interpreter 或任意插件市场。
- Agent 自主发布策略、修改生产配置或连接真实券商。
- 把对话文本无条件转为长期记忆或训练反馈。
- 用回测 holdout 的反复查看指导搜索。

最终方向是当前金融 AI 工程的前沿实践：**模型负责不确定的语义与搜索，确定性金融宿主负责事实、时间、计算、权限和审计。**

## 4. 产品边界

### 4.1 用户与自治等级

- 首发用户：内部、本机、单操作者。
- 通用自治：governed advisory。Agent 可读、起草、校验和提出动作；正式写动作等待审批。
- 研究自治：用户审批一个不可变 `CampaignAuthorization` 后，Agent 可在授权预算和单一搜索轴内自动生成、执行和评价多个研究候选。
- 任何授权都不能隐式扩展到策略 publish、DailyDecision 修改、订单生成、真实数据写入或券商调用。

### 4.2 R5.0—R5.5

| 阶段 | 交付 | 生产权限 |
|---|---|---|
| R5.0 | 合同、状态机、模型 port、审计、Episode/replay、eval 基线 | Fake provider 为主，无业务写入 |
| R5.1 | Evidence Copilot：研究、回测、组合、风险、DailyDecision V3 解读 | 只读 |
| R5.2 | Author Copilot：StrategySpec/DSL/配置草案、校验和差异预览 | 草案；正式写入逐动作 HITL |
| R5.3 | Autonomous Research Campaign：假设、候选代码、实验、反馈和研究记忆 | 一次审批后的受控研究写入 |
| R5.4 | Decision Briefing：DailyDecision V3 之后生成 `DecisionOpinion` | Shadow-only，不影响决策或交易 |
| R5.5 | 安全、评测、SLO、retention、降级和发布证据 | feature flags 默认关闭 |

### 4.3 非目标

- 真实券商连接、自动下单、策略自动发布和生产参数自动修改。
- 公网服务、认证、RBAC、多租户和面向客户的投资建议。
- 开放 Web/RAG/MCP、第三方 tool marketplace、Hosted Code Interpreter。
- 任意宿主挂载、联网安装依赖或通用 Notebook 执行。
- R5 生产多 Agent、强化学习交易、分钟级交易或全球资产扩展。

## 5. 架构与所有权

### 5.1 依赖图

```text
ditto_apps ──> ditto_agent ──> ditto_application ──> capability packages
     └──────────────────────> ditto_application

ditto_platform = 横向技术基础设施
ditto_kernel   = 最小稳定原语
```

`ditto_agent` 不是 application 的 peer，也不是 capability 包的入口替代品。它位于 apps 与 application 之间，消费 application 暴露的用例合同。

### 5.2 四要素边界

| 能力平面/owner | provider/实现 | 直接消费者 | 跨边界合同 |
|---|---|---|---|
| `ditto_agent` 运行时 | 单 Agent 状态机、Agents SDK adapter、Agent SQLite | apps API/CLI、registry | `AgentModelPort`、Agent contracts、Agent store ports |
| `ditto_application.queries` | 既有及新增 evidence facade | `ditto_agent.tools` | 叶级 query/read-model |
| `ditto_application.commands/processes` | 草案命令、Campaign coordinator、可信 evaluator | `ditto_agent.tools` | command/process DTO、`CandidateSandboxPort` |
| `ditto_analysis.experiments` | 研究领域对象与独立 SQLite adapter | application experiment processes | research contracts、reader/writer protocols |
| `ditto_apps.registry.agent` | 配置加载、OpenAI runtime 装配、OCI sandbox adapter | apps API/CLI | consumer-owned ports 的具体实现 |
| `ditto_platform` | SQLite/OTel/clock/serialization 技术原语 | agent/analysis/application/apps | 业务无关的既有技术合同 |

### 5.3 机器边界

实施时将 `ditto_agent` 加入 `.importlinter` root packages，并至少建立：

1. `agent-capability-isolation`：禁止 `ditto_agent` 导入 data/features/strategy/portfolio/risk/execution/backtest/analysis。
2. `application-no-agent`：禁止 `ditto_application` 反向导入 `ditto_agent`。
3. `capabilities-no-agent`：所有业务能力包禁止导入 `ditto_agent`。
4. `platform-no-agent`：platform 禁止依赖 Agent 业务概念。
5. `agent-no-apps`：`ditto_agent` 禁止依赖 apps。
6. apps 非 registry 路径不得直接导入 Agent 的物理 storage/provider/sandbox adapter。

消费者从定义符号的叶模块导入，不通过跨包 re-export、`TYPE_CHECKING`、延迟导入或 service locator 掩盖方向。

### 5.4 模型与基础设施放置

- `AgentModelPort` 及 OpenAI Agents SDK adapter 位于 `ditto_agent.models`，因为它们服务于 Agent runtime，不是通用平台能力。
- Fake model 与 deterministic scripted model 同样实现该 port，测试默认不调用云端。
- Agent 业务 SQLite schema、reader、writer 和 audit chain 位于 `ditto_agent.storage.sqlite`。
- 环境变量、OpenAI project、模型 profile、OTel exporter 和 sandbox runtime 配置只在 `ditto_apps.registry` 读取并注入。
- 不新增 `ditto_platform.services.llm` 一类通用 LLM Gateway。

## 6. 公共领域合同

### 6.1 Agent-owned 类型

| 类型 | 必需语义 |
|---|---|
| `AgentManifest` | agent/prompt/tool schema/model profile 的版本和摘要 |
| `AgentSession` | 本地会话身份、创建时间、retention class；不充当长期研究事实 |
| `AgentRun` | 状态、目标、authority、预算、model profile、manifest hash、开始/结束时间 |
| `AgentEvent` | 单调 `event_id`、run_id、event type、payload hash、发生时间、prev hash |
| `TemporalToolContext` | 由服务端注入的完整可见性、授权和数据外发上下文 |
| `EvidenceEnvelope` | tool 结果、artifact refs、snapshot、时间边界、lineage、完整性 hash |
| `GroundedAnswer` | 结论、逐结论 evidence refs、不确定性、缺失证据、拒答原因 |
| `ApprovalRequest` | action kind、规范化参数、action hash、过期时间、所需权限 |
| `CampaignAuthorization` | immutable campaign hash、预算、搜索轴、工具白名单和有效期 |
| `AgentEpisodeManifest` | 输入、模型/prompt/tool 版本、事件、调用、结果和 replay identity |
| `DecisionOpinion` | DailyDecision V3 的只读解释、异议、证据和 shadow outcome identity |

### 6.2 Analysis-owned 类型

| 类型 | 必需语义 |
|---|---|
| `ResearchCampaignManifest` | 预注册目标、搜索空间、validation protocol、预算和 lineage root |
| `SearchLedger` | operational attempts、statistical trials、fork/retry lineage |
| `HypothesisSpec` | 可证伪假设、机制、目标 universe、预期信号和失败条件 |
| `CandidateSpec` | 单一 search axis、父候选、代码/参数 hash、数据需求 |
| `ExperimentPlan` | folds、purge/embargo、成本、seed、snapshot、评价目标 |
| `EvaluationResult` | 宿主计算指标、约束、显著性、失败分类和证据引用 |
| `ResearchFeedback` | 可供下一代使用的结构化、非 holdout 反馈 |
| `KnowledgeItem` | scope、claim、evidence refs、`outcome_known_at`、状态和 promotion |
| `ResearchCodeArtifact` | 代码、AST hash、依赖清单、image digest、输入/输出 schema |
| `SandboxExecutionManifest` | runtime digest、资源限制、输入输出 hash、退出状态和 attestation |

这些对象必须可在没有 Agent runtime 的情况下被研究域读取和验证；analysis 不负责调度。

### 6.3 `TemporalToolContext`

所有 PIT-sensitive tool 必须接收服务端生成且模型不可覆盖的：

```text
decision_time             offset-aware，规范化为 UTC
knowledge_cutoff          系统在决策时可知的最晚时间
publication_cutoff        允许使用的最晚发布时间
source_snapshot_id        不可为空的修订宇宙身份
execution_eligible_at     信号最早可执行时间；纯研究读取也需显式为 not_applicable
allowed_universe          允许证券集合或其不可变摘要
license_class             数据使用权等级
egress_class              cloud_allowed / local_only / prohibited
campaign_authorization_id 可空；研究自治时必需
campaign_authority_hash   可空；研究自治时必需
```

缺少 cutoff、snapshot、version metadata 或授权时 fail closed，禁止回退到 latest 或 wall-clock `now`。

## 7. PIT、回测与研究真实性

### 7.1 四个时间维度

- observation/effective time：事实描述市场的时间。
- publication/knowledge time：系统能够知道事实的时间。
- source snapshot：可见修订版本宇宙。
- execution time：信号可以成为订单或成交的最早时间。

所有 request、cache key、artifact、Episode、Campaign、candidate 和 replay identity 都包含相关时间与 snapshot。

### 7.2 计算规则

- 版本有效性使用半开区间：`effective_from <= as_of < effective_to`。
- as-of join 只能按 knowledge time 做 backward join，并按完整实体键分区、显式排序。
- T 行只有在决策时已知才可参与计算；否则时间 rolling 左闭，点数 rolling 先 `shift(1)`。
- 使用 T 日收盘信息的信号不能在同一收盘价成交，除非数据与执行合同显式证明可行。
- 所有 R5.3 测试加入 cutoff 外极值 sentinel 与 cutoff 内相邻可用记录。

### 7.3 权威计算边界

LLM 或生成代码不得输出可被采信的收益、回撤、IC、风险、权重、订单或显著性。可信宿主负责：

- fold/purge/embargo 和一次性 holdout；
- 数据读取、PIT 过滤和 snapshot 传播；
- backtest、交易成本、组合构建、风控和执行模拟；
- 评价指标、多重检验、PBO/DSR 等既有统计控制；
- evidence、artifact、lineage 和 replay。

## 8. Agent 运行时与授权

### 8.1 单 Agent 状态机

Agent Run 状态：

```text
QUEUED -> RUNNING -> COMPLETED
                   -> WAITING_APPROVAL -> RUNNING
                   -> PAUSED -> RUNNING
                   -> FAILED
                   -> CANCELLED
```

状态转换由确定性 host 决定，模型只返回结构化 intent。非法转换、过期 lease、重复终态写入和 action hash 不一致全部 fail closed。

### 8.2 工具权限

| 工具类别 | 示例 | 默认权限 | 审批 |
|---|---|---|---|
| Evidence read | experiment、factor、portfolio、risk、DailyDecision V3 | 自动 | 无 |
| Draft/validate | StrategySpec/DSL 草案、compile、diff、preview | 自动 | 不写正式状态 |
| Formal author write | 保存草案、提交 review 等 application command | 禁止 | 每个 action hash 审批 |
| Campaign internal | 创建候选、排队 fold、记录 feedback/memory | 禁止 | 一次 Campaign hash 审批后在预算内允许 |
| Holdout | 一次性聚合评价 | 禁止 | 独立人工审批，不被 Campaign 授权覆盖 |
| Publish/trading | publish、权重、订单、券商 | 不注册 | R5 永不允许 |

审批 hash 至少覆盖 `action_kind`、tool、规范化参数、temporal context、snapshot、subject identity、预算、权限和 expiry。任一字段改变都创建新审批，不能重用旧决定。

### 8.3 故障与恢复

- 创建操作使用 `Idempotency-Key`，服务端保存 key、request hash 和 result identity。
- 运行和 Campaign 使用 lease；lease 到期只能由持有恢复权限的协调器接管。
- 模型超时、限流或不可用时停止新增动作，保留已完成证据并进入 `PAUSED` 或结构化 `FAILED`。
- approval 状态序列化到 Ditto 本地 store；恢复时仍验证 action hash、authority 和过期时间。

## 9. Autonomous Research Campaign

### 9.1 不可变授权

`ResearchCampaignManifest` 在审批前 canonicalize 并生成 SHA-256。审批后的 `CampaignAuthorization` 固定：

- 目标和主评价指标；
- 数据 snapshot、universe、PIT protocol；
- 单一 `search_axis`；
- 候选/fold/时间/存储/并发/模型费用预算；
- 可调用工具和禁止动作；
- stopping rule、有效期和授权人。

改变任一字段会生成新 Campaign，不允许在运行中扩大权限。

### 9.2 默认预算

| 维度 | 默认上限 |
|---|---:|
| generations | 6 |
| unique evaluated candidates | 128 |
| fold runs | 384 |
| concurrent sandboxes | 2 |
| wall time | 4 小时 |
| temporary storage | 20 GiB |
| LLM spend | 8 美元 |
| per sandbox CPU | 2 vCPU |
| per sandbox memory | 4 GiB |

连续两代 validation 主指标没有改善时停止。预算耗尽进入 `PAUSED_BUDGET`，不能自动加额。

### 9.3 单一搜索轴

`search_axis` 只能是：

- `factor_code`（默认）；
- `model_code`；
- `parameters`。

一个 R5 Campaign 不做 factor-model co-optimization。需要切换轴时结束当前 Campaign，并以已批准的正式工件作为新 Campaign 基线。

### 9.4 SearchLedger

- operational attempt：执行同一 immutable trial 的重试、恢复或基础设施尝试。
- statistical trial：唯一 `candidate_hash × validation_protocol_hash`，无论重试几次只计一次。
- fork/retry 保留同一 lineage root 和 family counter，不能通过分叉重置 multiple-testing。
- 候选去重同时使用 canonical AST hash、输出相关性和 lineage。

### 9.5 Holdout

- holdout 数据、日期、逐期结果和中间特征不进入 Agent context、tool 输出或研究 memory。
- 一个预选 candidate 只有一次人工批准的 holdout claim。
- 只返回签名的 aggregate pass/fail、预注册门槛结果和 evidence hash。
- holdout 结果不能成为下一代搜索、prompt 或 `KnowledgeItem` 的输入。

### 9.6 研究记忆

scope 为 `campaign-local`、`strategy-family`、`global`；默认 local。每条 `KnowledgeItem` 必须有来源、claim、适用范围、`outcome_known_at`、snapshot 和状态。

- 读取条件：`outcome_known_at <= TemporalToolContext.knowledge_cutoff`。
- local 提升到 family/global 需要人工审批和独立证据。
- 失效、矛盾和撤销为 append-only 状态，不覆盖历史。
- 模型自评、未验证解释和 holdout 结果不得成为长期记忆。

## 10. 生成代码与沙箱

### 10.1 代码合同

```python
fit(training_stream) -> ModelStateArtifact
score(visible_window, immutable_model_state) -> CandidateScoreFrame
```

- `training_stream` 和 `visible_window` 只包含当前 fold、当前 cutoff、当前 snapshot 可见的数据。
- `ModelStateArtifact` 必须不可变、内容寻址且使用批准的 JSON/Arrow/NumPy 格式。
- `CandidateScoreFrame` 只包含 identity、time 和 score/prediction；不含收益、权重、订单和评价指标。
- `score` 不得写外部状态；同一输入、状态、image digest 和 seed 得到相同输出。

### 10.2 OCI 安全基线

- macOS 开发机：Docker Desktop VM 内运行；Linux：rootless OCI，优先以 gVisor 等额外隔离 runtime 验证。
- 无网络、无 socket、无 Docker socket、无 repo/host mounts、无 secret/env 凭证。
- non-root、read-only rootfs、tmpfs scratch、cap-drop ALL、no-new-privileges、seccomp。
- 固定 image digest、SBOM 和依赖集合；禁止 `pip install` 或动态下载。
- CPU、memory、PID、disk、wall time、stdout/stderr、输入输出大小均有限额。
- 禁止 pickle；NumPy 强制 `allow_pickle=False`；Arrow/JSON 解码做 schema 与大小校验。
- 每个 candidate/fold 新建沙箱；同一 fold 内允许宿主按因果顺序多次调用 `score`，模型状态不可被就地修改。

必须测试：fresh/reused runner、不同 candidate 顺序、fold 顺序和并发度下输出一致；网络、文件、进程、资源炸弹、恶意序列化和输出协议攻击全部失败。

### 10.3 晋级边界

生成代码永久首先是 `ResearchCodeArtifact`。进入正式 Ditto strategy/features 代码只能由人审查后创建独立 PR，重新经过 TDD、PIT、architecture、CI 和策略治理。R5 runtime 不动态加载研究代码到 EOD 或交易进程。

## 11. API、SSE 与 CLI

### 11.1 API

```text
POST /api/v1/agent/sessions
POST /api/v1/agent/runs
GET  /api/v1/agent/runs/{run_id}
GET  /api/v1/agent/runs/{run_id}/events
POST /api/v1/agent/approvals/{approval_id}/decision

POST /api/v1/agent/campaigns
POST /api/v1/agent/campaigns/{campaign_id}/approve
GET  /api/v1/agent/campaigns/{campaign_id}
POST /api/v1/agent/campaigns/{campaign_id}/cancel
```

- `POST` 创建操作要求 `Idempotency-Key`；相同 key 不同 body 返回 conflict。
- request/response DTO 只在 apps；业务 contracts 从 owner 叶模块导入。
- API 不接收模型提供的 `TemporalToolContext`，而是从服务端查询参数、配置和 authority 构造。
- approval decision 只允许 `approve`/`reject`，记录 operator、理由、时间和目标 action hash。

### 11.2 SSE

- `GET .../events` 返回 `text/event-stream`。
- 每个 run/campaign 的 `event_id` 单调递增且持久化。
- 客户端可用 `Last-Event-ID` 继续；服务端重放缺失事件而不是重新运行工具。
- heartbeat 不写业务事件；业务 event 包含 schema version 和 payload hash。

### 11.3 CLI

首批命令固定为：

```text
ditto agent run
ditto agent show RUN_ID
ditto agent events RUN_ID --follow
ditto agent approve APPROVAL_ID
ditto agent reject APPROVAL_ID
ditto agent campaign create MANIFEST
ditto agent campaign approve CAMPAIGN_ID
ditto agent campaign show CAMPAIGN_ID
ditto agent campaign cancel CAMPAIGN_ID
```

CLI 只调用同一 application/agent runtime，不另建同步执行旁路。

## 12. 模型、数据外发与可观测性

### 12.1 模型 profile

| profile | 模型 | reasoning | 用途 |
|---|---|---|---|
| balanced | `gpt-5.6-terra` | medium | 默认解释、工具选择、普通草案 |
| quality | `gpt-5.6-sol` | high | 高难度研究假设、代码生成、独立复核 |

profile 映射、模型 snapshot、prompt 和 tool schema 必须版本化；变更后完整重跑相关 eval。实际可用模型和成本在实施审批时再次按 [OpenAI 官方模型目录](https://developers.openai.com/api/docs/models) 核验。

### 12.2 OpenAI 数据边界

- 使用专用 OpenAI project，不使用 default project。
- 上线真实模型前必须确认该 project 已获 MAM 或 ZDR；所有 Responses 请求显式 `store=false`。
- 只允许 `egress_class=cloud_allowed` 且 license 允许的 evidence 进入模型。
- 首发禁用 Conversations、Files、Vector Stores、Background mode、Hosted Code Interpreter/Shell、Web Search、MCP 和远程 connectors。
- 不依赖 OpenAI 托管状态恢复；Ditto 本地 store 保存必要的脱敏状态和 encrypted reasoning continuation item（如 SDK/API 要求）。
- OpenAI `/v1/evals` 不是 R5 发布证据的唯一存储；ZDR 项目下正式 eval 以 Ditto 本地 dataset、Episode 和 grader 为事实源。

### 12.3 OTel 与审计

OTel 是主协议，Langfuse 只可作为可选 exporter，不能成为 Agent 运行依赖。每个 run 记录：

- trace/run/session/campaign identity；
- model/profile/prompt/tool schema/image digest；
- tool name、规范化参数 hash、authority、temporal context、结果 hash；
- guardrail、approval、budget、retry、latency、token 和 cost；
- artifact/evidence refs、最终状态和人工反馈。

审计事件使用本地 tamper-evident hash chain；不得把 secret、API key、完整持仓敏感内容或禁止外发的原始数据写入 trace。

### 12.4 留存

- 默认不保存完整敏感 prompt/response；先脱敏并保存结构化摘要、hash 和 evidence refs。
- 经配置允许保存的原始运行内容保留 30 天，由本地 cleanup job 删除。
- 正式研究工件、审批、Episode manifest、审计摘要和 hash chain 长期保存。
- 如未来需要保存完整原文，先完成静态加密、密钥管理、恢复和删除验证；该能力不在 R5 默认实现中。

## 13. 评测、SLO 与发布门

### 13.1 120 条正式用例

| 类别 | 数量 | 重点 |
|---|---:|---|
| grounded evidence | 30 | 工具选择、证据覆盖、引用、拒答 |
| author | 20 | StrategySpec/DSL 草案、compile、validate、diff |
| campaign/PIT/holdout | 30 | snapshot、sentinel、trial ledger、holdout 隔离 |
| permission/approval | 20 | 越权、hash 篡改、过期、恢复、幂等 |
| sandbox attacks | 10 | 网络、挂载、资源、序列化、逃逸 |
| shadow decision | 10 | V3 grounding、只读、不影响下游 |

### 13.2 硬门

- 禁止动作、PIT future sentinel、审批绕过、holdout 泄漏、sandbox escape：100%。
- tool choice、evidence coverage：至少 95%。
- factual correctness：至少 90%。
- 必须拒答场景：100%。
- Author compile/validate：至少 90%。
- 相同 Episode 的 tool/event replay：100% 确定。
- 任何模型、prompt、tool schema、routing 或 guardrail 变更都重跑受影响数据集；安全/PIT 指标零回退。

### 13.3 交互预算

- 普通 read：P95 ≤ 30 秒，单次模型成本 ≤ 0.25 美元。
- 复杂任务：P95 ≤ 60 秒，单次模型成本 ≤ 0.75 美元。
- Campaign 使用自身总预算，不以交互任务预算替代。

### 13.4 多 Agent ADR 触发条件

只有在同一 Episode 集上相对单 Agent：

- task success 提高至少 5 个百分点，或 candidate acceptance 提高至少 10%；
- safety、PIT、approval 指标无回退；
- cost 和 latency 均不超过 2 倍；

才允许提出生产多 Agent ADR。达到门槛不等于自动采用，仍需架构与运营审批。

## 14. 监管与控制映射

| 控制目标 | R5 设计 |
|---|---|
| 治理和责任 | owner 明确、feature flag、审批、release evidence、变更 eval |
| 模型验证 | 固定 dataset、独立确定性 grader、shadow outcome analysis |
| 第三方模型风险 | 专用 project、版本记录、MAM/ZDR、egress policy、provider 可替换 port |
| 记录和可追溯 | Episode、OTel、artifact refs、hash-chain audit、retention |
| 权限和人工干预 | tool allowlist、action hash、HITL、cancel/pause、fail closed |
| 程序化交易隔离 | 不注册 publish/order/broker tools；DecisionOpinion shadow-only |
| 系统安全 | OCI 隔离、资源限额、无网无挂载、攻击测试、runbook |
| 数据许可与隐私 | license/egress class、脱敏、最小外发、禁用托管状态能力 |

该映射用于内部工程治理，不构成法律意见或对外合规声明。进入 G4/G5 前必须由适格法律与合规人员复核具体使用方式。

## 15. 降级、开关与完成定义

所有 R5 feature flags 默认 `false`。Agent provider、OTel exporter、Agent SQLite 或 sandbox 不可用时：

- Ditto 核心 data/research/backtest/portfolio/risk/execution 和 DailyDecision 继续运行。
- Agent API 返回结构化 unavailable/paused，不回退为无证据回答。
- 已经持久化的审批、Campaign 和事件保持可恢复，不自动重放副作用。

R5 完成要求：

1. R5.0—R5.5 各波次 exit gate 全部通过。
2. 120 条正式 eval 达到硬门且留有可重放 evidence。
3. PIT、holdout、sandbox、approval 和禁止交易路径均有 adversarial 证据。
4. 交互 SLO、成本、retention、备份恢复、降级和 runbook 验收通过。
5. 设计、源码、OpenAPI、CLI、`.importlinter` 和 release evidence 一致。
6. 未满足 G4 时仍维持本机、内部、单操作者和非自动交易边界。
