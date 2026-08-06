# R3：A 股日频研究与策略治理 Beta 设计

> **首次创建**：2026-07-19<br>
> **状态**：CONFIRMED<br>
> **实施计划**：[2026-07-19 R3 implementation plan](2026-07-19-r3-a-share-research-strategy-governance-implementation-plan.md)<br>
> **上游状态**：R2 确定性工程完成；R2 live release evidence 并行收口<br>
> **目标 Gate**：G2 日频研究 Beta<br>
> **运行边界**：本机、单操作者、日频、人工审批<br>
> **目标结果**：把 R2 已有数据、因子、策略和单次回测能力产品化为可复现、可解释、可审查、可发布和可重新激活的完整研究闭环。

## 1. 决策摘要

R3 正式命名为 **A 股日频研究与策略治理 Beta**。它不重建第二套策略或
回测引擎，而是在现有能力上增加研究实验控制面、策略治理控制面和真实前端
工作台。

完整任务链为：

```text
Certified Snapshot
  → Strategy Studio
  → Experiment
  → Walk-forward
  → Candidate Selection
  → Sealed Holdout
  → Review
  → Publish
  → R1 Active Strategy
  → Reactivate Historical Version
```

| 决策项 | R3 口径 |
|---|---|
| 黄金路径 | A 股个股多因子选股为主线；ETF 为共享主干证明与 R1 回归线 |
| 作者能力 | 声明式 `StrategySpec`；表单和受约束类型化流水线是同一对象的两种投影 |
| 扩展边界 | R3 只保留版本化 `NodeDescriptor` 契约，不实现插件加载或任意代码执行 |
| 搜索能力 | 显式参数值列表和笛卡尔积；每个实验最多 128 个可执行配置 |
| 并发能力 | 默认 2、最大 4 worker；同一时刻只有一个 active experiment |
| 晋级历史 | 至少 96 个完整 strategy-eligible 月 |
| 验证协议 | 探索期至少 60 月、两个年度 walk-forward fold、最近 12 月一次性 sealed holdout |
| 研究门禁 | 正确性为硬门禁；稳健性证据强制展示；人工依据预注册目标决策 |
| 生命周期 | immutable version；`draft → review → published → deprecated` |
| 发布语义 | approval/rejection append-only；publish 原子切换 active pointer |
| 恢复语义 | 重新激活历史 published、非 deprecated 版本，不重写版本历史 |
| 前端验收 | `VITE_USE_MOCK=false` 完成 Studio → Experiment → Review → Publish → R1 → Reactivate |
| 估算投入 | 19–26 人周；不含真实数据权限、采购和供应商等待 |

## 2. 发布定义

R3 完成后，一个不了解 Ditto 内部代码的研究者必须能够：

1. 使用表单或类型化流水线创建策略 working copy。
2. 保存新的不可变 draft version，而不是覆盖历史版本。
3. 基于 R2 certified snapshot 创建实验。
4. 运行显式参数矩阵、baseline 和滚动样本外验证。
5. 比较候选并查看收益、回撤、稳定性、换手、成本与容量证据。
6. 查看个股候选池、逐级排除原因、因子贡献和行业/规模暴露。
7. 在打开 holdout 前登记唯一候选和选择理由。
8. 对该候选执行一次封存样本检验。
9. 生成不可变 review evidence bundle。
10. 人工批准并发布策略版本。
11. 让 R1 日频决策读取唯一 active published version。
12. 必要时重新激活历史 published version。
13. 对任意冻结实验执行确定性重放。

R2 的真实 provider entitlement/license、2015/2016 历史 bootstrap、19 份 live
certification、真实性能、backup/restore 和连续运行证据不并入 R3 功能范围。
这些 evidence 可以与 R3 工程并行，但在其关闭前：

- 未通过 live certification 的数据只能进入 research-only 路径；
- 不得把 fixture acceptance 包装成真实研究结果；
- G2 不得通过。

## 3. 产品目标与严格非目标

### 3.1 目标

- 把单次回测提升为可恢复的 experiment/candidate/fold/attempt 产品。
- 把现有因子能力整理为约 12 个可解释日频因子的受控核心目录。
- 建立研究、回测、解释、审查、发布和 R1 消费的一致语义。
- 用一次性 holdout、完整 trial ledger 和预注册目标约束研究选择偏差。
- 用 active pointer 替换“最高 published version 即活动版本”的隐式规则。
- 将现有研究原型页接到真实 OpenAPI，形成可长期使用的本机工作台。

