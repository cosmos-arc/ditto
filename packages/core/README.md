# ditto-core

**版本**: v0.9.0
**最后更新**: 2026-03-24
**状态**: ✅ 策略引擎 + 回测闭环

## 概要

量化交易系统核心引擎，提供策略引擎（Pipeline + Stage 架构）、回测引擎（EngineLoop 日历步进）、执行层（Brokerage + Reality Model）、组合构建、Expression DSL 编译器、因子评估体系和数据质量引擎。

## 核心功能

- **策略引擎**: Pipeline + Stage 架构，内置 8 个 Stage + 4 个策略模板
- **回测引擎**: EngineLoop 日历步进 + PreTrade（6 规则）/ PostTrade（4 Guard）
- **执行层**: ExecutionPlanner + BacktestBrokerage + TradeBuilder（FIFO/FlatToFlat）+ Reality Model
- **组合构建**: WeightAllocator（等权/评分/波动率倒数）+ ConstraintChecker
- **共享账户**: Account / CashBook / OrderBook / Position frozen 契约层
- **Expression DSL**: Pratt Parser 编译器，44 算子，Polars 向量化执行
- **因子评估**: IC / ICIR / Fama-MacBeth / Regime IC / Performance Attribution + 尾部风险
- **数据质量**: DQ Engine + L1/L2/L3/CrossSource 检查器

## 架构

```
┌─────────────────────────────────────┐
│         apps/port                   │
│     (FastAPI 应用层)                  │
├─────────────────────────────────────┤
│         ditto-core                  │  ← 当前层
│  ┌──────────┐  ┌──────────┐        │
│  │ strategy │  │execution │        │
│  │ Pipeline │  │ Planner  │        │
│  │ Stages   │  │ Brokerage│        │
│  │ Templates│  │ TradeBld │        │
│  └──────────┘  └──────────┘        │
│  ┌──────────┐  ┌──────────┐        │
│  │backtest  │  │portfolio │        │
│  │EngineLoop│  │Allocator │        │
│  │ PreTrade │  │Constraint│        │
│  │PostTrade │  │Compare   │        │
│  └──────────┘  └──────────┘        │
│  ┌──────────┐  ┌──────────┐        │
│  │engine    │  │accounting│        │
│  │Expr DSL  │  │ Account  │        │
│  │Evaluator │  │ CashBook │        │
│  │Materializ│  │ OrderBook│        │
│  └──────────┘  └──────────┘        │
│  ┌──────────┐                      │
│  │quality   │                      │
│  │DQ Engine │                      │
│  │Checkers  │                      │
│  └──────────┘                      │
├─────────────────────────────────────┤
│        ditto-datahub                │
│     (数据访问层)                      │
├─────────────────────────────────────┤
│        ditto-infra                  │
│     (基础设施层)                      │
└─────────────────────────────────────┘
```

**依赖方向**: 仅依赖 `ditto-datahub` 和 `ditto-infra`

## 核心模块

### strategy/ — 策略决策层

| 模块 | 职责 | 状态 |
|------|------|------|
| `StrategySpec` | 策略完整定义（语义契约） | ✅ |
| `StrategyTemplate` | 策略模板蓝图 | ✅ |
| `StrategyVersion` | 策略版本管理 | ✅ |
| `StrategyRun` | 策略运行记录 | ✅ |
| `StrategyContext` | 运行时上下文（风控锁定） | ✅ |
| `DecisionStage` | Pipeline 阶段 Protocol | ✅ |
| `StrategyPipeline` | 策略流水线编排 | ✅ |
| `StrategyInputBundle` | Pipeline 输入数据包 | ✅ |
| `SignalSnapshot` | 信号快照 | ✅ |
| `TargetPortfolio` | 目标持仓 | ✅ |
| `RebalancePlan` | 调仓计划数据对象 | ✅ |
| `validate_spec_params` | StrategySpec 参数校验 | ✅ |

**内置 Stages**:

