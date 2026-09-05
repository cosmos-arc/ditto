# Ditto 生产上线就绪度评估报告

> 评估日期: 2026-06-14
> 评估对象: ditto 后端(monorepo,当前分支 `dev/architecture-remediation-batch2-6`)
> 评估方法: 基于源码核查(非文档转述),4 个维度并行深度探索 + 关键断链源码确认
> 评估目标: 判断系统作为「个股 + ETF + 宏观数据,日频维度量化 + 个股分析 + 优秀选股能力」整体功能上线的差距
> 配套文档: `docs/plans/2026-06-14-production-launch-roadmap.md`(上线路线图与修复方案)
> 范围声明: 前端由独立团队(`ditto-app`)承担,本评估只覆盖后端系统功能;真实券商接入不在当前范围。

---

## 执行摘要

### 核心判断

Ditto 是一个**工程质量已收敛到 4.4–4.9★ 的强骨架平台**,在架构边界、类型安全、测试纪律上已优于多数同类。但作为「上线即可用的量化选股产品」,当前存在**工作重心与上线目标的错配**:

- 过去数月的主力投入集中在 **execution reconciliation / broker-event conformance 矩阵**(`capability-maturity.md` 中 30+ 条 addendum 均在此线),与"个股/ETF/宏观 日频量化 + 选股"上线目标**贡献度低**。
- `docs/reviews/2026-06-04-quality-eval.md` 自身的 convergence recommendation 已承认"工程质量进入收益递减区,应转为缺陷驱动"。
- **真正阻断上线的是产品功能断链,而非工程质量**——最致命的一条:基本面数据(PE/PB/ROE)根本没有接入回测链路,导致 26 个基本面因子和"个股选股"场景在回测中直接 `ColumnNotFoundError`。

**结论:ETF 日频链路可立即上线;个股选股链路存在硬断链,需先解阻才能上线。**

### 成熟度雷达(基于用户目标维度)

| 维度 | manifest 自评 | 源码核查 | 上线就绪 |
|---|---|---|---|
| ETF 日频(行情/回测/成本/T+1) | initial-focus | 完整,可直接实战 | ✅ 可上线 |
| 个股(行情/元数据) | experimental | 链路接通,需 promotion 解锁 | 🟡 工程 OK,流程未走 |
| 宏观数据 | experimental | Tushare(47)+FRED(25)真实接通 | 🟡 FRED 非 PIT |
| 日频量化(ETF 全链路) | initial-focus | 回测+成本+涨跌停+T+1 齐全 | ✅ 可上线 |
| **个股选股** | experimental | **框架在但端到端断链** | ❌ **阻断** |
| 个股分析(归因) | reserved/experimental | analysis 包仅 control-plane | ❌ 缺失 |
| 组合优化 | experimental | **完全无优化器** | ❌ 缺失 |
| 风控(机构级) | experimental | Pre/Post 完整,无 VaR | 🟡 个人级 OK |
| 端到端联通 | — | 有 golden lane,**但不在 CI** | 🟡 高风险 |
| 工程质量 | — | 4.4–4.9★,8257 测试全绿 | ✅ 远超门槛 |

### 三条最关键结论

1. **ETF 是当前唯一可立即上线的产品形态。** 数据、回测、成本建模、A 股成交规则、golden E2E 全齐。
2. **个股选股被一条数据断链卡死。** `build_input_bundle` 只注入 OHLCV,基本面因子无数据来源。这是 P0 阻断,修复成本不高(详见路线图 Phase 0)。
3. **端到端联通的回归保护是空的。** golden E2E committed 但被排除出 CI 门禁。上线前必须纳入。

---

## 一、关键诊断:工作重心与上线目标的错配

这是本次评估最重要的洞察。

**过去的工作产出(从 capability-maturity.md / quality-eval.md 的 addendum 序列统计):**