### 3.2 严格非目标

- 任意 Python、Notebook、代码节点或自定义 executor。
- 自由 DAG、动态 plugin loader 或 R3 插件安装 UI。
- Bayesian、随机搜索、AutoML 或大规模因子挖掘。
- 另类数据、分钟/tick、盘中策略或自动交易。
- 均值方差、风险平价、风险预算和组合级风险；这些继续由 R4 拥有。
- AI/LLM/Agent runtime。
- auth/RBAC、多用户、多租户、公网部署或分布式实验。

R3 的 `Allocator` 只允许等权、权重上限、简单逆波动等确定性基础分配方式。

## 4. 双黄金路径

| 维度 | 个股多因子选股主线 | ETF 证明与回归线 |
|---|---|---|
| 定位 | R3 主要产品能力 | 证明研究治理主干可复用并保护 R1 |
| Universe | A 股策略可交易股票池 | 有足够上市历史的核心 ETF 池 |
| 因子 | 动量、反转、波动、流动性、估值、质量、成长、规模 | 价格、成交、波动、流动性、相对强弱 |
| 解释 | 候选池、排除原因、原始值、标准化值、贡献、排名、行业/规模暴露 | 排名、动量/波动贡献、流动性过滤和 ETF 选择理由 |
| Baseline | 同 Universe 等权组合和预注册市场 benchmark | 当前 R1 active ETF 策略、等权或买入持有 benchmark |
| 验证 | 完整 96 月协议和一次性 holdout | 同一协议、同一 evidence 格式、同一状态机 |
| 价值 | 证明选股研究和解释能力 | 证明未破坏已有 ETF/R1 语义 |

两条路径共享 `StrategySpec`、node registry、scheduler、validation protocol、
evidence bundle、review/publish/reactivate、active pointer、OpenAPI 和工作台，
不得形成两套产品实现。

## 5. 架构与包边界

```text
ditto-app
    │ OpenAPI / polling
    ▼
ditto_apps
    │ HTTP / CLI / jobs / DI
    ▼
ditto_application
    ├── ExperimentPlanningProcess
    ├── ExperimentExecutionCoordinator
    ├── WalkForwardValidationProcess
    ├── ResearchEvidenceAssembler
    └── StrategyPromotionProcess
           │
           ├── ditto_analysis   experiment 与研究 evidence 控制面
           ├── ditto_strategy   StrategySpec 与生产治理控制面
           ├── ditto_features   因子计算、预处理和诊断
           ├── ditto_backtest   单次确定性运行、checkpoint 和 replay
           └── ditto_data       certified snapshot 与 PIT 数据
```

| 能力 | 归属 |
|---|---|
| `NodeDescriptor`、类型化节点和流水线语法 | `ditto_strategy.alpha.nodes` |
| 内置节点 registry | `ditto_strategy.alpha.node_registry` |
| canonical `StrategySpec` 与 hash | `ditto_strategy.alpha` |
| 版本治理、decision 和 active pointer | `ditto_strategy.governance` |
| 因子定义、IC、衰减、换手和归因 | `ditto_features` |
| experiment、candidate、fold 和 holdout | `ditto_analysis.experiments` |
| 批量运行、聚合与晋级编排 | `ditto_application.processes.experiments` |
| 单次回测、manifest、checkpoint 和 replay | 现有 backtest/application execution 主干 |
| REST、CLI 和本机 worker | `ditto_apps` |

边界规则：

- `analysis` 可以保存 opaque strategy/version/hash 引用，但不得导入 strategy 或 backtest 实现类型。
- `strategy` 不依赖 data、features、backtest 或 execution。
- application 负责跨包解析、编译、运行、聚合和晋级。
- backtest 保持单次运行语义，不接收 experiment、review 或 publish 行为。
- apps 只做传输、任务入口和 composition root wiring。
- R1 生产路径只读取 strategy 生产控制面，不读取 research SQLite。

## 6. StrategySpec v2 与 NodeDescriptor

### 6.1 Canonical StrategySpec

