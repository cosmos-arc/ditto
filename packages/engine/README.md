# ditto-engine

**版本**: v0.11.0
**最后更新**: 2026-04-27
**状态**: 策略引擎 + 回测闭环

## 概要

量化交易核心引擎 -- 策略 Pipeline 编排、日历步进回测、执行层、组合构建、共享账户契约。

## 模块结构

```
ditto_engine/
├── alpha/             # Alpha 决策层（StrategySpec / Pipeline / DecisionStage / 8 内置 Stages / 4 模板）
│   ├── builtins/      # Universe / Signal / Scoring / Filtering / Selection /
│   │                 #   Regime / RegimeAllocation / RegimeScoring
│   ├── templates/     # etf_rotation / etf_trend_swing / stock_sector_rotation / stock_selection_trend
│   └── ...            # validation.py, context.py, models.py, protocols.py, pipeline.py, specs.py
├── execution/         # 执行层（Planner / Brokerage / TradeBuilder / Reality Model）
│   └── reality/       # Reality Model（佣金/滑点/成交/结算）
├── backtest/          # 回测引擎（EngineLoop / Manifest / Statistics / Audit / Steps）
│   ├── audit/         # ExecutionAuditCollector
│   └── steps/         # Pipeline Steps（10 个）
├── portfolio/         # 组合构建（WeightAllocator / ConstraintChecker / compare_reports）
├── accounting/        # 共享账户契约（Account / CashBook / OrderBook / Position）
├── risk/              # 风险管理（PreTrade / PostTrade）
└── events.py          # 域事件定义
```

## 架构定位

```
interfaces → app → engine → kernel
                        → data (errors + provider Protocol only)
```

**允许的依赖**:

| 依赖 | 用途 |
|------|------|
| `ditto_kernel` | 共享类型 |
| `ditto_data.errors` | re-export 异常 |
| `ditto_data.provider` | Protocol 数据访问 |

**禁止依赖**: analytics / infra / interfaces / app

## 核心功能

| 模块 | 关键组件 | 说明 |
|------|---------|------|
| alpha | StrategyPipeline + 8 Stages + 4 Templates | 策略决策流水线 |
| backtest | EngineLoop + PreTrade(6) + PostTrade(4) | 日历步进回测 |
| execution | ExecutionPlanner + BacktestBrokerage + TradeBuilder | 订单执行与成交匹配 |
| portfolio | EqualWeight / ScoreWeight / InverseVol + Constraints | 组合权重分配与约束 |
| accounting | Account / CashBook / OrderBook / Position | 共享账户 frozen 契约 |

### 内置 Stages（alpha/builtins/）

| Stage | 职责 |
|-------|------|
| UniverseStage | 标的池白名单过滤 |
| SignalStage | 信号值附加 |
| ScoringStage | 信号 -> 评分（Mean/Rank/Percentile） |
| FilteringStage | 条件过滤（含 RiskLockFilter） |
| SelectionStage | Top-K 选择 |
| RegimeStage | 市场状态检测（MA 交叉 / 波动率阈值） |
| RegimeAllocationStage | 基于 Regime 的资产配置 |
| RegimeScoringStage | 基于 Regime 的评分 |

> 注：TrendFilterStage 在 etf_trend_swing 模板内（向量化 polars join），非全局内置。

### 策略模板（alpha/templates/）

| 模板 | 说明 |
|------|------|
| etf_rotation | ETF 行业轮动 |
| etf_trend_swing | ETF 趋势追踪（含 TrailingStop） |
| stock_sector_rotation | 股票板块轮动 |
| stock_selection_trend | 多因子股票选股 |

### 风控体系

**PreTrade 事前风控（6 规则）**:

| 规则 | 职责 |
|------|------|
| NoShortSell | 禁止卖空 |
| PriceValidity | 涨跌停/停牌过滤 |
| LotSize | 最小交易单位取整 |
| BuyingPower | 购买力检查 |
| Concentration | 单票集中度限制 |
| DailyTurnover | 日换手率限制 |

