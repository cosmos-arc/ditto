# 单元测试

## 测试框架

- pytest
- pytest-mock (Mock 工具)
- polars (数据处理)

## 测试覆盖

### Engine - 引擎模块单元测试

| 测试文件 | 测试范围 |
|---------|----------|
| `test_regime_detector.py` | 市场状态检测逻辑 |
| `test_adaptive_threshold.py` | 自适应阈值计算 |
| `test_confirmation.py` | 确认期机制 |
| `test_relative_strength.py` | 相对强弱因子计算 |
| `test_value_factor.py` | 估值因子计算 |
| `test_volatility_factor.py` | 波动率因子计算 |
| `test_crowding_factor.py` | 拥挤度因子计算 |
| `test_factor_monitor.py` | 因子健康度监控 |
| `test_rotation_scorer.py` | 多因子打分逻辑 |
| `test_rotation_selector.py` | TopN 选择逻辑 |
| `test_backtester.py` | 回测引擎核心逻辑 |
| `test_kill_switch.py` | Kill Switch 逻辑 |
| `test_drawdown.py` | 回撤计算逻辑 |

### Portfolio - 组合管理模块单元测试

| 测试文件 | 测试范围 |
|---------|----------|
| `test_portfolio_mgr.py` | 组合管理器核心逻辑 |
| `test_rebalance_mgr.py` | 调仓管理逻辑 |
| `test_risk_mgr.py` | 风险控制逻辑 |
| `test_weight_allocator.py` | 权重分配逻辑 |
| `test_position_sizer.py` | 仓位计算逻辑 |
| `test_trade_generator.py` | 交易生成逻辑 |
| `test_position_tracker.py` | 持仓跟踪逻辑 |
| `test_pnl_calc.py` | 盈亏计算逻辑 |

### Strategy - 策略模块单元测试

| 测试文件 | 测试范围 |
|---------|----------|
| `test_strategy.py` | 策略基类逻辑 |
| `test_strategy_state.py` | 策略状态管理 |
| `test_regime_signal.py` | Regime 信号生成 |
| `test_factor_signal.py` | 因子信号生成 |
| `test_composite_signal.py` | 组合信号生成 |
| `test_order_executor.py` | 订单执行逻辑 |
| `test_order.py` | 订单定义和验证 |
| `test_fill.py` | 成交模拟逻辑 |
| `test_cost.py` | 交易成本计算 |

## 运行测试

### 运行所有单元测试

```bash
pixi run -e dev pytest packages/core/tests/unit -v
```

### 运行特定模块测试

```bash
# 运行引擎模块测试
pixi run -e dev pytest packages/core/tests/unit/test_regime*.py -v

# 运行因子模块测试
pixi run -e dev pytest packages/core/tests/unit/test_*factor*.py -v

# 运行组合管理测试
pixi run -e dev pytest packages/core/tests/unit/test_portfolio*.py -v

# 运行策略模块测试
pixi run -e dev pytest packages/core/tests/unit/test_strategy*.py -v
```

### 运行特定测试函数

```bash
# 运行单个测试
pixi run -e dev pytest packages/core/tests/unit/test_regime_detector.py::test_regime_bull_market -v

# 运行包含特定关键字的测试
pixi run -e dev pytest packages/core/tests/unit -k "regime" -v
```

### 带覆盖率运行

```bash
# 生成覆盖率报告
pixi run -e dev pytest packages/core/tests/unit --cov=ditto_core --cov-report=term-missing

# 生成 HTML 覆盖率报告
pixi run -e dev pytest packages/core/tests/unit --cov=ditto_core --cov-report=html
```

## 测试示例

### Regime 引擎测试

```python
import pytest
from datetime import date
from ditto_core.engine.regime import RegimeEngine

@pytest.mark.unit
def test_regime_engine_initialization(hub):
    """测试 RegimeEngine 初始化"""
    engine = RegimeEngine(hub)
    assert engine is not None
    assert engine.TREND_WEIGHT == 0.4
    assert engine.MOMENTUM_WEIGHT == 0.3

@pytest.mark.unit
def test_calc_trend_score(hub):
    """测试趋势得分计算"""
    engine = RegimeEngine(hub)
    df = engine._calc_trend_score(test_df)

    assert "trend_score" in df.columns
    assert df["trend_score"].min() >= 0
    assert df["trend_score"].max() <= 1

@pytest.mark.unit
@pytest.mark.parametrize("regime,expected_min,expected_max", [
    ("bull", 0.7, 0.9),
    ("osc", 0.5, 0.7),
    ("bear", 0.1, 0.4),
])
def test_regime_classification(regime, expected_min, expected_max):
    """测试 Regime 分类逻辑"""
    # 测试不同 Regime 的得分范围
    assert expected_min <= get_regime_score(regime) <= expected_max
```