```text
schema_version
strategy_family_id
strategy_kind              stock_selection | etf_rotation
name
pipeline:
  nodes:
    - node_id
      node_type
      node_version
      config
  sequence:
    - node_id
parameter_schema
metadata
tags
```

后端编译产生不可变 `ResolvedStrategySpec`，包含：

- canonical spec hash；
- node registry manifest hash；
- resolved required datasets；
- factor IDs 和 versions；
- 最大真实 lookback；
- execution/cost assumptions；
- typed parameter binding；
- deterministic capability 和 lane compatibility。

前端不计算最终 hash。保存时由后端规范化、校验并返回 canonical spec/hash。

### 6.2 固定流水线语法

```text
Universe
  → FactorSet
  → Filter*
  → Scorer
  → Selector
  → Allocator
  → ExecutionAssumption
  → Validation
```

- `Filter` 可以为零到多个，其他黄金路径节点各一个。
- 用户只能添加、删除、启停、配置和在合法区间内排序。
- edge 由 `sequence` 推导，不持久化自由连线。
- 编译器检查节点顺序、数量、typed I/O、数据依赖和 lane compatibility。
- 非法顺序、端口不匹配、未知节点或未知版本均 fail closed。

### 6.3 NodeDescriptor

```text
node_type
version
category
display_name
input_contract
output_contract
config_schema
default_config
required_datasets
capability_tags
supported_strategy_kinds
deterministic
implementation_key
executor_contract_version
origin = builtin
```

持久化身份为 `node_type@version`；显示名和 UI metadata 不参与执行身份。
R3 只注册内置节点。未来扩展可以沿用 descriptor 契约，但 R3 不实现动态发现、
任意 import、代码编辑器或 custom executor。

未知 descriptor 在 UI 中允许只读查看原始配置，但不能保存、创建实验或晋级。

### 6.4 Typed parameter binding

当前 `parameter_overrides` 主要进入配置和 manifest，尚未形成明确的
StrategySpec runtime binding。R3 W0 必须先关闭这一缺口：

- 参数只能引用 `parameter_schema` 中注册的 JSON path；
- 检查类型、范围、枚举和节点版本；
- 应用参数后生成 resolved spec 和 parameter hash；
- 未知参数或错误类型不得忽略；
- runtime、manifest、API 和 UI 必须显示同一最终值；
- baseline 也必须展开为显式 candidate。

## 7. 核心因子目录与解释

Ditto 已有 119+ 因子规格，R3 不重建大型因子库，而是冻结一个可认证、可解释、
适用于双黄金路径的核心目录。建议首批 12 个稳定 ID 为：

| 类别 | 稳定 factor ID | 说明 |
|---|---|---|
| 动量 | `momentum_1m`、`momentum_3m` | 20/60 日价格动量 |
| 反转 | `reversal_1w` | 5 日短期反转 |
| 波动 | `volatility_factor`、`vol_ratio` | 低波和短长波动比 |
| 流动性 | `liquidity` | 日均成交金额横截面排名 |
| 相对强弱 | `relative_strength_60d` | 相对预注册 benchmark 的 60 日强弱；若无等价实现则为唯一新增核心因子 |
| 估值 | `ep_ttm`、`bp_ratio` | TTM 盈利收益率和账面市值比 |
| 质量 | `quality_roe` | PIT ROE |
| 成长 | `revenue_growth` | 同比收入成长 |
| 规模 | `log_free_float_cap` | 自由流通市值对数 |

个股路径可以使用全部核心因子；ETF 只允许动量、反转、波动、流动性和相对强弱。
基本面因子必须按公告日、known-at 和 knowledge lag 做 PIT 对齐。数据未认证或
历史不足时节点 unavailable/blocked，不得使用当前值回填。

标准预处理顺序：

```text
PIT alignment
  → coverage validation
  → missing-value policy
  → cross-sectional winsorization
  → industry/size neutralization
  → standardization
  → weighted scoring
```

每一步都是注册配置并进入 spec hash；规模因子本身不做规模中性化。

强制诊断包括 coverage、missingness、IC/ICIR、decay、quantile return、单调性、
turnover、cost drag、fold stability、factor contribution、industry/style exposure
和参数邻域稳定性。

每个再平衡日保存：

- 初始 `UniverseSnapshot`；
- 每级 `ExclusionEvent` 及稳定 reason code；
- factor raw/processed value、weight 和 contribution；
- score、rank 和 selected/not-selected 结果；
- 行业、规模和风格暴露摘要。