**PostTrade 事后风控（4 Guard）**:

| Guard | 职责 |
|-------|------|
| MaxDrawdown | 组合最大回撤检测 |
| SingleLoss | 单标的亏损检测 |
| Concentration | 持仓集中度检测 |
| MarketAnomaly | 市场异常波动检测 |

## 使用示例

### 策略 Pipeline

```python
from ditto_engine.alpha import StrategySpec, StrategyPipeline, StrategyInputBundle
from ditto_engine.alpha.templates import build_etf_rotation_pipeline, ETFRotationConfig

# 从模板构建 Pipeline
config = ETFRotationConfig(top_n=3, rebalance_freq="monthly")
pipeline = build_etf_rotation_pipeline(config)

# 运行 Pipeline
result = pipeline.run(bundle)
print(result.target_portfolio)  # TargetPortfolio
```

### 回测

```python
from ditto_engine.backtest import EngineLoop, EngineConfig, ProviderBackedDataFeed
from ditto_engine.execution import BacktestBrokerage
from ditto_engine.accounting import Account

# 配置并运行回测
config = EngineConfig(start_date="2024-01-01", end_date="2024-12-31", initial_cash=1_000_000)
engine = EngineLoop(config)
data_feed = ProviderBackedDataFeed(provider=..., tickers=..., start_date=..., end_date=..., id_map=...)
account = Account(cash=1_000_000)
result = engine.run(data_feed, pipeline, account)

# 查看报告
report = result.report
print(f"Sharpe: {report.alpha.sharpe:.2f}")
print(f"Max DD: {report.alpha.max_drawdown:.2%}")
```

## 设计原则

1. **PIT 安全** -- 所有计算必须使用 `knowledge_date <= trade_date` 的数据
2. **涨跌停感知** -- BacktestBrokerage 通过 MarketSnapshot 判断涨跌停
3. **向量化优先** -- Pipeline 使用 Polars DataFrame（DecisionFrame）列名约定流转
4. **纯函数** -- Engine 层无 I/O，数据通过 Provider Protocol 注入

### execution_delay 语义

- 基于调仓日（rebalance day）计数，非自然日
- daily rebalance 模式下 1 execution_delay = 1 交易日
- weekly/monthly rebalance 模式下延迟效果与自然日不对应
- 尾部 flush 使用 last_date，为"最佳努力"执行，非 PIT 精确

## 相关文档

- [Engine 层规范](CLAUDE.md)
- [PIT 安全指南](../../.claude/rules/pit.md)
- [v3 系统设计](../../docs/plans/2026-03-21-strategy-engine-system-design-v3.md)

## 变更记录

### v0.11.0 (2026-04-27)
- 新增 RegimeAllocationStage / RegimeScoringStage（8 内置 Stages）
- 新增 execution/reality/、backtest/audit/、backtest/steps/ 模块
- 新增 execution_delay 语义说明
- TrendFilterStage 移入 etf_trend_swing 模板（非全局内置）

### v0.10.0 (2026-04-04)
**重构**
- Phase 4 App 层提取: engine 独立包，去除 engine/quality/engine 子模块（迁至 analytics/data）
- 目录重命名: strategy -> alpha, engine -> alpha 下的 stages + templates
- README 全面重写，反映当前模块结构

### v0.9.0 (2026-03-24)
**改进**
- README 文档全面更新，反映代码库实际状态
- 新增 execution/backtest/quality/engine/accounting 模块详细说明
- 修正架构图（ditto-foundation -> ditto-platform）

### v0.8.0 (2026-03-23)
**新增** -- Phase 6: Gap 补齐 + 质量加固
- RegimeStage（MA 交叉法 + 波动率阈值法）
- validate_spec_params() 独立参数校验
- RebalancePlan / SignalSnapshot.valid_until
- 62 个新测试，3849 个测试全部通过
