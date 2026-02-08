# 引擎模块

**版本**: v0.2.0
**最后更新**: 2026-01-23
**状态**: 🔄 开发中

## 概要

核心量化引擎 - Regime 识别、因子计算、轮动策略、回测、风控，是 Ditto 量化系统的核心计算层。

## 核心功能

引擎模块是 Ditto 量化系统的核心计算层，负责市场状态识别、因子计算、策略执行、回测验证和风险管理。

## 目录结构

```
engine/
├── regime/           # Regime 识别引擎
│   ├── detector.py   # 市场状态检测器
│   ├── adaptive.py   # 自适应阈值计算
│   └── confirmation.py # 确认期机制
├── factor/           # 因子计算引擎
│   ├── relative_strength.py # 相对强弱因子
│   ├── value.py      # 估值因子
│   ├── volatility.py # 波动率因子
│   ├── crowding.py   # 拥挤度因子
│   └── monitor.py    # 因子健康度监控
├── rotation/         # 轮动策略引擎
│   ├── scorer.py     # 多因子打分
│   ├── selector.py   # TopN 选择
│   └── rebalancer.py # 调仓执行
├── backtest/         # 回测引擎
│   ├── fast.py       # 向量化回测引擎
│   ├── production.py # 事件驱动回测引擎
│   └── alignment.py  # 双引擎对齐验证
└── risk/             # 风险管理引擎
    ├── kill_switch.py # 三层 Kill Switch
    ├── drawdown.py   # 回撤计算
    ├── position_limit.py # 仓位限制
    └── speed_detector.py # 回撤速度检测
```

## 核心功能

### Regime 识别引擎

**功能**: 将市场状态分为三类（`bull` / `osc` / `bear`）

**核心特性**:
- 自适应阈值（基于历史分位数，非硬编码）
- 确认期机制（避免频繁切换）
- 多维度评分（趋势 + 动量 + 波动率 + 宽度）

**使用示例**:

```python
from ditto_core.engine.regime import RegimeEngine

engine = RegimeEngine(hub)

# 计算一段时间内的 Regime
result = engine.calc_regime_for_range(
    start_date="2024-01-01",
    end_date="2024-01-31",
    index_code="000300.SH"
)

# 结果包含
# - regime_type: 'bull' / 'osc' / 'bear'
# - regime_score: 0-1 综合得分
# - trend_score, momentum_score, volatility_score, width_score
# - bull_threshold, bear_threshold (自适应阈值)
# - is_confirmed: 是否经过确认期
```

**维度权重**:
- 趋势 (Trend): 40%
- 动量 (Momentum): 30%
- 波动率 (Volatility): 20%
- 宽度 (Width): 10%

### 因子计算引擎

**功能**: 计算多因子用于行业轮动决策

**支持的因子**:

| 因子 | 说明 | 计算方法 |
|------|------|----------|
| **RS** (相对强弱) | 相对沪深300的超额收益 | 20/60日收益率差值 |
| **Value** (估值) | 行业指数PE/PB分位数 | 历史分位数归一化 |
| **Vol** (波动率) | 价格波动率惩罚 | 年化波动率，低波动优 |
| **Crowding** (拥挤度) | 成交额和溢价率指标 | 综合评分 |

**使用示例**:

```python
from ditto_core.engine.factor import FactorEngine

engine = FactorEngine(hub)

# 计算因子
factors = engine.calc_factors(
    universe=["510300.SH", "510500.SH", "512000.SH"],
    start_date="2024-01-01",
    end_date="2024-01-31"
)

# 结果包含
# - rs_factor: 相对强弱因子
# - value_factor: 估值因子
# - vol_factor: 波动率因子
# - crowding_factor: 拥挤度因子
# - composite_score: 综合得分

# 因子健康度检查
health = engine.check_health(factors)
if not health.is_healthy:
    logger.warning(f"因子健康度异常: {health.issues}")
```

### 轮动策略引擎

**功能**: 多因子加权打分与 TopN 选择

**核心逻辑**:
1. 计算各因子得分（归一化到 0-1）
2. 按权重加权求和
3. TopN 选择
4. 权重分配（等权或 Score 加权）

**使用示例**:

```python
from ditto_core.engine.rotation import RotationEngine

engine = RotationEngine(
    hub=hub,
    factor_weights={
        "rs": 0.3,
        "value": 0.3,
        "vol": 0.2,
        "crowding": 0.2
    },
    top_n=3
)

# 生成调仓计划
plan = engine.generate_rebalance_plan(
    universe=["510300.SH", "510500.SH", ...],
    rebalance_date="2024-01-31",
    regime="bull"
)

# 结果包含
# - selected_etfs: 选中的 ETF 列表
# - weights: 各 ETF 的目标权重
# - rebalance_trades: 调仓交易列表
```

### 回测引擎

**双引擎架构**:

