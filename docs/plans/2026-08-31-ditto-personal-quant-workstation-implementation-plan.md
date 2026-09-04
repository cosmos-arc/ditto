# Ditto 个人量化投研与 Paper 工作站实施计划

> 版本：1.0
> 日期：2026-08-31
> 状态：IMPLEMENTATION COMPLETE / RELEASE CANDIDATE PASSED
> 目标设计：[Ditto 个人量化投研与 Paper 工作站系统设计](../design/2026-08-31-ditto-personal-quant-workstation-system-design.md)
> 产品基线：[系统产品定位与 App 蓝图基线](../reviews/2026-08-30-system-product-positioning-and-app-blueprint-baseline.md)
> 当前路线图：[Ditto Development Roadmap](../roadmaps/ditto-development-roadmap.md)
> 执行证据：[个人工作站 Gate 与验证总表](../evidence/personal-workstation/README.md)

截至 2026-09-03，I0—I15 已完成，Q0—Q6 按顺序全部通过并由内容寻址 manifest 鉴证。Q1—Q3 使用真实 Tushare/FRED、有界 snapshot、PIT 重放、mock-disabled UI 和最小化 GLM 证据；I12 沿同一 Selection/PIT lineage 精确保存 Strategy Draft，完成 136 个合资格月份的 Backtest、holdout 防重复和 10/10 hard gates，并以独立精确批准的受治理 Agent 工具调用进入 review/pending。PAP-09 在保留 2026-09-02 live anchor 的同时，按顺序处理了 2026-08-06 至 2026-09-02 的 20 个已收盘真实 Tushare 交易日，逐日重启、账本对账和 HMAC 链均通过；这是发布验收，不宣称自然时钟 soak。精确批准的 Q5 闭环把 Model、Paper、Manual 绑定到同一 as-of、snapshot 和 valuation lineage，GLM-5.3 PortfolioDiagnostic 仅调用一次只读比较工具并通过 guardrail。UI-08 十步真实用户旅程全部通过且浏览器 console error 为 0。最终后端 `pixi run -e dev ci`、PIT 专项、前端 `bun run ci` 和 OpenAPI zero-diff 均通过；OPS-10 已复验恢复、Q0—Q5、20 日回放、组合诊断和 UI-08，生成自校验发布候选。全程未连接券商、未提交真实订单、未发布或激活策略。

## 0. 计划结论

本计划把目标系统拆为 13 个工作流、106 个可独立验收的主工作包和 7 个发布 Gate。执行方式不是后端全部完成后再做前端，也不是最后再接 Agent，而是按用户可完成的垂直切片交付：

    数据事实
      → 市场环境
      → 行业与选股
      → 标的技术与研究
      → Model 组合
      → Paper 与 Manual 账本
      → 三组合比较与复盘

每个切片同时包含：

- 领域合同与确定性计算；
- application 用例；
- API/OpenAPI；
- ditto-app 真实页面；
- Agent 工具和结构化输出；
- PIT、恢复、审计和真实数据证据。

现有 R1—R5 资产继续复用，不重新实现已经成立的 StrategySpec、研究实验、组合风险、Paper 基础、Agent runtime、审批、SSE、审计和前端设计系统。新计划解决的是新产品定位相对旧 ETF/认证夹具 Beta 的差额。

推荐关键路径为 14—18 个专注实施周，再加 20 个已收盘真实 A 股交易日输入的生产 Paper 加速验收和一个真实当日 live anchor。按单一主要开发者配合 Agent 的节奏，完整上线证据预计需要 18—24 个日历周。真实数据供应商权限、限流和历史覆盖可能延长数据 Gate，但不改变架构顺序。

## 1. 目标、边界与完成定义

### 1.1 必须交付

- A 股个股与 ETF 同时进入 Universe、Selection、Research、Model、Paper 和 Manual；
- 全球核心指数、A 股核心指数、行业指数和宏观进入 MarketContext；
- 行业轮动、SelectionRun 和 TechnicalAnalysisSnapshot 成为真实产品对象；
- Model、Paper、Manual 三类组合事实及统一 PortfolioComparisonView；
- Paper 连续运行、重启恢复、成交假设和日终对账；
- Manual 支持无 Signal 的实际成交、现金事件、期初、冲正和更正；
- Agent 覆盖市场简报、投研、选股、技术分析、仓位预演、策略编写和复盘；
- ditto-app 重构为 Today、Markets、Research、Portfolio、System 五域；
- 真实数据、真实模型、20 个真实交易日输入的加速 Paper 验收、live anchor 和完整用户任务证明。

### 1.2 永久非目标

- A 股真实券商、MiniQMT/QMT、FIX 或真实订单；
- 全球资产交易；
- 多 Agent 投委会；
- 微服务、Kafka、Kubernetes；
- LLM 直接计算金融数值或修改账本；
- Agent 发布策略、启动 Paper、写 Manual；
- 上线前历史迁移、兼容 API、旧路由 redirect 或双读。

### 1.3 完成口径

工作包只能使用以下状态：

| 状态 | 含义 |
|---|---|
| NOT_STARTED | 尚未开始 |
| RED | 已有能解释目标行为的失败测试 |
| GREEN | 目标实现和焦点测试通过 |
| INTEGRATED | 跨包、API 和前端真实链路通过 |
| PROVEN | 真实数据/真实模型/恢复或 DOGFOOD 证据通过 |
| BLOCKED | 已记录外部阻塞、owner 和解除条件 |

页面存在、Mock 通过、OpenAPI 有端点或单元测试全绿，最多只能支撑 INTEGRATED，不能直接标记 PROVEN。

## 2. 当前基线与差额处理

### 2.1 可直接复用

| 资产 | 当前基础 | 本计划处理 |
|---|---|---|
| 13 包模块化单体 | import-linter 和 CI 边界已成立 | 保留，不新增顶层包 |
| PIT 数据和研究合同 | dataset/snapshot、knowledge cutoff、holdout | 扩展到宏观、指数、行业、技术和 Agent 工具 |
| StrategySpec 与研究治理 | 实验、walk-forward、review、publish | 连接新 SelectionRun 和 Agent Author |
| 组合与风险 | 目标组合、风险和 Daily Decision V3 | 增加三组合视图与情景预演 |
| Paper 基础 | Paper gateway/runtime、订单/成交测试 | 收敛为唯一执行模式并完成持续运行 |
| Agent runtime | Run、Campaign、Approval、SSE、Episode、eval | 增加五类业务 evidence 工具和 UI |
| ditto-app | 33 路由、页面合同、Graphite Studio | 硬切五域 IA 和真实工作流 |

### 2.2 不继承为新目标完成证据

[Integrated Product Roadmap Closure Ledger](../reviews/2026-08-30-integrated-product-roadmap-closure.md) 对认证夹具、ETF 主线、五日 Paper 和既有页面的结论继续有效，但不能证明：

