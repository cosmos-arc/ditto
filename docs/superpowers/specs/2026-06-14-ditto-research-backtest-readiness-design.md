# Ditto 研究/回测生产可用性评估设计

日期：2026-06-14
状态：已按用户确认口径形成评估基线
评估口径：研究/回测生产可用，系统产生日频信号与报告，人工交易，不包含真实券商实盘、自动下单和产品前端。

## 1. 结论摘要

按当前源码和架构文档判断，Ditto 已经具备一个较强的“日频量化研究与回测内核”雏形，尤其是 A 股 ETF 日频数据、策略模板、回测、因子评估、catalog/maturity gate、PIT 防泄漏、checkpoint/replay 等基础设施。但如果目标是“个股、ETF、宏观数据，日频量化和个股分析，以及优秀选股能力”的整体上线，当前不能直接判定为生产可用。

当前更准确的上线判断是：

- A 股 ETF 日频研究/回测：接近可限制上线，但仍需修复当前端到端红灯，并补齐最终 release gate。
- A 股个股分析/选股：已有模板和因子基础，但系统自身仍将股票数据、股票模板标为 experimental；只能作为研究预览，不应作为生产级选股信号源。
- 宏观数据/宏观择时：已有接口和源路由，但 maturity 明确为 experimental；不能作为生产级宏观信号输入。
- 人工交易信号闭环：回测/报告基础存在，但还缺少“每日信号包”的稳定契约、解释字段、风险标记、数据快照和 API/CLI 联通验收。

因此总判定为：**不建议整体上线为“股票+ETF+宏观生产研究/回测系统”；可以先以“ETF 日频研究/回测受限版本”上线内测，同时把股票、宏观和人工交易信号包作为上线前 P0/P1 补齐项。**

## 2. 范围与非范围

本评估只关注后端现有系统功能，不评价独立前端团队的 UI 交付。

范围内：

- A 股 ETF、个股、指数、宏观数据的日频研究/回测能力。
- 因子研究、个股分析、选股模板和信号生成。
- 回测、报告、checkpoint/resume/replay、API/CLI 联通。
- 人工交易场景下的信号输出、解释、审计和风险提示。
- 与业界研究/回测系统的能力差距。

范围外：

- 真实券商实盘 adapter。
- 自动下单、自动调仓和盘中交易。
- 独立前端产品体验。
- 高频、tick、盘口、微观结构和多市场实时交易。

## 3. 主要源码证据

### 3.1 系统 maturity 自证

`docs/architecture/capability-maturity.md` 的目的就是防止路线图语言被误读为生产就绪。maturity 定义中，`initial-focus` 表示已有有意义实现和测试，但仍在架构 review；`experimental` 表示对研究或未来方向有用，但不是当前生产范围。见 [capability-maturity.md](../../architecture/capability-maturity.md:52)。

同一文件明确当前后端排除真实 broker adapter 和产品 UI，后端只提供 FastAPI、DTO、OpenAPI metadata、JSON/report surface 给前端消费。见 [capability-maturity.md](../../architecture/capability-maturity.md:65)。

关键能力 maturity：

- A 股 ETF 日频数据、研究、回测 workflow 为 `initial-focus`。见 [capability-maturity.md](../../architecture/capability-maturity.md:71)。
- A 股股票/指数 metadata 和 market data 中，股票数据为 `experimental`，默认 fail closed，除非显式 `allow_experimental_data=True` 或通过 promotion override。见 [capability-maturity.md](../../architecture/capability-maturity.md:72)。
- Fundamental/capital 为 `experimental`。见 [capability-maturity.md](../../architecture/capability-maturity.md:73)。
- Macro data 为 `experimental`。见 [capability-maturity.md](../../architecture/capability-maturity.md:74)。
- Strategy alpha templates 中，ETF 模板为 `initial-focus`，股票模板 `stock_selection_trend` 和 `stock_sector_rotation` 为 `experimental`。见 [capability-maturity.md](../../architecture/capability-maturity.md:77)。
- Portfolio accounting/rebalancing 和 Risk checks 均为 `experimental`。见 [capability-maturity.md](../../architecture/capability-maturity.md:78) 与 [capability-maturity.md](../../architecture/capability-maturity.md:79)。
- Backtest engine 为 `initial-focus`，但下一步仍要求更广的非全现金 deterministic order/fill identity fixtures。见 [capability-maturity.md](../../architecture/capability-maturity.md:80)。

