# 集成测试

## 测试框架

- pytest
- polars (数据处理)
- pytest-asyncio (异步测试)

## 测试覆盖

### 完整回测流程测试

**文件**: `test_backtest_flow.py`

**测试场景**:
- 策略初始化 → 信号生成 → 订单执行 → 持仓更新 → 结果分析
- Fast 引擎回测完整流程
- Production 引擎回测完整流程
- 双引擎结果对齐验证

**示例**:

```python
@pytest.mark.integration
@pytest.mark.slow
def test_full_backtest_flow():
    """测试完整回测流程"""
    # Arrange
    hub = DataHub()
    strategy = RotationStrategy(top_n=3)
    backtester = FastBacktester(hub)

    # Act
    result = backtester.run(
        strategy=strategy,
        start_date="2023-01-01",
        end_date="2024-01-31",
        initial_capital=1_000_000
    )

    # Assert
    assert result.start_date == date(2023, 1, 1)
    assert result.end_date == date(2024, 1, 31)
    assert result.initial_capital == 1_000_000
    assert result.final_value > 0
    assert len(result.trades) > 0
    assert len(result.daily_returns) > 0
```

### 调仓流程测试

**文件**: `test_rebalance_flow.py`

**测试场景**:
- 信号生成 → 订单生成 → 订单执行 → 持仓更新
- 不同 Regime 下的调仓行为
- 涨跌停过滤
- 交易成本计算

**示例**:

```python
@pytest.mark.integration
def test_rebalance_flow():
    """测试调仓流程"""
    # Arrange
    hub = DataHub()
    portfolio_mgr = PortfolioManager(hub)
    portfolio_mgr.add_strategy(RotationStrategy(top_n=3))

    # Act
    result = portfolio_mgr.rebalance(
        rebalance_date=date(2024, 1, 31),
        regime="bull"
    )

    # Assert
    assert len(result.trades) > 0
    assert result.estimated_cost > 0
    assert all(t.status == "executed" for t in result.trades)
```

### 风控流程测试

**文件**: `test_risk_flow.py`

**测试场景**:
- 回撤计算 → Kill Switch 触发 → 仓位调整
- 三层 Kill Switch 机制
- 回撤速度检测
- 仓位限制检查

**示例**:

```python
@pytest.mark.integration
def test_kill_switch_level1():
    """测试 Level 1 Kill Switch"""
    # Arrange
    hub = DataHub()
    risk_engine = RiskEngine(hub)
    portfolio = create_test_portfolio(value=900_000, peak=1_000_000)

    # Act
    risk_status = risk_engine.check_risk(
        portfolio_value=portfolio.value,
        peak_value=portfolio.peak_value,
        initial_capital=1_000_000
    )

    # Assert
    assert risk_status.level == 1
    assert risk_status.action == "stop_new_open"
    assert risk_status.recovery_condition == "drawdown < 0.08"
```

### 双引擎对齐测试

**文件**: `test_engine_alignment.py`

**测试场景**:
- Fast 引擎 vs Production 引擎
- 收益率对齐（误差 ≤ 0.1%）
- 回撤对齐（误差 ≤ 0.1%）
- 交易数量对齐

**示例**:

```python
@pytest.mark.integration
@pytest.mark.slow
def test_fast_vs_production_alignment():
    """测试 Fast 与 Production 引擎对齐"""
    # Arrange
    hub = DataHub()
    strategy = RotationStrategy(top_n=3)
    fast_engine = FastBacktester(hub)
    prod_engine = ProductionBacktester(hub)

    # Act
    fast_result = fast_engine.run(strategy, date(2023, 1, 1), date(2024, 1, 31))
    prod_result = prod_engine.run(strategy, date(2023, 1, 1), date(2024, 1, 31))

    # Assert
    return_diff = abs(fast_result.total_return - prod_result.total_return)
    drawdown_diff = abs(fast_result.max_drawdown - prod_result.max_drawdown)

    assert return_diff < 0.001, f"收益率差异过大: {return_diff:.4f}"
    assert drawdown_diff < 0.001, f"回撤差异过大: {drawdown_diff:.4f}"
```

### 因子计算集成测试

**文件**: `test_factor_integration.py`

**测试场景**:
- 多因子计算流程
- 因子健康度检查
- 因子缺失处理

**示例**:

```python
@pytest.mark.integration
def test_factor_calculation_flow():
    """测试因子计算流程"""
    # Arrange
    hub = DataHub()
    factor_engine = FactorEngine(hub)
    universe = ["510300.SH", "510500.SH", "512000.SH"]

    # Act
    factors = factor_engine.calc_factors(
        universe=universe,
        start_date="2024-01-01",
        end_date="2024-01-31"
    )

    # Assert
    assert "rs_factor" in factors.columns
    assert "value_factor" in factors.columns
    assert "vol_factor" in factors.columns
    assert "crowding_factor" in factors.columns
    assert "composite_score" in factors.columns

    # 检查健康度
    health = factor_engine.check_health(factors)
    assert health.is_healthy
```

## 运行测试

### 运行所有集成测试

