# Ditto 后续发展规划与分阶段开发设计

> **首次创建**：2026-07-10<br>
> **最近复核**：2026-08-12<br>
> **状态**：母路线图（Roadmap Source of Truth）<br>
> **北极星**：全球全品类、AI 原生、以证据驱动人工决策的量化平台；十个能力维度最终全部达到 10/10。

## 1. 路线图职责

本文决定“做什么、按什么顺序、通过什么 Gate”。它不替代能力事实和 release 施工图。

| 文档 | 职责 |
|---|---|
| `docs/plans/2026-07-10-capability-benchmark-design.md` | 当前能力、评分、对标、缺口和 10 分完成定义 |
| 本文 | R0-R7 顺序、依赖、横向工程、发布 Gate 和投资重点 |
| `docs/plans/2026-07-10-r1-implementation-plan.md` | R1 已完成的逐 task 施工与验收记录 |
| `docs/plans/2026-07-17-r2-data-product-design.md` | R2 确定性工程实现、详细范围、发布 evidence 缺口与 live Gate；实施 task 见 2026-07-18 R2 implementation plan |
| `docs/plans/2026-07-19-r3-a-share-research-strategy-governance-design.md` | R3 已确认的发布边界、双黄金路径、架构、研究协议、治理状态机、工作台与 G2 验收 |
| `docs/plans/2026-07-19-r3-a-share-research-strategy-governance-implementation-plan.md` | R3 W0-W5、22 个 TDD task、精确文件/测试、审批点和跨仓库施工顺序 |
| `docs/plans/2026-08-12-r5-governed-quant-research-agent-design.md` | R5 产品、架构、PIT、自主研究、沙箱、模型风险与发布门的权威设计 |
| `docs/plans/2026-08-12-r5-governed-quant-research-agent-implementation-plan.md` | R5.0-R5.5、38 个 TDD task、审批点、波次 Gate 与恢复合同 |
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
- R2 确定性工程与 live Gate 已完成，R3/G2 已以可复现 evidence 通过。
- R3 A 股日频研究与策略治理、R4 组合风险与 G3 控制已经完成。
- 当前产品主线：R5 治理型量化研究 Agent；仍保持本机单操作者、日频、人工审批
  和非自动交易边界。

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
| I 日频闭环 | R2 A 股日频数据产品 | 19 个核心数据集有区间认证、PIT、DQ、恢复和工作台 | 工程开发完成；真实发布 Gate 并行收口 | 13-19 人周 |
| II 研究产品化 | R3 A 股日频研究与策略治理 Beta | 双黄金路径的可复现研究、审查、发布与历史版本重新激活闭环 | 已完成，G2 通过 | 19-26 人周 |
| II 研究产品化 | R4 组合、风险与复盘 | 组合优化、风险与执行后复盘产品化 | 已完成，G3 控制落地 | 12-18 人周 |
| III AI 与盘中 | R5 治理型量化研究 Agent | grounded、可评测、HITL、PIT-safe 的 AI 投研、自治研究与 shadow 建议 | 设计与 38-task 实施计划已确认；实施待启动 | 18-26 人周 |
| III AI 与盘中 | R6 分钟级与盘中 Beta | 分钟数据、增量因子和盘中信号 | 未开始 | 24-36 人周 |
| IV 全球机构化 | R7 全球全品类扩展 | 多市场、多资产、多账户与机构运营 | 未开始 | 40+ 人周，滚动规划 |

\* 人周是范围估算，不是日期承诺；不含数据采购、法务审批、供应商等待和多人并行收益。每个 release 在上一 Gate 通过后重新估算。

## 5. 十维到 10 分的闭环路径