| 工作方向 | addendum 条数(近 1 个月) | 对"选股上线"目标的贡献 |
|---|---|---|
| execution reconciliation / broker callback 矩阵 | ~30 条 | 极低(实盘/对账才需要,日频选股回测不需要) |
| catalog source-fallback / remediation 治理 | ~20 条 | 中(数据治理,但个股 promotion 还没走) |
| promotion / maturity governance | ~10 条 | 中(机制有了,但没用它晋级个股数据) |
| 回测 checkpoint / replay proof | ~8 条 | 中(复现性,ETF 回测受益) |
| **基本面接入回测** | **0** | **——而这正是选股的命脉** |
| **组合优化器** | **0** | **——而这正是"优秀选股"的落点** |
| **归因分析** | **0** | **——而这正是"个股分析"的核心** |

**quality-eval.md(2026-06-14)的收敛口径原文:**

> 当前后端工程质量与代码架构整改已经进入收益递减区间……后续应从"持续攻坚"切换为"高信号验收/缺陷驱动"。

**这意味着:** 继续在 execution/broker 矩阵上投入是负收益。要让系统真正上线,必须把精力转移到**基本面接入、组合优化、归因、个股数据 promotion、CI golden 门禁**这五件事上——它们才是阻断产品价值的真正瓶颈。

---

## 二、阻断性差距(P0)— 已通过源码确认

### P0-#1 基本面数据未注入回测链路 ⛔

**这是"个股选股"目标上线的硬阻断。**

#### 证据