```bash
pixi run -e dev pytest packages/core/tests/integration -v
```

### 运行特定集成测试

```bash
# 运行回测流程测试
pixi run -e dev pytest packages/core/tests/integration/test_backtest_flow.py -v

# 运行调仓流程测试
pixi run -e dev pytest packages/core/tests/integration/test_rebalance_flow.py -v

# 运行风控流程测试
pixi run -e dev pytest packages/core/tests/integration/test_risk_flow.py -v

# 运行双引擎对齐测试
pixi run -e dev pytest packages/core/tests/integration/test_engine_alignment.py -v
```

### 运行标记的测试

```bash
# 只运行集成测试
pixi run -e dev pytest -m integration packages/core/tests/

# 排除慢速测试
pixi run -e dev pytest -m "integration and not slow" packages/core/tests/
```

## 测试环境要求

### 数据要求

集成测试需要完整的市场数据：

- **行情数据**: ETF 日线数据（2023-01-01 至今）
- **指数数据**: 沪深300 指数数据
- **复权因子**: ETF 复权因子数据
- **交易日历**: A 股交易日历

**准备测试数据**:

```bash
# 下载测试数据
pixi run python scripts/download_test_data.py

# 验证数据完整性
pixi run python scripts/verify_test_data.py
```

### 配置要求

集成测试使用测试环境配置：

```python
# tests/conftest.py
import pytest
from ditto_datahub import DataHub
from ditto_core.engine import RegimeEngine, FactorEngine
from ditto_core.portfolio import PortfolioManager

@pytest.fixture(scope="session")
def test_hub():
    """创建测试用的 DataHub"""
    return DataHub(data_root="packages/core/data")

@pytest.fixture
def regime_engine(test_hub):
    """创建测试用的 RegimeEngine"""
    return RegimeEngine(test_hub)

@pytest.fixture
def factor_engine(test_hub):
    """创建测试用的 FactorEngine"""
    return FactorEngine(test_hub)

@pytest.fixture
def portfolio_manager(test_hub):
    """创建测试用的 PortfolioManager"""
    return PortfolioManager(test_hub, initial_capital=1_000_000)
```

## 测试最佳实践

### 1. 使用 Fixture 共享资源

```python
@pytest.fixture(scope="session")
def test_hub():
    """整个测试会话共享一个 hub"""
    return DataHub(data_root="packages/core/data")

@pytest.fixture
def clean_portfolio(test_hub):
    """每个测试前创建新的组合"""
    portfolio = PortfolioManager(test_hub)
    yield portfolio
    # 清理
```

### 2. 使用标记分类测试

```python
@pytest.mark.integration
@pytest.mark.slow
def test_slow_integration_test():
    """慢速集成测试"""
    # 测试逻辑...

@pytest.mark.integration
def test_fast_integration_test():
    """快速集成测试"""
    # 测试逻辑...
```

### 3. 使用参数化测试

```python
@pytest.mark.integration
@pytest.mark.parametrize("regime,expected_min_position", [
    ("bull", 0.7),
    ("osc", 0.5),
    ("bear", 0.1),
])
def test_position_limit_by_regime(regime, expected_min_position):
    """测试不同 Regime 的仓位限制"""
    hub = DataHub()
    risk_engine = RiskEngine(hub)
    limits = risk_engine.get_position_limits(regime)

    assert limits.max_total_position >= expected_min_position
```

### 4. 验证端到端流程

```python
@pytest.mark.integration
def test_end_to_end_strategy():
    """端到端策略测试"""
    # 1. 初始化
    hub = DataHub()
    strategy = RotationStrategy(top_n=3)
    portfolio_mgr = PortfolioManager(hub)
    backtester = FastBacktester(hub)

    # 2. 运行回测
    result = backtester.run(strategy, date(2023, 1, 1), date(2024, 1, 31))

    # 3. 验证结果
    assert result.total_return > -0.5
    assert len(result.trades) > 0
    assert result.max_drawdown < 0.3
```

## 测试数据管理

### 测试数据目录

```
packages/core/data/
├── bars/                 # 测试行情数据
│   ├── etf_daily/
│   └── index_daily/
├── factors/              # 测试因子数据
│   └── expected_factors.parquet
└── backtest/             # 测试回测结果
    └── expected_results.parquet
```

### 数据准备脚本

```python
# scripts/prepare_test_data.py
"""准备测试数据"""
from ditto_datahub import DataHub

def prepare_test_data():
    """准备集成测试所需数据"""
    hub = DataHub(data_root="packages/core/data")

    # 下载测试期间数据
    hub.sources.tushare.fetch_etf_daily(
        trade_date="2023-01-01",
        end_date="2024-01-31"
    )

    # 计算期望因子
    factors = calc_expected_factors(hub)
    factors.write_parquet("packages/core/data/factors/expected_factors.parquet")

if __name__ == "__main__":
    prepare_test_data()
```

## 相关文档

- [单元测试说明](../unit/README.md)
- [测试总说明](../README.md)
- [Python 测试最佳实践](../../../../.claude/skills/python-testing-patterns/SKILL.md)