### 因子引擎测试

```python
@pytest.mark.unit
def test_calc_rs_factor(hub):
    """测试相对强弱因子计算"""
    engine = FactorEngine(hub)
    factors = engine._calc_rs_factor(test_df)

    assert "rs_factor" in factors.columns
    assert factors["rs_factor"].is_not_null().all()
    assert factors["rs_factor"].min() >= -1
    assert factors["rs_factor"].max() <= 1

@pytest.mark.unit
def test_factor_health_check(hub):
    """测试因子健康度检查"""
    engine = FactorEngine(hub)
    factors = engine.calc_factors(["510300.SH"], date(2024, 1, 31))

    health = engine.check_health(factors)
    assert health.is_healthy
    assert len(health.missing_factors) == 0
    assert len(health.outliers) == 0
```

### 组合管理测试

```python
@pytest.mark.unit
def test_portfolio_manager_initialization(hub):
    """测试组合管理器初始化"""
    mgr = PortfolioManager(hub, initial_capital=1_000_000)
    assert mgr.initial_capital == 1_000_000
    assert mgr.total_value == 1_000_000
    assert mgr.available_cash == 1_000_000

@pytest.mark.unit
def test_add_strategy(hub):
    """测试添加策略"""
    mgr = PortfolioManager(hub, initial_capital=1_000_000)
    strategy = RotationStrategy(top_n=3)

    mgr.add_strategy(strategy, allocation=0.6)
    assert len(mgr.strategies) == 1
    assert mgr.strategies[0].allocation == 0.6

@pytest.mark.unit
def test_build_equal_weighted_portfolio(hub):
    """测试等权组合构建"""
    builder = PortfolioBuilder(hub)
    portfolio = builder.build_equal_weighted(
        targets=["510300.SH", "510500.SH", "512000.SH"],
        total_capital=600_000,
        max_single_position=0.15
    )

    assert len(portfolio.positions) == 3
    for pos in portfolio.positions:
        assert pos.weight <= 0.15
```

### 策略测试

```python
@pytest.mark.unit
def test_strategy_initialization(hub):
    """测试策略初始化"""
    strategy = RotationStrategy(hub, top_n=3)
    assert strategy.name == "rotation"
    assert strategy.top_n == 3
    assert strategy.state is not None

@pytest.mark.unit
def test_generate_buy_signals(hub):
    """测试生成买入信号"""
    strategy = RotationStrategy(hub, top_n=3)
    signals = strategy.generate_signals(date(2024, 1, 31))

    assert all(s.action == SignalAction.BUY for s in signals)
    assert len(signals) == 3

@pytest.mark.unit
def test_generate_orders_from_signals(hub):
    """测试从信号生成订单"""
    strategy = RotationStrategy(hub, top_n=3)
    signals = [
        Signal(symbol="510300.SH", action=SignalAction.BUY, weight=0.33),
        Signal(symbol="510500.SH", action=SignalAction.BUY, weight=0.33),
    ]

    orders = strategy.generate_orders(signals, date(2024, 1, 31))
    assert len(orders) == 2
    assert all(o.action == OrderAction.BUY for o in orders)
```

### 订单执行测试

```python
@pytest.mark.unit
def test_order_executor_market_order(hub):
    """测试市价单执行"""
    executor = SimpleOrderExecutor(hub)
    order = Order(
        symbol="510300.SH",
        action=OrderAction.BUY,
        quantity=1000,
        order_type=OrderType.MARKET
    )

    fills = executor.execute([order], date(2024, 1, 31))
    assert len(fills) == 1
    assert fills[0].quantity == 1000
    assert fills[0].price > 0

@pytest.mark.unit
def test_calc_commission():
    """测试佣金计算"""
    executor = SimpleOrderExecutor(hub)
    fill = Fill(
        symbol="510300.SH",
        action=OrderAction.BUY,
        quantity=1000,
        price=4.5,
        trade_date=date(2024, 1, 31)
    )

    commission = executor._calc_commission(fill)
    expected_commission = 1000 * 4.5 * 0.0003  # 万三佣金
    assert commission == expected_commission
```

