# Engine 层架构规范

## 定位

Engine 层是 **Domain Layer（领域层）**，包含量化系统的核心业务逻辑、领域知识和算法。

**核心原则**：
- 纯业务逻辑，无 I/O 操作
- 无状态计算，可独立测试
- 依赖 Kernel 获取共享类型，依赖 Data Provider Protocol 获取数据

## 模块结构

```
ditto_engine/
├── accounting/        # 共享账户契约层
│   ├── account.py     # Account / AccountView
│   ├── buying_power.py # BuyingPowerModel
│   ├── cash.py        # CashBook
│   ├── fills.py       # 成交记录
│   ├── order_book.py  # OrderBook
│   └── position.py    # Position
├── execution/         # 执行层
│   ├── brokerage.py   # BacktestBrokerage
│   ├── fills.py       # FillOutcome
│   ├── planner.py     # ExecutionPlanner
│   ├── rules.py       # 交易规则
│   ├── targets.py     # 交易目标
│   ├── trade_builder.py # TradeBuilder
│   └── reality/       # Reality Model（佣金/滑点/成交/结算）
│       ├── brokerage.py  # RealityBrokerage
│       ├── constants.py  # 常量定义
│       ├── fee.py        # 佣金模型
│       ├── fill.py       # 成交模拟
│       ├── market.py     # 市场状态
│       └── settlement.py # T+1 结算逻辑
│       └── slippage.py   # 滑点模型
├── alpha/             # Alpha 决策层
│   ├── context.py     # 策略运行上下文
│   ├── frame.py       # DecisionFrame
│   ├── models.py      # Alpha 领域模型
│   ├── pipeline.py    # StrategyPipeline
│   ├── protocols.py   # DecisionStage Protocol
│   ├── seeds.py       # 种子/初始化
│   ├── specs.py       # StrategySpec 定义
│   ├── validation.py  # 参数校验
│   ├── builtins/      # 内置 Stages（8 个）
│   │   ├── filtering.py       # FilteringStage
│   │   ├── regime.py          # RegimeStage
│   │   ├── regime_allocation.py # RegimeAllocationStage
│   │   ├── regime_scoring.py  # RegimeScoringStage
│   │   ├── scoring.py         # ScoringStage
│   │   ├── selection.py       # SelectionStage
│   │   ├── signal.py          # SignalStage
│   │   └── universe.py        # UniverseStage
│   └── templates/     # 策略模板
│       ├── etf_rotation.py
│       ├── etf_trend_swing.py
│       ├── stock_sector_rotation.py
│       └── stock_selection_trend.py
├── backtest/          # 回测引擎
│   ├── engine.py      # EngineLoop 主循环 + 配置/结果模型
│   ├── data_feed.py   # ProviderBackedDataFeed
│   ├── manifest.py    # RunManifest + build_run_manifest
│   ├── replay.py      # 回放控制
│   ├── config.py      # EngineMode + EngineConfig
│   ├── statistics.py  # BacktestReport / Statistics
│   ├── audit/         # 执行审计
│   │   ├── collector.py  # ExecutionAuditCollector
│   │   └── records.py    # 审计记录类型
│   └── steps/         # Pipeline Steps（10 个）
│       ├── _input_bundle.py  # InputBundle 构建
│       ├── audit.py          # 审计 Step
│       ├── data_fetch.py     # 数据获取 Step
│       ├── execution.py      # 执行 Step
│       ├── planning.py       # 规划 Step
│       ├── pre_trade.py      # PreTrade 检查 Step
│       ├── risk_scan.py      # 风险扫描 Step
│       ├── strategy.py       # 策略 Step
│       └── types.py          # Step 类型定义
├── portfolio/         # 组合构建
│   ├── allocation.py  # WeightAllocator / ConstraintChecker
│   ├── comparison.py  # 组合比较
│   ├── constraints.py # 约束定义
│   └── report_views.py # 报告视图
├── risk/              # 风险管理
│   ├── _validation.py # 风险校验
│   ├── post_trade.py  # PostTrade Guard
│   └── pre_trade.py   # PreTrade 检查
└── events.py          # 领域事件定义
```

## 子领域规范

### Factor（因子计算）

**职责**：因子计算算法（RS、动量、波动率）

