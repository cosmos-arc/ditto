# Ditto 后续发展规划与分阶段开发设计

> **首次创建**：2026-07-10<br>
> **最近复核**：2026-07-17<br>
> **状态**：母路线图（Roadmap Source of Truth）<br>
> **北极星**：全球全品类、AI 原生、以证据驱动人工决策的量化平台；十个能力维度最终全部达到 10/10。

## 1. 路线图职责

本文决定“做什么、按什么顺序、通过什么 Gate”。它不替代能力事实和 release 施工图。

| 文档 | 职责 |
|---|---|
| `docs/plans/2026-07-10-capability-benchmark-design.md` | 当前能力、评分、对标、缺口和 10 分完成定义 |
| 本文 | R0-R7 顺序、依赖、横向工程、发布 Gate 和投资重点 |
| `docs/plans/2026-07-10-r1-implementation-plan.md` | R1 已完成的逐 task 施工与验收记录 |
| `docs/plans/2026-07-17-r2-data-product-design.md` | R2 已确认的范围、架构、历史区间、数据集矩阵与 Definition of Done；详细施工图待创建 |
| `docs/plans/2026-07-10-phase-a-implementation-plan.md` | 已废弃施工属性的历史迁移索引 |

事实冲突时，以验收证据、当前源码/OpenAPI/CLI、能力基准、母路线图、release 计划的顺序判定。

## 2. 产品原则

1. **日频先成产品**：先让 A 股日级人工决策每天可靠运行，再扩分钟和全球资产。
2. **人工审批是正式架构**：建议、证据、风险、审批、成交和复盘是主流程，不把人工看成临时占位。
3. **PIT 与 provenance 不妥协**：无 `knowledge_date`、snapshot、lineage 或质量证据的数据不得进入决策。
4. **研究与决策一致**：同一策略定义、市场规则、特征和风险契约贯穿研究、回测和信号。
5. **Gate 优先于平均分**：安全、数据、恢复、合规任一失败都阻止发布。
6. **复用现有领域能力**：新 release 先做源码审计，不重复实现已有 handler、port、planner 或 storage。
7. **渐进式实时化**：先抽象 frequency/clock/state，再引入 minute/event，不把日频系统一次性推翻。
8. **AI 必须可评测**：AI 只基于受控 tools 和可追溯证据；建议必须结构化、受 guardrail 约束并由人审批。
9. **全球化是领域扩展**：日历、时区、货币、税费、交收、公司行动和合约规则必须显式建模。
10. **10 分靠持续证据**：release 完成只提供提分资格，不自动把能力分改成目标值。

## 3. 当前基线

### 3.1 能力定位

- 能力广度：**5.9/10**。
- R1 日频人工交易就绪度：**7.9/10，G1 已通过**。
- 最强项：PIT、promotion evidence、数据血缘、回测严谨性、OMS/对账协议和工程边界。
- 最大空白：正式 AI runtime、分钟/盘中、全球资产统一模型。
- 最大产品缺口：R2 的 A 股日频数据产品覆盖、许可与长期 SLO 尚未启动；
  R1 仍只适用于本机单操作者边界。

### 3.2 R1 原五个硬阻塞（已清零）

1. latest-published 与幂等 seed bootstrap 已通过确定性验收。
2. 完整 signal package、零调仓与失败状态已持久化并可校验。
3. EOD same-input no-op、changed-input conflict 与中断恢复已验收。
4. 账户基线、D+1 数量、多笔部分成交与追加式更正已闭环。
5. Daily Decision V2 与 `ditto-app` live 复核、成交和复盘已验收。

### 3.3 明确不重复建设的能力

- strategy create/publish handler 与 API。
- `AccountSnapshotRecord`、position/fill/intents SQLite storage。
- execution target diff、T+1、手数与涨跌停基础。
- Prefect EOD flow、StrategyArtifactService 和 Daily Decision V1。
- 配置 provider 的 env > keyring > config 凭证优先级。

## 4. 阶段与 Release 总览