| 引擎 | 类型 | 用途 | 特点 |
|------|------|------|------|
| **FastBacktester** | 向量化 | 研究阶段 | 快速迭代，策略验证 |
| **ProductionBacktester** | 事件驱动 | 生产前验证 | 模拟实盘，精确成交 |

**FastBacktester 使用示例**:

```python
from ditto_core.engine.backtest import FastBacktester
from ditto_core.strategy import RotationStrategy

strategy = RotationStrategy(
    top_n=3,
    rebalance_freq="monthly",
    factor_weights={"rs": 0.3, "value": 0.3, "vol": 0.2, "crowding": 0.2}
)

backtester = FastBacktester(hub)
result = backtester.run(
    strategy=strategy,
    start_date="2023-01-01",
    end_date="2024-01-31",
    initial_capital=1_000_000
)

# 结果分析
print(f"总收益: {result.total_return:.2%}")
print(f"年化收益: {result.annual_return:.2%}")
print(f"最大回撤: {result.max_drawdown:.2%}")
print(f"夏普比率: {result.sharpe_ratio:.2f}")
print(f"胜率: {result.win_rate:.2%}")
```

**ProductionBacktester 使用示例**:

```python
from ditto_core.engine.backtest import ProductionBacktester

backtester = ProductionBacktester(hub)
result = backtester.run(
    strategy=strategy,
    start_date="2023-01-01",
    end_date="2024-01-31",
    initial_capital=1_000_000
)

# 事件驱动引擎会模拟:
# - 涨跌停过滤
# - 实际成交价格
# - 流动性约束
# - 交易成本
```

**双引擎对齐验证**:

```python
from ditto_core.engine.backtest import alignment

# 运行双引擎
fast_result = FastBacktester(hub).run(strategy, ...)
prod_result = ProductionBacktester(hub).run(strategy, ...)

# 验证对齐
alignment_result = alignment.verify(fast_result, prod_result)

# 误差必须 ≤ 0.1%
assert alignment_result.return_diff < 0.001
assert alignment_result.drawdown_diff < 0.001
```

### 风险管理引擎

**三层 Kill Switch**:

| Level | 触发条件 | 操作 | 恢复条件 |
|-------|---------|------|----------|
| 1 | 回撤 ≥ 10% | 停止新开仓 | 回撤 < 8% |
| 2 | 回撤 ≥ 18% | 强制减仓 50% | 人工确认 |
| 3 | 回撤 ≥ 20% | 强制清仓 | 策略重构评审 |

**使用示例**:

```python
from ditto_core.engine.risk import RiskEngine

engine = RiskEngine(hub)

# 检查风险状态
risk_status = engine.check_risk(
    portfolio_value=900_000,
    peak_value=1_000_000,
    initial_capital=1_000_000
)

# 根据风险状态执行操作
if risk_status.level == 1:
    logger.warning("Level 1 Kill Switch: 停止新开仓")
    # 停止新开仓
elif risk_status.level == 2:
    logger.error("Level 2 Kill Switch: 强制减仓 50%")
    # 强制减仓
elif risk_status.level == 3:
    logger.critical("Level 3 Kill Switch: 强制清仓")
    # 强制清仓
```

**回撤速度检测**:

```python
# 检测回撤速度（是否超过阈值）
speed_check = engine.check_drawdown_speed(
    current_drawdown=0.15,
    days_from_peak=5
)

if speed_check.is_too_fast:
    logger.warning(f"回撤速度过快: {speed_check.drawdown_per_day:.2%}/天")
    # 触发早期预警
```

**仓位限制**:

```python
# 根据 Regime 获取仓位限制
position_limit = engine.get_position_limit(regime="bull")
print(f"最大总仓位: {position_limit.max_total_position}")
print(f"单票上限: {position_limit.max_single_position}")

# 验证仓位合规
compliance = engine.check_position_compliance(
    portfolio=portfolio,
    regime="bull"
)

if not compliance.is_compliant:
    logger.error(f"仓位违规: {compliance.violations}")
```

## 依赖关系

- **上游**: `ditto-datahub` (数据访问)、`ditto-foundation` (基础设施)
- **下游**: `ditto-core.portfolio` (组合管理)、`ditto-core.strategy` (策略层)

## 核心设计原则

### 1. PIT 安全

所有计算必须遵守 Point-in-Time 安全原则：

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

回测引擎必须过滤涨跌停无法成交的情况：

```python
def is_limit_price(bar: Bar) -> bool:
    return bar.close == bar.high or bar.close == bar.low

# 过滤无法成交的订单
filtered_orders = [
    order for order in orders
    if not is_limit_price(order.bar)
]
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

## 相关文档

- [引擎设计文档](../../../../docs/design/03_engine_design.md)
- [风险宪法](../../../../docs/design/08_risk_constitution.md)
- [PIT 安全指南](../../../../.claude/skills/pit-guide/SKILL.md)
- [Polars 使用指南](../../../../.claude/skills/polars-guide/SKILL.md)