1. [input_bundle.py:60-91](packages/backtest/src/ditto_backtest/steps/input_bundle.py#L60) 的 `build_input_bundle`,market_data 只注入 `open/high/low/close/volume`,signal 只注入一个 `signal_value`(单日收益率 `(close/prev_close - 1)`)。**无任何 fundamentals 列。**

2. [factor_bridge.py](packages/application/src/ditto_application/processes/execution/factor_bridge.py) 的 `build_factor_bundle` 同样只读 OHLCV + 历史 OHLCV 窗口。`grep "fundamentals"` 零命中。

3. [seeds.py:154-155](packages/strategy/src/ditto_strategy/alpha/seeds.py#L154) 的个股选股 seed 声明:
   ```python
   signal_expressions=("quality_roe", "value_pe", "momentum_1m"),
   signal_weights=(0.4, 0.3, 0.3),
   ```
   其中 `quality_roe`、`value_pe` 是基本面因子别名(展开后依赖 `roe`、`pe_ratio` 列)。**回测时这些列不存在 → `FactorBridge.compute_signals` 执行 `df.with_columns([compiled_expr])` 时 polars 抛 `ColumnNotFoundError`。**

4. **对照组证据**:同文件 [seeds.py:63](packages/strategy/src/ditto_strategy/alpha/seeds.py#L63) 的 ETF seed 用 `signal_expressions=("momentum_1m","reversal_1w","volatility_factor")`——全是技术/动量因子,可纯靠 OHLCV 计算,所以能跑。这精确解释了"ETF 通、个股选股断"的现象。

#### 根因

不是数据层的问题——[fundamental_store.py:44-78](packages/data/src/ditto_data/services/fundamental_store.py#L44) 的 PIT 查询已实现,三大报表 + 分红 + 公司行为全 PIT 化存储(schema.sql 有 `effective_from/effective_to/knowledge_date` 三列 + PIT 索引)。**问题在 application 编排层**:没有人在回测路径里调用 `FundamentalStore` 把基本面列注入到 `StrategyInputBundle`。

#### 影响范围

- 26 个基本面因子(PE/PB/ROE/ROA/营收增长/利润增长/股息率/EV-EBITDA 等)在回测中**全部不可用**。
- 价值、质量、成长三类选股逻辑**全部失效**——而这正是"优秀选股"的核心 alpha 来源。
- 财务 PIT 防未来函数的语义对基本面因子无法生效(PIT 存储层有,但回测没接)。

### P0-#2 Golden E2E 不在 CI 自动门禁 ⛔

**这是上线后最大的工程风险:端到端联通一旦回归,CI 不会发现。**

#### 证据

1. [ci.yml](.github/workflows/ci.yml) 所有 job:
   - `audit` job 跑 `pixi run -e dev test --fast`(line 81)——跳过慢速;
   - `test-unit` job 只跑 `packages/*/tests/unit/`(line 149)——不跑 integration;
   - 无任何 job 跑 golden integration。

2. [ci-integration.yml:8-17](.github/workflows/ci-integration.yml#L8) 触发器:
   ```yaml
   on:
     workflow_dispatch:        # 仅手动
     # schedule: ...           # 注释掉 "Disabled to save CI minutes"
     # workflow_run: ...        # 注释掉 "Disabled to save CI minutes"
   ```

3. golden lane 本身**真实存在且 committed**:[test_golden_e2e.py](apps/backend/tests/integration/test_golden_e2e.py)(5 tests,验证合成数据→策略→组合→风控→执行→报告全链路),已通过实测。`capability-maturity.md:71` "needs one committed synthetic golden lane" 的描述**已过时**。

#### 影响

- committed 的 golden E2E 一旦回归(如重构 EngineLoop、改 DecisionFrame schema、调 fill 模型),PR/merge 到 main 都不会发现。
- 这是"工程质量 4.4★ 但上线没保障"的根因——单测覆盖率再高,也覆盖不了跨包联通。

### P0-#3 capability-maturity.md 自相矛盾

[capability-maturity.md:71](docs/architecture/capability-maturity.md#L71) 称 E2E "needs one committed synthetic golden lane",而 [第 80 行](docs/architecture/capability-maturity.md#L80) 的 Backtest 行又声称已有 checkpoint/resume/replay golden E2E proof。**文档与代码、文档内部均不一致**,会误导所有评估者(包括前端团队、新成员)。需同步。

---

## 三、重要差距(P1)— 影响产品价值完整性

### P1-#1 宏观数据不是真正的 PIT

[fred/client.py:93-126](packages/data/src/ditto_data/sources/fred/client.py#L93) 的 `FredClient` 支持 ALFRED realtime(`realtime_start/realtime_end`),但 [fred/adapters/macro.py:71-75](packages/data/src/ditto_data/sources/fred/adapters/macro.py#L71) 的 adapter **从不传递这些参数**,直接用 `knowledge_date = observation date`——adapter 源码自己承认此局限。后果:FRED 宏观数据对修正/重述无感知,不是真正的 PIT。Tushare 宏观的 `release_lag_days` 也只是估算常数而非真实公告日。

### P1-#2 单源无 fallback

Tushare 是唯一在线源;TDX 仅本地文件质量对账,非热备份。AKShare/东财**完全不存在代码**(grep 全仓零命中)。catalog 的 source-fallback-policy 框架已搭好,但**无第二真实源可切**。Tushare 故障或积分受限即全线停摆。

### P1-#3 个股/宏观数据 promotion 流程未走完

[catalog.promotion](packages/data/src/ditto_data/catalog/promotion/) 的 evidence/assessment/history/revoke 全套机制已实现,promotion readiness / maturity governance API 也齐备。**但没有任何一个 stock/macro 数据集真正提交过 promotion evidence**,所以它们仍默认 fail-closed。需"提交证据 → 评审 → 自动晋级"走一遍,才能在 FastAPI/回测默认放行。

### P1-#4 组合优化器完全缺失

grep 全 portfolio 包零命中 `mean_variance` / `risk_parity` / `Black-Litterman` / `min_variance` / `cvxpy` / `scipy.optimize`。只有 [allocation.py](packages/portfolio/src/ditto_portfolio/rebalancing/allocation.py) 的启发式 allocator(EqualWeight/InverseVol/ScoreWeight)。`target_portfolios/` 是 reserved 目录(PORT-P1-02 未完成)。**"优秀选股"无法落到"科学化组合构建"**,只能做规则化打分加权。

> 注:用户选股目标定位为"规则化多因子打分选股",此 P1 非阻断,但影响"优秀"程度。路线图 Phase 2+ 可选。

### P1-#5 选股策略只有最简融合

[stock_selection_trend_stages.py](packages/strategy/src/ditto_strategy/alpha/templates/stock_selection_trend_stages.py) 的 `MultiFactorSignalStage` 仅 `rank(method="average") + 加权求和` 一种融合。缺失:

- 因子预处理(winsorize 去极值 / zscore 标准化)——表达式引擎有 `cs_winsorize`/`cs_zscore`,但 stage 没调用;
- 因子中性化(行业/市值中性)——[orthogonalization.py](packages/features/src/ditto_features/evaluation/orthogonalization.py) 有,但模板没用;
- [CompositeDecisionStage](packages/strategy/src/ditto_strategy/alpha/builtins/composite.py#L99)(Score Fusion + Rank Normalization)**实现了完整逻辑但没接入任何模板**。

### P1-#6 因子 IC 评估与选股策略未闭环

[features/evaluation/metrics/ic.py](packages/features/src/ditto_features/evaluation/metrics/ic.py) 有完整 IC 评估(rank_ic/IC_decay/regime_adjusted_ic/Fama-MacBeth),但这是**独立工具**,策略模板不消费它来选因子或调权重。缺少"因子 IC 报告 → 推荐因子组合 → 生成选股策略"的工作流。

### P1-#7 无内置行业分类数据

`stock_sector_rotation` 模板要求输入携带 `is_sector`/`sector_id` 列(stage 有 fail-closed 校验),但**没有内置行业分类数据 provider**(申万行业),上游必须自己注入。行业内选股、行业中性化都受制于此。

---

## 四、体验与机构级差距(P2)

| # | 差距 | 证据 | 影响 |
|---|---|---|---|
| P2-#1 | 回测无 intraday 粒度 | EngineLoop 由 BacktestSynchronizer 日级步进 | 无法回测日内/VWAP/TWAP;ETF/选股已够 |
| P2-#2 | HTML 报告无图表 | report_renderer 纯表格 | 对比 LEAN tearsheet/聚宽 plotly,体验差 |
| P2-#3 | 归因缺失 | analysis 包仅 control-plane;无 Brinson/风险分解 | 无法回答"钱从哪赚、哪个因子贡献 alpha" |
| P2-#4 | 风控无 VaR/CVaR/压力测试 | grep 零命中 | 机构级合规不足(个人级 OK) |
| P2-#5 | 连续 RiskGate 未实现 | RISK-P1-01 open | paper/实盘缺持续风控监测 |
| P2-#6 | 因子库 spec 占位 | volatility/KDJ 等 `computation_type="python"` 且 `expression=""` | 7+ 个因子定义了没实现 |
| P2-#7 | fundamental spec/DDL 漂移 | specs.py 窄投影 vs DDL 16 列 | latent bug(主路径不走 spec,但复用基类会丢字段) |
| P2-#8 | 限流器单机 | rate_limiter 用 MemoryStorage | 多 worker 并发摄取触发 Tushare 封禁 |
| P2-#9 | Parquet 单年分区 | 按 year 单维分区 | 全市场 5000+ 标的回测 IO 放大 |
| P2-#10 | 无 materialize CLI | DerivedMaterializationOrchestrator 仅内部调用 | 运维无法手动触发特征物化 |
| P2-#11 | paper_trading 薄弱 | paper_trading_process.py 仅 49 行 | 模拟盘链路成熟度远低于回测 |

---

## 五、分域详细评估(基于源码核查)

### 5.1 数据层 — 工程骨架完整,个别域 experimental

**数据源适配器真实落地:**

| 数据源 | 个股 | ETF | 宏观 | 结论 |
|---|---|---|---|---|
| Tushare | ✅ 完整 | ✅ 完整 | ✅ 完整(47 指标) | 真实接通(分页/限流/重试齐全) |
| FRED | — | — | ✅ 完整(25 指标) | 真实接通(PIT 受限) |
| TDX | ✅ 本地文件 | — | — | 仅质量对账 |
| AKShare/东财 | ❌ 不存在 | ❌ | ❌ | 代码零命中 |

**存储层:** 行情走 Parquet(单年分区),元数据/基本面/宏观/资金走 SQLite,全部带 `knowledge_date`/`effective_from`/`effective_to` PIT 三列 + 索引。DuckDB SQL 引擎统一 attach 跨源查询。

**摄取链路:** [dataset_registry.py](packages/application/src/ditto_application/processes/ingestion/dataset_registry.py) 注册全部 16 个数据集路由(不只 ETF),IngestionCoordinator 三个入口端到端跑通。

**数据质量:** L1-L4 四层校验引擎真实实现,L4 跨源(Tushare vs TDX)对账。

**评级:** ETF = 完整实现;个股/宏观/基本面/资金 = 部分实现(链路通但 experimental、PIT 个别缺口、单源无 fallback)。

### 5.2 选股与 alpha 能力 — 框架强,内容物断链

**强项:**

- 因子表达式引擎业界级([registry.py](packages/features/src/ditto_features/expression/registry.py)):lexer+parser+compiler,49 个算子(时序 + 截面齐全),用户可自定义因子。
- StrategyPipeline 无状态编排,[validate_frame](packages/strategy/src/ditto_strategy/alpha/frame.py) 在每个 stage 边界校验 DecisionFrame schema。
- CompositeDecisionStage(Score Fusion + Rank Normalization)实现完整,是业界标准做法。

**断链:**

- 基本面因子在回测中无数据来源(P0-#1)——详见上文。
- 多因子融合只有 rank+加权求和(P1-#5)。
- 因子 IC 评估与选股未闭环(P1-#6)。
- 因子库 101 个 FactorSpec,但 volatility/KDJ/SuperTrend/OBV 等 7+ 个是 `computation_type="python"` 且 `expression=""` 占位(P2-#6)。

**评级:** 框架质量高(可直接用于 ETF 动量实战);个股选股端到端断链(需先解阻基本面接入)。

### 5.3 回测引擎 — 偏齐全

**已实现:** Sharpe/Sortino/Calmar/MaxDD/胜率/盈亏比/换手率([statistics_returns.py](packages/backtest/src/ditto_backtest/statistics_returns.py) / [statistics_alpha.py](packages/backtest/src/ditto_backtest/statistics_alpha.py) / [statistics_trades.py](packages/backtest/src/ditto_backtest/statistics_trades.py));基准 alpha/beta/tracking_error/information_ratio;A 股成本全套([AShareFeeModel](packages/execution/src/ditto_execution/reality/fee.py#L52) 佣金+印花税+过户费);涨跌停/停牌/T+1 全套([AShareFillModel](packages/backtest/src/ditto_backtest/simulation/fill.py#L123) / [AShareSettlementModel](packages/backtest/src/ditto_backtest/simulation/settlement.py#L75) / [BacktestBrokerage T+1 冻结](packages/backtest/src/ditto_backtest/simulation/brokerage.py#L157));滑点模型;HTML 报告导出;checkpoint + replay proof 可复现性。

**缺失:** intraday 粒度(P2-#1);报告无图表(P2-#2)。

**评级:** 部分实现偏齐,ETF 日频场景足够。

### 5.4 分析能力 — 仅骨架

[analysis](packages/analysis/src/ditto_analysis/) 包只实现 research control-plane(数据集 catalog/spine/artifact spec + 持久化 Protocol)。`experiments/` 是 reserved(`__all__=[]`)。归因/因子分析分散在 features 包且是简化版([attribution.py](packages/features/src/ditto_features/evaluation/metrics/attribution.py) 的 `interaction=0.0` 占位)。无 Brinson 行业归因、无组合收益归因到因子贡献、无风险分解。

**评级:** 仅骨架(control-plane only)。

### 5.5 组合管理 — allocator 齐全,优化器缺失

**已实现:** 权重分配器(EqualWeight/InverseVol/ScoreWeight)、约束检查器(MaxWeight/MinWeight/MaxPositions)、会计核算(Account/Position/CashBook/BuyingPower)、组合对比、状态投影。

**缺失:** 完全无组合优化器(P1-#4);target_portfolios/events 是 reserved。

**评级:** 部分实现。

### 5.6 风控 — Pre/Post 完整,连续风控与 VaR 缺失

**已实现:** 事前 6 规则(NoShortSell/PriceValidity 涨跌停/LotSize 100 股整数倍/BuyingPower/DailyTurnoverPreCheck 30%/ConcentrationPreCheck)+ CompositePreTradeCheck resize 重检;事后 4 规则(ConcentrationLimit 20%/MarketAnomaly 5%/MaxDrawdown warning10%-emergency20% 有状态/SingleLossLimit 15%);A 股特有 T+1/涨跌停/停牌;KillSwitch 三级熔断数据结构。

**缺失:** 连续 RiskGate 未实现(RISK-P1-01);无 VaR/CVaR/ES/压力测试/行业集中度;KillSwitch 无触发引擎。

**评级:** 部分实现(个人级 OK,机构级不足)。

---

## 六、业界最佳系统对比

| 能力 | ditto | QuantConnect LEAN | 米筐 Ricequant | 聚宽 JoinQuant |
|---|---|---|---|---|
| 架构/工程质量 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| ETF 日频回测 | ✅ | ✅ | ✅ | ✅ |
| 基本面因子入回测 | ❌ **断链** | ✅ get_fundamentals | ✅ | ✅ |
| 财务 PIT 回测 | 🟡 存储有,回测没接 | ✅ announcement-time | ✅ 核心卖点 | ✅ 核心卖点 |
| 组合优化器 | ❌ **无** | ✅ PortfolioOptimizer | ✅ | ✅ |
| Brinson/风险归因 | ❌ | ✅ | ✅ | ✅ |
| 行业分类数据 | ❌ 需上游注入 | ✅ 内置 | ✅ 申万 | ✅ 申万 |
| 数据源冗余 | ❌ 单源 | ✅ 多源 | ✅ | ✅ |
| intraday 回测 | ❌ | ✅ tick/秒 | ✅ 分钟 | ✅ 分钟 |
| 真实券商接入 | reserved | ✅ | ✅ | ✅ |
| 端到端 CI 门禁 | ❌ golden 不在 CI | ✅ | ✅ | — |

**判断:** ditto 在架构与工程上已优于多数同类,但在「选股产品的端到端可用性」上落后于米筐/聚宽——核心差距不在工程质量,而在**基本面数据接入、组合优化、归因、行业数据、CI 门禁**这些"内容物"与"上线保障"。

---

## 七、结论与建议

### 上线就绪度分层

| 产品形态 | 就绪度 | 阻断项 |
|---|---|---|
| **ETF 日频量化(轮动/趋势)** | ✅ 可立即上线 | 无 |
| **个股日频行情/元数据查询** | 🟡 工程就绪 | 走完 promotion 流程 |
| **个股选股(多因子打分)** | ❌ 阻断 | P0-#1 基本面接入、P1-#5 融合增强 |
| **宏观日频量化** | 🟡 工程就绪 | FRED PIT、promotion |
| **个股分析(归因)** | ❌ 缺失 | P2-#3 归因 |

### 核心建议

1. **立即停止 execution/broker 矩阵的主动扩展**(已进入负收益区)。
2. **把精力转向 5 件阻断产品价值的事**:基本面接入回测、CI golden 门禁、个股数据 promotion、选股融合增强、归因(可选)。
3. **ETF 链路可立即作为首个上线产品形态**,个股选股作为第二阶段(解阻 P0 后)。

### 下一步

详细的分阶段修复方案、选股能力深化设计、端到端验证计划见配套文档:

→ [docs/plans/2026-06-14-production-launch-roadmap.md](../plans/archive/2026-06-14-production-launch-roadmap.md)

---

## 附录:评估方法与证据强度

- **数据源**:本报告所有结论基于实际源码核查,关键断链(P0-#1/P0-#2)经主分析者二次 Read 确认,非文档转述。
- **维度覆盖**:数据源覆盖、端到端联通、选股能力、回测/分析/组合/风控,4 个维度并行深度探索。
- **交叉验证**:capability-maturity.md 自评与源码核查一致(无过度宣传),唯一矛盾在 golden lane 状态(P0-#3)。
- **未覆盖**:真实券商接入、产品 UI、intraday 高频场景(均明确 out of scope 或 P2)。
- **评估时点**:2026-06-14,分支 `dev/architecture-remediation-batch2-6`,最新 commit `d39ad1e9`。