API maturity 也与此一致：`/backtests`、`/market`、`/metadata`、`/strategies`、`/universes` 为 `initial-focus`；`/fundamental`、`/capital`、`/macro`、`/trade` 为 `experimental`。见 [capability-maturity.md](../../architecture/capability-maturity.md:155)。

### 3.2 数据目录 maturity

数据目录把生产近端范围和研究范围分开：

- `etf_basic`、`index_basic`、`calendar`、`etf_daily`、`index_daily`、`adj_factor`、`fund_adj` 是 `_INITIAL_FOCUS_DATASETS`。见 [metadata.py](../../../packages/data/src/ditto_data/catalog/metadata.py:149)。
- `stock_basic`、`stock_daily`、`stock_status`、财务三表、估值、两融、质押、corporate actions、`macro_indicators` 等是 `_EXPERIMENTAL_DATASETS`。见 [metadata.py](../../../packages/data/src/ditto_data/catalog/metadata.py:161)。
- experimental 数据晋级要求包括：完整 PIT/replay 覆盖、runtime owner/freshness SLA/source failover policy、catalog-backed runtime/read-model tests 在无 research opt-in 下通过。见 [metadata.py](../../../packages/data/src/ditto_data/catalog/metadata.py:181)。

应用层 runtime gate 会根据 strategy `asset_class` 映射到数据集：ETF 使用 `etf_daily/etf_basic`，stock 使用 `stock_daily/stock_basic`。非 `initial-focus` 默认阻断，只有显式 `allow_experimental_data` 或 promotion reader 可放行。见 [catalog_maturity.py](../../../packages/application/src/ditto_application/catalog_maturity.py:24) 与 [catalog_maturity.py](../../../packages/application/src/ditto_application/catalog_maturity.py:52)。

这说明 Ditto 的数据治理方向是正确的，但也说明“股票+宏观生产级研究/回测”尚未完成 promotion。

### 3.3 股票选股模板

`stock_selection_trend` 不是空壳。它的流程为：

`MultiFactorSignal -> TrendFilter -> Scoring -> RiskLockFilter -> Select(top_k) -> optional Regime`

见 [stock_selection_trend.py](../../../packages/strategy/src/ditto_strategy/alpha/templates/stock_selection_trend.py:1) 与 [stock_selection_trend.py](../../../packages/strategy/src/ditto_strategy/alpha/templates/stock_selection_trend.py:49)。

配置支持：

- `signal_factors`、`signal_weights`
- `top_k`
- `max_weight`
- `allocation_method = equal_weight / inverse_vol`
- `cash_target`
- `trend_threshold`
- `rebalance_freq = daily / weekly / monthly`
- optional `regime_config`

见 [stock_selection_trend_config.py](../../../packages/strategy/src/ditto_strategy/alpha/templates/stock_selection_trend_config.py:49) 与参数扫描约束 [stock_selection_trend_config.py](../../../packages/strategy/src/ditto_strategy/alpha/templates/stock_selection_trend_config.py:163)。

多因子信号 stage 使用 rank-based 标准化后加权。缺失因子列会被跳过，但分母仍是全部权重和。见 [stock_selection_trend_stages.py](../../../packages/strategy/src/ditto_strategy/alpha/templates/stock_selection_trend_stages.py:14) 与 [stock_selection_trend_stages.py](../../../packages/strategy/src/ditto_strategy/alpha/templates/stock_selection_trend_stages.py:48)。

生产级差距在于：当前模板仍偏通用 pipeline，默认信号为 `signal_value`，还没有形成“可上线选股模型”的完整证据链，例如因子晋级、权重生成、行业/风格中性化、容量/流动性约束、停牌/ST/涨跌停过滤、信号解释与每日候选输出契约。

### 3.4 因子研究能力

因子规格注册表已经覆盖 primitive、technical、fundamental、alpha、size、value、momentum、quality、volatility、liquidity、growth、alternative 等类别。见 [factor_specs.py](../../../packages/features/src/ditto_features/factors/factor_specs.py:21)。

`FactorEvaluator` 已实现较完整的因子评估链路：

- 数据准备和 forward return 对齐。
- Rank IC 与 Pearson IC。
- IC decay / half-life。
- IC autocorrelation。
- turnover-adjusted IR 与 Grinold-Kahn IR。
- quantile returns、long-short、sub-period IC。
- 可选 Fama-MacBeth、exposure、regime IC、performance attribution。