| 宏观阶段 | Release | 目标结果 | 状态 | 估算投入* |
|---|---|---|---|---:|
| I 日频闭环 | R0 产品边界固化 | 目标、评分、文档职责和架构边界稳定 | 已完成，持续维护 | 1-2 人周/次复核 |
| I 日频闭环 | R1 日频人工交易 MVP | 单操作者本机 Beta，从 EOD 到成交复盘闭环 | 已完成，G1 通过 | 8-12 人周 |
| I 日频闭环 | R2 A 股日频数据产品 | 19 个核心数据集有区间认证、PIT、DQ、恢复和工作台 | 设计已确认，实施未开始 | 13-19 人周 |
| II 研究产品化 | R3 回测、选股、策略管理 | 可复现研究工作台与基础策略治理 | 未开始 | 12-18 人周 |
| II 研究产品化 | R4 组合、风险与复盘 | 组合优化、风险与执行后复盘产品化 | 未开始 | 12-18 人周 |
| III AI 与盘中 | R5 AI Copilot / Agent v1 | grounded、可评测、HITL 的 AI 投研与建议 | 未开始 | 14-22 人周 |
| III AI 与盘中 | R6 分钟级与盘中 Beta | 分钟数据、增量因子和盘中信号 | 未开始 | 24-36 人周 |
| IV 全球机构化 | R7 全球全品类扩展 | 多市场、多资产、多账户与机构运营 | 未开始 | 40+ 人周，滚动规划 |

\* 人周是范围估算，不是日期承诺；不含数据采购、法务审批、供应商等待和多人并行收益。每个 release 在上一 Gate 通过后重新估算。

## 5. 十维到 10 分的闭环路径

| 能力维度 | 第一次产品闭环 | 深化节点 | 10/10 最终证据 |
|---|---|---|---|
| 数据覆盖与接入 | R2 A 股日频 | R6 分钟；R7 全球 | 多资产/多频率、日历/时区/FX/合约/公司行动与供应商切换验收 |
| 数据治理与 PIT | R2 全部日频核心集 | R6 盘中 lineage | 全球数据集质量、许可、回补、降级、SLO 和恢复证据 |
| 因子与特征 | R3 日频研究生产一致 | R5 AI 辅助；R6 增量 | 跨资产/频率因子库、诊断、复现、版本和在线一致性 |
| 策略与研究 | R3 基础生命周期 | R5 AI 辅助；R7 多市场 | 实验、审批、发布、回滚、监控、复现和用户价值证据 |
| 回测与仿真 | R3 日频产品化 | R6 event-driven | 全球市场规则、容量/冲击、研究/决策一致和确定性回放 |
| 组合构建与优化 | R4 | R7 跨资产 | 多目标多约束、成本/税费/风险预算、稳定求解和解释证据 |
| 风险管理 | R4 日频 | R6 盘中；R7 机构 | 事前/事中/事后、压力测试、恢复、告警、人工处置和审计 |
| 执行、OMS 与账户 | R1 人工单账户 | R4 多 sleeve；R7 多账户 | 完整账本、对账恢复、可选券商、多市场交收和运营证据 |
| AI、ML 与 Agent | R5 v1 | R7 机构治理 | eval、grounding、HITL、模型风险、成本、安全和持续质量证据 |
| 平台、体验与运营 | R1 本机工作台 | 每个 release 横向推进 | RBAC、多租户、SLO、灾备、API 兼容、安全供应链和支持体系 |

每一行的最终证据全部通过后，该维度才能标记 10/10。

## 6. R0：产品边界固化

### 目标

让团队在每次迭代前明确产品是谁、近期不做什么、能力事实来自哪里。

### 已交付

- 全球全品类北极星与 A 股日频优先路径。
- 10 维能力基准、证据等级和 release gate。
- R0-R7 命名和本文档职责。
- 阶段 A 旧计划降级，R1 成为唯一施工图。

### 持续任务

- 每个 release 后重跑能力审计。
- 记录 ADR、OpenAPI 兼容策略和 schema migration 清单。
- 删除过期命令、动态社区数据和未经证据支持的营销结论。