- 真实个股和 ETF 全 Universe；
- 当前宏观、全球/A 股指数与行业数据；
- 中国宏观 revision 的完整 PIT；
- 正式 SelectionRun 与技术分析工作台；
- Manual 账户账本；
- Model/Paper/Manual 同时点比较；
- Agent 市场、选股、技术和仓位业务能力；
- 20 个真实交易日 Paper；
- 新五域产品旅程。

### 2.3 开始实施前的工作树条件

当前两个仓库均有大量未提交变化。任何代码实施开始前必须：

1. 只读列出 ditto 与 ditto-app 的 status、branch、diff summary；
2. 确认哪些变化属于已完成 R1—R5、产品重构或用户工作；
3. 将接受的现状形成可恢复 commit 或明确基线；
4. 不使用 reset、checkout、clean 或递归删除处理未知变化；
5. 为新实施使用 codex/ 前缀分支或经过确认的现有分支；
6. 记录后端 OpenAPI 与前端 generated types 的匹配 hash。

该步骤是保护当前成果，不是历史兼容。

## 3. 实施方法

### 3.1 垂直切片优先

每个切片按固定顺序：

1. 冻结用户场景、领域 owner、provider、consumer 和跨界合同；
2. 使用 ditto-test-first 观察公共行为 RED；
3. 若涉及数据/PIT，使用 ditto-pit-safety 补 future sentinel；
4. 在 owner capability 完成最小领域行为；
5. 在 application 添加 query、command 或 process；
6. 在 apps 添加薄 API、DTO、错误映射和 registry wiring；
7. 生成 OpenAPI，ditto-app 更新 generated types；
8. 以前端用户可见行为 RED 驱动 live 页面；
9. 添加 Agent application contract、tool、eval 和上下文 UI；
10. 完成跨仓库 E2E、恢复和真实证据；
11. 高风险 diff 使用 ditto-change-review；
12. 只有证据齐全才进入下一 Gate。

### 3.2 工作包规模

| 规模 | 预期专注时间 | 规则 |
|---|---:|---|
| S | 1—3 天 | 单包或单层、风险可控 |
| M | 4—7 天 | 一个垂直切片的核心部分 |
| L | 8—12 天 | 开始前必须进一步拆分 |

计划表中的规模用于排序，不是工期承诺。任何工作包不得以 XL 进入施工。

### 3.3 架构硬边界

    apps → agent → application → capability planes → kernel
    apps ─────────→ application

- data、features、strategy、portfolio、risk、execution、backtest、analysis 是并列平面；
- application 负责跨平面编排；
- agent 只消费 application 叶合同；
- apps.registry 是具体 provider 的唯一 composition root；
- route、job、provider 不承载领域计算；
- consumer port 由消费者拥有；
- 不修改 .importlinter 来迁就实现；只有产品要求确实改变边界时才单独审批。

## 4. 目标合同与所有权总表

| 能力 | Owner | Provider/实现 | 直接 Consumer | 跨界合同 |
|---|---|---|---|---|
| 数据目录与 PIT | data | source adapters、stores、query services | application、backtest adapters | DatasetSnapshot、PITQueryContext |
| 市场/宏观特征 | features | factor/materialization services | application | MarketRegimeFeatureSet |
| 技术分析 | features | deterministic indicator service | application | TechnicalAnalysisSnapshot |
| 行业轮动 | strategy | rotation service | application、backtest adapter | IndustryRotationInputBundle、IndustryRotationSnapshot |
| 个股/ETF 选择 | strategy | selection pipeline/store | application、backtest adapter | SelectionInputBundle、SelectionRun |
| Model 组合 | portfolio | rebalance/accounting services | application、risk | TargetPortfolio、PortfolioSnapshot |
| Manual 账本领域 | portfolio | account event state machine | application、execution storage adapter | ManualAccountEvent、AccountEventJournalPort |
| Paper 订单/成交 | execution | Paper gateway、reality、SQLite | application | PaperOrder、PaperFill、FillAssumption |
| 风险/情景 | risk | constraint/scenario services | application | RiskSnapshot、ScenarioResult |
| 跨域工作流 | application | query/command/process | apps、agent | workspace read models、receipts |
| Agent | agent | host/tools/model/eval | apps | EvidenceEnvelope、AgentRun、Approval |
| HTTP/Jobs/DI | apps | FastAPI/CLI/jobs/registry | ditto-app | OpenAPI、SSE |
| 产品 UI | ditto-app feature | TanStack Query/API adapters | 用户 | page contracts、generated API types |

业务消费关系不代表 capability 之间可以直接 import。例如 strategy 所需的市场/特征数据由 Strategy 侧定义 InputBundle，application 从 data/features 获取并注入；strategy 不直接依赖 data 或 features。

Manual 的领域事件和会计规则归 portfolio。物理 SQLite adapter 复用 execution 的交易状态存储边界，因为 execution 允许依赖 portfolio 且已有 account/fill storage；这不把 Manual 解释为券商执行。application 只面向 portfolio-owned journal port 编排。

## 5. 总体依赖图

    Q0 基线与绿地合同
      └─ Q1 数据真相
           ├─ Q2 市场环境
           │    ├─ Q3 行业/选股
           │    └─ Q3 技术分析
           │          └─ Q4 研究/策略
           └─ Q4 Model/Paper/Manual
                    └─ Q5 三组合/复盘
                         └─ Q6 五域产品与真实验收

Agent 随 Q2—Q5 各切片增加工具，不形成独立后置关键路径。ditto-app 随每个 API 切片交付页面，Q6 只做全局 IA 收口、视觉一致性和完整任务证明。

## 6. 工作流 FND：基线、绿地初始化与安全边界

### 6.1 目标

建立可恢复施工基线、一次性 fresh bootstrap 和永久无真实券商边界。

### 6.2 工作包

| ID | 位置 | 任务 | 验证/产物 | 规模 | 依赖 |
|---|---|---|---|---:|---|
| FND-01 | 两仓库 | 冻结 branch/status/diff/OpenAPI 基线 | baseline manifest | S | 无 |
| FND-02 | docs | 将 D1—D16 标记为实施事实源 | decision ledger | S | FND-01 |
| FND-03 | 全后端 | 枚举所有 DB、Parquet、cache、Agent、research、Paper runtime 路径 | reset inventory，精确绝对路径 | S | FND-01 |
| FND-04 | apps | 设计 fresh bootstrap 命令；默认 dry-run | 目标测试、拒绝宽路径 | M | FND-03 |
| FND-05 | storage owners | 为目标 schema 提供 fresh create DDL，不写旧数据迁移 | 空库启动集成测试 | M | FND-04 |
| FND-06 | apps.registry | 审计并移除/禁止真实 broker provider 装配 | composition test、无真实网关证明 | S | FND-01 |
| FND-07 | apps/API | 删除真实下单语义的公开动作，统一 Paper/Manual 名称 | OpenAPI diff、route tests | M | FND-06 |
| FND-08 | ditto-app | 删除旧 broker/trading 产品文案和危险动作 | 文案审计、交互测试 | M | FND-07 |