### 回测引擎测试

```python
@pytest.mark.unit
def test_backtester_initialization(hub):
    """测试回测引擎初始化"""
    backtester = FastBacktester(hub)
    assert backtester is not None

@pytest.mark.unit
def test_calc_daily_returns(hub):
    """测试日收益率计算"""
    backtester = FastBacktester(hub)
    portfolio_values = [1000000, 1010000, 1005000, 1020000]

    returns = backtester._calc_daily_returns(portfolio_values)
    assert len(returns) == 3
    assert abs(returns[0] - 0.001) < 1e-6

@pytest.mark.unit
def test_calc_max_drawdown(hub):
    """测试最大回撤计算"""
    backtester = FastBacktester(hub)
    portfolio_values = [1000000, 1050000, 950000, 900000, 950000]

    max_dd = backtester._calc_max_drawdown(portfolio_values)
    assert abs(max_dd - 0.142857) < 1e-6  # (1050000 - 900000) / 1050000
```

### 风险管理测试

```python
@pytest.mark.unit
def test_kill_switch_level1():
    """测试 Level 1 Kill Switch"""
    risk_engine = RiskEngine(hub)
    risk_status = risk_engine.check_risk(
        portfolio_value=900_000,
        peak_value=1_000_000,
        initial_capital=1_000_000
    )

    assert risk_status.level == 1
    assert risk_status.action == "stop_new_open"
    assert risk_status.recovery_condition == "drawdown < 0.08"

@pytest.mark.unit
def test_drawdown_speed_detection():
    """测试回撤速度检测"""
    risk_engine = RiskEngine(hub)
    speed_check = risk_engine.check_drawdown_speed(
        current_drawdown=0.15,
        days_from_peak=5
    )

    assert speed_check.is_too_fast == True
    assert speed_check.drawdown_per_day == 0.03  # 0.15 / 5
```

## Mock 使用示例

### Mock DataHub

```python
from unittest.mock import Mock
import polars as pl

@pytest.fixture
def mock_hub():
    """创建 Mock DataHub"""
    hub = Mock()
    hub.sources.bars.get.return_value = pl.DataFrame({
        "symbol": ["510300.SH", "510500.SH"],
        "close": [4.5, 4.2],
        "trade_date": [date(2024, 1, 31), date(2024, 1, 31)]
    })
    return hub

def test_with_mock_hub(mock_hub):
    """使用 Mock hub 进行测试"""
    engine = RegimeEngine(mock_hub)
    result = engine.calc_regime_for_range(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31)
    )

    mock_hub.sources.bars.get.assert_called_once()
    assert result is not None
```

### Patch 外部依赖

```python
from unittest.mock import patch

@pytest.mark.unit
@patch('ditto_core.engine.regime.fetch_index_data')
def test_regime_with_patch(mock_fetch):
    """使用 patch 测试"""
    mock_fetch.return_value = test_df

    engine = RegimeEngine(hub)
    result = engine.calc_regime_for_range(date(2024, 1, 1), date(2024, 1, 31))

    mock_fetch.assert_called_once()
    assert result is not None
```

## 测试最佳实践

### 1. AAA 模式

```python
def test_something():
    # Arrange - 准备测试数据
    hub = create_mock_hub()
    engine = RegimeEngine(hub)

    # Act - 执行被测试的功能
    result = engine.calc_regime(date(2024, 1, 31))

    # Assert - 验证结果
    assert result.regime_type == "bull"
```

### 2. 使用 Fixture

```python
@pytest.fixture
def regime_engine(hub):
    """创建 RegimeEngine 实例"""
    return RegimeEngine(hub)

def test_with_fixture(regime_engine):
    """使用 fixture 进行测试"""
    result = regime_engine.calc_regime(date(2024, 1, 31))
    assert result is not None
```

### 3. 参数化测试

```python
@pytest.mark.parametrize("input_value,expected", [
    (0.8, "bull"),
    (0.5, "osc"),
    (0.2, "bear"),
])
def test_regime_classification(input_value, expected):
    """参数化测试 Regime 分类"""
    result = classify_regime(input_value)
    assert result == expected
```

## 相关文档

- [集成测试说明](../integration/README.md)
- [测试总说明](../README.md)
- [Python 测试最佳实践](../../../../.claude/skills/python-testing-patterns/SKILL.md)