见 [\_orchestrator.py](../../../packages/features/src/ditto_features/evaluation/evaluator/_orchestrator.py:82)、[\_orchestrator.py](../../../packages/features/src/ditto_features/evaluation/evaluator/_orchestrator.py:201)、[\_orchestrator.py](../../../packages/features/src/ditto_features/evaluation/evaluator/_orchestrator.py:272) 与 [\_report_builder.py](../../../packages/features/src/ditto_features/evaluation/evaluator/_report_builder.py:92)。

但当前 report builder 仍把 `factor_id="unknown"`、`factor_version=1` 固定写入报告。见 [\_report_builder.py](../../../packages/features/src/ditto_features/evaluation/evaluator/_report_builder.py:141)。这意味着因子评估计算能力较强，但生产级研究治理还需要因子 ID、版本、实验记录、样本外验证和晋级标准打通。

### 3.5 端到端测试现状

已有纯合成 golden E2E，覆盖：

`合成行情 -> 策略信号 -> 组合构建 -> 风控检查 -> 模拟执行 -> 绩效报告`

该测试强调零外部依赖、确定性和最小全链路证明。见 [test_golden_e2e.py](../../../packages/apps/tests/integration/test_golden_e2e.py:1)。验收包括引擎运行、final NAV、成交记录、无跳过日期、BacktestReport、NAV 序列、portfolio stats 和绩效统计。见 [test_golden_e2e.py](../../../packages/apps/tests/integration/test_golden_e2e.py:284)。

真实/准真实 E2E 仍依赖 TDX 样本、PIT snapshots、Tushare token；缺失时会 skip。见 [conftest.py](../../../packages/apps/tests/e2e/conftest.py:44)、[conftest.py](../../../packages/apps/tests/e2e/conftest.py:80) 与 [conftest.py](../../../packages/apps/tests/e2e/conftest.py:129)。

策略 integration fixtures 覆盖了 ETF 和股票模板 snapshot：

- `test_etf_rotation_e2e.py`
- `test_etf_trend_swing_snapshot.py`
- `test_stock_selection_trend_snapshot.py`
- `test_stock_sector_rotation_snapshot.py`

但 snapshot 不等于生产晋级。生产晋级还需要 maturity promotion evidence、无 research opt-in runtime tests、数据治理和报告契约。

### 3.6 当前验证红灯

已执行代表性测试：

```bash
pixi run -e dev pytest \
  packages/apps/tests/integration/test_golden_e2e.py \
  packages/application/tests/integration/test_restored_run_replay_execution_golden.py \
  packages/strategy/tests/integration/alpha/test_etf_rotation_e2e.py \
  packages/strategy/tests/integration/alpha/test_stock_selection_trend_snapshot.py \
  -q --no-cov
```

结果：23 passed, 1 failed。

失败项：

`packages/application/tests/integration/test_restored_run_replay_execution_golden.py::test_restored_run_replay_execution_golden`

失败原因：`BacktestService._on_step_complete()` 调用 `Metrics.backtest_step_duration.record(...)` 时，`Metrics` 上没有 `backtest_step_duration` 属性。

代码位置：

- BacktestService 在构造 `on_step_complete` 时只捕获 import-time exception，真正 callback 执行时的 metric lookup 异常不会被吞掉。见 [backtest_process.py](../../../packages/application/src/ditto_application/processes/execution/backtest_process.py:470)。
- apps composition root 的 observability provider 会注册 backtest metrics。见 [observability.py](../../../packages/apps/src/ditto_apps/registry/infra/observability.py:81) 与 [observability.py](../../../packages/apps/src/ditto_apps/registry/infra/observability.py:111)。
- 当前 application-level synthetic restored-run golden 直接构造 service，不经过 apps composition root，因此 backtest step metrics 未注册。

这不是业务策略错误，但它是上线前必须修复的端到端联通问题：生产路径、测试路径和 observability 初始化契约需要一致，或者 application service 对未注册 metric 具备 fail-soft 行为。

## 4. 业界最佳系统对标

### 4.1 QuantConnect / LEAN

LEAN 官方定位是统一的研究、回测、优化和 live-trade 技术，并集成数据供应商和券商。QuantConnect 也提供 backtest report，覆盖收益、交易分布、累计收益等分析；walk-forward optimization 文档强调参数需要随市场变化持续调整。参考：

