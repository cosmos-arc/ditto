# Ditto 个人量化投研与 Paper 工作站系统设计

> 版本：1.0
> 日期：2026-08-31
> 状态：READY FOR ARCHITECTURE REVIEW
> 适用范围：Ditto monorepo 的后端与 `apps/web` 前端
> 前置基线：[系统产品定位与 App 蓝图基线](../reviews/2026-08-30-system-product-positioning-and-app-blueprint-baseline.md)
> 本文性质：目标系统设计，不代表所述能力已经交付

## 0. 执行摘要

Ditto 的目标不再是“A 股 ETF 自动交易平台”，而是：

> 面向单一投资者的 A 股个股与 ETF 个人量化投研、选股、组合决策、Paper Trading、手工实际账户记录和复盘工作站。系统以宏观与全球市场作为 A 股环境解释层，以行业轮动和个股选择为核心发现流程，以 Model、Paper、Manual 三类组合事实形成决策闭环，并由受治理 Agent 提供投研、选股、技术分析、仓位诊断和策略编写辅助。

本设计作出五项关键调整：

1. 不连接 A 股券商，不创建、修改或撤销真实订单；实时数据只读。
2. 个股和 ETF 同为核心可决策资产，选股与行业轮动是一等产品能力。
3. Paper 是系统自动运行的正式模拟账户；Manual 是用户可录入、更正并重建的实际账户事实账本。
4. 宏观、全球核心指数和 A 股核心指数必须进入 Regime、行业、选股、仓位与风险解释链，不能只是展示型行情卡片。
5. Agent 是一等产品能力，但不是自动交易员。它可以读取证据、计算预演、解释、生成草案和在逐动作审批后保存策略草案；它不能篡改金融计算、账本事实、策略发布状态或触发真实交易。

项目尚未上线，因此采用一次性绿地重建：

- 不设计历史数据库迁移、双读、兼容 API、旧路由保留期或弃用窗口。
- 已有运行时数据库、缓存、物化数据、测试研究历史、Agent 历史、Paper/Manual 测试账本可在实施阶段按精确路径清空。
- 原始市场、指数和宏观数据重新摄取，派生数据重新计算。
- 策略定义、因子定义、配置与测试种子以版本库中的声明式源文件重新初始化。
- 本文不执行任何数据删除；真正删除前仍需列出精确目标并进行只读核对。

当前系统并非“什么都没有”。它已经拥有较强的模块化架构、PIT 约束、研究与回测骨架、Agent 治理运行时、前后端 API 和设计系统。问题是能力分布失衡：治理与框架成熟度明显高于真实数据、核心用户流程和持续运行证明。后续建设应从“增加页面和抽象”转向“按真实用户旅程贯通数据、计算、账户、Agent 和 UI”。

## 1. 设计范围与事实依据

### 1.1 本文解决的问题

本文完整定义：

- 产品边界、用户目标和非目标；
- 当前系统能力、已验证证据和未验证风险；
- 目标逻辑架构与依赖方向；
- 宏观、指数、行业、选股、技术分析、研究、策略、组合、Paper、Manual 和 Agent 的领域设计；
- 前后端读模型、命令、API 和关键数据流；
- `apps/web` 五域信息架构与主要工作台；
- Agent 的权限、工具、审计、评测和人机审批边界；
- 绿地初始化、真实验证矩阵、非功能目标和完成标准；
- 需要保留的业界最佳实践与应拒绝的过度设计。

本文不执行：

- 数据删除、数据库初始化或重新摄取；
- 生产代码改造；
- 前端视觉实现；
- 真实数据供应商采购；
- 券商、MiniQMT、QMT、FIX 或其他真实交易网关接入。

### 1.2 事实优先级

当前行为按以下顺序判定：

1. [.importlinter](../../.importlinter)、Pixi、Pyproject、CI 等机器约束；
2. 源码、类型和测试；
3. [架构快速参考](../architecture/agent-context-pack.md)；
4. [边界与抽象标准](../architecture/boundaries-and-abstraction-standards.md)；
5. 产品基线、路线图和历史设计。

历史文档与源码冲突时，以源码和测试为准。本文提出的是目标态，未完成部分必须继续标记为目标，不得写成现状。

### 1.3 成熟度和验证口径

| 等级 | 定义 | 可宣称内容 |
|---|---|---|
| L0 | 概念 | 只有文档、原型或接口设想 |
| L1 | 骨架 | 存在类型、路由、适配器或局部实现 |
| L2 | 集成 | 跨层调用和自动化测试成立 |
| L3 | 真实验证 | 使用真实供应商数据完成可重复端到端流程 |
| L4 | 运行证明 | 连续运行、恢复、对账、审计和用户闭环达标 |

验证证据必须区分：

- CODE：源码存在；
- TEST：自动化测试通过；
- CONTRACT：OpenAPI、schema 或边界检查通过；
- LIVE：真实数据供应商或真实模型运行通过；
- DOGFOOD：用户按真实工作流连续使用通过。

只有 LIVE 和 DOGFOOD 才能支撑“产品可用”判断。路由数、页面数、Mock、截图和测试替身不能替代真实验证。

## 2. 已关闭的产品与架构决策

### 2.1 D1—D10 延续决策

| ID | 决策 | 结论 |
|---|---|---|
| D1 | 核心可决策资产 | A 股个股与 A 股 ETF |
| D2 | 全球范围 | 核心指数、利率、汇率、商品只作为环境参照，不进入全球交易 |
| D3 | 宏观角色 | 必须进入 Regime、行业、选股和风险解释 |
| D4 | 选股地位 | 与行业轮动共同构成一级核心流程 |
| D5 | 执行边界 | 无 A 股券商连接、无真实订单；实时数据只读 |
| D6 | 组合事实 | Model、Paper、Manual 三类事实；Paper 与 Manual 为独立账本 |
| D7 | Manual 账户 | 可记录任意外部实际成交和现金事件，不要求 Ditto Signal |
| D8 | 产品域 | Today、Markets、Research、Portfolio、System |
| D9 | 视觉基线 | Graphite Studio 与“市场到组合证据链” |
| D10 | 完成口径 | 真实数据与完整用户闭环，不按 route、contract 或 overlay 数量验收 |

### 2.2 本轮新增并关闭的决策

| ID | 决策 | 正式结论 |
|---|---|---|
| D11 | 上线前数据与兼容 | 采用绿地重建；不做历史迁移、兼容 API、双读或旧路由保留 |
| D12 | Agent 产品地位 | Agent 是跨五域的一等投研与决策副驾驶，不后置到核心流程完成之后 |
| D13 | Agent 能力范围 | 覆盖投研、选股、行业轮动、技术分析、仓位诊断、策略编写和复盘 |
| D14 | Agent 计算边界 | 金融数值和模式识别由确定性领域能力计算，模型只组织、解释和提出受约束草案 |
| D15 | Agent 权限边界 | 默认只读与预演；仅策略草案保存和提交评审允许逐动作审批写入；禁止策略发布、账本写入、Paper 启动和真实交易 |
| D16 | 前端兼容 | `apps/web` 可直接重构信息架构、路由和读模型，不保留旧产品心智或技术兼容层 |

### 2.3 对旧基线的明确覆盖

本文覆盖产品基线中以下旧表述：

- 旧 /trading 与 /platform 路由不再需要迁移期兼容，可直接按五域重新设计。
- Agent 不再等到所有核心工作流达到 L4 后才扩展；Agent 与每条核心垂直链同步交付。
- “不优先扩建 Agent 角色体系”继续有效，含义是保持单一治理型 Agent，不是削弱 Agent 的业务能力。

## 3. 产品目标、用户和非目标

### 3.1 北极星用户任务

每个交易日，用户应能在一个系统中完成：

    市场与宏观状态
        → 行业强弱和轮动
        → 个股/ETF 候选与排除理由
        → 标的研究与技术确认
        → 策略/信号和目标组合
        → 风险与仓位预演
        → Paper 模拟运行
        → Manual 实际账户记录
        → Model/Paper/Manual 偏差和事后复盘