### 6.3 实施约束

- FND-03 只生成 inventory，不删除数据；
- 真正执行 reset 前再次展示精确目标并取得用户确认；
- fresh bootstrap 可以使用 schema version，但不得包含旧 schema transform；
- 上线后必须恢复正式 schema 演进，绿地策略只适用于首次上线前；
- 不删除策略/因子源文件、密钥或未知用户文件。

### 6.4 Gate Q0

- 两仓库基线可恢复；
- D1—D16 无冲突；
- broker composition test 证明无真实 provider；
- reset dry-run 不接受仓库根、HOME、波浪号、glob 和未解析环境变量；
- fresh empty runtime 能启动；
- 后端 arch-check/check 和前端 check 通过。

## 7. 工作流 DATA：真实数据产品与 PIT

### 7.1 目标

形成 A 股个股+ETF、A 股/行业/全球指数、宏观、基本面和公司行动的正式数据目录，所有下游共用明确快照与时间可见性。

### 7.2 数据集首批范围

| 组 | 首批内容 | 频率 | 必须的时间语义 |
|---|---|---|---|
| Security Master | 个股、ETF、上市状态、行业、ST、交易状态 | 日/事件 | effective_from/to、published_at |
| A-share Market | 日线、成交、复权因子、停复牌、涨跌停 | 日；可选只读实时 | market time、received_at、snapshot |
| A-share Indices | 核心宽基、风格指数 | 日；可选只读实时 | timezone、session、currency |
| Industry | 申万一级指数和成分 | 日/月度变更 | classification version、effective date |
| Global Context | 美股/欧洲/亚太核心指数 | 日；可选准实时 | timezone、previous close |
| Rates/FX/Commodity | 中美利率、人民币、美元、黄金、原油、铜、VIX | 日 | published/market time |
| Macro | 增长、通胀、信用、货币、地产、景气 | 月/季/事件 | period、published_at、revision |
| Fundamentals | 财务、估值、质量、成长 | 季/日 | report period、announcement date、revision |
| Corporate Actions | 分红、拆分、送转、除权 | 事件 | announce/ex/effective/pay date |

### 7.3 工作包

| ID | Owner | 任务 | 主要合同/实现 | 验证 | 规模 |
|---|---|---|---|---|---:|
| DATA-01 | data.catalog | 从裸字符串收敛目标 DatasetSpec | coverage、schema、frequency、license | catalog tests | M |
| DATA-02 | data.sources | 对用户可用实时/历史 provider 建窄 adapter | source-specific adapters | contract tests、rate limit | M |
| DATA-03 | data.storage | 为各数据域建立 fresh store/read model | market/macro/fundamental/metadata stores | roundtrip、empty bootstrap | M |
| DATA-04 | data.ingestion | 增量游标、幂等、晚到、冻结和补偿 | ingestion run records | retry/replay tests | M |
| DATA-05 | data.quality | 覆盖、缺口、重复、异常、公司行动、时区规则 | DQ result/certification | bad sample quarantine | M |
| DATA-06 | data.query | 统一 PIT query context 与 source snapshot | fail-closed query facade | future sentinel | M |
| DATA-07 | application | 数据产品状态与 certification query | DataProductView | app tests | S |
| DATA-08 | apps/ditto-app | System/Data Products 真实工作台 | API、coverage、DQ、license、repair UI | live boundary E2E | M |

### 7.4 Provider 认证

每个 provider 必须记录：

- entitlement 和使用许可；
- 可缓存、衍生、展示和发送给模型的范围；
- 历史覆盖和字段差异；
- 限流、分页、schema drift、超时和重连；
- 数据时区、货币、交易日和单位；
- fallback 与 unavailable policy；
- 真实样本 hash 和最近认证时间。

Provider 多不等于成熟。未通过认证的 provider 只能处于 experimental，不能进入 Selection、Paper 或 Agent 正式 allowlist。

### 7.5 Gate Q1

- 个股与 ETF 主数据和日频行情真实摄取；
- A 股核心指数、申万一级和首批全球/宏观数据真实摄取；
- 关键宏观指标至少三组历史发布时间/修订人工核对；
- PIT future sentinel 和 snapshot replay 通过；
- 公司行动、停牌、复权、交易日和时区样本通过；
- System/Data Products 不依赖 Mock；
- 后端 pytest -m pit、arch-check、check 通过。

## 8. 工作流 CTX：MarketContext 与 Today

### 8.1 边界

| 项 | 内容 |
|---|---|
| Owner | features 拥有确定性 Regime/市场特征；application 拥有聚合读模型 |
| Provider | data PIT queries + features evaluator |
| Consumer | ditto-app Today/Markets、strategy input adapter、agent |
| Contract | MarketRegimeFeatureSet、MarketContextView、MarketContextQueryPort |

### 8.2 工作包

| ID | 位置 | 任务 | 验证 | 规模 | 依赖 |
|---|---|---|---|---:|---|
| CTX-01 | features | 定义市场宽度、风格、波动、跨市场和宏观状态特征 | 公式 golden tests、PIT | M | DATA-06 |
| CTX-02 | features | 版本化 Regime 计算与 driver attribution | deterministic replay | M | CTX-01 |
| CTX-03 | application.queries | 聚合 MarketContextView | exact as_of/snapshot tests | M | CTX-02 |
| CTX-04 | apps.api | GET /v1/market/context 与错误语义 | OpenAPI、route tests | S | CTX-03 |
| CTX-05 | agent | market_context_evidence 与 EvidenceBrief eval | tool/evidence/PIT tests | M | CTX-03 |
| CTX-06 | ditto-app Markets | Macro & Cross-Market、Regime 和影响链 | live page tests | M | CTX-04 |
| CTX-07 | ditto-app Today | Daily Brief、变化、风险、待办、Agent Brief | task E2E | M | CTX-04/05 |

### 8.3 验收场景

- 用户选择任意历史 as_of 时，只看到当时已发布宏观版本；
- 全球隔夜变化按时区进入 A 股交易日，不误用同日未来收盘；
- Regime 变化能解释到 driver、行业影响、Selection 因子和当前持仓；
- 数据缺失时返回 blocked/degraded，不输出伪完整结论；
- Agent Brief 的每个数值引用都能落到 MarketContext evidence。

## 9. 工作流 SEL：行业轮动和个股/ETF SelectionRun