- https://www.lean.io/
- https://www.quantconnect.com/
- https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/report

对 Ditto 的启示：

- Ditto 的 backtest/replay/catalog 方向接近专业系统底座，但当前缺少生产级数据广度、统一研究实验治理、参数优化/样本外/walk-forward 产品链路。
- 本评估不要求 live trading，但即便只做人工交易信号，也需要像 LEAN report 一样稳定产出可审计的回测与信号报告。

### 4.2 NautilusTrader

NautilusTrader 官方强调同一套 actors、strategies、execution algorithms 可运行在 backtest engine 和 live trading node；backtesting engine 包含 Cache、MessageBus、Portfolio、Actors、Strategies、Execution Algorithms，并输出 performance metrics。参考：

- https://nautilustrader.io/docs/latest/concepts/backtesting/
- https://nautilustrader.io/docs/latest/concepts/live/
- https://nautilustrader.io/docs/latest/concepts/strategies/

对 Ditto 的启示：

- Ditto 当前不需要真实 live node，但 replay/checkpoint、event/time/state/OMS spine、portfolio state projection 仍决定研究结果是否可复现、可解释。
- 当前 runtime spine、portfolio、risk 在 maturity 中仍为 experimental，因此还不能说达到 NautilusTrader 式的生产一致性。

### 4.3 Alphalens

Alphalens 用于 alpha factor 分析，典型能力包括 factor values、forward returns、Spearman rank IC、quantile returns、turnover 和 grouped analysis。参考：

- https://alphalens.ml4trading.io/notebooks/overview.html
- https://quantopian.github.io/alphalens/alphalens.html

对 Ditto 的启示：

- Ditto 的 FactorEvaluator 已经覆盖 IC、decay、long-short、turnover-adjusted IR、Fama-MacBeth 等核心指标，底层研究能力不弱。
- 差距在于生产治理：factor_id/version、实验记录、分组/行业中性、样本外、因子晋级标准和报告可消费性。

### 4.4 PyPortfolioOpt

PyPortfolioOpt 覆盖 classical efficient frontier、Black-Litterman、shrinkage、Hierarchical Risk Parity 等组合优化方法。参考：

- https://pyportfolioopt.readthedocs.io/
- https://pyportfolioopt.readthedocs.io/en/latest/BlackLitterman.html
- https://pyportfolioopt.readthedocs.io/en/latest/OtherOptimizers.html

对 Ditto 的启示：

- 当前 stock_selection_trend 的 allocation 只有 equal_weight / inverse_vol 级别，Portfolio accounting/rebalancing maturity 仍是 experimental。
- 如果目标是“优秀选股能力”，短期不一定要做复杂组合优化；但至少要有稳定的风险约束、行业/风格暴露控制、换手和成本控制。中期应补 robust optimizer 或接入类似 HRP/BL/mean-variance 的组合构建能力。

## 5. 差距矩阵

| 维度 | 当前状态 | 与目标差距 | 上线判定 |
|---|---|---|---|
| ETF 日频数据/回测 | initial-focus，有 synthetic golden 和 ETF strategy tests | 当前仍需最终 release gate；端到端 restored-run 测试有红灯 | 修复红灯后可受限上线 |
| 股票日频数据 | stock_basic/stock_daily 为 experimental | 缺生产 promotion evidence、无 research opt-in runtime green lane | 不能生产上线 |
| 基本面/资金面 | experimental | PIT、SLA、failover、promotion 和回测链路未形成生产证据 | 研究预览 |
| 宏观数据 | macro_indicators 为 experimental | 缺 release-date/PIT/lag 语义、宏观 regime golden lane | 研究预览 |
| 因子库 | 覆盖多类 factor specs | 缺因子版本、实验治理、晋级标准、样本外验证 | 底座可用，治理不足 |
| 因子评估 | IC、decay、long-short、Fama-MacBeth 等较完整 | 报告 ID/version 固定，缺完整 factor registry 与 frontend/API 消费契约 | 需补生产报告 |
| 股票选股模板 | 有多因子 rank、趋势过滤、risk lock、top_k、regime | 模板 experimental，缺优秀选股模型证据和稳定日信号包 | 不应生产上线 |
| 回测引擎 | initial-focus，checkpoint/replay 能力强 | 当前恢复/replay golden 失败；还需非全现金 order/fill identity fixtures | 修复后可作为底座 |
| Portfolio/Risk | 多数为 experimental | 人工交易也需要风险标记、仓位约束、暴露控制、异常阻断 | P0/P1 需补 |
| API/CLI 联通 | 路由 maturity 清晰 | 需完整 run-through smoke：创建策略、跑回测、取报告、取信号、取 lineage | 上线前必做 |
| Observability | composition root 有 metrics 注册 | application direct path 可失败，run correlation/SLO 未完整验收 | 上线前必修 |