Agent 在每一步读取相同证据链，帮助用户减少查找、拼接和解释成本，但不替代领域计算或用户最终决策。

### 3.2 主要用户角色

这是个人工作站，不需要企业级组织模型。保留三种逻辑角色即可：

| 角色 | 主要目标 | 权限 |
|---|---|---|
| Investor | 看市场、选标的、管理账户、复盘 | 全部用户功能 |
| Researcher | 编写因子/策略、实验和回测 | 研究与草案能力 |
| Operator | 管理数据源、任务、Agent 和审计 | 系统配置与恢复 |

同一个用户可同时拥有三种角色。无需多租户、复杂 RBAC 或审批组织树。

### 3.3 明确非目标

- 不连接任何 A 股券商；
- 不执行或路由真实订单；
- 不自动导入券商账户；
- 不交易全球股票、期货、期权、外汇或加密资产；
- 不做社交交易、策略市场、跟单或多人协作平台；
- 不以 LLM 生成的未经验证文本作为行情、指标、仓位或收益事实；
- 不做多 Agent 投委会；
- 不建设 Kubernetes、Kafka、服务网格或微服务体系；
- 不以向量数据库替代结构化市场、研究和账本查询；
- 不提供无限制联网和执行代码的通用 Agent。

## 4. 当前系统事实与成熟度判断

### 4.1 已有架构资产

后端为 13 包模块化单体：

    apps
      ↓
    agent → application
                ↓
    data / features / strategy / portfolio / risk / execution
                ↓
              kernel

analysis 是独立研究存储与控制平面；platform 仅承载横切技术能力。Agent 只消费 application，apps 是唯一 composition root。这个依赖方向已经由 import-linter 机器约束，目标设计继续保留。

现有可复用资产包括：

- data：数据源、摄取、存储、质量与 PIT 查询；
- features：表达式、因子、物化与评估；
- strategy：策略规格、Alpha pipeline、信号和选择证据；
- portfolio：会计、持仓、现金和调仓；
- risk：约束、暴露和风险决策；
- execution：OMS、成交、审计与 Paper 网关骨架；
- backtest：回放、统计和报告；
- analysis：实验、研究工件和独立研究存储；
- application：CQRS 与跨能力编排；
- agent：运行时、工具、模型端口、审计、审批、Campaign 和 eval；
- apps：API、CLI、Jobs 和装配。

### 4.2 Agent 当前真实状态

Agent 不是纯 Mock：

- [工具注册表](../../packages/agent/src/ditto_agent/tools/registry.py) 已允许实验、因子、策略、回测、组合、风险和 Daily Decision V3 证据读取；
- [研究证据工具](../../packages/agent/src/ditto_agent/tools/research.py) 要求精确版本、dataset、universe 和 host 注入的 source snapshot；
- [Author 写工具](../../packages/agent/src/ditto_agent/tools/author_write.py) 仅允许保存策略草案和提交评审，并要求逐动作审批；
- [DecisionOpinion](../../packages/agent/src/ditto_agent/decision_opinion.py) 是绑定 V3 证据的 shadow-only 意见，明确禁止权重、风险状态、动作、订单和发布；
- [Agent API](../../apps/backend/src/ditto_apps/api/routes/agent_routes.py) 已有 capability、session、run、event stream、approval 和 campaign 端点；
- Web 的 [Agent API client](../../apps/web/src/features/agent/api/agent-api.ts) 已调用 /v1/agent 真实接口，并通过 [恢复型事件流](../../apps/web/src/features/agent/api/agent-event-stream.ts)、[Agent Console](../../apps/web/src/features/agent/components/agent-console-page.tsx) 和 [上下文入口](../../apps/web/src/features/agent/components/agent-context-actions.tsx) 承接 Run、Campaign 与 Approval。

因此当前 Agent 治理底座可评为 L2，部分内部合同接近 L3；但投研产品工作流仍只有 L1—L2。已有工具主要围绕研究证据和运行治理，缺少宏观环境、行业/选股、技术快照、三组合对比和仓位情景预演。

### 4.3 能力成熟度矩阵

| 能力 | 当前证据 | 当前成熟度 | 主要差距 |
|---|---|---:|---|
| 包边界与 composition root | import-linter、架构文档、测试 | L2 | 目标新增合同仍需 arch-check |
| A 股基础数据 | adapter、dataset/snapshot、部分 API | L1—L2 | 真实覆盖、新鲜度、复权和停复牌验证不足 |
| 宏观数据 | FRED/Tushare adapter、knowledge date 基础 | L1—L2 | 中国指标真实发布时间、修订和产品消费链未验证 |
| 全球/A 股指数 | 部分数据与原型 | L1 | 统一注册表、交易日、币种和实时新鲜度未闭环 |
| 行业强弱与轮动 | 研究/特征基础、UI 设想 | L1 | 无正式 IndustryRotationSnapshot 与真实工作台 |
| 个股/ETF 选取 | SelectionEvidence 等后端基础 | L1—L2 | 前端筛选仍偏标的目录；无可保存 SelectionRun |
| 技术分析 | 表达式/因子/图表基础 | L1 | 无版本化多周期 TechnicalAnalysisSnapshot |
| 研究与回测 | 实验、因子、回测、工件和测试 | L2 | 真实 PIT、成本模型、walk-forward 与重放证明需统一 |
| 策略生命周期 | StrategySpec、Author preview/write 基础 | L2 | 从自然语言到草案、验证、测试、回测计划和评审尚未贯通 |
| Model Portfolio | Daily Decision V3/组合投影 | L2 | 与 Selection、Risk、Paper、Manual 对比读模型不足 |
| Paper | gateway/runtime 单元测试基础 | L1—L2 | 持续运行、成交假设、恢复、对账和 UI 闭环未证明 |
| Manual | AccountView 等可复用基础 | L0—L1 | 无独立外部成交/现金事件/更正的完整合同 |
| Agent 治理 | authority、PIT、budget、audit、HITL、SSE | L2 | 真实模型、故障恢复和业务 eval 尚需证明 |
| Agent 业务工具 | 研究证据、V3、Author | L1—L2 | 缺市场、选股、技术、三组合和仓位预演 |
| `apps/web` 视觉与页面 | Graphite Studio、页面合同、大量组件 | L2 | UI 丰富但真实读模型、业务动作和闭环不均衡 |

### 4.4 结论：为什么完善多个版本仍“不理想”

根因不是页面数量不足，而是建设顺序倒置：

1. 治理、抽象、页面合同和视觉骨架比真实数据与核心旅程成熟；
2. 多数页面以“有什么数据”组织，而不是以“用户下一步决策”组织；
3. Markets、Research、Trading、Platform 的旧分类强化了系统模块心智，没有形成从市场到组合的证据链；
4. 个股筛选缺少可保存、可比较、可解释、可流转的 SelectionRun；
5. Paper 和 Manual 没有成为用户每天使用的两条独立账本；
6. Agent Console 更像运行控制台，缺少嵌入市场、选股、标的、策略和仓位页面的业务输出；
7. 自动化测试证明了合同存在，但没有证明真实数据、真实模型和连续使用成立。

## 5. 目标架构原则

### 5.1 原则

1. 事实、计算、解释分离：data 提供事实，领域包提供确定性计算，Agent 提供有证据的解释和草案。
2. 选择、信号、组合、风险、执行分离：不能用一个综合分数直接跳过组合和风险。
3. 所有历史研究 PIT fail closed：缺 knowledge cutoff、publication cutoff 或 source snapshot 时不返回 latest。
4. 账本事件不可被派生视图替代：持仓和收益必须可从事件重建。
5. 每个产品页面都有明确决策问题、证据、动作和下游去向。
6. Agent 不拥有金融真相：它不能自行计算未注册指标、修改仓位事实或发布策略。
7. 先完成单用户闭环，再考虑组织级扩展。
8. 模块化单体优先，新增概念先进入现有 owner 包。