| Stage | 职责 | 状态 |
|-------|------|------|
| `UniverseStage` | 标的池白名单过滤 | ✅ |
| `SignalStage` | 信号值附加 | ✅ |
| `ScoringStage` | 信号 → 评分转换（Mean/Rank/Percentile） | ✅ |
| `FilteringStage` | 条件过滤（FilterCondition） | ✅ |
| `SelectionStage` | Top-K 选择 | ✅ |
| `RiskLockFilter` | 风控锁定标的过滤 | ✅ |
| `TrendFilterStage` | 趋势方向过滤 | ✅ |
| `RegimeStage` | 市场状态检测（MA 交叉 / 波动率阈值） | ✅ |

**策略模板**:

| 模板 | 职责 | 状态 |
|------|------|------|
| `build_etf_rotation_pipeline` | ETF 行业轮动 | ✅ |
| `build_etf_trend_swing_pipeline` | ETF 趋势追踪（含 TrailingStop） | ✅ |
| `build_stock_sector_rotation_pipeline` | 股票板块轮动 | ✅ |
| `build_stock_selection_trend_pipeline` | 多因子股票选股 | ✅ |

### execution/ — 执行层

| 模块 | 职责 | 状态 |
|------|------|------|
| `ExecutionPlanner` | 订单执行规划（SimpleExecutionPlanner） | ✅ |
| `BacktestBrokerage` | 回测经纪商（T+1 冻结、批内滚动更新） | ✅ |
| `TradeBuilder` | 成交匹配（FifoTradeBuilder / FlatToFlatTradeBuilder） | ✅ |
| `rules.py` | InstrumentDefinition / TradingRuleSet / FeeSchedule | ✅ |
| `reality/` | Reality Model（佣金/滑点/成交/结算） | ✅ |
| `fills.py` | FillOutcome（Filled / NoFill 联合类型） | ✅ |

### backtest/ — 回测引擎

| 模块 | 职责 | 状态 |
|------|------|------|
| `EngineLoop` | 日历步进回测主循环 | ✅ |
| `ParquetDataFeed` | Parquet 数据源适配（DataFeed Protocol） | ✅ |
| `EngineConfig` | 回测配置（日期/资金/模式/频率/匹配方式） | ✅ |
| `BacktestReport` | 回测报告（NAV/收益/回撤/Sharpe/Calmar/CVaR） | ✅ |
| `RunManifest` | 运行清单（规则引用、输入引用、配置哈希） | ✅ |
| `pre_trade.py` | PreTrade 6 条规则（NoShortSell/PriceValidity/LotSize/BuyingPower/Concentration/DailyTurnover） | ✅ |
| `post_trade.py` | PostTrade 4 个 Guard（MaxDrawdown/SingleLoss/Concentration/MarketAnomaly） | ✅ |
| `statistics.py` | AlphaStatistics / PortfolioStatistics / TradeStatistics | ✅ |
| `serialization.py` | BacktestReportSerializer（SQLite 存储） | ✅ |
| `audit/` | ExecutionAuditCollector（账户快照/成交/风控/审计） | ✅ |

### portfolio/ — 组合构建层

| 模块 | 职责 | 状态 |
|------|------|------|
| `WeightAllocator` | Protocol — 权重分配接口 | ✅ |
| `EqualWeightAllocator` | 等权分配 | ✅ |
| `ScoreWeightAllocator` | 评分加权分配 | ✅ |
| `InverseVolAllocator` | 波动率倒数加权 | ✅ |
| `ConstraintChecker` | 约束检查（按 priority 排序） | ✅ |
| `MaxWeightConstraint` | 最大权重约束 | ✅ |
| `MinWeightConstraint` | 最小权重约束 | ✅ |
| `MaxPositionsConstraint` | 最大持仓数约束 | ✅ |
| `AllocationStage` | DecisionStage 适配器（权重分配） | ✅ |
| `ConstraintStage` | DecisionStage 适配器（约束检查） | ✅ |
| `compare_reports()` | 回测报告对比（MetricsDelta） | ✅ |

