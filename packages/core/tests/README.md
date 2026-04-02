# 核心模块测试

## 测试框架

- **pytest**: 测试框架
- **pytest-cov**: 覆盖率测试
- **pytest-mock**: Mock 工具
- **polars**: 数据处理测试

## 测试覆盖

### 单元测试 (tests/unit/)

测试各个模块的独立功能：

| 模块 | 测试文件 | 覆盖范围 |
|------|---------|----------|
| `engine/regime` | `test_regime_engine.py` | Regime 识别逻辑 |
| `engine/factor` | `test_factor_engine.py` | 因子计算逻辑 |
| `engine/rotation` | `test_rotation_engine.py` | 轮动策略逻辑 |
| `engine/backtest` | `test_backtester.py` | 回测引擎逻辑 |
| `engine/risk` | `test_risk_engine.py` | 风险管理逻辑 |
| `portfolio/manager` | `test_portfolio_manager.py` | 组合管理逻辑 |
| `portfolio/builder` | `test_portfolio_builder.py` | 组合构建逻辑 |
| `portfolio/position` | `test_position_manager.py` | 持仓管理逻辑 |
| `strategy/base` | `test_strategy.py` | 策略基类逻辑 |
| `strategy/signal` | `test_signal_generator.py` | 信号生成逻辑 |
| `strategy/execution` | `test_order_executor.py` | 订单执行逻辑 |

### 集成测试 (tests/integration/)

测试模块间的集成功能：

| 场景 | 测试文件 | 覆盖范围 |
|------|---------|----------|
| 完整回测流程 | `test_backtest_flow.py` | 策略 → 回测 → 结果分析 |
| 调仓流程 | `test_rebalance_flow.py` | 信号生成 → 订单执行 → 持仓更新 |
| 风控流程 | `test_risk_flow.py` | 回撤计算 → Kill Switch → 仓位调整 |
| 双引擎对齐 | `test_engine_alignment.py` | Fast 引擎 ↔ Production 引擎对齐验证 |

## 运行测试

### 运行所有测试

```bash
# 运行核心模块所有测试
pixi run -e dev pytest packages/core/tests

# 运行所有测试（带覆盖率）
pixi run -e dev pytest packages/core/tests --cov=ditto_engine --cov-report=html
```

### 运行单元测试

```bash
# 运行所有单元测试
pixi run -e dev pytest packages/core/tests/unit -v

# 运行特定模块单元测试
pixi run -e dev pytest packages/core/tests/unit/test_regime_engine.py -v

# 运行特定测试函数
pixi run -e dev pytest packages/core/tests/unit/test_regime_engine.py::test_regime_bull_market -v
```

### 运行集成测试

```bash
# 运行所有集成测试
pixi run -e dev pytest packages/core/tests/integration -v

# 运行特定集成测试
pixi run -e dev pytest packages/core/tests/integration/test_backtest_flow.py -v
```

## 测试标记

使用 pytest标记分类测试：

| 标记 | 说明 | 示例 |
|------|------|------|
| `@pytest.mark.unit` | 单元测试 | 测试独立函数/类 |
| `@pytest.mark.integration` | 集成测试 | 测试模块间交互 |
| `@pytest.mark.slow` | 慢速测试 | 运行时间 > 1秒 |
| `@pytest.mark.parametrize` | 参数化测试 | 多组输入测试 |

**示例**:

```python
import pytest

@pytest.mark.unit
def test_regime_engine_initialization():
    """测试 RegimeEngine 初始化"""
    engine = RegimeEngine(hub)
    assert engine is not None

@pytest.mark.unit
@pytest.mark.parametrize("regime,expected_min,expected_max", [
    ("bull", 0.7, 0.9),
    ("osc", 0.5, 0.7),
    ("bear", 0.1, 0.4),
])
def test_position_limit_by_regime(regime, expected_min, expected_max):
    """测试不同 Regime 的仓位限制"""
    limits = RiskEngine.get_position_limits(regime)
    assert expected_min <= limits.max_total_position <= expected_max

@pytest.mark.integration
@pytest.mark.slow
def test_full_backtest_flow():
    """测试完整回测流程"""
    # 1. 初始化策略
    strategy = RotationStrategy(top_n=3)

    # 2. 运行回测
    result = FastBacktester(hub).run(
        strategy=strategy,
        start_date="2023-01-01",
        end_date="2024-01-31"
    )

    # 3. 验证结果
    assert result.total_return > -0.5  # 回测期间亏损不超过 50%
    assert len(result.trades) > 0       # 有交易记录
```