### 5.2 目标组件图

    apps/web
      ├─ Today / Markets / Research / Portfolio / System
      ├─ Contextual Agent Sidecar
      └─ Agent Lab / Approval Inbox / Agent Ops
                     │ HTTPS + SSE
                     ▼
    apps API / Jobs / CLI / Registry
      ├─ User workflow endpoints
      ├─ Agent run/campaign/approval endpoints
      └─ Composition root
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
    application              agent
      ├─ queries               ├─ deterministic host
      ├─ commands              ├─ evidence tools
      ├─ processes             ├─ author tools
      └─ read models           ├─ audit / replay / eval
          ▲                    └─ model provider port
          │                            │
          └──────── Agent tools ───────┘
          │
    data / features / strategy / portfolio / risk / execution / backtest / analysis
          │
        kernel + platform

### 5.3 包所有权、Provider 与 Consumer

| 能力 | Owner | Provider | Consumer | 目标合同 |
|---|---|---|---|---|
| 市场与宏观事实 | data | datasource adapters、PIT store | features、application | DatasetSnapshot、MacroObservation、MarketBar |
| Regime 与市场特征 | features | materializer/evaluator | strategy、application | MarketRegimeFeatureSet |
| 行业轮动 | strategy | selection/rotation service | application、backtest | IndustryRotationSnapshot |
| 个股/ETF 选取 | strategy | universe/selection pipeline | application、backtest | SelectionRun、SelectionCandidate |
| 技术分析 | features | versioned indicator/pattern service | strategy、application | TechnicalAnalysisSnapshot |
| 策略定义与信号 | strategy | compiler/validator/signal service | application、backtest | StrategySpec、SignalIntent |
| 组合会计 | portfolio | ledger/projector/optimizer | risk、application | AccountLedger、PortfolioSnapshot、TargetPortfolio |
| 风险与情景 | risk | constraint/scenario service | application、backtest | RiskSnapshot、ScenarioPreview |
| Paper 订单与成交 | execution | Paper gateway/fill model | application | PaperOrder、PaperFill、FillAssumption |
| 研究与回测 | analysis/backtest | experiment and replay runtime | application | ExperimentRun、BacktestArtifact |
| 跨域工作流 | application | queries/commands/processes | apps、agent | Workspace read models、receipts |
| Agent 编排 | agent | host/tools/provider/eval | apps | AgentRun、EvidenceEnvelope、Approval |
| UI/API 装配 | `apps/backend` | API/jobs/registry | `apps/web` | OpenAPI、SSE events |

新增能力不需要新增顶层 Python 包。TechnicalAnalysisSnapshot 属于 features，SelectionRun 属于 strategy，账户账本属于 portfolio，Paper 成交属于 execution，跨域视图属于 application，Agent 只适配 application 合同。

表中的 Consumer 表示业务消费关系，不等于允许 Python 直接 import。涉及 peer capability 的数据传递继续使用现有 ports、application 注入和 apps composition root，具体依赖必须满足 .importlinter。

### 5.4 机器边界

- agent 只能依赖 application 和获准的 platform 技术合同；
- apps 是唯一装配点；
- application 不反向依赖 agent；
- capability 包之间保持现有 import-linter 约束；
- 所有新增跨包公共合同从定义它的源包或 application 叶模块直接导入；
- 不使用跨包 re-export、TYPE_CHECKING 或延迟导入掩盖循环依赖；
- 每次跨包改造必须运行 arch-check。

## 6. 数据与时间语义设计

### 6.1 数据范围

| 数据域 | 最低范围 | 用途 |
|---|---|---|
| A 股证券主数据 | 个股、ETF、上市状态、行业、板块、交易日、公司行动 | Universe、复权、行业和标的身份 |
| A 股行情 | 日线为研究底座；可用时接入只读实时/分钟数据 | 技术分析、信号、Paper |
| A 股核心指数 | 上证、深证、创业板、科创、沪深300、中证500/1000 等 | 市场宽度、风格和基准 |
| 行业指数 | 申万一级为首批，必要时扩展二级 | 行业强弱和轮动 |
| 全球核心指数 | 美股、欧洲、亚太主要指数 | 隔夜风险与跨市场环境 |
| 利率与汇率 | 中国与美国核心利率、人民币汇率、美元指数 | 流动性、估值和风险解释 |
| 商品与波动 | 原油、黄金、铜、VIX 等核心参照 | 周期、通胀和风险偏好 |
| 宏观 | 增长、通胀、信用、货币、地产、就业、景气 | Regime、行业和风险 |
| 公司基本面 | 可获得的财务、估值、质量、成长数据 | 个股选择和解释 |

### 6.2 统一时间合同

每条可用于决策或回测的数据必须有：

| 字段 | 含义 |
|---|---|
| event_time | 经济事件或市场观测实际发生时间 |
| effective_period | 指标归属期间，例如 2026-07 |
| published_at | 来源首次公开时间 |
| ingested_at | Ditto 摄取时间 |
| available_at | 经过许可、清洗和交易日规则后可被系统使用的时间 |
| revised_at | 修订版本公开时间，可为空 |
| source_snapshot_id | 本次查询绑定的来源快照 |
| dataset_version | schema、清洗和供应商版本 |
| knowledge_cutoff | 运行时允许看见的信息边界 |
| publication_cutoff | 运行时允许看见的发布版本边界 |

宏观和基本面历史查询必须按当时可见版本返回；未知发布时间不得用估算值静默替代。确需使用估算 lag 时，记录 estimate_method、confidence 和 provider evidence，并禁止进入正式 PIT 认证集。

### 6.3 实时数据边界

- 实时/准实时适配器只能实现 MarketDataProvider，不实现 BrokerGateway；
- apps registry 不装配任何真实券商 provider；
- 实时数据不可绕过 dataset/snapshot 身份直接进入 Agent；
- Paper 使用的每个 bar/tick 都要保留 source snapshot、received_at 和迟到/缺失状态；
- 实时中断时 Paper fail paused，不用未来数据补成交；
- 浏览器不持有供应商密钥。

### 6.4 数据质量与可用性

每个 Data Product 显示：

- 覆盖范围、最后成功时间和预期频率；
- 延迟、缺口、重复、异常值和公司行动状态；
- 数据许可类别与是否允许发送给云模型；
- PIT 认证状态；
- 下游依赖和最近一次物化版本；
- 当前是否可用于 Research、Selection、Paper 和 Agent。

### 6.5 绿地重建数据分类

| 类别 | 上线前处理 | 重新生成方式 |
|---|---|---|
| 原始市场/宏观数据 | 删除 | 从认证 provider 重新摄取 |
| 清洗表、快照、特征、索引 | 删除 | 从原始数据重建 |
| 回测和实验历史 | 删除 | 重新运行受治理实验 |
| Agent session/run/approval/campaign | 删除 | 新 schema 初始化 |
| Paper/Manual 测试账本 | 删除 | 以正式期初余额和事件重新建立 |
| 策略/因子定义 | 不从旧数据库迁移 | 从版本库 seed 或用户确认的导出文件初始化 |
| 系统配置 | 不兼容迁移 | 使用新配置 schema 和安全密钥重新配置 |

绿地重建只适用于首次上线前。上线后，Paper/Manual 账本、策略版本、研究审计和 Agent 审计必须采用不可变历史、备份和正式 schema 演进。

## 7. 市场环境与宏观产品设计

### 7.1 MarketContextSnapshot

MarketContextSnapshot 是 Markets、Today、Selection、Portfolio 和 Agent 共用的 application 读模型：

- as_of、knowledge_cutoff、publication_cutoff、source_snapshot_ids；
- A 股核心指数表现、宽度、成交、波动和风格；
- 全球核心指数隔夜/当日状态；
- 利率、汇率、商品和波动率状态；
- 宏观指标最新可见值、趋势、surprise、revision 和 freshness；
- Regime 标签、概率或得分、变化驱动和历史相似期；
- 行业受益/受压映射；
- 对 Selection 因子、Portfolio 暴露和 Risk 的解释；
- 数据缺口、冲突和不确定性。

### 7.2 产品要求

Markets 首屏回答四个问题：

1. 当前是什么市场环境？
2. 与上一交易日/周相比发生了什么变化？
3. 哪些行业、风格和风险因子受到影响？
4. 这些变化会怎样影响当前候选和持仓？

