---
paths: tests/**/*.py
---

# 测试规范

## 组件栈(**必须，无法使用其他组件！！**)

| 组件 | 用途 | 使用场景 |
|------|------|----------|
| `pytest` | 测试框架 | 所有测试 |
| `polars.testing` | DataFrame断言 | 数据处理验证 |
| `polars.testing.parametric` | DataFrame生成 | Property测试 |
| `pandera[polars]` | Schema验证 | 数据合同、运行时检查 |
| `hypothesis` | Property-based测试 | 边界条件、数值计算 |
| `pytest-mock` | Mock框架 | 需要验证调用的场景 |
| `monkeypatch` | 简单替换 | 环境变量、属性替换 |
| `respx` | HTTP Mock | 外部API测试 |
| `inline-snapshot` | 快照测试 | 回测结果、API响应 |
| `pytest-cov` | 覆盖率 | CI集成 |

## 目录结构

```
tests/
├── conftest.py
├── fixtures/
├── unit/           # 70% - 每次提交，含内存DB测试，含property测试10%（基于Hypothesis）
└── integration/    # 20% - CI运行，完整数据流
```
**数据层测试归入 unit/**：
- 内存DB（DuckDB/SQLite `:memory:`）→ 测 Repository 逻辑
- Parquet Store（`tmp_path`）→ 测 Store 读写逻辑
- 都够快、都是测你的代码而非底层库，测的是业务逻辑而非数据库本身。

## 编写规则

### 命名
```python
# ✅ test_calculate_sharpe_ratio_returns_zero_when_std_is_zero
# ❌ test_sharpe
```

### AAA模式
```python
def test_xxx():
    # Arrange - 准备数据
    # Act - 执行代码
    # Assert - 验证结果
```

### 单一职责
每个测试只验证一个行为，不要在一个测试中验证多个场景。

## DataFrame测试

```python
from polars.testing import assert_frame_equal
assert_frame_equal(result, expected, atol=1e-4)  # 浮点容差
```

### Property测试
```python
from polars.testing.parametric import dataframes, column
from hypothesis import given

@given(dataframes(cols=[column("price", dtype=pl.Float64)], min_size=10))
def test_calculation_properties(df: pl.DataFrame):
    ...
```

### Schema验证
```python
import pandera.polars as pa

class QuoteSchema(pa.DataFrameModel):
    date: pl.Date
    symbol: str
    price: float = pa.Field(gt=0)

QuoteSchema.validate(df)  # 测试中使用
```

## Mock选择

| 场景 | 工具 |
|------|------|
| 验证调用参数/次数 | `pytest-mock (mocker)` |
| 简单替换返回值 | `monkeypatch.setattr()` |
| 环境变量 | `monkeypatch.setenv()` |
| HTTP请求 | `respx` |

```python
# respx示例
def test_api(respx_mock):
    respx_mock.get("https://api.example.com/quote").mock(
        return_value=httpx.Response(200, json={"price": 15.5})
    )
```

**原则**：只Mock外部依赖，不Mock内部实现。

## PIT (Point-in-Time) 测试

量化系统核心测试，验证无未来数据泄露。

```python
@pytest.mark.pit
def test_no_future_data_in_features(sample_quotes):
    """特征计算不能使用未来数据"""
    features = calculate_features(sample_quotes, as_of=date(2024, 1, 15))

    # 验证所有数据日期 <= as_of
    assert features["date"].max() <= date(2024, 1, 15)

@pytest.mark.pit
def test_signal_uses_only_past_data():
    """信号生成只能用历史数据"""
    signal_date = date(2024, 1, 15)
    signals = generate_signals(as_of=signal_date)

    # 信号应基于 T-1 及更早的数据
    for signal in signals:
        assert signal.data_date < signal_date

@pytest.mark.pit
def test_backtest_respects_pit():
    """回测严格遵守PIT原则"""
    result = run_backtest(
        start=date(2024, 1, 1),
        end=date(2024, 3, 31)
    )

    # 验证每个交易日只用了当时可知的数据
    for trade in result.trades:
        assert trade.decision_data_date < trade.execution_date
```

## 快照测试

**使用规则**：输出结构复杂（>3个字段）且需要防止意外变更时用快照；简单断言（≤3个字段）或含随机/时间值时不用。

### 适用场景

| 场景 | 示例 |
|------|------|
| 回测报告 | 多字段摘要、交易记录 |
| 信号输出 | 策略生成的信号列表 |
| API响应格式 | 需要保持稳定的接口 |
| 数据管道输出 | 特征工程结果结构 |

### 不适用场景

```python
# ❌ 简单断言更清晰
assert calculate_sharpe(returns) == pytest.approx(1.5)

# ❌ 包含随机/时间值
result = {"timestamp": datetime.now(), ...}  # 每次都变
```

### 示例

```python
from inline_snapshot import snapshot

def test_backtest_output():
    result = run_backtest(...)
    assert result.summary == snapshot({
        "total_return": 0.156,
        "sharpe_ratio": 1.23,
        "max_drawdown": -0.089,
        "win_rate": 0.58,
    })

def test_signal_format():
    signals = generate_signals(date="2024-01-15")
    assert signals.to_dicts() == snapshot([
        {"symbol": "000001", "action": "BUY", "weight": 0.1},
    ])
```

### 命令

```bash
pytest --inline-snapshot=create   # 首次生成
pytest --inline-snapshot=update   # 确认变更并更新
```

## Parquet Store 测试

使用 `tmp_path` 创建临时目录，测试 Store 业务逻辑而非 Parquet 格式本身。

```python
@pytest.fixture
def store(tmp_path):
    """临时目录的ParquetStore"""
    return QuoteParquetStore(base_path=tmp_path / "quotes")

@pytest.fixture
def store_with_data(store, sample_quotes):
    """预填充数据的Store"""
    store.save(sample_quotes)
    return store
```

### 分区测试

```python
def test_partitioned_write(store, sample_quotes):
    store.save(sample_quotes, partition_by="symbol")
    assert (store.base_path / "symbol=000001").exists()
```

**不需要测**：Parquet格式正确性（那是Polars的责任）


## Fixture规范

- `sample_*`: 标准测试数据
- `empty_*`: 空数据/边界测试
- `mock_*`: Mock对象
- `duckdb_conn` / `sqlite_conn`: 内存数据库连接

作用域：`function`（默认）用于可变状态，`module` 用于只读数据。

## 运行命令

```bash
# 本地开发 - 跳过慢速和外部测试
pytest tests/unit/ -m "not slow and not external"

# 快速检查
pytest tests/unit/ -x --ff

# 冒烟测试
pytest -m smoke

# CI完整测试（跳过external）
pytest -m "not external" --cov

# 集成测试
pytest -m integration

# PIT验证测试
pytest -m pit

# 性能基准
pytest -m benchmark --benchmark-only

# 外部API测试（手动触发）
pytest

```

## Marker 使用指南

| Marker | 用途 | 运行时机 |
|--------|------|----------|
| (无) | 普通单元测试 | 每次提交 |
| `@pytest.mark.integration` | 多组件协作测试 | CI |
| `@pytest.mark.e2e` | 端到端完整流程 | CI/手动 |
| `@pytest.mark.slow` | 耗时测试 | CI/手动 |
| `@pytest.mark.smoke` | 冒烟测试，核心功能 | 每次提交 |
| `@pytest.mark.benchmark` | 性能基准测试 | 手动/定期 |
| `@pytest.mark.pit` | PIT数据正确性验证 | CI |
| `@pytest.mark.data` | 需要数据fixtures | 按需 |
| `@pytest.mark.external` | 调用外部API（Tushare等） | 手动/CI |

### 示例

```python
@pytest.mark.pit
def test_no_future_data_leakage(sample_quotes):
    """验证回测中无未来数据泄露"""
    ...

@pytest.mark.external
def test_tushare_daily_quote():
    """调用Tushare获取日行情"""
    ...

@pytest.mark.benchmark
def test_signal_generation_performance(benchmark, large_dataset):
    result = benchmark(generate_signals, large_dataset)
    assert result.height > 0
```

## 代码审查检查清单

提交测试代码前，确认：

- [ ] 测试命名清晰描述了被测行为
- [ ] 遵循 AAA 模式
- [ ] 每个测试只验证一个行为
- [ ] 使用 fixture 而非重复代码
- [ ] Mock 只用于外部依赖
- [ ] 浮点数比较使用容差
- [ ] 边界条件有测试覆盖
- [ ] 异常路径有测试覆盖
- [ ] 无 sleep/time.sleep 等待
- [ ] 无硬编码路径或环境依赖