| 能力维度 | 第一次产品闭环 | 深化节点 | 10/10 最终证据 |
|---|---|---|---|
| 数据覆盖与接入 | R2 A 股日频 | R6 分钟；R7 全球 | 多资产/多频率、日历/时区/FX/合约/公司行动与供应商切换验收 |
| 数据治理与 PIT | R2 全部日频核心集 | R6 盘中 lineage | 全球数据集质量、许可、回补、降级、SLO 和恢复证据 |
| 因子与特征 | R3 可解释日频因子目录与诊断 | R5 AI 辅助；R6 增量 | 跨资产/频率因子库、诊断、复现、版本和在线一致性 |
| 策略与研究 | R3 实验、审查、发布与重新激活闭环 | R5 AI 辅助；R7 多市场 | 实验、审批、发布、回滚、监控、复现和用户价值证据 |
| 回测与仿真 | R3 批量实验、walk-forward 与确定性重放 | R6 event-driven | 全球市场规则、容量/冲击、研究/决策一致和确定性回放 |
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

**状态：DEVELOPMENT COMPLETE / RELEASE ACCEPTANCE BLOCKED（2026-07-18 对账）。**

详细设计事实源：`docs/plans/2026-07-17-r2-data-product-design.md`；发布 evidence
事实源：`docs/evidence/r2/README.md`。本节只维护 release 级范围和 Gate。

代码、测试、API、CLI、工作台、runbook 与确定性 fixture acceptance 已完成；
真实 provider 权限与许可、历史覆盖、19 份 live certification、真实性能、
backup/restore 和 5 个连续交易日运行 evidence 仍须独立关闭。R3 工程实施可与
这些 live evidence 并行，但未通过 R2 live Gate 的数据只能用于 research-only
路径，且 G2 不得通过。

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

## 9. R3：A 股日频研究与策略治理 Beta

**状态：已完成，G2 已通过。**

详细设计事实源：
`docs/plans/2026-07-19-r3-a-share-research-strategy-governance-design.md`；
逐 task 施工图：
`docs/plans/2026-07-19-r3-a-share-research-strategy-governance-implementation-plan.md`。

### 目标

让不了解系统内部代码的本机单操作者，能够从 R2 certified snapshot 出发，
通过受约束的类型化 StrategySpec 完成实验、滚动样本外验证、候选比较、解释、
审查、发布与历史 published version 重新激活，并让 R1 读取唯一 active version。
R3 保持日频、人工审批和本机边界。

### 发布边界

- 双黄金路径：A 股个股多因子选股为主线，ETF 为共享研究/治理主干的证明与
  R1 回归线。
- 作者能力：固定阶段的类型化流水线；表单和画布是同一不可变 StrategySpec 的
  两种投影。内置 `NodeDescriptor` 使用 `node_type@version` 和 typed I/O/config
  schema；未知节点 fail closed。
- 研究协议：可晋级策略至少 96 个完整 strategy-eligible 月；最近 12 个月为
  一次性 sealed holdout，此前 24 个月为两个年度 walk-forward folds，更早探索期
  至少 60 个月；purge/embargo 按真实 horizon、持有期和 execution lag 动态计算。
- 实验预算：显式参数列表/笛卡尔积，最多 128 个 candidate；默认 2、最多 4 个
  worker；单 active experiment，支持排队、pause/cancel/checkpoint/retry/resume。
- 治理协议：不可变版本，`draft → review → published → deprecated`；approval/
  rejection append-only；发布原子切换 active pointer；重新激活只能指向历史
  published、非 deprecated 版本。

### 核心工作包

1. StrategySpec v2、NodeDescriptor registry、canonical hash、typed parameter
   binding 与 unknown-node fail-closed。
2. 约 12 个可解释日频因子的核心目录及 PIT、winsorize、标准化、行业/规模
   中性化、IC/衰减/换手诊断。
3. experiment/candidate/fold/attempt 控制面，复用现有单次 backtest manifest、
   checkpoint、retry/resume 和 replay。
4. 96 月 validation protocol、动态 purge/embargo、baseline、multiple-testing
   ledger 与一次性 `HoldoutClaim`。
5. 两层研究门禁：正确性/evidence 为硬门禁，样本外收益、稳定性、回撤、换手、
   容量和调整后统计为必须展示的人工判断 evidence。
6. 个股候选池、逐级排除原因、factor contribution、行业/规模暴露；ETF 共享同一
   evidence 与发布协议。