宏观指标不直接给“买入某股票”的结论。它先进入 Regime 和行业/风险映射，再由 Selection 和 Portfolio 组合使用。

### 7.3 真实验证

- 对每个中国宏观指标人工核对至少三个历史发布时间和修订事件；
- 用 future sentinel 证明回到历史时点看不到未来修订；
- 验证全球指数时区、节假日、币种和前收盘定义；
- 验证 A 股指数、行业指数和证券的交易日对齐；
- 验证一个宏观变化能沿 lineage 到达 Regime、行业、Selection、Portfolio 和 Agent 输出。

## 8. 行业轮动与个股/ETF 选取

### 8.1 SelectionRun 是核心产品对象

筛选条件不是最终产品。每次选股必须保存为不可变 SelectionRun：

- run_id、as_of、universe_id/version/hash；
- source snapshots、feature versions、strategy/selection spec version；
- 宏观与 Regime context identity；
- 行业排名和行业配额；
- 过滤规则、硬排除、排序因子和权重；
- 候选列表、分数、分位数、排名变化；
- 入选理由、排除理由、缺失数据和风险标记；
- 与上一次 run 的新增、移除和跃迁；
- 下游 Research case、Watchlist、Model proposal 和 Paper intent 引用；
- replay identity 和 artifact refs。

### 8.2 选取流程

    可交易 Universe
      → 数据完整性与流动性硬过滤
      → 宏观/Regime 约束
      → 行业强弱与轮动排序
      → 行业内个股/ETF 因子排名
      → 风险、停牌、涨跌停、ST、上市天数等排除
      → 候选比较
      → 研究/目标组合/Paper 去向

股票和 ETF 可以使用不同 selection spec，但必须进入统一 SelectionRun 合同，UI 可共同比较资产类型、行业、因子贡献和风险。

### 8.3 IndustryRotationSnapshot

- 行业层级、分类版本和成分股 snapshot；
- 多周期相对强弱、趋势、宽度、成交和资金代理指标；
- 估值、盈利预期或基本面变化；
- 宏观敏感度与 Regime 适配；
- 当前排名、变化、持续性和拥挤风险；
- 行业内候选覆盖与权重上限；
- 算法版本、参数和解释证据。

### 8.4 Agent 选股辅助

Agent 可以：

- 解释候选为何入选、为何被排除；
- 比较两个或多个候选的因子、行业、技术和风险差异；
- 说明排名变化来自数据变化还是模型变化；
- 建议需要补充的研究问题；
- 生成 SelectionMemo，引用 SelectionRun 和证据。

Agent 不能：

- 自己发明选股分数；
- 在没有 SelectionRun 的情况下给出确定性榜单；
- 绕过硬排除和 Universe；
- 直接把候选写入 Model、Paper 或 Manual。

## 9. 技术分析设计

### 9.1 定位

技术分析是 Selection、Research 和 Portfolio 的辅助证据，不是独立交易权威，也不是让 LLM“看图猜形态”。

### 9.2 TechnicalAnalysisSnapshot

由 features 拥有并确定性计算：

- instrument_id、asset_type、as_of；
- 价格调整策略、bar frequency、交易日历和 source snapshot；
- 日/周及配置的更短周期；
- 趋势：收益、均线、斜率、突破和趋势状态；
- 动量：RSI、MACD、ROC 等已注册指标；
- 波动：ATR、历史波动、波动分位数；
- 成交：量价、相对成交量、换手；
- 市场结构：版本化算法计算的支撑、阻力、缺口和形态；
- 相对强弱：相对基准、行业和同类候选；
- 多周期一致与冲突；
- 每个指标的算法、版本、参数、输入窗口和 freshness；
- 缺失数据、warm-up 不足和不可计算原因。

第一版只纳入能写出公式、测试和稳定解释的指标。形态识别必须由确定性算法产生，不把视觉模型输出当事实。

### 9.3 Agent 技术分析辅助

Agent 读取 TechnicalAnalysisSnapshot 后生成 TechnicalAnalysisBrief：

- 当前趋势、动量、波动和量价状态；
- 多周期确认与冲突；
- 与行业/基准相对强弱；
- 关键条件与失效条件；
- 对 Selection、Model 和现有持仓的含义；
- 明确区分事实、领域规则、Agent 解释和不确定性。

### 9.4 验证

- 指标与独立参考实现做 golden test；
- 复权、停牌、除权除息和不完整窗口有边界测试；
- 所有 rolling 窗口保持 PIT 左闭语义；
- 历史重放结果由 snapshot 身份可重复；
- Agent 不能引用 snapshot 中不存在的指标或点位。

## 10. 研究、回测与策略编写

### 10.1 研究流程

采用 hypothesis-first：

1. 声明假设、机制、Universe、预期信号和失败条件；
2. 冻结 dataset、snapshot、feature 和成本模型；
3. 定义 baseline、候选数量、参数预算和统计试验预算；
4. 使用时间有序 walk-forward、purge 和 embargo；
5. 隔离 holdout，不把逐期结果泄露给 Agent；
6. 记录数据、代码、参数、指标、工件和环境 lineage；
7. 生成 Research Review Bundle；
8. 用户决定拒绝、继续、保存策略草案或进入 Paper。

### 10.2 防过拟合合同

- 每个研究 Campaign 有 candidate_limit、generation_limit、fold_run_limit 和 wall-time；
- 统计试验次数与运行失败重试次数分开计数；
- 参数搜索空间在运行前冻结；
- 主指标和失败条件在运行前冻结；
- 训练、验证和 holdout 身份分离；
- 不允许 Agent 看到 sealed holdout 的逐期数据；
- 只有通过 walk-forward 和成本敏感性才可提交策略评审。

### 10.3 策略 Author 工作流

现有 Author preview 与审批写入基础继续复用，目标流程为：

    用户研究目标
      → Agent 生成 StrategySpec 草案
      → 表达式编译
      → schema/语义/PIT 校验
      → 与基线版本 diff
      → 生成单元测试与研究计划草案
      → 用户检查
      → exact approval 保存不可变 draft
      → 回测/实验
      → Review Bundle
      → exact approval 提交评审
      → 用户在非 Agent 流程中决定发布

Agent 可调用：

- author_draft_strategy；
- author_compile_expression；
- author_validate_strategy；
- author_diff_strategy；
- author_save_strategy_draft，逐动作审批；
- author_submit_strategy_review，逐动作审批。

Agent 永远不能：

- 发布策略；
- 修改已经发布的不可变版本；
- 直接执行任意代码；
- 安装依赖或访问未经授权网络；
- 触发 Paper 或 Manual 账本变更。

对于仓位辅助，Agent 可以整理用户约束并请求 portfolio_scenario_preview。目标权重、调仓差额、暴露和风险变化必须由 portfolio/risk 的确定性服务计算；Agent 只解释方案、比较情景和指出假设，结果始终是未生效的 proposal。

若未来支持生成 Python 扩展，必须在无网络、只读输入、CPU/内存/进程/时限受控的 sandbox 中编译和测试；第一版优先使用现有声明式 StrategySpec 和表达式 DSL。

## 11. Model、Paper 与 Manual 三类组合事实

### 11.1 语义

| 类型 | 是什么 | 事实来源 | 能否修改历史 |
|---|---|---|---|
| Model Portfolio | 策略与组合流程产生的目标权重和调仓意图 | Selection、Strategy、Portfolio、Risk | 新版本替代，旧版本不可变 |
| Paper Account | 系统按模拟订单和成交假设运行的虚拟经济事实 | PaperOrder、PaperFill、CashEvent | 追加事件和冲正 |
| Manual Account | 用户对系统外实际账户的手工事实记录 | ManualTrade、CashEvent、CorporateAction、Correction | 追加更正，不覆盖原事件 |

三个对象不得共享一张含糊的 positions 表作为事实源。统一比较只能由 application 生成 PortfolioComparisonView。

### 11.2 Paper 设计

Paper 是正式运行模式：

    Model rebalance intent
      → Paper pre-trade risk
      → Paper order
      → fill model + market snapshot
      → Paper fill with assumption
      → cash/position ledger
      → valuation/PnL
      → reconciliation and review