## 6. 端到端验收设计

上线前必须把验证从“模块测试很多”升级为“业务闭环可证明”。建议设置以下 gate。

### Gate 0: 基础质量闸

命令：

```bash
pixi run -e dev check
```

要求：

- 静态检查、类型检查、单测、集成测试全部通过。
- 当前 restored-run replay execution golden 红灯必须修复。
- 所有新增上线 lane 禁止依赖外部 token 才能给出最低限度结果。

### Gate 1: 数据目录与 PIT 闸

覆盖 ETF、股票、宏观三个目标域。

要求：

- 每个生产候选 dataset 有 DataCatalog asset、schema_version、source_snapshot_id、freshness/SLA、storage URI 和 source coverage。
- 股票和宏观如果要作为生产输入，必须完成 promotion criteria；否则所有报告必须明确标为 research-only。
- PIT 查询默认使用 `knowledge_date`，任何 `trade_date` fallback 只允许 research unsafe policy，并写入 manifest/report。

### Gate 2: ETF 生产候选 lane

输入：

- 固定 A 股 ETF universe。
- 固定日频区间。
- 指数 benchmark。

验收：

- 通过 FastAPI 或 CLI 创建 backtest run。
- 生成 NAV、trade log、positions、metrics、lineage、source snapshot。
- 同一输入重复运行结果 deterministic。
- checkpoint/resume/replay proof 通过。
- 输出人工交易 signal package。

### Gate 3: 股票选股候选 lane

输入：

- 固定股票 universe，例如沪深 300/中证 500 的 committed fixture 或 catalog-backed sample。
- 至少一组技术因子、一组基本面/质量/估值因子、一组流动性/波动率约束。

验收：

- 无显式 research opt-in 时，如果数据仍 experimental，必须 fail closed。
- 完成 promotion 后，stock lane 应无 opt-in 通过。
- 输出每日 top-k、目标权重、过滤原因、风险标记、行业/风格暴露摘要、换手和成本估计。
- golden snapshot 锁定最终 NAV、总交易数、最终持仓、每日候选列表摘要。
- 因子窗口使用 strict as-of，证明无未来函数。

### Gate 4: 宏观 regime lane

输入：

- macro_indicators committed fixture 或 promoted catalog data。
- 每个指标必须包含 release/effective/knowledge date 语义。

验收：

- 宏观信号不能使用未来发布数据。
- regime 输出可解释：当前状态、触发指标、阈值、滞后、适用日期。
- 与 ETF/股票策略组合时，报告记录宏观输入快照和 policy。

### Gate 5: 人工交易信号包

信号包是本口径下的最终产品契约。

最低字段：

- `run_id`
- `trade_date`
- `strategy_id`
- `universe_id`
- `data_snapshot_ids`
- `pit_policy`
- `benchmark`
- `selected_instruments`
- `target_weights`
- `suggested_orders`
- `risk_flags`
- `filter_reasons`
- `factor_contributions`
- `expected_turnover`
- `estimated_cost`
- `report_artifact_uri`
- `checksum`

验收：

- API 和 CLI 都能获取同一份信号包。
- 信号包能从 run lineage 追溯到数据快照、策略版本和配置。
- 同一 run_id 重复读取内容稳定。
- experimental 数据参与时必须有显式标记。

### Gate 6: API/CLI 联通调试

最小联通路径：

1. 查询数据 readiness/source-health。
2. 查询 universe。
3. 创建 strategy run/backtest。
4. 查询 run status。
5. 查询 report。
6. 查询 replay proof。
7. 查询 daily signal package。
8. 查询 lineage/catalog report。

验收：

- HTTP contract、DTO、OpenAPI metadata 与后端实际响应一致。
- 错误路径稳定：缺数据、experimental 未 opt-in、PIT unsafe、schema mismatch、source unsupported 都有结构化错误。

### Gate 7: 运维与审计