### 9.1 边界

| 项 | 内容 |
|---|---|
| Owner | strategy |
| Provider | IndustryRotationService、SelectionPipeline、SelectionRunStore |
| Consumer | application、backtest adapter、agent |
| Contract | IndustryRotationInputBundle、IndustryRotationSnapshot、SelectionInputBundle、SelectionRun |

Strategy 不导入 data/features。application 负责把 Universe、MarketContext、feature values 和风险标记适配为 strategy-owned input bundles。

### 9.2 工作包

| ID | 位置 | 任务 | 验证 | 规模 | 依赖 |
|---|---|---|---|---:|---|
| SEL-01 | strategy | 固定 IndustryRotationSnapshot schema 和 identity | domain RED/GREEN、hash replay | M | CTX-02 |
| SEL-02 | strategy | 多周期强弱、宽度、趋势、基本面/Regime 适配 | golden cases | M | SEL-01 |
| SEL-03 | strategy | 固定 SelectionRun/SelectionCandidate/Exclusion | schema、canonical hash | M | DATA-01 |
| SEL-04 | strategy | 个股与 ETF 两类 SelectionSpec | stock/ETF fixtures | M | SEL-03 |
| SEL-05 | strategy | 流动性、ST、停牌、上市天数、涨跌停等硬过滤 | boundary tests | M | SEL-04 |
| SEL-06 | application.processes | RunIndustryAndSecuritySelection | cross-plane integration | M | SEL-02/05 |
| SEL-07 | application.queries | 精确读取与比较 SelectionRun | previous-run diff tests | S | SEL-06 |
| SEL-08 | apps.api | create/get/compare Selection API | OpenAPI、idempotency | M | SEL-06/07 |
| SEL-09 | agent | industry_rotation_evidence、selection_run_evidence、SelectionMemo eval | factual/exclusion tests | M | SEL-07 |
| SEL-10 | ditto-app | Industry Rotation 与 Selection Workspace | live candidate flow | L→拆两包 | SEL-08 |

### 9.3 SEL-10 施工前拆分

- SEL-10A：Industry Rotation 页面和行业 Inspector；
- SEL-10B：Selection toolbar、saved spec、run history；
- SEL-10C：Candidate table、factor contribution、why in/out；
- SEL-10D：Compare cart、Research/Watchlist/Model/Paper 下游动作；
- SEL-10E：Agent SelectionMemo Sidecar。

### 9.4 验收

- 同一 snapshot/spec/seed 重放得到相同 SelectionRun hash；
- 股票和 ETF 使用不同规则但共享统一结果合同；
- 每个入选与排除都有 reason code；
- 行业排名变化能区分数据变化、成分变化和算法变化；
- UI 保存的是 SelectionRun，不只是临时筛选条件；
- Agent 不得在 evidence 外新增候选或篡改排名。

## 10. 工作流 TA：确定性技术分析

### 10.1 v1 指标范围

第一版固定以下最小集，不建立指标百科：

- 收益与相对收益；
- SMA/EMA 与斜率；
- RSI；
- MACD；
- ATR 与历史波动；
- 成交量、相对成交量和换手；
- Donchian/区间突破；
- 相对行业和基准强弱；
- 由版本化算法产生的支撑/阻力；
- 日/周多周期一致与冲突。

### 10.2 工作包

| ID | Owner | 任务 | 验证 | 规模 | 依赖 |
|---|---|---|---|---:|---|
| TA-01 | features | TechnicalAnalysisSpec 与 Snapshot | schema/hash tests | M | DATA-06 |
| TA-02 | features | 指标实现与注册表 | independent golden reference | M | TA-01 |
| TA-03 | features | 多周期、warm-up、复权、停牌处理 | PIT/boundary tests | M | TA-02 |
| TA-04 | features | 支撑/阻力和冲突算法 | deterministic cases | M | TA-02 |
| TA-05 | application/apps | TechnicalAnalysisQueryPort 与 API | exact snapshot/OpenAPI | M | TA-03/04 |
| TA-06 | agent | instrument_technical_evidence 与 TechnicalAnalysisBrief | no-hallucinated-level eval | M | TA-05 |
| TA-07 | ditto-app | Instrument Hub 技术视图和 Selection Inspector 嵌入 | live UI/visual test | M | TA-05 |

### 10.3 验收

- 所有指标可由算法版本、参数、窗口和输入重放；
- 除权、停牌、不足窗口不产生静默错误；
- rolling 使用 PIT 左闭语义；
- Agent 不能引用不存在的指标、点位或形态；
- 技术分析与 Selection、Research、Portfolio 关联，而不是孤立图表。

## 11. 工作流 ACC：三类组合语义与基础账本

### 11.1 边界

| 项 | 内容 |
|---|---|
| Owner | portfolio |
| Provider | Account state machines、rebalance services；execution 提供物理 journal adapter |
| Consumer | application、risk、execution、backtest adapter |
| Contract | AccountKind、AccountEvent、AccountEventJournalPort、PortfolioSnapshot |

### 11.2 工作包

| ID | 位置 | 任务 | 验证 | 规模 | 依赖 |
|---|---|---|---|---:|---|
| ACC-01 | portfolio | 固定 MODEL/PAPER/MANUAL 语义与禁止混账规则 | domain tests | S | FND-02 |
| ACC-02 | portfolio | 统一现金、持仓、成本、估值和 PnL 投影输入 | accounting tests | M | ACC-01 |
| ACC-03 | portfolio | AccountEvent identity、hash、reversal/correction | append-only tests | M | ACC-01 |
| ACC-04 | portfolio | AccountEventJournalPort 和 rebuild service | full replay tests | M | ACC-03 |
| ACC-05 | execution.storage | fresh SQLite journal adapter | roundtrip/transaction tests | M | ACC-04/FND-05 |
| ACC-06 | application | account commands/queries 与 idempotency | application tests | M | ACC-05 |
| ACC-07 | apps | account API DTO/error mapping | route/OpenAPI tests | S | ACC-06 |
| ACC-08 | ditto-app | Account identity strip 与禁止混淆文案 | component tests | S | ACC-07 |

### 11.3 验收

- 三类账户不能用同一个 command 隐式转换；
- 任意账户可从期初和事件完整重建；
- reversal/correction 保留原事件；
- 金额、数量和费用遵守 Decimal/货币精度合同；
- application 不直接访问 SQLite；
- execution adapter 不拥有 Manual 业务规则。

## 12. 工作流 PAPER：正式模拟交易账户

### 12.1 目标

将现有 Paper 基础收敛为唯一系统执行模式，并证明连续运行、恢复和现实成交假设。

### 12.2 工作包