每个 Paper Fill 必须记录：

- 触发的 signal/intent/model version；
- 决策时点、最早可执行时点和实际模拟时点；
- 使用的 bar/tick snapshot；
- fill model、滑点、费用、税费和成交量约束版本；
- 未成交、部分成交、涨跌停、停牌和数据中断原因；
- 事件 hash、correlation_id 和 lineage。

Paper 账户必须支持：

- 初始现金和多账户；
- 定时/事件驱动的 session；
- 订单、撤销、拒绝、部分成交和过期；
- T+1、交易日、涨跌停、最小手数、费用和税费；
- 重启恢复、幂等、重复事件防护；
- 日终估值、现金、持仓、收益和风险；
- 与同期回测和 Model 进行差异解释。

### 11.3 Manual 设计

Manual 必须支持无 Signal 的真实事实：

- 买入、卖出；
- 入金、出金；
- 分红、利息、税费、佣金；
- 证券转入、转出；
- 拆分、合并和其他公司行动；
- 期初持仓和期初现金；
- 对错误录入的冲正与更正。

ManualEvent 包含：

- account_id、event_id、event_type；
- instrument_id 或 cash currency；
- trade_date、settlement_date、recorded_at；
- quantity、price、gross_amount、fees、tax、net_cash；
- source 为 manual_entry 或 file_import；
- note、attachment refs、external_reference；
- reverses_event_id 或 corrects_event_id；
- actor、idempotency_key 和 hash。

更正必须追加 correction/reversal，不允许直接覆盖旧事件。用户可编辑草稿，但事件一旦入账就只能冲正。

### 11.4 三组合对比

PortfolioComparisonView 同一 as_of 下返回：

- Model、Paper、Manual 的现金、持仓、权重、成本和 PnL；
- 相对基准、行业、风格和风险暴露；
- Model vs Paper 的未成交、滑点和执行偏差；
- Model vs Manual 的用户选择偏差；
- Paper vs Manual 的账户差异；
- 数据时点、估值价格、FX、snapshot 和 completeness；
- 待处理 Manual 事件、Paper 异常和风险告警。

## 12. Agent 一等产品能力

### 12.1 产品形态

Agent 采用“全局上下文 Sidecar + Research 内 Agent Lab + System 内 Agent Ops”：

- Sidecar：在 Today、Markets、Research、Portfolio 页面读取当前稳定 context identity；
- Agent Lab：查看完整 Run、研究 Campaign、证据、策略草案和比较结果；
- Agent Ops：能力状态、provider、预算、审计、失败、retention 和 Approval Inbox。

不新增第六个顶级产品域，也不把 Agent 限制在 Platform Console。

### 12.2 核心工作流

| 工作流 | 输入 | 确定性工具 | Agent 输出 |
|---|---|---|---|
| 每日市场简报 | MarketContextSnapshot | 市场/宏观/Regime 查询 | EvidenceBrief |
| 行业与选股解释 | SelectionRun、IndustryRotationSnapshot | selection evidence | SelectionMemo |
| 标的技术分析 | TechnicalAnalysisSnapshot | indicator/pattern query | TechnicalAnalysisBrief |
| 投研辅助 | experiment/factor/backtest evidence | 现有研究工具 | ResearchMemo |
| 仓位诊断与调仓预演 | PortfolioComparisonView、RiskSnapshot、用户约束 | comparison/scenario preview | PortfolioDiagnostic |
| 策略编写 | StrategySpec、compiler、validator、diff | 现有 Author 工具 | StrategyDraftProposal |
| 日终复盘 | 当日 evidence spine、Paper/Manual 事件 | decision/outcome query | DecisionReview |

### 12.3 新增 Agent 只读/预演工具

| 工具名 | application 合同 | 目的 | 权限 |
|---|---|---|---|
| market_context_evidence | MarketContextQueryPort | 宏观、全球、A 股和 Regime | 自动只读 |
| industry_rotation_evidence | IndustryRotationQueryPort | 行业强弱与轮动 | 自动只读 |
| selection_run_evidence | SelectionRunQueryPort | 精确选股运行与候选 | 自动只读 |
| instrument_technical_evidence | TechnicalAnalysisQueryPort | 精确标的技术快照 | 自动只读 |
| portfolio_comparison_evidence | PortfolioComparisonQueryPort | Model/Paper/Manual 对比 | 自动只读 |
| portfolio_scenario_preview | PortfolioScenarioPreviewPort | 用户给定约束下的确定性仓位预演 | 自动预演、不写入 |
| account_event_evidence | AccountEventQueryPort | 精确账本事件和 lineage | 自动只读 |

这些工具必须沿用现有 TemporalToolContext、EvidenceEnvelope、authority allowlist、预算和审计机制。模型不能提供 source_snapshot_id，也不能请求 latest。

### 12.4 Agent 输出合同

所有业务输出共享：

- output_kind、schema_version；
- run_id、context_type、context_id；
- as_of、knowledge_cutoff、publication_cutoff；
- evidence_refs、artifact_refs 和 source snapshots；
- facts、interpretations、uncertainties、conflicts；
- recommended_next_steps；
- model、prompt、tool 和 policy versions；
- guardrail status、freshness 和 completeness；
- disclaimer：非真实订单、非账本事实。

不同输出增加专属字段：

| 输出 | 专属内容 |
|---|---|
| EvidenceBrief | market changes、drivers、risks、watch items |
| SelectionMemo | inclusions、exclusions、comparisons、research gaps |
| TechnicalAnalysisBrief | timeframe alignment、levels、conditions、invalidations |
| PortfolioDiagnostic | drift、exposure、PnL attribution、scenario references |
| StrategyDraftProposal | spec diff、validation、tests、open assumptions |
| DecisionReview | expected vs observed、Paper/Manual divergence、lessons |

### 12.5 权限矩阵

| 动作 | Agent 是否可做 | 控制 |
|---|---:|---|
| 读取精确证据 | 是 | host allowlist、PIT、预算 |
| 生成解释和比较 | 是 | 结构化输出、引用校验 |
| 运行确定性情景预演 | 是 | application 计算、无写入 |
| 创建研究 Campaign 草案 | 是 | 用户授权前不运行 |
| 运行已授权 Campaign | 是 | 冻结 manifest 和预算 |
| 保存策略草案 | 是 | exact per-action approval |
| 提交策略评审 | 是 | exact per-action approval |
| 发布策略 | 否 | 不注册工具 |
| 启动或修改 Paper session | 否 | 用户 UI/command 专属 |
| 写入或更正 Manual 账本 | 否 | 用户 UI/command 专属 |
| 修改 Model Portfolio | 否 | 确定性 workflow 专属 |
| 提交真实订单 | 否 | 系统不存在真实网关 |

### 12.6 Agent 安全与可靠性

- 模型只返回结构化 intent；host 决定权限、状态、PIT、预算、审批和副作用；
- provider 调用 store=false；
- prompt 不包含密钥、Manual 备注、敏感附件或超出许可的数据；
- 工具输入、输出和模型输出都做 guardrail；
- malformed arguments、缺失 evidence、版本不匹配、快照不一致一律 fail closed；
- exact approval 绑定 action payload、hash、authority、budget、TTL 和 provider continuation；
- 审计保留模型请求 hash、工具调用、证据、审批、输出和结果，不记录明文 secrets；
- SSE 断开后按 cursor 恢复，不重复执行副作用；
- live provider 不可用时显示 unavailable/degraded，不回退成无证据聊天；
- eval 覆盖证据引用、数值忠实、PIT、工具选择、过度自信、权限越界和拒绝质量。

### 12.7 为什么不做多 Agent

投研、选股、技术、仓位和策略编写是同一个治理型 Agent 的不同 context profile 与工具 allowlist，不是五个自治角色。多 Agent 会增加：

- 权限和证据边界组合；
- 上下文漂移和结论冲突；
- 模型成本和延迟；
- 审计、重放和评测复杂度。

