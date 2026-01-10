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

### 文件命名规范（防止import冲突）

**禁止同名测试文件存在于不同测试层级**：

```
# ❌ 错误：会导致 pytest 收集冲突
packages/datahub/tests/unit/stores/test_pipeline_store.py
packages/datahub/tests/integration/stores/test_pipeline_store.py

# ✅ 正确：添加层级后缀区分
packages/datahub/tests/unit/stores/test_pipeline_store_unit.py
packages/datahub/tests/integration/stores/test_pipeline_store_integration.py
```

**命名规则**：
- 单元测试: `test_{module}_unit.py`
- 集成测试: `test_{module}_integration.py`
- E2E测试: `test_{module}_e2e.py`

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

### 禁止假测试（绝对禁止）

**以下断言形式被视为假测试，严格禁止**：

```python
# ❌ 禁止：assert True
assert True  # 如果能到这里就通过 - 没有实际验证

# ❌ 禁止：assert False
assert False  # 永远失败

# ❌ 禁止：空断言
pass
# 或者没有 assert 语句

# ❌ 禁止：无意义的断言
assert result is not None  # 过于宽泛
assert len(result) > 0     # 过于宽泛
```

**正确的做法**：

```python
# ✅ 验证具体行为
assert result.status == "success"
assert result.count == 3
assert "expected" in result.message

# ✅ 测试异常路径
with pytest.raises(ValueError, match="Invalid input"):
    function_with_invalid_input()

# ✅ 使用 DataFrame 断言
assert_frame_equal(result, expected)
```

**检查命令**：
```bash
# 提交前必须检查
grep -r "assert True" tests/
grep -r "assert False" tests/
grep -r "^\\s*pass\\s*$" tests/
```

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
| 验证调用参数/次数 | `pytest-mock (mocker)`,`禁止使用unittest.mock` |
| 简单替换返回值 | `monkeypatch.setattr()` |
| 环境变量 | `monkeypatch.setenv()` |
| HTTP请求 | `respx` |

```python
# ✅ pytest-mock 示例（推荐）
def test_api(mocker):
    mock_get = mocker.patch("httpx.Client.get")
    mock_get.return_value = httpx.Response(200, json={"price": 15.5})

    # 验证调用
    result = fetch_quote("000001")
    mock_get.assert_called_once_with("https://api.example.com/quote?symbol=000001")

# ❌ 禁止：unittest.mock
from unittest.mock import patch  # 不要使用
@patch("httpx.Client.get")
def test_api(mock_get):  # 旧方式，不够简洁
    ...

# respx示例
def test_api(respx_mock):
    respx_mock.get("https://api.example.com/quote").mock(
        return_value=httpx.Response(200, json={"price": 15.5})
    )
```

**原则**：
1. 只Mock外部依赖，不Mock内部实现
2. 优先使用 `pytest-mock` 的 `mocker` fixture
3. 禁止使用 `unittest.mock.patch` 装饰器

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
- [ ] 无假测试（assert True、assert False、空 pass）
- [ ] 无 import 冲突（同名测试文件）
- [ ] 使用参数化测试减少重复

---

## 参数化测试（减少重复代码）

**当测试逻辑相同，只是输入/输出不同时，必须使用参数化测试**：

```python
# ❌ 错误：重复代码
def test_read_filter_by_sids_1(self, store, sample_df):
    store.write("adj_factor", sample_df, 2024)
    df = store.read("adj_factor", sids=[1000001])
    assert len(df) == 3

def test_read_filter_by_sids_2(self, store, sample_df):
    store.write("adj_factor", sample_df, 2024)
    df = store.read("adj_factor", sids=[1000002])
    assert len(df) == 1

def test_read_filter_by_sids_3(self, store, sample_df):
    store.write("adj_factor", sample_df, 2024)
    df = store.read("adj_factor", sids=[1000001, 1000002])
    assert len(df) == 4

# ✅ 正确：参数化测试
@pytest.mark.parametrize("sids,expected_count", [
    ([1000001], 3),                    # 单个 SID
    ([1000002], 1),                    # 另一个 SID
    ([1000001, 1000002], 4),           # 多个 SID
    ([], 0),                           # 空 SID 列表
])
def test_read_filter_by_sids(self, store, sample_df, sids, expected_count):
    store.write("adj_factor", sample_df, 2024)
    df = store.read("adj_factor", sids=sids)
    assert len(df) == expected_count
```

**参数化测试的优势**：
- 减少重复代码 50%+
- 更容易添加新的测试用例
- 测试失败时显示具体参数
- 一次运行所有变体

**适用场景**：
- 边界值测试（0、-1、MAX、None）
- 多种输入组合
- 相同逻辑的不同配置

---

## 异步测试

**对于异步函数，必须使用异步测试**：

```python
import pytest

# ✅ 异步测试
@pytest.mark.asyncio
async def test_async_data_fetch():
    result = await fetch_data_async("000001")
    assert result is not None

@pytest.mark.asyncio
async def test_async_database_operation(async_db_pool):
    result = await async_db_pool.fetchrow("SELECT * FROM securities WHERE sid = $1", 100001)
    assert result["symbol"] == "000001"

# ✅ 异步 + 参数化
@pytest.mark.asyncio
@pytest.mark.parametrize("symbol,expected_sid", [
    ("000001", 1000001),
    ("000002", 1000002),
])
async def test_resolve_sid_async(symbol, expected_sid):
    sid = await async_resolve_sid(symbol)
    assert sid == expected_sid
```