7. 不可变策略版本、append-only review decision、active pointer、publish/
   deprecate/历史版本重新激活和 R1 集成。
8. Strategy Studio、Experiment、Review 工作台接真实 OpenAPI，覆盖队列、失败恢复、
   比较、lineage、artifact、发布和历史。
9. SQLite 控制面加内容寻址 Parquet/JSON artifact、备份恢复、确定性重放和双黄金
   路径 release evidence。

### 严格非目标

- 任意 Python/Notebook/代码节点、自由 DAG、R3 动态 plugin loader 或 custom executor。
- Bayesian/随机搜索/AutoML、大规模因子挖掘、另类数据、分钟/盘中和自动交易。
- 组合优化、组合级风险、AI/Agent、auth/RBAC、多租户、公网部署和分布式实验。

### 验收

- 同一 code/environment、canonical spec、registry、snapshot、参数、seed 与成本假设
  可确定性重放。
- 个股主线完整展示候选、排除、贡献与暴露；ETF 线与 R1 策略/数据语义一致。
- 96 月、PIT、split integrity、purge/embargo、成本、multiple-testing 和一次性
  holdout 均由服务端 fail closed。
- 用户只能为一个预选 candidate 打开 holdout 一次；基础设施恢复不得改变 logical
  run 输入。
- review approval、publish 和历史版本重新激活均为显式、append-only、可审计动作；
  R1 每批锁定 active version。
- `VITE_USE_MOCK=false` 下完成 Strategy Studio → Experiment → Review → Publish →
  R1 → Reactivate 全闭环。
- metadata/research DB 与 artifact 通过备份恢复；后端、前端和双黄金真实数据
  evidence 通过。
- R2 live Gate 与上述 R3 evidence 同时关闭后，G2 日频研究 Beta 才通过。

## 10. R4：组合优化、风险与复盘工作台

**状态：已完成（`9ee6c48c`，PR #72），G3 组合风险控制已落地。**

详细设计事实源：`docs/plans/2026-08-04-r4-portfolio-risk-design.md`；最终施工与
验收入口：`docs/plans/2026-08-10-r4-portfolio-risk-g3-execution-plan.md`。

### 目标

把“有信号”提升为“仓位可解释、风险可控、执行后可复盘”的日频决策产品。

R3 只提供为回测和选股语义服务的确定性基础分配方式，例如等权、权重上限和
简单逆波动；均值方差、风险平价、风险预算、组合约束与组合级风险仍由 R4 独占。

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

## 11. R5：治理型量化研究 Agent

**实施状态（2026-08-17）：** R5.0—R5.4 与 R5.5 的确定性/Fake/运营检查点已实现；**R5.5 BLOCKED** 于 A3 物理 sandbox acceptance 和 A4 balanced/quality live-model comparison。所有 Agent flags 仍默认关闭，不声明 G4/G5、自动交易或 broker 能力。当前 evidence 与恢复入口见 [R5 implementation plan](../plans/2026-08-12-r5-governed-quant-research-agent-implementation-plan.md) 和 [R5 Agent runbook](../operations/r5-agent-runbook.md)。

### 目标

在 R3 可复现研究、R4 组合风险和 Daily Decision V3 之上增加 grounded、可评测、
可恢复的 AI 研究与决策辅助，不让模型成为新的事实源、回测裁判或隐形交易者。

权威设计：`docs/plans/2026-08-12-r5-governed-quant-research-agent-design.md`；
逐 Task 施工图：
`docs/plans/2026-08-12-r5-governed-quant-research-agent-implementation-plan.md`。

### 技术选择

新增第 13 包 `ditto_agent`，依赖方向固定为
`apps -> agent -> application -> capabilities`。生产默认采用单 Agent、确定性状态机、
function tools、服务端状态与 HITL；OpenAI Agents SDK 通过 Agent-owned port 接入，
不在 platform 建通用 LLM Gateway。OTel 是主观测协议，Langfuse 仅可选 exporter。