| ID | 位置 | 任务 | 验证 | 规模 | 依赖 |
|---|---|---|---|---:|---|
| PAP-01 | execution | 审计 PaperOrder/PaperFill 状态机 | RED/GREEN、invalid transitions | M | ACC-02 |
| PAP-02 | execution.reality | T+1、手数、涨跌停、停牌、费用、税费、滑点 | boundary/golden tests | M | DATA-06 |
| PAP-03 | execution | FillAssumption 与 market snapshot lineage | hash/replay tests | M | PAP-02 |
| PAP-04 | application.processes | OperatePaperSession | crash/idempotency tests | M | PAP-01/03 |
| PAP-05 | application | session create/start/pause/reconcile commands | command tests | M | PAP-04 |
| PAP-06 | apps/jobs | Paper API、EOD job、恢复入口 | integration/restart tests | M | PAP-05 |
| PAP-07 | ditto-app | Paper account、orders、fills、session、异常 UI | live workflow tests | L→拆两包 | PAP-06 |
| PAP-08 | evidence | 5 日预验收 | no duplicate、daily reconciliation | S | PAP-07 |
| PAP-09 | evidence | 20 个已收盘真实交易日的加速验收 + live anchor | daily signed evidence bundle | 20 个交易日输入 | PAP-08 |

### 12.3 PAP-07 拆分

- PAP-07A：Paper Overview 与 Session 状态；
- PAP-07B：Paper Orders/Fills 和成交假设 Inspector；
- PAP-07C：异常、暂停、恢复和日终对账；
- PAP-07D：与 Model 的 drift 和 attribution。

### 12.4 加速验收规则

每天记录：

- 数据 snapshot 与 freshness；
- session state；
- intent/order/fill 数量和幂等 identity；
- 未成交/拒绝/部分成交原因；
- 现金、持仓、估值和 PnL；
- EOD checksum；
- 中断、恢复和人工处置；
- 与 Model/同期回测的差异。

验收按真实交易日历顺序逐日运行同一生产 Paper 路径；每个交易日都重新打开存储、校验真实 provider bar、执行 session/order/fill/reconcile、生成 HMAC 签名日证据，并在全链完成后执行重启重放。2026-09-02 的收盘后真实运行作为 live anchor。该证据可用于发布验收，但不得表述为 20 个自然日的 wall-clock soak。

20 个交易日输入中任何重复成交、不可重建账本、未来数据、provider 漂移或无法解释的现金差异都会使整组加速验收失败；不得跳过失败日继续累计。

## 13. 工作流 MAN：手工实际账户

### 13.1 v1 事件类型

- OpeningCash、OpeningPosition；
- Buy、Sell；
- Deposit、Withdrawal；
- Fee、Tax、Interest；
- Dividend；
- TransferIn、TransferOut；
- Split、Merge、OtherCorporateAction；
- Reversal、Correction。

### 13.2 工作包

| ID | 位置 | 任务 | 验证 | 规模 | 依赖 |
|---|---|---|---|---:|---|
| MAN-01 | portfolio | ManualAccountEvent union 与字段规则 | event-type tests | M | ACC-03 |
| MAN-02 | portfolio | 成交、现金、公司行动和期初会计 | accounting RED/GREEN | M | MAN-01 |
| MAN-03 | portfolio | reversal/correction 与 settlement semantics | replay tests | M | MAN-02 |
| MAN-04 | execution.storage | Manual journal adapter | transaction/roundtrip | M | ACC-05 |
| MAN-05 | application.commands | create account、record event、correct event | idempotency/conflict tests | M | MAN-03/04 |
| MAN-06 | apps.api | Manual account/event/correction API | OpenAPI/route tests | M | MAN-05 |
| MAN-07 | ditto-app | 我的账户、录入、流水、冲正、更正 | user behavior tests | L→拆三包 | MAN-06 |
| MAN-08 | evidence | 期初+事件完整重建演练 | checksum 与人工对账 | M | MAN-07 |

### 13.3 MAN-07 拆分

- MAN-07A：账户创建、期初现金/持仓；
- MAN-07B：成交和现金事件表单；
- MAN-07C：流水、附件/备注、冲正和更正；
- MAN-07D：持仓、现金、收益和数据完整性状态。

### 13.4 安全边界

- Agent 无 Manual write tool；
- UI 入账前显示净现金、费用和持仓变化预览；
- 入账后不可直接编辑，只能追加 correction/reversal；
- 文件导入放 P2，v1 先保证逐笔录入正确；
- 备注和附件默认不出站到云模型。

## 14. 工作流 CMP：三组合比较、风险与仓位预演

### 14.1 边界

| 项 | 内容 |
|---|---|
| Owner | portfolio 计算目标/差额；risk 计算暴露和情景；application 聚合 |
| Provider | Portfolio services、Risk services |
| Consumer | apps、agent、ditto-app |
| Contract | PortfolioComparisonView、PortfolioScenarioInput、ScenarioPreview |

### 14.2 工作包

| ID | 位置 | 任务 | 验证 | 规模 | 依赖 |
|---|---|---|---|---:|---|
| CMP-01 | portfolio | 同 as_of 组合标准化与 drift | math/property tests | M | ACC-02 |
| CMP-02 | risk | 暴露、压力、约束的 scenario 输入/输出 | boundary tests | M | CMP-01 |
| CMP-03 | application.queries | PortfolioComparisonView | mismatched-as-of fail closed | M | PAP-06/MAN-05 |
| CMP-04 | application.queries | PreviewPortfolioScenarioQuery | read-only/no side effect test | M | CMP-02 |
| CMP-05 | apps.api | comparison/scenario endpoints | OpenAPI/route tests | S | CMP-03/04 |
| CMP-06 | agent | portfolio_comparison_evidence、portfolio_scenario_preview、PortfolioDiagnostic | factual/permission eval | M | CMP-03/04 |
| CMP-07 | ditto-app | Portfolio Overview、三栏比较、Scenario、Attribution | live E2E/visual | L→拆三包 | CMP-05 |

### 14.3 验收

- 三组合估值价格、as_of 和 snapshot 一致，否则 fail closed；
- Model/Paper drift 能区分未成交、滑点、费用和风险阻塞；
- Model/Manual drift 能标记用户选择而非系统执行失败；
- scenario 不写任何账户或 target；
- Agent 只能解释 host 计算结果，不能自行生成权重数字。

## 15. 工作流 RES：研究、回测与 Strategy Author

### 15.1 原则

R3 的实验、walk-forward、holdout、review 和 StrategySpec 不重做。该工作流只完成新产品输入、Agent Author 和真实工作台衔接。

### 15.2 工作包