## 测试规范

### AAA 模式

测试遵循 **Arrange → Act → Assert** 模式：

```python
def test_factor_engine_calc_rs_factor():
    # Arrange - 准备测试数据
    hub = create_mock_hub()
    engine = FactorEngine(hub)
    trade_date = date(2024, 1, 31)
    universe = ["510300.SH", "510500.SH"]

    # Act - 执行被测试的功能
    factors = engine.calc_factors(universe, trade_date)

    # Assert - 验证结果
    assert "rs_factor" in factors.columns
    assert factors.shape[0] == len(universe)
    assert factors["rs_factor"].is_not_null().all()
```

### 测试隔离

每个测试应该独立运行，不依赖其他测试：

```python
@pytest.fixture
def clean_hub():
    """每次测试前创建新的 hub"""
    hub = DataHub(data_root=mkdtemp())
    yield hub
    # 清理
    shutil.rmtree(hub.data_root)

def test_with_fresh_hub(clean_hub):
    """使用全新的 hub 进行测试"""
    engine = RegimeEngine(clean_hub)
    # 测试逻辑...
```

### 边界覆盖

测试需要覆盖正常、边界、异常情况：

```python
@pytest.mark.parametrize("input_data,expected", [
    # 正常情况
    ([1, 2, 3, 4, 5], 3.0),

    # 边界情况
    ([1], 1.0),            # 单元素
    ([], 0.0),             # 空列表

    # 异常情况
    ([None, 1, 2], 1.0),   # 包含 None
])
def test_calc_mean(input_data, expected):
    """测试均值计算"""
    result = calc_mean(input_data)
    assert result == expected
```

## Mock 和 Fixture

### 使用 Fixture

```python
import pytest
from ditto_data import DataHub

@pytest.fixture
def hub():
    """创建测试用的 DataHub"""
    return DataHub(data_root="tests/data")

@pytest.fixture
def regime_engine(hub):
    """创建测试用的 RegimeEngine"""
    return RegimeEngine(hub)

def test_regime_engine(regime_engine):
    """使用 fixture 进行测试"""
    result = regime_engine.calc_regime_for_range(
        start_date="2024-01-01",
        end_date="2024-01-31"
    )
    assert result is not None
```

### 使用 Mock

```python
from unittest.mock import Mock, patch
import polars as pl

def test_factor_engine_with_mock():
    """使用 Mock 测试"""
    # 创建 Mock hub
    hub = Mock()

    # Mock 返回数据
    hub.sources.bars.get.return_value = pl.DataFrame({
        "symbol": ["510300.SH"],
        "close": [4.5],
        "trade_date": [date(2024, 1, 31)]
    })

    # 测试
    engine = FactorEngine(hub)
    factors = engine.calc_factors(["510300.SH"], date(2024, 1, 31))

    # 验证
    hub.sources.bars.get.assert_called_once()
    assert factors is not None
```

## 覆盖率要求

| 模块 | 目标覆盖率 | 当前覆盖率 |
|------|-----------|-----------|
| `engine` | 85% | - |
| `portfolio` | 85% | - |
| `strategy` | 90% | - |
| **总体** | **≥80%** | - |

**生成覆盖率报告**:

```bash
# 生成 HTML 覆盖率报告
pixi run -e dev pytest packages/core/tests --cov=ditto_engine --cov-report=html

# 查看报告
# 打开 packages/core/htmlcov/index.html
```

## 测试数据

测试数据存储在 `packages/core/data/` 目录：

```
data/
├── bars/             # 测试用行情数据
├── factors/          # 测试用因子数据
└── expected/         # 期望结果数据
```

## 相关文档

- [单元测试说明](unit/README.md)
- [集成测试说明](integration/README.md)
- [Python 测试最佳实践](../../../../.claude/skills/python-testing-patterns/SKILL.md)