### accounting/ — 共享账户契约层

| 模块 | 职责 | 状态 |
|------|------|------|
| `Account` / `AccountView` | 账户（可变/只读快照） | ✅ |
| `CashBook` | 资金账本 | ✅ |
| `OrderBook` / `OrderBookReadOnly` | 订单簿 | ✅ |
| `Order` / `OrderTicket` | 订单 | ✅ |
| `Position` | 持仓 | ✅ |
| `BuyingPowerModel` | 购买力模型 Protocol | ✅ |

### engine/ — Expression DSL 与因子评估

| 模块 | 职责 | 状态 |
|------|------|------|
| `ExpressionCompiler` | Pratt Parser → AST → Polars 表达式（44 算子） | ✅ |
| `FactorEvaluator` | 因子评估编排（IC/FM/暴露分析/Regime IC） | ✅ |
| `DerivedSpec` | 统一语义合约（feature/factor/signal/label） | ✅ |
| `DerivedExecutionPlanner` | 物化执行规划（计算窗口、分区） | ✅ |
| `PublicationSafety` | 发布安全（认证、兼容性、Shadow Diff） | ✅ |
| `factor_analysis` | Fama-MacBeth、暴露分析、正交化 | ✅ |
| `compile_cache` | 两级编译缓存（内存 + SQLite） | ✅ |

### quality/ — 数据质量引擎

| 模块 | 职责 | 状态 |
|------|------|------|
| `QualityEngine` | DQ 检查引擎编排 | ✅ |
| `technical.py` | L1 技术检查（非空、唯一、外键） | ✅ |
| `business.py` | L2 业务检查（OHLC 一致性、涨跌幅限制） | ✅ |
| `statistical.py` | L3 统计检查（Z-score、完整性） | ✅ |
| `cross_source.py` | 跨源校验 | ✅ |
| `spec.py` | DQ 规则配置模型 | ✅ |
| `golden.py` | Golden Dataset 验证 | ✅ |

## 使用示例

### 策略 Pipeline

```python
from ditto_core.strategy import (
    StrategySpec,
    StrategyPipeline,
    StrategyInputBundle,
)
from ditto_core.strategy.templates import (
    ETFRotationConfig,
    build_etf_rotation_pipeline,
)

# 定义策略
spec = StrategySpec(name="etf_rotation", ...)

# 从模板构建 Pipeline
config = ETFRotationConfig(
    top_n=3,
    rebalance_freq="monthly",
)
pipeline = build_etf_rotation_pipeline(config)

# 运行 Pipeline
result = pipeline.run(bundle)
print(result.target_portfolio)  # TargetPortfolio
```

### 回测

```python
from ditto_core.backtest import (
    EngineLoop,
    EngineConfig,
    ParquetDataFeed,
)
from ditto_core.execution import BacktestBrokerage
from ditto_core.accounting import Account

# 配置回测
config = EngineConfig(
    start_date="2024-01-01",
    end_date="2024-12-31",
    initial_cash=1_000_000,
)

# 运行回测
engine = EngineLoop(config)
data_feed = ParquetDataFeed(...)
account = Account(cash=1_000_000)
result = engine.run(data_feed, pipeline, account)

# 查看报告
report = result.report
print(f"Sharpe: {report.alpha.sharpe:.2f}")
print(f"Max DD: {report.alpha.max_drawdown:.2%}")
```

## 核心设计原则

### 1. PIT 安全

所有引擎计算必须遵守 Point-in-Time 安全原则：

```python
# ✅ 正确：使用 PIT 过滤
from ditto_datahub.stores.market import MarketBarsQuery

df = hub.market.query(
    MarketBarsQuery(
        instrument_ids=[1, 2],
        start="2024-01-01",
        end="2024-01-31",
        asof="2024-01-15",  # 只使用该时点之前的数据
    )
)
```

