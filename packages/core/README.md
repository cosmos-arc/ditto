# ditto-core

> 量化交易系统核心引擎 - 回测引擎、组合管理、策略框架

## 概述

`ditto-core` 是 Ditto 量化系统的核心业务逻辑层，提供：

- **回测引擎**：向量化 Fast 引擎 + 事件驱动 Production 引擎
- **组合管理**：多策略协调、持仓管理、风险控制
- **策略框架**：抽象策略基类、信号生成、订单执行
- **市场识别**：Regime（牛/震荡/熊）引擎 + 自适应阈值
- **因子系统**：多因子计算 + 健康度监控
- **风险管理**：三层 Kill Switch + 回撤速度检测

## 架构定位

```
┌─────────────────────────────────────┐
│         apps/port                 │
│     (FastAPI 服务层)                  │
├─────────────────────────────────────┤
│         ditto-core                  │  ← 当前层
│  ┌──────────┐  ┌──────────┐         │
│  │ Engine   │  │Strategy  │         │
│  │ - Regime │  │- Base    │         │
│  │ - Factor │  │- Signal  │         │
│  │ - Backtest│ │- Order   │         │
│  │ - Risk   │  │          │         │
│  └──────────┘  └──────────┘         │
│  ┌──────────┐                       │
│  │Portfolio │                       │
│  │- Manager │                       │
│  │- Builder │                       │
│  └──────────┘                       │
├─────────────────────────────────────┤
│        ditto-datahub                │
│     (数据访问层)                      │
├─────────────────────────────────────┤
│      ditto-foundation               │
│     (基础设施层)                      │
└─────────────────────────────────────┘
```

**依赖方向**: 仅依赖 `ditto-datahub` 和 `ditto-foundation`

## 核心模块

### Engine - 引擎层

| 模块 | 职责 | 状态 |
|------|------|------|
| `RegimeEngine` | 市场状态识别（牛/震荡/熊）+ 自适应阈值 | 🔄 规划中 |
| `FactorEngine` | 多因子计算（RS/Value/Vol/Crowding） | 🔄 规划中 |
| `RotationEngine` | 行业轮动策略 + TopN 选择 | 🔄 规划中 |
| `FastBacktester` | 向量化回测引擎 | 🔄 规划中 |
| `ProductionBacktester` | 事件驱动回测引擎 | 🔄 规划中 |
| `RiskEngine` | 三层 Kill Switch + 回撤速度检测 | 🔄 规划中 |

### Portfolio - 组合管理层

| 模块 | 职责 | 状态 |
|------|------|------|
| `PortfolioManager` | 多策略协调 + 持仓管理 | 🔄 规划中 |
| `PortfolioBuilder` | 组合构建 + 权重分配 | 🔄 规划中 |
| `PositionManager` | 持仓跟踪 + 盈亏计算 | 🔄 规划中 |

### Strategy - 策略层

| 模块 | 职责 | 状态 |
|------|------|------|
| `Strategy` | 策略抽象基类 | 🔄 规划中 |
| `SignalGenerator` | 信号生成接口 | 🔄 规划中 |
| `OrderExecutor` | 订单执行接口 | 🔄 规划中 |

## 目录结构

```
packages/core/
├── src/
│   └── ditto_core/
│       ├── engine/           # 引擎模块
│       │   ├── regime/       # Regime 识别
│       │   ├── factor/       # 因子计算
│       │   ├── rotation/     # 轮动策略
│       │   ├── backtest/     # 回测引擎
│       │   └── risk/         # 风险管理
│       ├── portfolio/        # 组合管理
│       │   ├── manager/      # 组合管理器
│       │   ├── builder/      # 组合构建器
│       │   └── position/     # 持仓管理
│       └── strategy/         # 策略模块
│           ├── base/         # 策略基类
│           ├── signal/       # 信号生成
│           └── execution/    # 订单执行
├── tests/
│   ├── unit/                 # 单元测试
│   └── integration/          # 集成测试
├── data/                     # 测试数据
└── pyproject.toml
```

## 快速开始

### 安装

```bash
# 通过 pixi 安装（推荐）
pixi install

# 开发模式安装
pip install -e ./packages/core
```

### 基本用法