## 7. R1：日频人工交易 MVP

**状态：已完成（2026-07-16，G1 内部本机 Beta PASS）。**

验收事实源：`docs/acceptance/r1-g1-evidence-2026-07-16.md`。该状态不扩大为
公网、商业、自动交易或真实券商生产能力。

### 目标

完成单操作者、单账户、单执行 sleeve、本机使用的 A 股日频人工决策闭环，通过 G1。

### 核心工作包

1. latest-published 策略语义与 seed bootstrap。
2. 账户/持仓 baseline 和稳定 sleeve identity。
3. 复用 execution planner 生成 A 股建议数量。
4. 持久化完整 signal package，区分零调仓、失败与缺失。
5. deterministic EOD batch、同日重跑幂等和冲突处理。
6. 多笔部分成交、append-only 更正和 effective-fill read model。
7. Daily Decision V2 readiness 真值表与 API。
8. `ditto-app` Trading live 工作台。
9. runbook、备份恢复、真实数据 evidence 和 loopback-only 验收。

逐 task 文件、测试和命令以 `docs/plans/2026-07-10-r1-implementation-plan.md` 为准。

### 验收

- 有交易与零调仓两个交易日都可完整解释。
- 相同输入重跑不重复，输入变化和已有成交时 fail closed。
- 一个 intent 支持同日多笔成交和可追溯更正。
- `VITE_USE_MOCK=false` 下完成 ready/review/blocked、成交和复盘。
- 默认测试确定性通过，另有一次显式真实数据验收。
- 无认证时只监听 loopback，数据库可备份和恢复。

## 8. R2：A 股日频数据产品

**状态：设计已确认（2026-07-17），实施未开始。**

详细设计事实源：`docs/plans/2026-07-17-r2-data-product-design.md`。本节只维护
release 级范围和 Gate；数据集契约、失败状态、波次与测试以详细设计为准。

### 目标

把 A 股 ETF、个股、宏观和商品日级数据从“能接入”提升为具有明确历史区间、
PIT、质量、来源、恢复和 promotion 证据的数据产品，服务本地单操作者的日频
人工决策与后续研究。

### 历史边界

- 股票、ETF 和核心指数行情 raw 从 `2015-01-01` 开始；ETF 不早于自身上市日。
- 个股 universe/status 从 `2016-01-01` 开始认证；更早状态不声明完整。
- 策略可用起点由所需数据集认证区间、证券上市日和真实最大 lookback 动态计算。
- 2015 年以前历史不是 R2 release gate；这不等于将其判定为噪音，也不把
  2015 至今包装成完整市场周期。

### 数据范围

- P0 市场核心 12 个：`calendar`、`stock_basic`、`etf_basic`、`index_basic`、
  `stock_daily`、`etf_daily`、`index_daily`、`adj_factor`、`fund_adj`、
  `stock_status`、`index_weight`、`corporate_actions`。
- P1 稀疏与跨市场参考 7 个：`balance_sheet`、`income_statement`、
  `cash_flow`、`dividend`、`valuation_metrics`、`macro_indicators`、
  `commodity_daily`。
- `margin_trading`、`pledge_ratio` 延至 R4 或作为 R2 stretch；`fx_daily`
  延至 R7 或出现明确消费闭环后再立项。

### 核心工作包

1. 在现有 metadata/catalog/promotion 主干上补齐产品契约、三类覆盖起点和
   provider-specific snapshot identity。
2. 建立 schedule-aware、分块、可 checkpoint/resume 的 bootstrap 与增量管线，
   只把 DQ、payload、catalog、lineage 和 success evidence 全部闭环的 partition
   判为完成。
3. 修复 survivorship-bias-safe universe、公司行动、ETF 复权写入和
   effective-dated 指数权重闭环。
4. 为财务、分红和宏观修订建立 `knowledge_date`/revision-preserving PIT 语义。
5. 记录 source 权限、许可、差异、fallback 和 unavailable policy，不因 provider
   数量提升 maturity。