| ID | 位置 | 任务 | 验证 | 规模 | 依赖 |
|---|---|---|---|---:|---|
| RES-01 | application/analysis | SelectionRun 可生成 Research Case | lineage tests | M | SEL-07 |
| RES-02 | backtest/application | Technical/MarketContext 输入进入 replay manifest | PIT/replay tests | M | TA-05/CTX-03 |
| RES-03 | analysis | 研究 run 追踪 dataset/code/params/metrics/artifacts | content hash tests | M | DATA-06 |
| RES-04 | agent | Author 从 Selection/Research context 生成 StrategySpec proposal | author eval | M | RES-01 |
| RES-05 | ditto-app | Strategy Studio 展示 Author draft、compile、validate、diff、tests | user workflow tests | M | RES-04 |
| RES-06 | e2e | Selection → Research → Strategy Draft → Backtest → Review | real data E2E | M | RES-02/05 |

### 15.3 验收

- Agent 生成的是声明式 StrategySpec，不是无限制代码；
- save draft 与 submit review 保持 exact approval；
- publish 仍由非 Agent 用户流程完成；
- 参数和试验预算在运行前冻结；
- holdout 不进入 Agent context；
- Selection、MarketContext、Technical snapshot 和 Backtest artifact lineage 连续。

## 16. 工作流 AGT：Agent 业务化

### 16.1 复用与新增

复用：

- Run/Session/Campaign/Approval；
- TemporalToolContext、EvidenceEnvelope；
- research/portfolio/risk/daily decision 工具；
- Author preview/write；
- Episode、replay、guardrail、SSE 和 eval runner。

新增：

- market_context_evidence；
- industry_rotation_evidence；
- selection_run_evidence；
- instrument_technical_evidence；
- portfolio_comparison_evidence；
- portfolio_scenario_preview；
- account_event_evidence。

### 16.2 工作包

| ID | 位置 | 任务 | 验证 | 规模 | 依赖 |
|---|---|---|---|---:|---|
| AGT-01 | application | 七个叶级 QueryPort/preview port | contract tests | M | 对应领域 query |
| AGT-02 | agent.tools | 新 evidence tools 与 exact allowlist | registry/tool tests | M | AGT-01 |
| AGT-03 | agent.contracts | 六类结构化业务输出 | schema/canonical tests | M | AGT-02 |
| AGT-04 | agent.runtime | context profile → tool allowlist | permission tests | M | AGT-02 |
| AGT-05 | agent.guardrails | 数值引用、evidence coverage、forbidden action | adversarial eval | M | AGT-03 |
| AGT-06 | agent.evals | 市场/选股/技术/仓位/Manual 隐私固定集 | fake + live eval | M | AGT-05 |
| AGT-07 | apps.registry | provider、egress、license、redaction wiring | composition tests | S | AGT-04 |
| AGT-08 | ditto-app | Context Sidecar 在五域挂载 | navigation/context tests | M | 对应页面 |
| AGT-09 | ditto-app | Research/Agent Lab 与 System/Agent Ops 分离 | route/page tests | M | AGT-08 |
| AGT-10 | evidence | 真实模型业务 eval、恢复、成本和延迟报告 | signed report | M | AGT-06/09 |

### 16.3 Agent 发布门

固定集必须证明：

- 工具选择正确；
- 所有金融数值来自 evidence；
- 缺数据时拒绝或降级；
- selection exclusion 不被模型绕过；
- 技术点位不被编造；
- as_of/snapshot 冲突 fail closed；
- publish、Paper start、Manual write、broker 均被拒绝；
- approval tamper、expiry、replay 和 concurrent resume 被阻止；
- provider failure 不回退成无证据聊天；
- 组合金额和 Manual 敏感备注遵守 redaction policy。

## 17. 工作流 UI：五域信息架构硬切

### 17.1 目标路由

| 产品域 | 目标路由 |
|---|---|
| Today | / |
| Markets | /markets、/markets/a-shares、/markets/industries、/markets/screener、/markets/watchlist、/instruments/{id} |
| Research | /research、/research/universes、/research/factors、/research/experiments、/research/backtests、/research/strategies、/research/agent、/research/reviews |
| Portfolio | /portfolio、/portfolio/model、/portfolio/paper、/portfolio/manual、/portfolio/transactions、/portfolio/risk、/portfolio/review |
| System | /system、/system/data-products、/system/jobs、/system/agent、/system/approvals、/system/settings、/system/audit |

旧 /trading 和 /platform 路由直接删除，不提供 redirect。后端 Agent API 路径可保留，因为它不是用户产品路由兼容层。

### 17.2 工作包

| ID | 位置 | 任务 | 验证 | 规模 | 依赖 |
|---|---|---|---|---:|---|
| UI-01 | docs/contracts | 重写五域 IA 与 route inventory | contract validation | M | FND-02 |
| UI-02 | src/features | 将 trading 产品能力收敛为 portfolio feature | architecture tests | L→机械/行为拆分 | ACC/PAP |
| UI-03 | src/features | 将 platform 产品能力收敛为 system feature | architecture tests | M | DATA/AGT |
| UI-04 | src/routes | 硬切 route tree 和 navigation | routes:generate、route tests | M | UI-01/02/03 |
| UI-05 | shell | 五域 header、context identity、action rail 和 Agent slot | shell tests | M | UI-04 |
| UI-06 | page contracts | 更新目标页面 states、overlay 和 live boundary | validator/generator | M | 各垂直页面 |
| UI-07 | visual | 1200/1366/1536 视觉、键盘、焦点和 console audit | prototype/Playwright | M | UI-06 |
| UI-08 | product E2E | 完整用户旅程 | live backend E2E | M | 全部 |

### 17.3 前端施工规则

- 不手写 generated OpenAPI types；
- 服务端状态全部使用 TanStack Query；
- 破坏性 Manual/Paper 动作显式确认；
- loading、empty、error、stale、blocked、review、ready 全覆盖；
- Mock 与 live 使用同一页面组件，但 PROVEN 只认 live；
- 页面合同 schema 本身尽量不变，只更新合同实例；若必须改 schema，先单独批准；
- 路由变更先运行 routes:generate，不编辑生成 route tree；
- feature 机械重命名和行为改造分开提交，降低审查噪声。

## 18. 工作流 OPS：运行、审计、备份与证据

### 18.1 工作包