```python
from ditto_core.engine import RegimeEngine, FactorEngine
from ditto_core.portfolio import PortfolioManager
from ditto_datahub import DataHub

# 初始化 DataHub
hub = DataHub()

# Regime 识别
regime_engine = RegimeEngine(hub)
regime_result = regime_engine.calc_regime_for_range(
    start_date="2024-01-01",
    end_date="2024-01-31",
    index_code="000300.SH"
)
print(regime_result)  # 包含 regime_type, regime_score 等

# 因子计算
factor_engine = FactorEngine(hub)
factors = factor_engine.calc_factors(
    universe=["510300.SH", "510500.SH"],
    start_date="2024-01-01",
    end_date="2024-01-31"
)
print(factors)  # 包含 RS, Value, Vol, Crowding 因子

# 组合管理
portfolio_mgr = PortfolioManager(hub)
portfolio = portfolio_mgr.build_portfolio(
    strategy_name="etf_rotation",
    rebalance_date="2024-01-31",
    regime="bull"
)
print(portfolio.positions)
```

### 回测示例

```python
from ditto_core.engine import FastBacktester
from ditto_core.strategy import RotationStrategy

# 定义策略
strategy = RotationStrategy(
    top_n=3,
    rebalance_freq="monthly"
)

# 运行回测
backtester = FastBacktester(hub)
result = backtester.run(
    strategy=strategy,
    start_date="2023-01-01",
    end_date="2024-01-31",
    initial_capital=1_000_000
)

# 查看结果
print(f"总收益: {result.total_return:.2%}")
print(f"年化收益: {result.annual_return:.2%}")
print(f"最大回撤: {result.max_drawdown:.2%}")
print(f"夏普比率: {result.sharpe_ratio:.2f}")
```

## 核心设计原则

### 1. PIT 安全

所有引擎计算必须遵守 Point-in-Time 安全原则：

```python
# ✅ 正确：使用 PIT 过滤
df = hub.bars.get(
    sids=[1, 2],
    start="2024-01-01",
    end="2024-01-31",
    asof="2024-01-15"  # 只使用该时点之前的数据
)

# ❌ 错误：使用未来数据
df = hub.bars.get(
    sids=[1, 2],
    start="2024-01-01",
    end="2024-01-31"
)
```

### 2. 涨跌停感知

回测引擎必须过滤涨跌停无法成交的情况：

```python
# 检查涨跌停
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

# ✅ 推荐：向量化计算
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

### 4. 双引擎对齐

Fast 与 Production 引擎必须对齐，误差 ≤ 0.1%：

```python
# 运行双引擎
fast_result = FastBacktester(hub).run(strategy, ...)
prod_result = ProductionBacktester(hub).run(strategy, ...)

# 验证对齐
assert abs(fast_result.total_return - prod_result.total_return) < 0.001
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

**三层 Kill Switch**（按风险宪法）：

| Level | 触发条件 | 操作 | 恢复条件 |
|-------|---------|------|----------|
| 1 | 回撤 ≥ 10% | 停止新开仓 | 回撤 < 8% |
| 2 | 回撤 ≥ 18% | 强制减仓 50% | 人工确认 |
| 3 | 回撤 ≥ 20% | 强制清仓 | 策略重构评审 |

**仓位限制**（Regime驱动）：

| Regime | 总仓位 | 单票上限 |
|--------|--------|----------|
| Bull   | 70-90% | 15% |
| Osc    | 50-70% | 12% |
| Bear   | 10-40% | 10% |

## 开发

### 运行测试

```bash
# 单元测试（快速）
pixi run -e dev pytest packages/core/tests/unit

# 集成测试
pixi run -e dev pytest packages/core/tests/integration

# 完整测试（带覆盖率）
pixi run -e dev pytest packages/core/tests --cov=ditto_core
```

### 代码质量检查

```bash
# 快速检查
pixi run -e dev quick-check

# 提交前检查
pixi run -e dev pre-commit-run

# 完整 CI 检查
pixi run -e dev ci-check
```

### TDD 开发流程

1. **RED**: 编写失败测试
2. **GREEN**: 最小实现通过测试
3. **REFACTOR**: 重构优化代码

```python
# 示例：测试 RegimeEngine
def test_regime_engine_bull_market():
    # Arrange
    engine = RegimeEngine(hub)
    start = date(2024, 1, 1)
    end = date(2024, 1, 31)

    # Act
    result = engine.calc_regime_for_range(start, end)

    # Assert
    assert "regime_type" in result.columns
    assert result["regime_type"].is_in(["bull", "osc", "bear"]).all()
```

## 相关文档

- [引擎设计文档](../../../docs/design/03_engine_design.md)
- [风险宪法](../../../docs/design/08_risk_constitution.md)
- [系统设计总览](../../../docs/design/01_system_design.md)
- [数据层设计](../../../docs/design/02_data_design.md)
- [PIT 安全指南](../../../.claude/skills/pit-guide/SKILL.md)
- [Polars 使用指南](../../../.claude/skills/polars-guide/SKILL.md)

## 许可证

MIT License