6. 数据工作台展示 coverage、DQ、run/repair、certification 和 license evidence。
7. 只以固定 seed 因子做输入、最大 lookback、物化和数据正确性 smoke；IC、衰减、
   换手、参数比较、批量回测和策略治理全部留到 R3。

### 严格非目标

- auth/RBAC、多租户、公网部署、外部 Beta 和新付费 provider 前置采购。
- 分钟/tick、盘中信号、券商自动交易、AI/Agent runtime。
- 完整因子研究、回测与策略产品、组合优化和组合风险。

### 验收

- 19 个数据集逐一冻结产品契约并生成不可变 certification report；bundle readiness
  不替代单数据集 promotion。
- P0 行情 raw 自 2015 起，个股 PIT universe 自 2016 起认证；所有缺口可解释或有
  带 owner/evidence 的批准例外。
- 任意样本可还原当时可知数据、universe、source snapshot、schema 和 lineage；
  point-in-time 语义缺失时 fail closed。
- 历史 bootstrap 可恢复、幂等且确定；限流、schema drift、DQ/PIT、orphan payload、
  catalog/lineage 失败均有补偿和 runbook。
- promotion、revoke、recertification、backup/restore、性能、连续真实数据运行和
  R1 ready/review/blocked 回归全部保留证据。
- 固定 seed 因子在 certified snapshot 上通过输入、最大 lookback、确定性物化重放
  和数据正确性 smoke；完整研究仍由 R3 验收。
- 数据使用权、本地缓存、衍生计算、展示和再分发边界已记录；不明确的数据不得
  进入外部 Beta。

## 9. R3：回测、选股与策略管理产品化

### 目标

让研究员无需修改系统内部代码即可创建、比较、复现、发布和回滚日频策略。

### 核心工作包

1. 统一 StrategySpec、参数 schema、universe、factor set、allocator、risk 和 execution assumptions。
2. 批量回测、walk-forward、滚动训练/验证和 baseline comparison。
3. 收益、风险、换手、容量、交易成本、行业/因子/个股归因。
4. 选股结果解释、候选池、排除原因和历史稳定性。
5. 策略 draft/review/published/deprecated 生命周期、审批、版本、diff 和 rollback。
6. 研究工作台接真实 API，支持实验列表、比较、报告、artifact 和 lineage。
7. 防数据窥探、过拟合与多重检验的研究门禁。

### 验收

- 同一 commit、spec、snapshot 和 seed 可复现同一报告。
- 研究结果能一键形成候选 published version，但发布必须人工审批。
- 选股、回测与 R1 signal 的策略/数据语义一致。
- G2 日频研究 Beta 的 API、备份、数据许可和复现 Gate 通过。

## 10. R4：组合优化、风险与复盘工作台

### 目标

把“有信号”提升为“仓位可解释、风险可控、执行后可复盘”的日频决策产品。

### 核心工作包

1. 受约束均值方差、风险平价、风险预算、Black-Litterman 和可行域/有效前沿。
2. 交易成本、税费、换手、流动性、行业、个股、风格和现金约束。
3. 组合/因子风险、压力测试、情景分析、drawdown budget 与 risk attribution。
4. `RiskGate` 状态持久化、崩溃恢复、typed audit 和风险事件流。
5. 多 sleeve 账户归因、成交/持仓/资金对账与偏差根因。
6. 决策前比较 target/optimized/executable，决策后比较 signal/order/fill/position。

### 验收

- 求解不可行、数值失败或数据缺失时有确定性降级，不输出伪最优解。
- 每个风险阻塞可追溯到规则、输入、阈值和人工处置。
- 账本重建与存量快照一致，偏差和 PnL 可解释。
- G3 决策工作台 Beta 的 SLO、告警、runbook 和恢复 Gate 通过。

## 11. R5：AI Copilot / Agent v1

### 目标

在稳定数据、策略、回测、组合和 Daily Decision 上增加 grounded AI，不让模型成为新的事实源或隐形交易者。

### 技术选择