| ID | 位置 | 任务 | 验证 | 规模 | 依赖 |
|---|---|---|---|---:|---|
| OPS-01 | apps/jobs | 数据、Selection、Paper、EOD 调度表 | schedule tests | M | Q1/Q3 |
| OPS-02 | observability | correlation_id 串联 ingest→Agent→ledger | trace integration | M | 各切片 |
| OPS-03 | storage | data/research/trading/agent 分库备份 | isolated restore | M | fresh schemas |
| OPS-04 | runbooks | data outage、Paper pause、Agent unavailable、Manual correction | tabletop review | S | 对应功能 |
| OPS-05 | metrics | freshness、DQ、run、Paper、Agent、E2E 指标 | dashboard tests | M | OPS-02 |
| OPS-06 | evidence | 每 Gate 生成 machine-readable manifest | hash validation | M | 各 Gate |
| OPS-07 | recovery | 进程中断、DB failure、SSE resume、duplicate request drills | recovery report | M | Q5 |
| OPS-08 | privacy | provider license、Agent egress、Manual redaction audit | policy evidence | M | AGT-07 |
| OPS-09 | performance | 读模型、Selection、TA、comparison 基准 | p95 report | M | Q5 |
| OPS-10 | launch | fresh bootstrap、restore、20 交易日加速验收、完整旅程总报告 | release candidate bundle | M | Q6 |

## 19. 7 个发布 Gate

### Gate Q0：施工基线

必须通过：

- 两仓库可恢复基线；
- fresh bootstrap 和 reset dry-run；
- 无真实 broker provider；
- D1—D16 固定；
- arch-check/check。

### Gate Q1：数据真相

必须通过：

- 个股+ETF、指数、行业、宏观首批真实数据；
- PIT future sentinel；
- 数据许可和 DQ；
- Data Products live UI；
- provider outage fail closed。

### Gate Q2：市场解释

必须通过：

- MarketContextView；
- Today/Markets live；
- Regime→行业/风险解释；
- Agent EvidenceBrief；
- 历史 as_of 重放。

### Gate Q3：发现链

必须通过：

- IndustryRotationSnapshot；
- SelectionRun 个股与 ETF；
- TechnicalAnalysisSnapshot；
- Selection/Instrument live UI；
- Agent SelectionMemo 和 TechnicalAnalysisBrief；
- SelectionRun deterministic replay。

### Gate Q4：账户链

必须通过：

- Model/Paper/Manual 三类语义；
- Paper 5 日预验收；
- Manual 期初+事件+更正重建；
- 三组合比较和 scenario；
- Agent PortfolioDiagnostic；
- 无真实交易入口。

### Gate Q5：研究与产品闭环

必须通过：

- Selection→Research→Strategy→Backtest→Review；
- Agent Author exact approval；
- 五域 route hard cut；
- live page contracts；
- backup/restore、EOD、Agent/SSE recovery；
- 前后端 full CI。

### Gate Q6：上线候选

必须通过：

- Paper 20 个已收盘真实交易日的顺序加速验收通过，并绑定真实当日 live anchor；
- 完整 Manual 对账；
- 真实模型 Agent eval；
- 用户十步完整任务；
- 性能、隐私、许可和 runbook；
- fresh bootstrap 后再次从零完成验收。

任一 Gate 未通过，不得用后续页面或更多功能绕过。

## 20. 推荐迭代顺序

| 迭代 | 主要目标 | 工作包 | 可并行 |
|---|---|---|---|
| I0 | 基线与决策冻结 | FND-01—03、UI-01 | 文档/只读审计 |
| I1 | Fresh bootstrap 和执行边界 | FND-04—08、ACC-01 | 后端/前端文案 |
| I2 | 数据目录和真实 provider | DATA-01—06 | catalog/source/storage |
| I3 | Data Products 与 MarketContext | DATA-07—08、CTX-01—04 | API/UI |
| I4 | Today 与 Agent Brief | CTX-05—07、AGT-01 基础 | Agent/UI |
| I5 | 行业与 Selection 领域 | SEL-01—07 | industry/selection |
| I6 | Selection API/UI/Agent | SEL-08—10、SEL Agent | API/UI/eval |
| I7 | 技术分析 | TA-01—07 | indicators/UI/eval |
| I8 | 账本基础与 Manual | ACC-02—08、MAN-01—06 | domain/storage/API |
| I9 | Manual UI 与 Paper 核心 | MAN-07—08、PAP-01—06 | 前后端 |
| I10 | Paper UI、5 日预验收 | PAP-07—08 | 验收同时修复非关键项 |
| I11 | 三组合与仓位 Agent | CMP-01—07 | portfolio/risk/UI |
| I12 | Research/Author 闭环 | RES-01—06、AGT-03—06 | research/agent |
| I13 | 五域硬切与 Agent Lab/Ops | UI-02—06、AGT-07—09 | mechanical/behavior 分开 |
| I14 | 恢复、视觉、性能 | OPS-01—09、UI-07 | evidence 并行 |
| I15 | 20 交易日加速验收与上线候选 | PAP-09、UI-08、AGT-10、OPS-10 | signed daily evidence |

I15 已在 Q4 后使用 20 个已收盘真实交易日完成加速验收，没有等待自然时钟；2026-09-02 真实当日 live anchor 与 20 日回放分别保留且互不替代。若发布候选之后改变 Paper 核心语义、数据快照或账本 schema，整组验收必须重新开始；本次验收不冒充 wall-clock soak。

## 21. 每个工作包的 Definition of Done

### 21.1 后端

- owner/provider/consumer/contract 已记录；
- 公共行为先观察 RED；
- 最小 GREEN 后重构；
- PIT 任务有 future sentinel；
- 类型和异常语义明确；
- composition root 测试存在；
- OpenAPI 更新且 zero-diff；
- 目标包测试通过；
- arch-check 和 check 通过；
- 高风险任务完成 change review；
- 真实数据/恢复证据按适用范围生成。

### 21.2 前端

- 页面合同和 live boundary 明确；
- 用户可见行为先 RED；
- generated API types 来自后端；
- TanStack Query 管理服务端状态；
- loading/empty/error/stale/blocked/ready 覆盖；
- destructive action 有确认和结果回执；
- 键盘、焦点和屏幕阅读语义通过；
- 目标 vitest、bun run check 通过；
- 发布 Gate 才运行完整 bun run ci 和视觉矩阵。

### 21.3 Agent

- 只调用 application leaf contract；
- tool 在 exact allowlist；
- host 注入 PIT/authority，不接受模型覆盖；
- evidence sealed、引用校验；
- forbidden actions 无工具；
- Fake 固定集和真实模型 eval 都通过；
- provider failure、timeout、malformed output 和 resume 有证据；
- 业务输出在 UI 中区分 facts、interpretations、uncertainties。

## 22. 验证命令矩阵

### 22.1 后端日常

| 场景 | 命令 |
|---|---|
| 目标测试 | pixi run -e dev pytest 对应 package/tests 路径 |
| PIT | pixi run -e dev pytest -m pit |
| 架构 | pixi run -e dev arch-check |
| 生产代码 | pixi run -e dev check |
| 提交/PR 候选 | pixi run -e dev ci |
| whitespace | git diff --check |

涉及公共行为、PIT、交易、风控、账户和回测时，任务说明必须显式调用对应项目 skill，不能只在最终补测试。

### 22.2 前端日常