只有单 Agent 在固定 Episode 集上无法达到质量目标，且多 Agent 在质量、成本、延迟和审计上有量化净收益时，才允许单独提出 ADR。

## 13. Application 读模型、命令与 API

### 13.1 目标 application 合同

Queries：

- GetMarketContextQuery；
- GetIndustryRotationQuery；
- GetSelectionRunQuery；
- CompareSelectionRunsQuery；
- GetTechnicalAnalysisSnapshotQuery；
- GetPortfolioComparisonQuery；
- PreviewPortfolioScenarioQuery；
- GetAccountLedgerQuery；
- GetPaperSessionQuery。

Commands：

- CreateSelectionRunCommand；
- CreatePaperAccountCommand；
- StartPaperSessionCommand；
- PausePaperSessionCommand；
- RecordManualEventCommand；
- CorrectManualEventCommand；
- SetAccountOpeningBalanceCommand；
- SaveStrategyDraftCommand；
- SubmitStrategyReviewCommand。

Processes：

- BuildDailyMarketContext；
- RunIndustryAndSecuritySelection；
- BuildModelPortfolio；
- OperatePaperSession；
- ReconcilePaperAccount；
- RebuildManualAccountProjection；
- ProduceDailyDecisionReview。

Agent 不直接调用 capability service 或 storage，只通过这些 application 叶合同。

### 13.2 建议 REST API

| 方法与路径 | 用途 |
|---|---|
| GET /v1/market/context | 当前或历史 PIT 市场环境 |
| GET /v1/markets/industries/rotation | 行业轮动快照 |
| POST /v1/selections | 创建受治理 SelectionRun |
| GET /v1/selections/{run_id} | 获取精确 SelectionRun |
| GET /v1/selections/{run_id}/compare | 与前次/指定运行比较 |
| GET /v1/instruments/{instrument_id}/technical-analysis | 技术分析快照 |
| GET /v1/portfolio/comparison | 三组合对比 |
| POST /v1/portfolio/scenario-previews | 无写入仓位情景 |
| POST /v1/paper/accounts | 创建 Paper 账户 |
| POST /v1/paper/sessions | 创建/启动 Paper session |
| POST /v1/paper/sessions/{id}/pause | 暂停 |
| GET /v1/paper/accounts/{id}/ledger | Paper 账本 |
| POST /v1/manual/accounts | 创建 Manual 账户 |
| POST /v1/manual/accounts/{id}/events | 录入事件 |
| POST /v1/manual/accounts/{id}/corrections | 冲正/更正 |
| GET /v1/manual/accounts/{id}/ledger | Manual 账本 |

现有 /v1/agent/session、run、campaign、approval 和 event stream API 保留其合同语义；前端路由可重构，API 不为旧 UI 设计兼容层。

### 13.3 错误语义

- 400：schema 或业务输入非法；
- 404：精确 identity 不存在；
- 409：revision、idempotency、状态或 snapshot 冲突；
- 422：PIT、数据完整性、Universe 或计算前置条件不满足；
- 424：上游 provider/data product 不可用；
- 429：预算或运行并发限制；
- 503：能力被禁用或运行时降级。

禁止返回空成功来掩盖数据缺失。响应必须携带 reason_code、retryable、missing_dependencies 和 correlation_id。

## 14. `apps/web` 产品蓝图

### 14.1 五域导航

| 顶级域 | 用户问题 | 主要页面 |
|---|---|---|
| Today | 今天最重要的变化、机会、风险和待办是什么 | Daily Brief、Priority Queue、Agent Findings、Data Health |
| Markets | 当前环境如何，机会在哪里 | Macro & Cross-Market、A 股、Industry Rotation、Screener、Watchlist、Instrument Hub、Calendar |
| Research | 这个想法是否有效，策略如何形成 | Universes、Factors、Experiments、Backtests、Strategies、Strategy Studio、Agent Lab、Reviews |
| Portfolio | 模型、Paper 和我的账户发生了什么 | Overview、Model、Paper、我的账户、Transactions、Risk、Attribution、Review |
| System | 数据、自动化和 Agent 是否可靠 | Data Products、Jobs、Provider、Agent Ops、Approval Inbox、Settings、Audit |

不再向用户显示 Trading 作为真实下单域。旧 Orders 页面改为 Paper Orders；实际成交入口改为“记录实际成交”。

### 14.2 页面统一结构

每个核心工作台使用同一信息层级：

1. Identity strip：as_of、snapshot、freshness、运行版本；
2. Decision banner：当前结论、变化和状态；
3. Evidence canvas：图表、表格、因子、风险和 lineage；
4. Comparison/Inspector：候选、版本或组合差异；
5. Action rail：研究、加入观察、创建 Model proposal、加入 Paper、记录实际事件；
6. Agent sidecar：基于当前 context 的解释、比较和草案；
7. Audit drawer：证据、算法、数据和事件来源。

### 14.3 关键页面原型

#### Today

    ┌──────────────────────────────────────────────────────────────┐
    │ Market Regime · 数据时点 · 风险状态 · Paper 状态            │
    ├──────────────────────────────┬───────────────────────────────┤
    │ 今日变化与驱动               │ Priority Queue                │
    │ 全球 → A股 → 行业            │ 待看候选 / 待录入 / 待审批   │
    ├──────────────────────────────┼───────────────────────────────┤
    │ Selection Movers             │ Model / Paper / Manual Drift  │
    ├──────────────────────────────┴───────────────────────────────┤
    │ Agent Daily Brief · 证据 · 不确定性 · 建议下一步            │
    └──────────────────────────────────────────────────────────────┘

#### Markets / Selection

    ┌──────────────────────────────────────────────────────────────┐
    │ Macro & Cross-Market → Regime → Industry Rotation           │
    ├───────────────┬──────────────────────────────┬───────────────┤
    │ Universe/Rule │ Candidate Table              │ Inspector     │
    │ Saved Views   │ Rank/Change/Factor/Industry  │ Why in/out    │
    │ Run History   │ Risk/Technical/Freshness     │ Compare       │
    ├───────────────┴──────────────────────────────┴───────────────┤
    │ Research · Watchlist · Model Proposal · Paper · Agent       │
    └──────────────────────────────────────────────────────────────┘

#### Instrument Hub

- 行情与多周期技术图；
- TechnicalAnalysisSnapshot 的指标和条件；
- 行业/基准相对强弱；
- 基本面、事件、研究、Selection 历史；
- 当前 Model/Paper/Manual 暴露；
- Agent 标的分析与候选比较。

#### Research / Strategy Studio

- StrategySpec 表单与 DSL 编辑；
- 版本 diff、编译、验证和测试；
- 实验计划、参数预算、walk-forward 和成本模型；
- backtest 工件和 Review Bundle；
- Agent Author 草案、解释和逐动作审批。

#### Portfolio

    ┌──────────────────────────────────────────────────────────────┐
    │ As-of · Valuation Snapshot · Account Health                 │
    ├───────────────────┬───────────────────┬──────────────────────┤
    │ Model Portfolio   │ Paper Account     │ 我的账户 / Manual   │
    │ target & intent   │ orders/fills/PnL │ events/cash/holdings │
    ├───────────────────┴───────────────────┴──────────────────────┤
    │ Drift · Exposure · Attribution · Scenario Preview           │
    ├──────────────────────────────────────────────────────────────┤
    │ Agent Portfolio Diagnostic · 异常 · 解释 · 复盘             │
    └──────────────────────────────────────────────────────────────┘

### 14.4 Agent 前端改造

保留现有恢复型 SSE、Run/Campaign/Approval 组件和 API client；改造重点：

- Agent launcher 从“进入 Console”升级为当前页面的上下文 Sidecar；
- Console 的运行治理视图下沉到 System / Agent Ops；
- Research 增加 Agent Lab，聚合研究 Memo、Campaign 和 Strategy Draft；
- Markets、Selection、Instrument、Portfolio 增加结构化输出卡片；
- 用户动作始终在原业务页面完成，Agent 只生成 proposal 或跳转；
- 每个 Agent 输出都可展开 evidence refs、tool records、PIT context 和 guardrail。

## 15. 关键端到端数据流