**注意**：
- 异步测试需要 `pytest-asyncio` 插件
- 测试函数必须是 `async def`
- fixture 也需要是异步的（使用 `@pytest_asyncio.fixture`）

---

## 覆盖率要求

**项目覆盖率标准**：

| 指标 | 要求 | 检查命令 |
|------|------|----------|
| 分支覆盖率 | >= 80% | `pytest --cov --cov-report=term-missing` |
| 行覆盖率 | >= 80% | `pytest --cov --cov-report=html` |
| 新增代码 | >= 85% | CI 自动检查 |

### 覆盖率提升策略

**1. 优先覆盖核心业务逻辑**
```python
# ✅ 优先测试这些
- Repository 层的业务规则
- Store 层的数据转换
- DQ Engine 的验证逻辑
- 异常处理路径
```

**2. 分支覆盖率关键点**
```python
# 测试所有条件分支
if condition:      # 需要 True 和 False 两种情况
    pass
else:
    pass

# 测试异常路径
try:
    risky_operation()
except ValueError:  # 需要触发这个异常
    handle_error()
```

**3. 使用覆盖率报告定位缺失**
```bash
# 生成详细报告
pytest --cov-report=term-missing:skip-covered

# 输出示例：
# packages/datahub/src/ditto_datahub/errors.py:40  <<<<<<< 需要添加测试
#                                                          40    def __init__(self, message: str = "..."):
```

### 覆盖率检查流程

```bash
# 1. 本地开发时快速检查
pytest tests/unit/ -m "not slow" --cov

# 2. 提交前完整检查
pytest --cov --cov-report=html --cov-report=term-missing

# 3. 查看 HTML 报告
open htmlcov/index.html  # 找出未覆盖的代码行

# 4. 检查假测试（提交前必须）
grep -r "assert True" tests/
grep -r "assert False" tests/
```

---

## 并发测试配置

**项目已配置 pytest-xdist 并发测试**：

```bash
# pyproject.toml 配置
addopts = [
    "-ra",
    "-v",
    "-n", "auto",  # 使用所有可用 CPU 核心并行测试
    ...
]
```

**并发测试注意事项**：
- 测试必须独立，不能有共享状态
- 使用 `tmp_path` 而非固定路径
- 每个测试应有独立的数据库 fixture
- 避免使用全局变量或单例

**预期提速**：2-4倍（取决于 CPU 核心数）

---

## 测试隔离性

**确保测试可以独立运行，无执行顺序依赖**：

```python
# ✅ 正确：每个测试独立准备数据
def test_feature_a(store):
    store.write(sample_data_a)
    result = store.read("a")
    assert result == expected_a

def test_feature_b(store):
    store.write(sample_data_b)  # 独立准备，不依赖 test_feature_a
    result = store.read("b")
    assert result == expected_b

# ❌ 错误：依赖执行顺序
def test_feature_a(store):
    global shared_state = "a"  # 不要使用全局状态

def test_feature_b(store):
    assert global_state == "a"  # 依赖前面的测试
```

**使用 fixture 确保隔离**：
```python
@pytest.fixture
def clean_store(tmp_path):
    """每个测试都获得新的 store"""
    store = ParquetStore(tmp_path)
    yield store
    # 自动清理
```

---

## 检测问题命令（提交前必跑）

```bash
grep -r "assert True" tests/          # 假测试检测
grep -r "assert False" tests/
pytest --collect-only 2>&1 | grep "import mismatch"  # import冲突
grep -r "from unittest.mock" tests/   # 应迁移到pytest-mock
grep -r "@patch" tests/
grep -r "async def test" tests/       # 异步测试覆盖
```

---

## 类型检查（mypy）

**配置**：`tests.*` 模块已配置宽松规则（禁用 index/operator/attr-defined 等，适配 mock 场景）

```bash
pixi run -e dev typecheck        # 完整检查
pixi run -e dev mypy tests/      # 只检查测试
```

---

## 安全检查（bandit # nosec B608）

```python
# ✅ 需要注释：已验证/白名单/参数化
sql = f"SELECT * FROM {table}"  # nosec B608 - table in ALLOWED_TABLES
query = f"SELECT id FROM t WHERE id IN ({placeholders})"  # nosec B608

# ❌ 禁止：直接拼接用户输入
sql = f"SELECT * FROM t WHERE name = '{user_input}'"
```

```bash
pixi run -e dev security         # 运行检查
```

---

## 异步测试注意

```python
# ❌ 避免被pytest误识别为测试
@app.get("/api/test")
async def test_logging():  # ← 函数名以test_开头

# ✅ 重命名避免歧义
async def generate_test_logs():
```

---

## 完整检查命令

```bash
pixi run -e dev quick-check       # 开发时（lint-fix + format + test-fast）
pixi run -e dev pre-commit-run    # 提交前（lint + format + typecheck + security）
pixi run -e dev ci-check          # CI完整（以上 + test-cov-xml）
```