| 场景 | 命令 |
|---|---|
| 路由 | bun run routes:generate |
| 目标行为 | bun test 或 vitest run 目标文件 |
| TS/TSX/API | bun run check |
| 页面合同 | validator/generator + 消费测试 |
| 发布候选 | bun run ci |
| 视觉 | 1200/1366/1536 prototype/Playwright matrix |
| whitespace | git diff --check |

### 22.3 跨仓库

- 后端生成 OpenAPI；
- 前端 regenerated API types 无手工差异；
- VITE_USE_MOCK=false；
- fresh runtime；
- 真实 provider 或明确 certified snapshot；
- Browser E2E 完成用户旅程；
- evidence manifest 记录两个 commit、config hash、snapshot 和时间。

## 23. 数据重置执行清单

该清单只有在 FND-03 inventory 经用户确认后才能执行。

### 23.1 Preflight

- 服务、Jobs、Paper、Agent 全部停止；
- 精确列出每个目标路径、类型、大小、最后修改时间；
- 对策略源文件、密钥、附件和未知文件标记 DO_NOT_DELETE；
- 生成 dry-run hash；
- 用户确认同一 hash；
- 可恢复内容先备份或明确不可恢复。

### 23.2 Reset

- 删除确认的 runtime DB、cache、materialization 和测试 evidence；
- 不删除仓库、HOME、未知目录；
- 创建 fresh schemas；
- seed Universe/Strategy/Factor 配置；
- 重摄取数据；
- 重建快照/特征/read model；
- 初始化正式 Paper/Manual 期初；
- 运行 Q0—Q1 smoke。

### 23.3 Postflight

- 报告删除目标和恢复性；
- 报告重摄取覆盖和失败；
- 记录 fresh bootstrap manifest；
- 建立首次正式备份；
- reset 工具恢复为需要显式确认的运维命令，不暴露普通 UI。

## 24. 风险登记

| 风险 | 概率 | 影响 | 早期信号 | 缓解 | Owner |
|---|---:|---:|---|---|---|
| 实时 provider 权限/限流不稳定 | 高 | 高 | 缺字段、断线、封禁 | provider certification、read-only、paused | DATA |
| 中国宏观发布时间不可靠 | 高 | 高 | 只有 period 无 published time | 人工样本、estimate 隔离、PIT fail closed | DATA |
| 选股工作台再次退化为筛选器 | 中 | 高 | 无 SelectionRun identity | run-first 合同和 E2E | STRATEGY/UI |
| Technical 变指标堆砌 | 中 | 中 | 新增大量无用途指标 | v1 固定集、Selection/Portfolio 消费门 | FEATURES |
| Paper 与回测成交语义漂移 | 中 | 高 | 同输入差异无法解释 | FillAssumption、comparison、加速验收 | EXECUTION |
| Manual 错录破坏账本 | 中 | 高 | 直接 UPDATE/DELETE | append-only correction、preview | PORTFOLIO |
| 三组合 as_of 不一致 | 高 | 高 | 错误比较收益/权重 | query fail closed、identity strip | APPLICATION |
| Agent 业务扩展越权 | 中 | 高 | tool 请求写账本/权重 | no tools、allowlist、eval | AGENT |
| 前端路由硬切造成大 diff | 高 | 中 | review 困难 | mechanical/behavior 分开 | UI |
| 当前 dirty worktree 丢失成果 | 中 | 高 | reset/clean 冲突 | FND-01 可恢复基线 | ALL |
| 全量 CI 反馈过慢 | 中 | 中 | 每小步跑全量 | 目标测试迭代、Gate 跑全量 | ALL |
| 20 日加速验收被核心变更作废 | 中 | 中 | 验收后改账本/Paper | Q4 后冻结核心语义并整组重跑 | EXECUTION |

## 25. 停止和回退规则

以下情况立即停止当前工作包：

- owner 或跨界合同无法在现有包边界表达；
- 需要修改 .importlinter 才能继续；
- 数据只有 latest、无法提供 PIT identity；
- 实现要求 Agent 直接访问 capability/storage；
- Manual 只能通过覆写历史实现；
- Paper 需要真实 broker provider 才能工作；
- 当前 dirty changes 与目标文件重叠且归属不明；
- 真实数据写入、依赖升级、schema 删除目标超出已确认范围。

回退采用：

- 关闭 feature flag；
- 停止未完成 Job/Agent/Paper session；
- 恢复 fresh baseline 备份；
- 保留失败 evidence 和事件；
- 不使用 hard reset 或强制清理。

## 26. 第一批可立即启动的任务

在不修改生产行为、不删除数据的前提下，优先顺序：

1. FND-01：两仓库 baseline manifest；
2. FND-02：同步 D1—D16 决策台账和实施事实源；
3. FND-03：runtime data inventory，只读；
4. FND-06：真实 broker composition 审计；
5. DATA-01：目标 DatasetSpec 与 provider coverage 表；
6. CTX-01：MarketContext 特征合同测试设计；
7. UI-01：五域 route/page contract inventory；
8. AGT-01：七个 application leaf contract 的接口草案。

第一个行为变更应是 MarketContext 的最小垂直切片，而不是先大规模重命名前端或删除旧存储。

## 27. 计划验收

该实施计划可执行的判断标准：

- [x] 每个目标能力有 owner、provider、consumer 和 contract；
- [x] 每个工作包有依赖、验证和退出条件；
- [x] Agent 在每个业务切片同步交付；
- [x] 个股与 ETF 都在计划主线；
- [x] 宏观、全球/A 股指数和行业真实数据有明确 Gate；
- [x] Paper 与 Manual 独立且无券商依赖；
- [x] 仓位辅助由确定性 portfolio/risk 计算；
- [x] ditto-app 五域硬切且无兼容路由；
- [x] 绿地 reset 有独立确认和安全边界；
- [x] 旧 R1—R5 资产被复用但不虚假继承新完成度；
- [x] 真实数据、真实模型、恢复、20 交易日加速验收、live anchor 和用户旅程定义完成；
- [x] 没有微服务、多 Agent、RAG 或迁移框架等过度设计。

## 28. 最终执行原则

后续每次开发只选择一个可以在一周左右达到 GREEN/INTEGRATED 的工作包。不能以“正在完善整个 Markets”“重做 Portfolio”或“增强 Agent”作为任务标题。

推荐任务标题格式：

    工作包 ID + 用户可见结果 + 精确合同

例如：

    SEL-03：保存可重放的股票/ETF SelectionRun
    MAN-05：录入无 Signal 的 Manual Buy/Sell 并返回不可变回执
    AGT-02：Agent 读取精确 SelectionRun evidence

系统最终不是按代码包数量验收，而是按用户能否每天稳定完成“理解市场—选股—研究—仓位—Paper—实际记录—复盘”验收。