### 15.1 每日市场与选股

    Data ingest
      → quality + PIT snapshot
      → features + Regime
      → IndustryRotationSnapshot
      → SelectionRun
      → Selection Workspace
      → Agent SelectionMemo
      → user sends candidates to Research or Model proposal

### 15.2 Model 到 Paper

    SelectionRun + Strategy signals
      → Portfolio target
      → Risk decision
      → user starts/continues Paper session
      → Paper orders
      → deterministic fills
      → Paper ledger
      → comparison and review

Agent 可解释每一步，不可触发 session 或改变事件。

### 15.3 Manual 实际账户

    User records trade/cash event
      → application validation
      → append immutable ManualEvent
      → account projection
      → valuation/risk/attribution
      → Model/Paper/Manual comparison
      → Agent diagnosis from redacted evidence

### 15.4 Agent Run

    UI context identity + objective
      → apps derives authority and PIT scope
      → agent host selects exact tool allowlist
      → model emits structured tool intent
      → tool calls application leaf query
      → EvidenceEnvelope sealed and audited
      → model emits structured output
      → guardrail and evidence citation validation
      → UI projection + SSE

需要写入策略草案时：

    model requests approved Author tool
      → run paused
      → exact payload/hash/TTL shown to user
      → approve or reject
      → provider continuation resumes once
      → application command receipt
      → audit and UI update

## 16. 非功能设计

### 16.1 可靠性

- 所有 command 有 idempotency key；
- Projection 可从事件和工件重建；
- Paper session 重启后不重复成交；
- Agent SSE 支持 cursor 恢复；
- 数据或模型降级显式展示；
- 关键任务支持重试但不改变统计试验计数；
- 每日自动生成数据、Paper、Manual、Agent 健康摘要。

### 16.2 性能目标

以下为目标 SLO，不是当前实测：

| 场景 | 目标 |
|---|---|
| Today/Markets/Portfolio 已物化读模型 | 本地 p95 小于 1 秒 |
| SelectionRun 1 万标的级排序 | p95 小于 10 秒，结果异步持久化 |
| 单标的技术快照 | p95 小于 2 秒或预物化命中 |
| PortfolioComparisonView | p95 小于 2 秒 |
| Agent 创建 Run 到首个进度事件 | p95 小于 3 秒，不含供应商模型生成时间 |
| SSE 恢复 | 断线后从最后 cursor 继续，无重复副作用 |

真实数据规模确认后再调整 SLO，不为达成数字引入分布式架构。

### 16.3 安全与隐私

- secrets 仅在服务端配置；
- Manual 备注、附件和账户金额默认不发送给云模型，除非字段级许可；
- 发送给模型的组合数据优先使用比例、区间或脱敏 identity；
- 记录 egress class 和 license class；
- Agent storage、研究存储和业务账本分离；
- 日志和 OTel 只保存脱敏字段与 hash；
- 本地备份加密，恢复流程定期演练。

### 16.4 可观测性

统一 correlation_id 串联：

- ingestion run；
- source snapshot；
- feature materialization；
- SelectionRun；
- strategy/signal；
- Model target；
- Paper order/fill；
- Manual event；
- Agent run/tool/evidence/approval；
- UI request。

System 页面能从一个用户结论下钻到所有来源和版本。

## 17. 真实验证矩阵

### 17.1 必须真实验证的能力

| 能力 | 当前不能宣称 | 目标验证 |
|---|---|---|
| A 股行情 | 数据可稳定用于决策 | 至少两段历史重摄取、复权/停牌/公司行动核对、增量更新 |
| 实时数据 | Paper 可持续运行 | 真实 provider 连接、断线、迟到、乱序、重连与交易日测试 |
| 中国宏观 | 历史 PIT 正确 | 人工发布时间样本、revision、future sentinel |
| 全球/A 股指数 | 跨市场比较正确 | 时区、币种、节假日和前收盘对齐 |
| 选股 | 榜单有投资意义 | SelectionRun replay、排名解释、样本外稳定性和用户盲评 |
| 技术分析 | 指标/形态可信 | golden reference、边界、复权和多周期一致性 |
| 回测 | 结果可用于决策 | PIT、成本、walk-forward、replay hash、未来哨兵 |
| Paper | 是正式账户 | 连续 20 个交易日、崩溃恢复、事件重放、日终对账 |
| Manual | 可维护实际账户 | 期初+事件重建、冲正、更正、现金与公司行动样例 |
| Agent | 是可信副驾驶 | 真实模型 eval、引用忠实、PIT、越权、恢复和成本 |
| `apps/web` | 完整产品可用 | 从 Today 到 Selection、Paper、Manual、Review 的用户任务测试 |

### 17.2 Agent Eval Suite

至少包含：

- 证据中存在/不存在的数值引用；
- 选股入选与排除解释；
- 多周期技术冲突；
- Model/Paper/Manual as_of 不一致；
- 数据缺失和 snapshot 冲突；
- 恶意 prompt 要求调用未授权工具；
- 尝试发布策略、修改 Manual 或启动 Paper；
- approval 过期、payload 改变和重复恢复；
- holdout 泄漏；
- provider timeout、无效 JSON 和截断输出；
- 中文金融表达的准确性和不确定性标注。

每个模型/提示/工具版本发布前必须在固定集上回归；生产运行抽样进入 shadow review，不以收益好坏直接训练 Agent memory。

### 17.3 完整用户验收

用户应能在一个交易日内完成：

1. 在 5 分钟内理解宏观、全球和 A 股状态；
2. 查看行业轮动并运行一次个股/ETF Selection；
3. 比较候选、查看技术和基本面证据；
4. 使用 Agent 生成有引用的 SelectionMemo；
5. 将候选进入研究或 Model proposal；
6. 查看风险与仓位情景；
7. 让 Paper 按正式规则记录模拟订单和成交；
8. 手工录入实际账户成交或现金事件并更正错误；
9. 查看 Model/Paper/Manual 差异；
10. 完成日终 Agent Review，并能追溯全部证据。

任一步必须依赖 Mock、手工改数据库或无法解释的“最新值”，则不算通过。

## 18. 绿地初始化与上线前重建

### 18.1 原则

- 不写旧 schema 到新 schema 的迁移；
- 不保留旧 API adapter；
- 不做 shadow read 或 dual write；
- 不为旧前端路由维护 redirect；
- 不把历史测试数据带入正式环境；
- 所有状态从新 schema、正式 seed 和重新摄取的数据开始。

### 18.2 一次性重建顺序

1. 冻结本文和 API/领域合同；
2. 列出所有数据库、缓存、对象目录和运行时文件的精确绝对路径；
3. 区分可重摄取数据、声明式源文件、密钥和用户需保留内容；
4. 停止 API、Jobs、Paper 和 Agent；
5. 经用户确认后删除精确目标；
6. 以新 schema 创建空存储；
7. 从版本库 seed 策略、因子、Universe 和配置；
8. 重新摄取主数据、行情、指数和宏观；
9. 重建快照、特征和读模型；
10. 创建正式 Paper 与 Manual 期初；
11. 配置 Agent provider，运行 eval 和 live smoke；
12. 完成端到端验收后建立首次备份。

### 18.3 删除安全边界

本文授权设计绿地重建，不等于授权立即执行任意删除。实施时必须：

- 只删除显式枚举且核对过的精确路径；
- 不使用 HOME、波浪号、仓库根或未解析 glob 作为递归删除目标；
- 先生成 inventory 和 dry-run；
- 对可能含有用户策略或密钥的目录先人工检查；
- 报告删除了什么、是否可恢复和重新生成状态。

## 19. 分阶段交付门

Agent 不作为最后一期，而是随每条垂直链交付对应工具和 UI。

