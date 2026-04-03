# Core 层架构规范

## 定位

Core 层是 **Domain Layer（领域层）**，包含量化系统的核心业务逻辑、领域知识和算法。

**核心原则**：
- 纯业务逻辑，无 I/O 操作
- 无状态计算，可独立测试
- 依赖 DataHub 获取数据，依赖 Infra 获取基础设施

## 模块结构

```
ditto_engine/
├── quality/           # 数据质量引擎（已实现）
│   ├── checkers/      # DQ 检查器
│   │   ├── technical.py    # L1 技术检查
│   │   ├── business.py     # L2 业务检查
│   │   ├── statistical.py  # L3 统计检查
│   │   └── cross_source.py # 跨源检查
│   ├── engine.py      # DQ 引擎
│   ├── spec.py        # 规则配置模型
│   ├── config.py      # DQ 配置
│   ├── report.py      # 检查报告
│   └── severity.py    # 严重程度
├── engine/            # 核心引擎（表达式编译器、因子定义、评估指标、物化模型）
├── accounting/        # 共享账户契约层（Account / CashBook / OrderBook / Position）
├── execution/         # 执行层（Planner / Brokerage / TradeBuilder / Reality Model）
├── strategy/          # 策略决策层（StrategySpec / Pipeline / 内置 Stages / 策略模板）
├── backtest/          # 回测引擎（EngineLoop / Manifest / Statistics / Audit / Serialization）
└── portfolio/         # 组合构建（WeightAllocator / ConstraintChecker / compare_reports）
```

## 子领域规范

### Quality（数据质量）

**职责**：检查规则算法（OHLC、涨跌停、成交量异常）

| 检查层级 | 职责 | 示例 |
|---------|------|------|
| L1 Technical | 技术校验 | 非空、唯一、外键 |
| L2 Business | 业务规则 | OHLC 一致性、涨跌幅限制 |
| L3 Statistical | 统计异常 | Z-score、完整性 |
| Cross Source | 跨源校验 | 价格与指数对齐 |

**关键点**：
- DQ 是量化业务规则，不是通用技术约束
- 配置文件（YAML）定义业务规则
- 检查逻辑在 Core，编排流程在 Port，结果存储在 DataHub

### Factor（因子计算）

**职责**：因子计算算法（RS、动量、波动率）

**关键点**：
- 计算逻辑在 Core（纯函数、无状态）
- 编排流程在 Application（获取数据、调用计算、保存结果）
- 存储在 DataHub（parquet 文件）

### Accounting（共享账户契约层）

**职责**：Position / CashBook / OrderBook / Account / AccountView / BuyingPowerModel

**关键点**：
- 纯数据结构层，frozen dataclass + Protocol
- Account 是唯一可变对象（内部替换 frozen 引用）
- AccountView 是只读快照，供上层安全消费
- 详见 v3 设计文档 §3.1-§3.6

### Execution（执行层）

**职责**：ExecutionPlanner / BacktestBrokerage / TradeBuilder / Reality Model / InstrumentDefinition / FillOutcome

**关键点**：
- InstrumentDefinition / TradingRuleSet / FeeSchedule 是 frozen dataclass
- FillOutcome 是显式联合类型（Filled / NoFill）
- BacktestBrokerage 实现 T+1 冻结逻辑和批内滚动更新
- TradeBuilder 支持 FIFO / FlatToFlat 两种匹配方式
- Reality Model 处理佣金/滑点/成交/结算
- 详见 v3 设计文档 §4.3, §5.1

### Strategy（策略决策层）

**职责**：StrategySpec / StrategyRun / StrategyContext / DecisionStage Protocol / StrategyPipeline / 内置 Stages / 策略模板

**关键点**：
- StrategySpec 是策略的完整语义契约
- DecisionStage 是 Protocol，Pipeline 通过它分发
- StrategyPipeline 顺序编排 Stages，纯函数无状态
- 内置 Stages: Universe / Signal / Scoring / Filtering / Selection / RiskLockFilter / TrendFilter / RegimeStage
- 4 个策略模板: etf_rotation / etf_trend_swing / stock_sector_rotation / stock_selection_trend
- etf_trend_swing 包含 TrailingStopStage（追踪止损，向量化 polars join）
- DecisionFrame 通过列名约定流转，不做运行时 schema 校验
- `validation.py` 提供 `validate_spec_params()` 独立参数校验函数
- 详见 v3 设计文档 §2, §6.1, §9.1

### Portfolio（组合构建层）

**职责**：WeightAllocator / ConstraintChecker / AllocationStage / ConstraintStage

**关键点**：
- WeightAllocator Protocol 定义权重分配接口
- EqualWeightAllocator / ScoreWeightAllocator / InverseVolAllocator 三种内置分配策略
- ConstraintChecker 按 priority 升序执行约束
- MaxWeight / MinWeight / MaxPositions 三种内置约束
- AllocationStage / ConstraintStage 是 DecisionStage 适配器
- 详见 v3 设计文档 §2.2, §9.1

### Backtest（回测引擎）

**职责**：EngineLoop / EngineConfig / ProviderBackedDataFeed / BacktestReport / RunManifest / PreTrade / PostTrade / Statistics / Audit / Serialization

**关键点**：
- EngineLoop 日历步进回测主循环，逐日推进
- PreTrade 6 条规则：NoShortSell / PriceValidity / LotSize / BuyingPower / Concentration / DailyTurnover
- PostTrade 4 个 Guard：MaxDrawdown / SingleLoss / Concentration / MarketAnomaly
- BacktestReport 包含 NAV / 收益 / 回撤 / Sharpe / Calmar / CVaR 等指标
- RunManifest 记录运行清单（规则引用、输入引用、配置哈希）
- ExecutionAuditCollector 收集账户快照/成交/风控审计
- BacktestReportSerializer 支持 SQLite 存储
- 详见 v3 设计文档 §7, §8

### Risk（风险管理）

**职责**：风险模型（回撤检测、风险度量）

**关键点**：
- 风险计算逻辑在 Core
- 告警编排在 Port
- 指标存储在 DataHub

## 依赖规则

```
┌─────────────────────────────────────┐
│  Core 可依赖                        │
│  core → datahub ✅                  │
│  core → infra ✅                    │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Core 禁止依赖                      │
│  core → port ❌                     │
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
    save_to_parquet(result, "momentum.parquet")  # 不应在 Core 层
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
    │   ├── backtest/
    │   ├── engine/
    │   ├── execution/
    │   ├── portfolio/
    │   ├── quality/
    │   └── strategy/
    └── integration/
```

### 运行测试

```bash
pixi run -e dev pytest packages/engine/tests/
```

## 判断决策树

```
问题：这个组件应该放在 Core 层吗？

1. 是否是业务逻辑/规则？
   YES → Core 层 ✅

2. 是否是纯计算/算法？
   YES → Core 层 ✅

3. 是否需要访问数据库/文件？
   YES → DataHub 层 ❌

4. 是否是流程编排？
   YES → Port 层 ❌
```