首个 runtime 采用 OpenAI Agents SDK，使用其 agents、function tools、handoffs、guardrails、sessions、tracing 与 human-in-the-loop interruption/resume。选择是当前路线，不等于当前已有能力，也不阻止未来在模型边界接入其他 provider。

### 分层交付

**R5.0 评测与安全底座**

- 建立宏观解读、报告解读、策略生成、仓位建议的黄金样本与评分 rubric。
- 定义 token/成本/延迟预算、模型版本、prompt/version、结构化输出 schema。
- 处理 prompt injection、越权工具调用、敏感数据、幻觉引用和 trace 脱敏。

**R5.1 只读 Copilot**

- 回测、因子、组合、风险和 Daily Decision 报告解读。
- 宏观/市场信息分析、带来源 RAG、受控自然语言查询。
- AI 生成的结论必须附 snapshot、artifact、tool result 与不确定性。

**R5.2 策略与建议辅助**

- StrategySpec/DSL 生成、参数解释、代码审计和测试建议。
- 仓位与买卖建议只调用 Ditto tools，并经过 deterministic risk guardrail。
- 所有写操作与建议发布使用 HITL；状态可序列化并恢复。

**R5.3 多 Agent（有证据才启用）**

- analyst/researcher/portfolio/risk 角色采用 manager-as-tools 或 handoff。
- 只有单 Agent 基线评测证明多 Agent 提升质量时才增加复杂度。
- Experience Memory 只保存经验证反馈，不自动把模型输出当经验真相。

### 运营要求

- tracing 记录模型、tool、handoff 和 guardrail，但敏感输入/输出默认不上传。
- sessions 负责会话连续性，不替代 Ditto 的长期研究 artifact 和审计账本。
- 每次运行记录模型、prompt、tools、usage、cost、latency、result 和人工反馈。
- Agent 不直接连接券商；R5 仍以人工建议为边界。

### 验收

- 黄金集质量、grounding、拒答、安全、成本和延迟指标达到预设阈值。
- 无来源结论、tool 失败和越权请求 fail closed。
- 敏感 tool 调用可暂停、批准/拒绝并恢复，审批记录可审计。
- G4 外部 Beta 前完成认证/RBAC、数据权利、隐私和安全 Gate。

## 12. R6：分钟级与盘中信号 Beta

### 目标

在不破坏日频正确性的前提下，支持分钟级数据、增量因子、盘中风险和人工盘中信号。

### 核心工作包

1. 显式 frequency、event time、knowledge time、market session、timezone 和 sequence contract。
2. minute bar 分区、压缩、增量摄取、缺口检测、回补和 retention。
3. event-driven clock、Synchronizer/TimeSlice 演进与确定性 replay。
4. streaming/incremental factor state、checkpoint 和崩溃恢复。
5. 盘中 signal package、去重、过期、节流和状态变化通知。
6. 连续 risk state、行情中断、数据延迟、kill switch 和降级到日频。
7. 事件驱动回测与盘中 runtime 的同语义验证。

### 验收

- minute 数据 freshness、完整性、延迟和回补达到明确 SLO。
- 相同事件序列 replay 得到相同因子和信号。
- 乱序、重复、迟到、断流、午休、跨日和重启均有测试。
- 盘中建议仍由人审批；券商 adapter 不是 R6 Beta 的必需条件。

## 13. R7：全球全品类与机构化

### 目标

把已验证的日频、研究、AI 和盘中能力扩展为多市场、多资产、多账户平台。

### 建议扩展顺序

1. 港股/美股 ETF 与股票。
2. 国内商品期货与主力/连续合约研究。
3. 全球期货、外汇与利率产品。
4. 期权及其他非线性产品。

每一类资产都要独立通过数据、市场规则、回测、风险、账户、合规与运营 Gate，不能只扩一个 `asset_class` enum。

### 平台能力

- 跨市场日历、时区、币种、FX conversion、税费、交收与公司行动。
- 期货合约链、换月、保证金、结算价、涨跌停；期权 Greeks、波动率面和行权指派。
- 多账户、多 sleeve、多币种现金、权限、租户隔离和机构审计。
- 多区域部署、灾备、容量、成本、SLA 和支持体系。
- 可选 broker/execution adapters，保持人工审批和 kill switch。