## 8. 实验与验证协议

### 8.1 96 月晋级协议

设最后一个 certified 完整月为 `T`：

```text
探索期：strategy-eligible start → T-36m，至少 60 个完整月
WF Fold 1：T-36m → T-24m
WF Fold 2：T-24m → T-12m
Sealed Holdout：T-12m → T
```

- Fold 1 使用此前全部探索数据训练/选择，在第一个 12 月窗口验证。
- Fold 2 扩展训练到 Fold 1 结束，在第二个 12 月窗口验证。
- 两个 walk-forward fold 完成后，人工预选唯一候选。
- 最后才允许打开最近 12 个月 holdout。

策略可用起点为所有 required dataset certified start、真实最大 lookback/warmup
和证券上市日的最大值。跨截面策略中每个标的独立计算上市日和 warmup eligibility；
计入月份还必须满足预注册 Universe coverage policy。

不足 96 个完整 strategy-eligible 月时：

- 允许创建 research-only experiment；
- 明确显示不足原因；
- 不能进入 review；
- 不能消费 holdout；
- 不能发布。

### 8.2 Purge 与 embargo

每个 split 边界的隔离宽度根据以下时间语义动态编译：

- 最大 forward-return horizon；
- 最大计划持有期；
- execution lag。

编译结果以交易日固化到 fold spec，并检查标签跨界、持仓跨界、窗口重叠和
warmup 污染；任一泄漏直接 hard fail。

### 8.3 一次性 holdout

运行前原子写入 `HoldoutClaim`：

```text
research_cycle_id
experiment_id
candidate_id
snapshot_id
window_start / window_end
logical_run_id
operator_confirmation
claimed_at
```

- 同一 research cycle 只能选择一个 candidate。
- clone、改名或修改参数不能重置 holdout。
- 基础设施失败只能恢复同一 logical run、同一候选、参数和输入。
- holdout 表现不佳后不能更换候选再试。
- 新 research cycle 需要更晚的数据截止点和新增 OOS 数据。
- 历史试验和 holdout 结果继续进入 multiple-testing ledger。
- 精确 deterministic replay 不计为第二次研究试验。

### 8.4 参数与资源预算

- 只允许显式值列表和笛卡尔积。
- 包括 baseline 在内最多 128 个可执行配置。
- 超过上限时 preflight 失败，禁止静默截断。
- 默认 2、最大 4 worker。
- 同一时刻只有一个 active experiment；paused 默认保留 slot。
- 其余实验按稳定 ordinal 排队。
- seed、worker limit、failure policy 和预算进入冻结 experiment spec。
- 每个 fold 完成后生成 checkpoint。
- pause 停止派发新 fold，并协作式结束当前 run。
- retry 创建新 attempt，不覆盖旧证据。

数据/schema/PIT/泄漏错误立即 fail-fast；候选局部数值错误可以隔离并形成
`completed_with_failures`。相同系统错误连续出现达到阈值时停止调度，默认阈值为 3。

### 8.5 状态机

Experiment lifecycle：

```text
draft → blocked | queued
queued → running
running → pause_requested → paused → queued
queued | running | paused → cancel_requested → cancelled
running → completed | completed_with_failures | failed
```

Experiment stage 独立表示 `preflight / exploration / walk_forward /
candidate_selection / holdout / evidence`。`blocked` 表示尚未启动且前置条件可修复；
`failed` 表示 attempt 已开始后失败，二者不得混用。

## 9. 两层研究门禁

### 9.1 硬正确性门禁

任一失败都不能提交 review：

- certified snapshot 和 strategy-eligible 历史；
- 96 月协议；
- PIT、known-at 和 knowledge lag；
- split 不重叠及 purge/embargo；
- spec/input/result 可复现；
- 成本、滑点和执行假设已声明；
- 参数矩阵、baseline 和全部试验已登记；
- multiple-testing declaration；
- holdout 未提前消费且只有一个 claim；
- evidence artifact 完整；
- G2 前 R2 live Gate 已关闭。

### 9.2 强制展示的统计与经济证据