**关键点**：
- 因子计算在 Analytics 层（ditto_analytics.factors/），Engine 层无独立因子计算模块
- 编排流程在 Application（获取数据、调用计算、保存结果）
- 存储在 Data 层（parquet 文件）

### Accounting（共享账户契约层）

**职责**：Position / CashBook / OrderBook / Account / AccountView / BuyingPowerModel / 成交记录

**关键点**：
- 纯数据结构层，frozen dataclass + Protocol
- Account 是唯一可变对象（内部替换 frozen 引用）
- AccountView 是只读快照，供上层安全消费
- BuyingPowerModel（`buying_power.py`）提供购买力计算
- Cash（`cash.py`）封装现金簿操作
- Fills（`fills.py`）管理成交记录
- 详见 v3 设计文档 §3.1-§3.6

### Execution（执行层）

**职责**：ExecutionPlanner / BacktestBrokerage / TradeBuilder / Reality Model / InstrumentDefinition / FillOutcome / 交易规则 / 交易目标

**关键点**：
- InstrumentDefinition / TradingRuleSet / FeeSchedule 是 frozen dataclass
- FillOutcome 是显式联合类型（Filled / NoFill）
- BacktestBrokerage 实现 T+1 冻结逻辑和批内滚动更新
- TradeBuilder 支持 FIFO / FlatToFlat 两种匹配方式
- Rules（`rules.py`）定义交易规则约束
- Targets（`targets.py`）计算交易目标
- Fills（`fills.py`）封装成交结果
- Reality Model（`reality/` 子包）处理佣金/滑点/成交/结算：
  - `brokerage.py` — RealityBrokerage
  - `constants.py` — 常量定义
  - `fee.py` — 佣金模型
  - `fill.py` — 成交模拟
  - `market.py` — 市场状态
  - `settlement.py` — T+1 结算逻辑
  - `slippage.py` — 滑点模型
- 详见 v3 设计文档 §4.3, §5.1

### Alpha（Alpha 决策层）

**职责**：StrategySpec / StrategyRun / StrategyContext / DecisionFrame / DecisionStage Protocol / StrategyPipeline / 内置 Stages / 策略模板

**关键点**：
- StrategySpec 是策略的完整语义契约
- DecisionStage 是 Protocol，Pipeline 通过它分发
- StrategyPipeline 顺序编排 Stages，纯函数无状态
- DecisionFrame（`frame.py`）通过列名约定流转，不做运行时 schema 校验
- Seeds（`seeds.py`）提供策略种子/初始化
- 内置 Stages（8 个）: Universe / Signal / Scoring / Filtering / Selection / RiskLockFilter / TrendFilter / RegimeStage / RegimeAllocationStage / RegimeScoringStage
- `regime_allocation.py` — RegimeAllocationStage（基于 Regime 的资产配置）
- `regime_scoring.py` — RegimeScoringStage（基于 Regime 的评分）
- 4 个策略模板: etf_rotation / etf_trend_swing / stock_sector_rotation / stock_selection_trend
- etf_trend_swing 包含 TrailingStopStage（追踪止损，向量化 polars join）
- `validation.py` 提供 `validate_spec_params()` 独立参数校验函数
- 模块路径：`ditto_strategy.alpha`
- 详见 v3 设计文档 §2, §6.1, §9.1

### Portfolio（组合构建层）

**职责**：WeightAllocator / ConstraintChecker / AllocationStage / ConstraintStage / 组合比较 / 报告视图

**关键点**：
- WeightAllocator Protocol 定义权重分配接口
- EqualWeightAllocator / ScoreWeightAllocator / InverseVolAllocator 三种内置分配策略
- ConstraintChecker 按 priority 升序执行约束
- MaxWeight / MinWeight / MaxPositions 三种内置约束（`constraints.py`）
- AllocationStage / ConstraintStage 是 DecisionStage 适配器
- Comparison（`comparison.py`）提供组合间比较分析
- ReportViews（`report_views.py`）提供报告视图生成
- 详见 v3 设计文档 §2.2, §9.1

### Backtest（回测引擎）

**职责**：EngineLoop / EngineConfig / ProviderBackedDataFeed / BacktestReport / RunManifest / PreTrade / PostTrade / Statistics / Audit / Replay / Pipeline Steps