首发只使用 Ditto 内部 evidence；禁用开放 Web/RAG/MCP、Hosted Code Interpreter、
Conversations、Files、Vector Stores 和 Background mode。多 Agent 只做离线对照，
没有量化增益证据不进入生产运行时。

### 分层交付

**R5.0 治理、评测与重放底座**

- 建立 Agent contracts、canonical action hash、状态机、Agent SQLite、Episode/replay。
- 建立 Fake/OpenAI provider contract、模型/提示/tool schema 版本与本地 eval harness。
- 服务端注入 decision/knowledge/publication/snapshot/execution/egress/authority 上下文。

**R5.1 Evidence Copilot**

- 只读解释实验、因子、策略、回测、组合、风险和 Daily Decision V3。
- 每个 claim 绑定 `EvidenceEnvelope`、snapshot、artifact、PIT 和不确定性。
- API + SSE + CLI；断线只重放持久化事件，不重复工具副作用。

**R5.2 Author Copilot**

- 生成 StrategySpec/DSL/配置草案，调用现有 compiler/validator 产生诊断与 diff。
- 正式保存/提交只经 application command，并绑定不可变审批 hash 和幂等 receipt。
- 不注册 publish、权重、订单或券商工具。

**R5.3 Autonomous Research Campaign**

- 一次人工审批不可变 Campaign hash 后，在单一搜索轴和预算内迭代假设、代码、
  fold 与非 holdout 反馈。
- 生成代码只在无网 hardened OCI 沙箱运行，输出 score/prediction；财务指标、组合、
  风险和统计全部由 Ditto 宿主计算。
- SearchLedger 区分 operational attempt/statistical trial；fork 不能重置多重检验。
- Holdout 对 Agent 不可见，只允许一次独立审批的签名 aggregate pass/fail。

**R5.4 Decision Briefing**

- 在持久化 Daily Decision V3 之后生成只读 `DecisionOpinion`。
- opinion 独立存储和评测，不得改变 V3、权重、risk status、订单或执行结果。
- outcome feedback 必须满足 `outcome_known_at <= knowledge_cutoff`。

**R5.5 发布硬化**

- OTel、tamper-evident audit、成本/预算、30 天允许原文 retention、备份恢复和降级。
- 120 条正式 eval 覆盖 grounded、author、campaign/PIT/holdout、permission、sandbox
  attack 与 shadow decision。
- 所有 feature flags 默认关闭，Agent 依赖失败不影响 Ditto 核心流程。

### 运营要求

- balanced profile 为 `gpt-5.6-terra`/medium，quality profile 为
  `gpt-5.6-sol`/high；任何变更重跑相关 eval。
- 使用专用 OpenAI project、MAM 或 ZDR、`store=false` 和显式 license/egress policy。
- 普通 read P95 不超过 30 秒/0.25 美元；复杂任务不超过 60 秒/0.75 美元。
- 研究 Campaign 默认最多 6 代、128 个唯一候选、384 fold、并发 2、4 小时、
  20 GiB 临时空间和 8 美元模型预算。
- Agent 不直接连接券商；R5 始终保持人工决策与非自动交易边界。

### 验收

- forbidden action、PIT sentinel、审批绕过、holdout 泄漏和 sandbox escape 100% 通过。
- tool choice/evidence coverage 至少 95%，factual correctness 至少 90%，必须拒答 100%。
- Author compile/validate 至少 90%，Episode tool/event replay 100% 确定。
- 多 Agent 只有相同 Episode 上成功率提高至少 5 个百分点或候选接受率提高至少
  10%、安全无回退且成本/延迟不超过 2 倍，才允许另立 ADR。
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
| G2 日频研究 Beta | 内部研究用户 | R2 live Gate；R3 双黄金路径、96 月/一次性 holdout、确定性重放、策略治理、真实 API、备份恢复与数据许可 |
| G3 决策工作台 Beta | 内部投资决策用户 | R4 组合/风险/账本、SLO、告警、runbook |
| G4 受控外部 Beta | 邀请用户 | auth/RBAC、隔离、安全、隐私、数据再分发、支持流程 |
| G5 A 股商业产品 | 付费/正式用户 | 法务合规、投资建议边界、授权、审计、灾备、SLA、客服与计费 |
| G6 全球机构版 | 多市场机构用户 | R7 市场规则、多账户/租户、区域合规、容量与机构运营 |