### 2. 涨跌停感知

回测引擎通过 PreTrade 规则过滤涨跌停无法成交的情况：

```python
# PriceValidity 规则自动过滤涨跌停
# BacktestBrokerage 通过 MarketSnapshot.is_limit_up/is_limit_down 判断
```

### 3. 向量化优先

研究阶段使用 Polars 向量化计算：

```python
import polars as pl

df = (
    pl.scan_parquet("data.parquet")
    .filter(pl.col("date") >= start_date)
    .with_columns([
        pl.col("close").pct_change().alias("return"),
        pl.col("close").rolling_mean(20, closed="left").alias("ma20")
    ])
    .collect()
)
```

### 4. Pipeline + Stage 架构

策略通过 Pipeline 编排，每个 Stage 接收 DecisionFrame（polars DataFrame），通过列名约定流转：

```python
# 列名约定: instrument_id (必须), signal_value, score, weight, reason_codes
from ditto_core.strategy import StrategyPipeline, StrategyInputBundle

pipeline = StrategyPipeline(stages=[universe, signal, scoring, selection])
result = pipeline.run(bundle)
```

## 策略说明

### ETF 行业轮动策略

**核心思路**: 基于市场 Regime 状态，在不同行业/主题 ETF 之间进行轮动配置

**因子体系**:
- **相对强弱 (RS)**: 相对沪深300的超额收益
- **估值 (Value)**: 行业指数PE/PB分位数
- **波动率 (Vol)**: 价格波动率惩罚
- **拥挤度 (Crowding)**: 成交额和溢价率指标

**调仓规则**:
- 月度调仓为主，触发型调仓为辅
- Top N 选择，等权或 Score 加权
- 最小调仓阈值，降低交易成本

### 风险管理

**PreTrade 事前风控**:

| 规则 | 职责 |
|------|------|
| NoShortSell | 禁止卖空 |
| PriceValidity | 涨跌停/停牌过滤 |
| LotSize | 最小交易单位取整 |
| BuyingPower | 购买力检查 |
| Concentration | 单票集中度限制 |
| DailyTurnover | 日换手率限制 |

**PostTrade 事后风控**:

| Guard | 职责 |
|-------|------|
| MaxDrawdown | 组合最大回撤检测 |
| SingleLoss | 单标的亏损检测 |
| Concentration | 持仓集中度检测 |
| MarketAnomaly | 市场异常波动检测 |

## 相关文档

- [v3 系统设计](../../docs/plans/2026-03-21-strategy-engine-system-design-v3.md)
- [Phase 2 实施计划](../../docs/plans/2026-03-22-strategy-engine-phase2-00-master.md)
- [Phase 2-5 路线图](../../docs/plans/2026-03-21-strategy-engine-phase2-5-roadmap.md)
- [Core 层规范](CLAUDE.md)
- [PIT 安全指南](../../.claude/rules/pit.md)

## 变更记录

### v0.9.0 (2026-03-24)
**改进**
- README 文档全面更新，反映当前代码库实际状态
- 新增 execution/、backtest/、quality/、engine/、accounting/ 模块详细说明
- 修正架构图（ditto-foundation → ditto-infra）
- 更新使用示例为实际 API

### v0.8.0 (2026-03-23)
**新增** — Phase 6: Gap 补齐 + 质量加固 Sprint
- `strategy/builtins/regime.py`: RegimeStage（市场状态检测：MA 交叉法 + 波动率阈值法）、RegimeLabel / RegimeMethod 枚举
- `strategy/validation.py`: validate_spec_params() 独立参数校验函数（类型、范围、枚举值）
- `strategy/models.py`: RebalancePlan（调仓计划）、SignalSnapshot.valid_until 字段
- `strategy/protocols.py`: DecisionFrame 类型别名（pl.DataFrame 语义化）
- `execution/orders.py`: Order 类型从 accounting 重导出到 execution
- `accounting/account.py`: Account._cash 私有化（property 访问器）
- `accounting/order_book.py`: OrderBook / OrderBookReadOnly 非 frozen 说明注释
- **DataHub 控制面**: StrategyCatalogService（Spec CRUD + 发布治理）、StrategyArtifactService（产物生命周期管理）
- 62 个新测试（regime 24 + validation 17 + models 6 + catalog 10 + artifact 11），3849 个测试全部通过，84.82% 覆盖率