**关键点**：
- EngineLoop 日历步进回测主循环，逐日推进
- EngineOptions 可选注入 EventBus，关键点发布域事件（OrderSubmitted / OrderFilled / RiskGuardTriggered）
- BacktestTradingOrchestrator = EngineLoop（TradingOrchestrator Protocol 的回测实现）
- Replay（`replay.py`）提供回放控制
- Steps（`steps/` 子包）封装回测 Pipeline 各阶段（10 个 Step）：
  - `_input_bundle.py` — InputBundle 构建
  - `data_fetch.py` — 数据获取
  - `strategy.py` — 策略执行
  - `planning.py` — 交易规划
  - `pre_trade.py` — PreTrade 检查
  - `execution.py` — 订单执行
  - `risk_scan.py` — 风险扫描
  - `audit.py` — 审计收集
  - `types.py` — Step 类型定义
- PreTrade 6 条规则：NoShortSell / PriceValidity / LotSize / BuyingPower / Concentration / DailyTurnover
- PostTrade 4 个 Guard：MaxDrawdown / SingleLoss / Concentration / MarketAnomaly
- BacktestReport 包含 NAV / 收益 / 回撤 / Sharpe / Calmar / CVaR 等指标
- RunManifest 记录运行清单（规则引用、输入引用、配置哈希）
- ExecutionAuditCollector 收集账户快照/成交/风控审计

#### execution_delay 语义

- 基于调仓日（rebalance day）计数，非自然日
- daily rebalance 模式下 1 execution_delay = 1 交易日
- weekly/monthly rebalance 模式下延迟效果与自然日不对应
- 尾部 flush 使用 last_date，为"最佳努力"执行，非 PIT 精确

- 详见 v3 设计文档 §7, §8

### Risk（风险管理）

**职责**：风险模型（回撤检测、风险度量、风险校验）

**关键点**：
- 风险计算逻辑在 Engine
- `_validation.py` 提供风险参数校验
- PreTrade（`pre_trade.py`）执行交易前风险检查
- PostTrade（`post_trade.py`）执行交易后风控守卫
- 告警编排在 App 层
- 指标存储在 Data 层

## 依赖规则

```
┌─────────────────────────────────────┐
│  Engine 可依赖                        │
│  engine → kernel ✅                   │
│  engine → data.errors ✅ (re-export)  │
│  engine → data.provider ✅ (Protocol) │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Engine 禁止依赖                      │
│  engine → data (beyond errors/provider) ❌│
│  engine → analytics ❌                │
│  engine → infra ❌                    │
│  engine → interfaces ❌               │
│  engine → app ❌                      │
└─────────────────────────────────────┘
```

## 代码规范

### 纯函数优先

```python
# ✅ 正确：纯函数，无副作用
def calculate_momentum(prices: pl.DataFrame, window: int) -> pl.Series:
    return prices["close"].pct_change(window)

# ❌ 错误：包含 I/O 操作
def calculate_momentum_and_save(prices: pl.DataFrame) -> None:
    result = prices["close"].pct_change(20)
    save_to_parquet(result, "momentum.parquet")  # 不应在 Engine 层
```

### 无状态设计

```python
# ✅ 正确：无状态，依赖注入
class QualityEngine:
    def __init__(self, checkers: list[Checker]):
        self._checkers = checkers

    def check(self, data: pl.DataFrame) -> list[CheckResult]:
        return [c.check(data) for c in self._checkers]

# ❌ 错误：有状态，持有数据源
class QualityEngine:
    def __init__(self):
        self._store = BarsStore(...)  # 不应持有 Store
```

## 测试规范

### 测试文件位置

```
packages/engine/
├── src/ditto_engine/
└── tests/
    ├── unit/
    │   ├── accounting/
    │   ├── alpha/           # 对应 src/ditto_engine/alpha/
    │   ├── backtest/
    │   ├── engine/          # test_specs_unit.py
    │   ├── execution/
    │   ├── portfolio/
    │   └── risk/
    └── integration/
```

### 运行测试

```bash
pixi run -e dev pytest packages/engine/tests/
```

## 判断决策树

```
问题：这个组件应该放在 Engine 层吗？

1. 是否是业务逻辑/规则？
   YES → Engine 层 ✅

2. 是否是纯计算/算法？
   YES → Engine 层 ✅

3. 是否需要访问数据库/文件？
   YES → Data 层 ❌

4. 是否是流程编排？
   YES → App 层 ❌
```