| Gate | 目标 | Agent 同步交付 | 退出标准 |
|---|---|---|---|
| G0 设计冻结 | D1—D16、合同、删除 inventory | 工具权限矩阵与 eval 基线 | 无未决产品边界 |
| G1 数据真相 | 主数据、行情、指数、宏观、PIT | market_context_evidence | 真实数据与 future sentinel |
| G2 发现链 | Regime、行业轮动、Selection、技术快照 | selection/industry/technical tools | 真实 SelectionRun 端到端 |
| G3 组合链 | Model、Paper、Manual、Risk、Comparison | portfolio comparison/scenario | 账本重建与 20 日 Paper |
| G4 研究链 | 因子、实验、回测、Strategy Studio | Research/Author 完整工作流 | walk-forward、Review Bundle、HITL |
| G5 产品证明 | 五域 UI、健康、审计和恢复 | 全场景 eval、Agent Lab/Ops | 用户闭环与 DOGFOOD 通过 |

这是一组完成门，不是当前路线图的任务拆解。本文确认后，再基于 Gate 生成后端/前端跨仓库执行计划。

## 20. 业界最佳实践映射

### 20.1 量化系统分层

[QuantConnect Algorithm Framework](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview) 将 Universe Selection、Alpha、Portfolio Construction、Risk Management 和 Execution 分开。Ditto 采用相同责任分离，但在 Execution 端只保留 Paper，不装配真实券商。

应用结论：

- 选股不能直接等于持仓；
- signal 不能绕过 portfolio construction；
- portfolio target 必须再经过 risk；
- Paper fill 与 backtest fill 使用明确现实模型；
- Manual 事实不应伪装成执行网关。

### 20.2 研究与防过拟合

[QuantConnect Research Guide](https://www.quantconnect.com/docs/v1/key-concepts/research-guide) 强调从假设开始、限制时间和参数、进行 out-of-sample 验证并警惕过拟合；[scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) 体现时间有序训练/测试分割和 gap。

Ditto 进一步要求 PIT snapshot、purge、embargo、sealed holdout、统计试验预算和成本模型，避免传统随机交叉验证泄漏未来。

### 20.3 研究追踪与可复现

[MLflow Tracking](https://mlflow.org/docs/latest/ml/tracking/) 的 run、parameter、metric、artifact、dataset 和 lineage 模型可作为 Ditto 研究工件合同参考。个人系统无需引入 MLflow Server；现有 analysis、artifact store 和 hash identity 已能承载同类语义。

### 20.4 Agent 人机审批、Guardrail 与 Trace

[OpenAI Agents SDK Human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/) 的暂停、逐调用批准和恢复模式与 Ditto 现有 exact approval 方向一致；[Guardrails](https://openai.github.io/openai-agents-js/guides/guardrails/) 和 [Tracing](https://openai.github.io/openai-agents-js/guides/tracing/) 支持对输入、输出、工具与运行轨迹进行结构化治理。

Ditto 需要保留并强化：

- host 决策而不是模型自授权；
- exact action payload/hash；
- PIT、authority 和 budget 绑定；
- SSE/continuation 恢复；
- evidence/tool/model/prompt trace；
- 不注册 publish、ledger 和 trading 工具。

### 20.5 AI 风险治理

[NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework) 和 [NIST Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) 将治理、场景映射、测量和风险处置贯穿 AI 生命周期，并强调生成内容失实、信息完整性和人机配置风险。

Ditto 对应措施：

- 所有 Agent 输出区分事实、解释和不确定性；
- 金融数值只来自确定性工具；
- 上线前 eval、上线后监测与 incident record；
- 防止自动化偏见和过度信任；
- 用户最终确认所有影响策略状态或账户状态的动作。

## 21. 明确拒绝的过度设计

| 方案 | 结论 | 原因 |
|---|---|---|
| 微服务/Kafka/Kubernetes | 拒绝 | 单用户本地工作站无收益，增加一致性和运维负担 |
| 多 Agent 研究团队 | 拒绝 | 单 Agent + profile + allowlist 足够，审计更清晰 |
| 通用向量数据库 RAG | 暂不采用 | 市场、研究和账本是结构化、版本化、PIT 查询 |
| 引入 MLflow Server | 暂不采用 | 借鉴合同即可，现有 analysis 能满足单用户追踪 |
| LLM 直接算指标/仓位/PnL | 拒绝 | 不可重放，易失实，破坏领域权威 |
| 图像模型看 K 线作正式形态 | 拒绝 | 形态必须由版本化确定性算法产生 |
| Agent 自动发布策略 | 拒绝 | 风险高且无必要 |
| Agent 自动启动 Paper | 拒绝 | Paper 是经济事实账本，必须用户明确触发 |
| Agent 写 Manual 账户 | 拒绝 | 用户实际经济事实不可由模型创造 |
| 真实券商抽象预留实现 | 拒绝 | 当前明确无真实交易目标，避免安全边界虚化 |
| 上线前兼容层和迁移框架 | 拒绝 | 项目未上线，可直接绿地重建 |

## 22. 系统最明显短板与优先级

### P0：不补齐就不是完整产品

1. 真实数据覆盖、新鲜度、PIT 和公司行动尚未产品化证明；
2. SelectionRun、IndustryRotationSnapshot 和 TechnicalAnalysisSnapshot 缺正式工作流；
3. Paper 未形成持续运行、恢复和对账的正式账户；
4. Manual 缺独立事件、现金、期初和冲正合同；
5. Model/Paper/Manual 无统一同一时点对比；
6. `apps/web` 仍未把五域和证据链完整落到真实 API；
7. Agent 缺市场、选股、技术和仓位工具。

### P1：决定系统是否可信

1. 中国宏观发布时间与 revision 合同；
2. walk-forward、purge/embargo、sealed holdout 和试验预算；
3. Paper fill reality model 与同期回测差异；
4. Agent 真实模型 eval、故障恢复和成本；
5. 数据、研究、组合和 Agent 的统一 lineage；
6. 日终复盘与 20 个交易日 DOGFOOD。

### P2：可以在闭环之后优化

- 更丰富技术指标和形态；
- 二级/三级行业与主题；
- 更复杂组合优化器；
- 本地小模型或多模型路由；
- 批量文件导入 Manual；
- 更长周期自动研究 Campaign。

## 23. 设计验收清单

本文确认后，后续实现不得违反：

- [ ] A 股个股和 ETF 都能进入 Universe、Selection、Research、Model、Paper 和 Manual；
- [ ] 全球和宏观只作为环境数据，不扩张真实交易范围；
- [ ] 无真实券商 provider、API、工具和前端动作；
- [ ] Paper 与 Manual 为独立不可变事件账本；
- [ ] Manual 允许无 Signal 的成交和现金事件；
- [ ] SelectionRun、TechnicalAnalysisSnapshot 和 PortfolioComparisonView 有正式 owner；
- [ ] Agent 只通过 application 调用业务能力；
- [ ] Agent 金融数值全部来自确定性工具；
- [ ] Agent 覆盖投研、选股、技术、仓位、策略编写和复盘；
- [ ] Agent 不发布策略、不修改账本、不启动 Paper；
- [ ] 所有历史查询传播 knowledge cutoff、publication cutoff 和 source snapshot；
- [ ] `apps/web` 只有 Today、Markets、Research、Portfolio、System 五个顶级域；
- [ ] 绿地初始化不实现旧数据迁移和兼容层；
- [ ] 完成以真实数据、恢复、对账、eval 和用户闭环证明；
- [ ] 实施前的任何真实删除均再次列出精确目标并核对。

## 24. 最终架构判断

Ditto 当前最有价值的资产是已经形成的模块化领域边界、PIT 安全意识、研究工件体系和治理型 Agent runtime。最需要改变的是产品交付重心，而不是推翻架构：

- 保留 13 包模块化单体；
- 绿地重建运行时数据和前端信息架构；
- 用 MarketContextSnapshot、SelectionRun、TechnicalAnalysisSnapshot、三类组合账本和 PortfolioComparisonView 补齐产品骨干；
- 让 Agent 随每条垂直链同步获得有证据的工具和结构化输出；
- 用真实数据、20 日 Paper、Manual 重建、Agent eval 和完整用户旅程定义上线。

目标不是“拥有很多量化模块”，而是让用户每天能够可靠地完成：理解市场、发现机会、验证想法、形成组合、模拟执行、记录实际账户并复盘，而且每一个结论都可以追溯、重放和纠错。