- OOS 净收益及相对 baseline 表现；
- Sharpe、Calmar 和最大回撤；
- 两个 fold 的方向和稳定性；
- 参数邻域稳定性；
- 换手和成本拖累；
- 流动性与容量；
- IC、decay 和分层表现；
- 行业、规模和风格暴露；
- 不同市场阶段表现；
- 全部尝试次数和 trial family；
- Deflated Sharpe Ratio；
- 数据分区允许时的 PBO 诊断。

实验启动前冻结 `PromotionObjective`：primary objective、hard constraints、tie-break
顺序、baseline、economic rationale 和 trial family。人工依据预注册目标决策，
不能在看到 holdout 后改变主指标；R3 不设置单一 Sharpe 自动晋级阈值。

参考方法：

- [The Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
- [The Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2460551_code87814.pdf?abstractid=2460551)
- [Harvey, Liu and Zhu: ... and the Cross-Section of Expected Returns](https://www.nber.org/papers/w20592)

## 10. 策略治理与 active pointer

### 10.1 不可变版本

Strategy version payload 只允许 insert：

```text
strategy_id
version
parent_version
schema_version
spec_json
spec_hash
created_at
```

spec payload 不可修改；生命周期由 append-only event 和可重建 projection 表达。

### 10.2 Lifecycle 与 review outcome

```text
draft → review → published → deprecated
review_outcome = pending | approved | rejected
```

- draft 提交后进入 review。
- 被拒绝版本保留为 `review/rejected`，只能 clone 成新 draft。
- approved review 仍需显式 publish。
- 多个历史版本可以保持 published，但只能有一个 active pointer。
- 发布新版本不会自动 deprecate 旧版本。
- deprecated 是明确退役状态，禁止重新激活。

### 10.3 Publish 与 reactivate

Publish 事务必须：

1. 校验 review approved。
2. 校验 hard gates、holdout 和 evidence hash 未漂移。
3. append publish/activation event。
4. CAS 更新 lifecycle projection。
5. CAS 切换 active pointer。
6. 原子提交。

重新激活历史版本时：

- 目标必须是 published、非 deprecated；
- 必填原因和确认语句；
- 展示当前与目标 diff；
- CAS 切换 active pointer；
- 保留完整 activation event；
- 不删除或重写此前发布记录。

R1 Daily Decision 和 EOD 在任务开始时解析并锁定 active version，运行中的 pointer
变化不能影响已启动批次。review 是单用户 provenance，不是 RBAC 或安全审批。

## 11. 持久化、artifact 与复现

### 11.1 生产控制面

现有 metadata SQLite 增加：

- `strategy_version`
- `strategy_version_state`
- `strategy_decision_event`
- `strategy_active_pointer`
- `strategy_activation_event`

### 11.2 研究控制面

独立 research SQLite 增加：

- `experiment`
- `experiment_candidate`
- `experiment_fold`
- `experiment_attempt`
- `experiment_status_event`
- `gate_evaluation`
- `holdout_claim`
- `research_artifact`

### 11.3 大型 artifact

SQLite 只保存控制面、状态、identity、hash 和索引。NAV、交易、候选池、排除原因、
贡献和诊断使用 Parquet/JSON：

```text
research/experiments/{experiment_id}/
  manifest.json
  candidates/{candidate_id}/
    summary.json
    folds/{fold_id}/
      run_manifest.json
      nav.parquet
      trades.parquet
      selections.parquet
      exclusions.parquet
      factor_contributions.parquet
      diagnostics.json
```

写入临时文件后计算 SHA-256、schema fingerprint 和 row count，再原子 rename，
最后写 SQLite index。retry 使用新 attempt 路径，不覆盖旧 evidence；进入 review
或 published 的 evidence 永久 pin。

### 11.4 Manifest 与 reproduction fingerprint

每个 fold attempt 冻结：

- experiment/candidate/fold/attempt ID；
- strategy version 和 canonical spec hash；
- node registry manifest hash；
- parameter hash；
- research snapshot、manifest 和 source snapshot IDs；
- train/test/purge/embargo；
- factor IDs/versions；
- universe hash；
- code/environment lock；
- seed、cost、slippage 和 execution assumptions；
- PIT/known-at/knowledge lag；
- checkpoint/parent attempt；
- artifact hashes。

Audit manifest 可以包含 run ID 和时间；reproduction fingerprint 只包含决定结果的
语义字段。重放比较 fingerprint、关键结果摘要及 Parquet content hash，而不是要求
两个 attempt 的 audit manifest 字节相同。

### 11.5 Migration 与恢复

现有 draft/published rows 先生成 dry-run migration report：

- 将旧 spec 转换为 StrategySpec v2；
- 为历史记录生成 `legacy_import` event；
- 按当前 latest-published 结果生成 active-pointer 映射预览；
- 操作者确认后才写正式迁移；
- 迁移前备份 metadata DB；
- G2 对 metadata DB、research DB 和 artifacts 执行完整恢复演练。

数据库 schema 变更属于独立实施审批点，设计确认不等于授权直接执行迁移。

## 12. Application processes 与 API

### 12.1 Processes

- `ExperimentPlanningProcess`：schema、node、snapshot、历史、矩阵和预算 preflight。
- `ExperimentExecutionCoordinator`：lease、worker、fold dispatch、pause/cancel/recovery。
- `ResearchRuntimeBuilder`：从显式 immutable version 和 candidate 参数构建 runtime，禁止读取 active pointer。
- `WalkForwardValidationProcess`：fold aggregation、稳定性和 multiple-testing evidence。
- `ResearchEvidenceAssembler`：生成 immutable promotion bundle。
- `StrategyPromotionProcess`：验证 hard gates、holdout、人工确认和 evidence hash，再事务性发布。

研究 builder 与生产 `StrategyRuntimeBuilder` 必须是两个明确类型，禁止通过
`allow_unpublished=True` 之类布尔开关混用边界。

### 12.2 HTTP resources

```text
GET  /research/node-descriptors
GET  /research/factors
GET  /research/factors/{factor_id}/diagnostics

POST /strategies
POST /strategies/{strategy_id}/versions
GET  /strategies/{strategy_id}/versions
GET  /strategies/{strategy_id}/versions/{version}
GET  /strategies/{strategy_id}/versions/{version}/diff
POST /strategies/{strategy_id}/versions/{version}/validate
POST /strategies/{strategy_id}/versions/{version}/submit-review
POST /strategies/{strategy_id}/versions/{version}/review-decisions
POST /strategies/{strategy_id}/versions/{version}/publish
POST /strategies/{strategy_id}/versions/{version}/deprecate
GET  /strategies/{strategy_id}/active
POST /strategies/{strategy_id}/reactivate
GET  /strategies/{strategy_id}/events

POST /research/experiments
GET  /research/experiments
GET  /research/experiments/{experiment_id}
POST /research/experiments/{experiment_id}/preflight
POST /research/experiments/{experiment_id}/launch
POST /research/experiments/{experiment_id}/pause
POST /research/experiments/{experiment_id}/resume
POST /research/experiments/{experiment_id}/cancel
GET  /research/experiments/{experiment_id}/candidates
GET  /research/experiments/{experiment_id}/comparison
GET  /research/experiments/{experiment_id}/gates
GET  /research/experiments/{experiment_id}/report
GET  /research/experiments/{experiment_id}/artifacts
POST /research/experiments/{experiment_id}/folds/{fold_id}/retry
POST /research/experiments/{experiment_id}/candidate-selection
POST /research/experiments/{experiment_id}/holdout-evaluations

GET /research/candidates/{candidate_id}/selections
GET /research/candidates/{candidate_id}/exclusions
GET /research/candidates/{candidate_id}/factor-contributions
GET /research/reviews
GET /research/reviews/{review_id}
```

现有 `/backtests/runs/...` 继续作为单次底层运行资源，不创建平行的
`/research/backtest/...` 契约。

所有 mutation 支持 `Idempotency-Key` 和 `expected_revision`/ETag，返回 request ID、
规范化对象、hash 和 evidence event ID。409 表示状态/pointer 冲突，422 表示 schema、
协议、参数或门禁错误。前端通过 polling 获取本机运行进度，R3 不引入 WebSocket/SSE。

稳定错误码至少包括：

```text
SPEC_INVALID
UNKNOWN_NODE
NODE_TYPE_MISMATCH
MATRIX_TOO_LARGE
BUDGET_EXCEEDED
SNAPSHOT_NOT_CERTIFIED
INSUFFICIENT_HISTORY
WINDOW_LEAKAGE
HOLDOUT_ALREADY_CLAIMED
CHECKPOINT_INVALID
ARTIFACT_WRITE_FAILED
REPRODUCIBILITY_FAILED
HARD_GATE_FAILED
REVIEW_NOT_APPROVED
EVIDENCE_STALE
ACTIVE_POINTER_CONFLICT
```

## 13. 前端工作台

R3 前端收束成 `Strategy Studio → Experiment → Review → Publish / Reactivate`，
不再增加互不连通的原型页。

### 13.1 信息架构

```text
/research
/research/strategies
/research/strategies/$id/studio
/research/experiments
/research/experiments/new
/research/experiments/$id
/research/reviews
/research/reviews/$id
/research/factors
/research/backtests/$runId
```

### 13.2 Strategy Studio

复用现有三栏 `StudioLayout`：

- 顶部：策略名称、黄金路径、base version、dirty 状态、certified snapshot、strategy-eligible start 和 R2 Gate；
- 左栏：Node/Factor Catalog；
- 中栏：有序 typed pipeline；
- 右栏：schema-driven Inspector；
- 底部：校验、数据依赖和日志。

编辑模式只有“表单”和“流水线”，删除现有 Code Editor。表单字段和节点错误共享
同一个 JSON path；保存生成新的 immutable draft version，不覆盖历史版本。

PandaAI 只作为模块化搭建、模板和参数面板的交互参考，不照搬其视觉皮肤，
也不引入开放代码执行：

- [PandaAI](https://www.pandaaiquant.com/)
- [PandaAI 模块化节点说明](https://www.pandaai.online/community/article/910)

### 13.3 Experiment 工作台

创建实验使用独立任务页，依次固定 StrategySpec version、certified snapshot、
PromotionObjective、baseline、参数矩阵、96 月协议、成本、seed、worker 和失败策略，
最后执行 preflight 并确认排队。

详情包含 Summary、Candidates、Validation、Candidate Selection、Holdout、Evidence
和 Artifacts/Lineage。候选比较最多同时 pin 4 个，但表格保留全部候选和 baseline。

### 13.4 Review 工作台

详情按以下顺序展示：

1. Decision Banner；
2. 硬门禁；
3. 强制统计证据；
4. StrategySpec diff；
5. candidate selection rationale；
6. lineage/artifact；
7. R1 影响范围；
8. append-only decision 表单。

Review approval、publish 和 reactivate 是三个明确动作。publish/reactivate 不提供危险
快捷键；确认 Dialog 必须展示影响摘要和 required confirmation。

### 13.5 状态、响应式与无障碍

必须覆盖 loading skeleton、empty、stale、offline/503、404、409、422、unknown
descriptor、holdout consumed、partial artifact、failed/cancelled/resumable 和刷新恢复。

所有拖拽必须有按钮和键盘等价路径；窄屏默认表单和有序节点列表，不依赖无限画布。
视觉继续遵循 Graphite Studio：高信息密度、低噪声、研究域紫色语义，不使用 SaaS
卡片墙或 AI chat 式编辑器。

默认不引入大型图编辑依赖；若需要第三方 graph/DnD 库，必须单独获得依赖审批。

## 14. 失败与恢复语义

| 场景 | 处理 |
|---|---|
| 数据未认证、历史不足 | `blocked`，不消耗实验预算 |
| schema、节点、参数错误 | preflight 422，不能排队 |
| 泄漏或 split 错误 | hard fail，不能 review |
| 单 candidate 数值失败 | 隔离失败，其他候选继续 |
| 重复系统错误 | fail-fast，停止派发新任务 |
| pause | 停止新 fold，当前 run checkpoint 后退出 |
| resume | 从同一冻结输入和 checkpoint 新建 attempt |
| cancel | 保留已有 evidence，不自动恢复 |
| artifact 不完整 | 标记 partial，禁止 review |
| holdout 已 claim | 409，并返回原消费记录 |
| active pointer 冲突 | 409，重新加载版本 diff |
| unknown descriptor | 只读，禁止执行和晋级 |
| 前端失联 | 停止伪造进度，以服务端状态恢复 |

## 15. 实施波次与投入

| 波次 | 主要工作 | Exit Gate | 估算 |
|---|---|---|---:|
| W0 契约与基座 | StrategySpec v2、NodeDescriptor、canonical hash、typed parameter binding、OpenAPI 和迁移设计 | override 真正影响 runtime；未知节点 fail closed；旧 seed 可转换 | 2 人周 |
| W1 策略与因子 | constrained compiler、核心因子目录、预处理和选择解释 | 双黄金 StrategySpec 可编译；个股输出解释证据 | 3–4 人周 |
| W2 实验控制面 | experiment schema、candidate expansion、scheduler lease、2–4 worker、pause/cancel/retry/resume | 128 配置 preflight；重启不重复 claim；checkpoint 可恢复 | 4–5 人周 |
| W3 验证与 evidence | 96 月协议、walk-forward、统计证据、artifact index 和 holdout ledger | 第二候选 holdout 被拒绝；硬门禁失败不能 review | 4–6 人周 |
| W4 策略治理 | immutable version、review、publish、active pointer、reactivate 和 R1 集成 | R1/EOD 只读取 active pointer；所有动作 append-only | 3–4 人周 |
| W5 真实前端与 G2 | Studio、Experiment、Review、双黄金真实 API、恢复和 release evidence | `VITE_USE_MOCK=false` 双线闭环；R2 live Gate 与 G2 evidence 关闭 | 3–5 人周 |

总投入为 **19–26 人周**。两名全职贡献者并行时约 10–14 个日历周；单人顺序
实施接近 person-week 总量。真实数据权限和供应商等待不计入估算。

## 16. G2 Definition of Done

1. R2 live data Gate 已关闭。
2. 两条黄金路径均使用真实 certified、strategy-eligible 数据。
3. 可晋级实验至少覆盖 96 个完整月。
4. StrategySpec 使用完整 canonical hash。
5. typed parameter override 确实改变 runtime、manifest 和结果。
6. 128 candidate、2/4 worker 和单 active experiment 由服务端强制。
7. 相同 environment/spec/registry/snapshot/params/seed/cost 可确定性重放。
8. PIT、split integrity 和 purge/embargo 无泄漏。
9. holdout 只允许预选候选消费一次。
10. 个股路径提供候选池、排除原因、factor contribution 和行业/规模暴露。
11. ETF 路径与 R1 当前语义一致，并能发布后重新激活旧版本。
12. 硬门禁失败无法 submit review 或 publish。
13. UI 不把软统计证据包装成自动通过。
14. active pointer 切换原子且 R1/EOD 每批锁定版本。
15. 服务重启后 experiment、checkpoint、decision 和 holdout claim 可恢复。
16. metadata、research DB 和 artifacts 通过备份恢复演练。
17. `VITE_USE_MOCK=false` 下全流程无 MSW、hardcoded row 或 prototype-only 空态。
18. OpenAPI 重新生成后零未提交 diff。
19. 后端通过 `pixi run -e dev check`。
20. 前端通过 `bun run check` 和 `bun run build`。
21. 真实浏览器 acceptance 生成可审计 artifact。
22. 128 个轻量候选通过 scheduler 压力与故障恢复测试。
23. 两条黄金路径各保留完整 release evidence bundle。

## 17. 风险与控制

| 风险 | 控制 |
|---|---|
| R2 live evidence 拖延 | 与 W0–W4 并行，但阻断 G2 |
| 完整闭环范围膨胀 | 按 W0–W5 Exit Gate 形成垂直提交 |
| 回测过拟合 | 预注册目标、trial ledger、walk-forward、一次性 holdout、调整后统计 |
| 本机资源失控 | 128 上限、单实验、2/4 worker、预算 preflight |
| retry 污染 evidence | 每次 retry 新 attempt，旧 evidence 不覆盖 |
| 解释明细过大 | SQLite 控制面、Parquet 明细和 artifact index |
| 历史策略迁移错误 | dry-run mapping、备份和显式 operator confirmation |
| Builder 演化成自由 DAG | 固定阶段、自动 edge、registry fail closed |
| 未来节点破坏复现 | `node_type@version`、registry hash 和旧 descriptor 保留 |
| Review 被误解为权限系统 | 明确单用户 provenance，不宣称 RBAC |

## 18. 实施审批点

以下事项必须在对应实施 task 开始前获得单独人工批准：

1. metadata/research SQLite schema 和迁移执行。
2. 新增前端 graph/DnD 或其他第三方依赖。
3. 修改 import-linter 或既有架构边界。
4. 修改 CI/CD 或环境配置。

设计确认授权创建本设计和实施计划，不自动授权上述变更。