### 验收

- 每个市场有 authoritative rule book、golden cases 和真实对账证据。
- 组合 NAV、FX、税费、公司行动和保证金可逐日重建。
- G6 全球机构 Gate 通过后才对外宣称全球全品类。
- 十维 10/10 必须逐维重新审查，不能由 R7 标签自动授予。

## 14. 横向工程轨道

这些工作不能留到 R7，一旦进入对应 Gate 就必须完成。

| 轨道 | R1 | R2-R3 | R4-R5 | R6-R7 |
|---|---|---|---|---|
| 安全与身份 | loopback、密钥不落盘/日志 | secret rotation、依赖扫描 | auth/RBAC、租户隔离、威胁建模 | 区域隔离、broker secrets、渗透测试 |
| Schema 与 API | migration 清单、OpenAPI 集成测试 | 版本/兼容策略、备份恢复 | deprecation、审计事件版本 | 多区域迁移、向后兼容回放 |
| 可靠性与运维 | runbook、备份恢复、结构化 outcome | freshness/DQ SLO、告警 | 服务 SLO、事件响应、容量 | 盘中延迟/可用性、灾备演练 |
| 数据权利与合规 | 内部使用边界 | 供应商许可、再分发清单 | 投资建议边界、隐私、留存 | 各市场监管、跨境和机构政策 |
| 质量与证据 | unit/integration/E2E/live 分层 | 数据与研究复现 | 风险、账本与 UX 验收 | replay、性能、全球 golden cases |
| AI 模型风险 | 不启动 runtime | 准备可引用 artifacts | eval 数据与权限基础 | R5 后持续 eval、成本、模型/提示版本 |

## 15. 发布 Gates

| Gate | 面向对象 | 必须通过 |
|---|---|---|
| G1 内部本机 Beta | 单个开发/交易操作者 | R1 清单、loopback、恢复、真实数据 evidence |
| G2 日频研究 Beta | 内部研究用户 | R3 可复现、数据许可、API 兼容、备份恢复 |
| G3 决策工作台 Beta | 内部投资决策用户 | R4 组合/风险/账本、SLO、告警、runbook |
| G4 受控外部 Beta | 邀请用户 | auth/RBAC、隔离、安全、隐私、数据再分发、支持流程 |
| G5 A 股商业产品 | 付费/正式用户 | 法务合规、投资建议边界、授权、审计、灾备、SLA、客服与计费 |
| G6 全球机构版 | 多市场机构用户 | R7 市场规则、多账户/租户、区域合规、容量与机构运营 |

G5 是独立横向 Gate，可以在 R7 之前完成；R7 不是 A 股商业化前置条件。任何 Gate 都不能由功能平均分替代。

## 16. 依赖关系

```text
R0
 └─ R1 ── G1
     └─ R2
         └─ R3 ── G2
             └─ R4 ── G3
                 ├─ 安全/合规横向工程 ── G4/G5
                 └─ R5
                     └─ R6
                         └─ R7 ── G6
```

允许的准备性并行：

- R1 期间可调研 R2 数据许可，但不启动大规模 ingestion 改造。
- R3 后期可制作 AI eval 数据集，但 R5 runtime 仍依赖 R4 稳定 artifacts。
- R5 与 R6 可在团队资源充足时并行，但共享 API/schema 需先冻结。
- 安全、备份、SLO、许可和合规按 Gate 持续推进，不受功能 release 串行限制。

## 17. 优先级与资源配置

### P0：当前 release 收口

- R1 九个 task 与 G1 evidence 已完成，保持回归门禁和本机运行边界。
- R1 过程中发现的非阻塞需求保留在 R2+ 候选池，不扩入已关闭的 R1。
- R2 已完成 code exploration、范围设计和投入评估；实施仍未开始，下一步创建
  逐 task implementation plan。

### P1：G1 后