G5 是独立横向 Gate，可以在 R7 之前完成；R7 不是 A 股商业化前置条件。任何 Gate 都不能由功能平均分替代。

## 16. 依赖关系

```text
R0
 └─ R1 ── G1
     └─ R2 工程开发（已完成）
         ├─ R2 真实发布 evidence 收口 ───────────┐
         └─ R3 研究与策略治理实施 ───────────────┴─ G2
             └─ R4 ── G3
                 ├─ 安全/合规横向工程 ── G4/G5
                 └─ R5
                     └─ R6
                         └─ R7 ── G6
```

当前依赖裁决：

- R2/R3/G2 与 R4/G3 的确定性宿主已经落地，R5.0、R5.1 可立即开始。
- R5.3 自主研究复用 R3 experiment/holdout/ledger，R5.4 shadow briefing 复用
  Daily Decision V3；实施前仍按 Task 1 核对真实叶级合同。
- R5 与 R6 可在团队资源充足时并行，但共享 API/schema 需先冻结。
- 安全、备份、SLO、许可和合规按 Gate 持续推进，不受功能 release 串行限制。

## 17. 优先级与资源配置

### P0：当前 release

- R1 与 G1 保持已完成状态、本机运行边界和回归门禁。
- R2/R3/G2 与 R4/G3 保持已完成状态和回归门禁。
- R5 从 R5.0 治理基础开始，先冻结真实消费合同，再按四个 Approval 点推进。

### P1：R5.1/R5.2

- 先交付 grounded read 与本地 eval，再增加 Author Copilot 的逐动作 HITL。
- 不因自然语言体验提前开放 Web/RAG/MCP 或正式 publish/交易动作。

### P2：R5.3/R5.4

- 在 hardened OCI、PIT、holdout 与 trial ledger 证据完整后开放受控研究 Campaign。
- DecisionOpinion 保持 shadow-only，以 outcome analysis 验证价值。

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
| 前端掩盖后端缺失 | live 模式展示 mock | Trading/Research domain 禁止 live fallback，契约测试 |
| 研究过拟合或 holdout 泄漏 | 反复换候选、看结果后改指标 | 预注册目标、完整 trial ledger、96 月 walk-forward、一次性 HoldoutClaim 和调整后统计 evidence |
| 本机实验耗尽资源 | 候选无界、并发争抢、恢复重复运行 | 128 上限、单 active experiment、2/4 worker、lease/checkpoint/idempotency |
| AI 输出像事实 | 无引用、越权调用 | grounded tools、structured output、eval、HITL、guardrails |
| 实时化破坏日频 | 时间语义混乱、结果不一致 | frequency/clock contract、replay、日频 regression suite |
| 全球化只扩枚举 | NAV/税费/交收错误 | 每市场 golden cases 与独立 Gate |
| 商业化后补安全合规 | 外部 Beta 才发现授权/RBAC 缺失 | G4/G5 横向轨道提前推进 |
| 单人关键依赖 | runbook 不可执行 | 恢复演练、证据包、自动化 preflight 和可观察 outcome |

## 20. 产品成功指标

### R1-R4 日频产品

- 交易日 EOD 成功率、数据按时率、blocked 原因分布和恢复时间。
- 建议复核耗时、建议到 fill 覆盖率、偏差、换手、费用和未解决冲突。
- 实验排队与恢复成功率、确定性重放率、holdout 一次性合规率、研究周期、
  review 拒绝原因、发布/重新激活频率和策略失效发现时间。
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

R1/G1、R2、R3/G2 和 R4/G3 已完成。R5 治理型量化研究 Agent 已完成 A3/A4
之外的实现与发布硬化检查点；R5.5 继续 fail closed，等待 A3 物理 sandbox 与 A4
live-model acceptance 后才能收口。分钟级改造继续留在 R6。