### v0.7.0 (2026-03-22)
**新增** — Phase 5 Part 01-02: etf_trend_swing 模板 + InverseVol 分配器
- `strategy/templates/etf_trend_swing.py`: TrailingStopStage（追踪止损，向量化 polars join）、ETFTrendSwingConfig、build_etf_trend_swing_pipeline
- `strategy/builtins/filtering.py`: TrendFilterStage（趋势方向过滤）
- `portfolio/allocation.py`: InverseVolAllocator（波动率倒数加权，含零波动率/cash_target 边界处理）
- `strategy/context.py`: StrategyContext 新增 `positions` 字段（持仓成本传递给 TrailingStop）
- **架构重构**: 移除 portfolio → strategy 循环依赖，WeightAllocator/Constraint 签名简化（不再接收 StrategyContext）
- 17 个 etf_trend_swing 测试 + 10 个 InverseVolAllocator 测试，3448 个测试全部通过

### v0.6.0 (2026-03-22)
**新增** — Phase 4 Part 01: PreTrade V3 + T+1 冻结逻辑
- PreTrade 风控完整版: 6 条规则（NoShortSell / PriceValidity / LotSize / BuyingPower / Concentration / DailyTurnover）
- PreTradeContext V3: `rules` + `market_snapshots` + `buying_power_model` + `pending_tickets`
- BacktestBrokerage T+1 冻结: `_register_frozen` / `_thaw_frozen` + SELL 守卫
- F1 rolling context: 批内订单通过后滚动更新（B3 anti-oversell）
- A1 resize recheck: LotSize resize 后重入检查链（最多 3 轮）
- 63 个 PreTrade 单元测试 + 10 个 T+1 冻结测试 + 6 个集成测试迁移
- 3410 个测试全部通过

### v0.5.0 (2026-03-22)
**新增** — Phase 2: 回测引擎闭环
- `execution/` 扩展: `ExecutionPlanner` + `BacktestBrokerage` + `TradeBuilder` (FIFO) + Reality Model (佣金/滑点/结算)
- `backtest/` 新增: `EngineLoop` (日历步进) + `ParquetDataFeed` + `ExecutionAuditCollector` + PreTrade 风控
- 3 日/5 日 etf_rotation 回测集成测试（快照 + 16 个不变量测试）
- 3260 个测试全部通过

### v0.4.0 (2026-03-21)
**新增** — Phase 1: Pipeline 闭环 + 组合构建
- `strategy/builtins/`: Universe / Signal / Scoring / Filtering / Selection 内置 Stage
- `strategy/pipeline.py`: StrategyPipeline + StrategyInputBundle
- `strategy/templates/etf_rotation.py`: ETF 轮动策略模板
- `portfolio/allocation.py`: EqualWeight / ScoreWeight 分配器
- `portfolio/constraints.py`: MaxWeight / MinWeight / MaxPositions 约束

### v0.3.0 (2026-03-21)
**新增** — Phase 0 Part 3: strategy/ 策略决策层类型定义
- `StrategySpec` + `ParamConstraint` / `CostModelSpec` / `ExecutionSpec` / `ConstraintSpec` / `ScorerSpec` / `SelectorSpec`
- `StrategyRun` / `StrategyTemplate` / `StrategyVersion` / `SignalSnapshot` / `TargetPortfolio`
- `StrategyContext`（可变运行时上下文）+ `DecisionStage` Protocol（Pipeline 阶段接口）
- 32 个单元测试，98.07% 覆盖率