- 先做 R2 数据产品，再做 R3 研究产品。
- 真实用户每天使用 R1 工作流产生的摩擦，优先回流到 R2/R3。

### P2：G2/G3 后

- R4 完成可靠组合与风险事实，R5 才接 AI 建议。
- AI 与分钟级分别立项，避免两个高不确定性架构改造同时压在核心团队上。

### P3：验证产品价值后

- R7 按市场/资产逐个立项，不启动“全球全品类大爆炸”项目。

## 18. 开发治理

1. 每个 release 在施工前重新做 code exploration 和 mini-design。
2. 计划必须列出目标、非目标、事实源、失败状态、schema/API 影响、测试和回滚。
3. 数据库 schema、新依赖、CI/CD、架构边界和环境配置变更遵循人工审批规则。
4. API 变更必须有 integration test、OpenAPI diff 和前端 codegen 验证。
5. migration 必须有前向、回滚、旧数据兼容和备份恢复测试。
6. 默认测试使用确定性 fixture；live acceptance 单独标记并保留证据。
7. 每个 task 独立提交；跨仓库提交分别保持可回滚。
8. release 结束填写 evidence pack，再更新评分、maturity 和路线图状态。
9. 每季度复核范围和投入；每半年复核外部对标。
10. 用户需求、事故和验收失败优先于计划中的主观排序。

## 19. 风险与缓解

| 风险 | 早期信号 | 缓解 |
|---|---|---|
| 计划膨胀 | R1 混入 AI/分钟/优化 | 严格 non-goals，新增项迁入后续 release |
| 文档与代码漂移 | 命令、路径、DTO 不存在 | 每个 release 开始复核源码，CI 加文档引用检查 |
| 数据“有但不可用” | 历史浅、延迟、许可不清 | dataset-level evidence 与 promotion gate |
| 重跑破坏交易账本 | 重复 intent/fill 或静默覆盖 | stable key、checksum、append-only、冲突 fail closed |
| 前端掩盖后端缺失 | live 模式展示 mock | Trading domain 禁止 live fallback，契约测试 |
| AI 输出像事实 | 无引用、越权调用 | grounded tools、structured output、eval、HITL、guardrails |
| 实时化破坏日频 | 时间语义混乱、结果不一致 | frequency/clock contract、replay、日频 regression suite |
| 全球化只扩枚举 | NAV/税费/交收错误 | 每市场 golden cases 与独立 Gate |
| 商业化后补安全合规 | 外部 Beta 才发现授权/RBAC 缺失 | G4/G5 横向轨道提前推进 |
| 单人关键依赖 | runbook 不可执行 | 恢复演练、证据包、自动化 preflight 和可观察 outcome |

## 20. 产品成功指标

### R1-R4 日频产品

- 交易日 EOD 成功率、数据按时率、blocked 原因分布和恢复时间。
- 建议复核耗时、建议到 fill 覆盖率、偏差、换手、费用和未解决冲突。
- 回测/策略复现率、研究周期、发布频率和策略失效发现时间。
- 组合/风险阻塞准确性、人工 override 率和账本重建一致率。

### R5 AI

- grounded answer rate、引用正确率、tool success、guardrail 拦截和人工采纳率。
- hallucination/unsafe action rate、单任务成本、P50/P95 延迟和恢复成功率。
- 单 Agent 与多 Agent 的增益必须通过 eval 证明。

### R6-R7

- 数据与信号延迟、事件丢失/重复、replay 一致性和盘中恢复时间。
- 各市场 NAV/FX/税费/交收 golden case 通过率。
- SLO、灾备、租户隔离、安全与合规审计结果。

## 21. 最近完成的实施切片

R1 已按以下顺序完成：

```text
活动策略
  → 账户基线
  → 建议数量
  → signal package / 幂等
  → EOD outcome / 运营入口
  → 成交账本
  → Daily Decision V2
  → ditto-app live
  → G1 evidence
```

R1 已通过 G1；R2 设计已确认、实施仍处于未开始状态。AI runtime 和分钟级改造
继续分别留在 R5、R6，不因 G1 通过而提前进入当前范围。