要求：

- 每个 run 有 correlation/run ID，贯穿 log、metrics、artifact、report。
- backtest step metrics 注册与 direct application path 一致。
- source-health 和 maturity-governance 报告可用于上线前检查。
- 失败 run 能保留错误、输入、artifact 和可重试状态。

## 7. 上线前必须完成项

### P0: 阻断整体上线

1. 修复 `test_restored_run_replay_execution_golden` 的 metrics 注册/调用失败。
2. 对目标范围做明确 product cut：如果上线只含 ETF，则股票/宏观必须标注 research-only；如果包含股票/宏观，则必须完成相关 dataset/template promotion。
3. 增加 committed、无外部 token 依赖的股票选股 golden lane。
4. 增加人工交易 signal package 的后端 DTO/API/CLI 契约或明确现有报告中哪个 artifact 承担该职责。
5. 跑通完整 API/CLI 联通调试，从 readiness 到 report/replay/signal。

### P1: 上线质量增强

1. 因子评估报告接入 factor_id、factor_version、experiment/run metadata。
2. 股票选股补齐行业/风格中性、流动性、停牌/ST/涨跌停、容量和换手约束。
3. 补齐样本外、walk-forward、参数稳定性和多重检验控制的 release evidence。
4. 宏观数据补齐 release date / knowledge date / lag handling，并增加 regime golden lane。
5. Portfolio/Risk 至少补齐人工信号场景下的风险标记、限制说明和阻断逻辑。

### P2: 可延期

1. 真实 broker adapter。
2. 自动执行和 paper/live trading。
3. intraday/tick。
4. 全功能组合优化套件，如 Black-Litterman、HRP、mean-variance。
5. 前端体验。

## 8. 建议里程碑

### M1: ETF 受限上线

目标：只承诺 A 股 ETF 日频研究/回测与人工信号。

完成标准：

- P0 restored-run golden 修复。
- ETF lane 通过 synthetic + committed data + API/CLI smoke。
- 报告和信号包可重复、可追溯。

### M2: 股票研究预览

目标：允许个股选股研究，但明确 research-only。

完成标准：

- stock lane 需要 `allow_experimental_data=True` 且 run config/report 留痕。
- top-k 选股、因子贡献、风险过滤原因可导出。
- 不对外宣称生产级选股。

### M3: 股票生产候选

目标：股票数据和 stock_selection_trend 晋级到生产候选。

完成标准：

- `stock_daily/stock_basic` 完成 promotion criteria。
- 无 opt-in 通过 stock selection golden lane。
- 因子、选股、报告、信号包、replay 都有 deterministic evidence。

### M4: 宏观生产候选

目标：宏观 regime 作为生产级辅助输入。

完成标准：

- `macro_indicators` 完成 promotion criteria。
- release date / knowledge date 语义清晰。
- macro regime lane 有防泄漏 golden evidence。

## 9. 风险判断

最大风险不是“代码有没有写”，而是“研究能力和生产可用边界被混淆”。Ditto 已经做了很多正确的架构防线，例如 maturity gate、PIT policy、catalog lineage 和 fail-closed，这些防线恰恰说明股票、宏观、组合、风险目前不应被包装成生产可用。

如果强行整体上线，主要风险是：

- 股票/宏观 experimental 数据绕过 maturity 进入生产信号。
- 个股选股结果缺少因子晋级、样本外和防泄漏证据。
- 人工交易使用的信号缺少解释、风险、数据快照和审计。
- 端到端联通在非 composition-root 路径出现 observability/metrics 类问题。
- 外部数据 token 或本地样本缺失导致验收 lane skip，而不是 fail/pass 明确。

## 10. 推荐决策

推荐采用分阶段上线：

1. **短期只上线 ETF 日频研究/回测受限版本。**
2. **股票和宏观先作为显式 research-only 能力开放给内部研究。**
3. **把股票选股生产化作为下一阶段主线，而不是把 experimental 能力直接纳入生产口径。**
4. **上线前以端到端 gate 替代单纯测试数量判断。**

最终上线标准应写成一句话：

> Ditto 仅在所有目标数据集通过 maturity promotion、所有生产 lane 通过无外部依赖 golden E2E、API/CLI 能输出可追溯人工交易信号包、且 replay/lineage/observability 全部通过 release gate 后，才能宣称“股票+ETF+宏观日频研究/回测生产可用”。
