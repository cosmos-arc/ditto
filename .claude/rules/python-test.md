---
paths: tests/**/*.py
---

# 测试规范

## 测试组件栈

**必须使用以下组件，不得替换**：

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

---

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

| 形式 | 状态 | 原因 |
|------|------|------|
| `assert True` | ❌ | 没有实际验证 |
| `assert False` | ❌ | 永远失败 |
| 空的 `pass` | ❌ | 无断言 |
| `assert result is not None` | ❌ | 过于宽泛 |

```python
# ✅ 正确：验证具体行为
assert result.status == "success"
assert result.count == 3

# ✅ 测试异常路径
with pytest.raises(ValueError, match="Invalid input"):
    function_with_invalid_input()
```

**检查命令**：
```bash
grep -r "assert True" tests/
grep -r "assert False" tests/
```

---

## DataFrame测试

```python
from polars.testing import assert_frame_equal
assert_frame_equal(result, expected, atol=1e-4)
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

QuoteSchema.validate(df)
```

---

## Mock选择

| 场景 | 工具 |
|------|------|
| 验证调用参数/次数 | `pytest-mock (mocker)` |
| 简单替换返回值 | `monkeypatch.setattr()` |
| 环境变量 | `monkeypatch.setenv()` |
| HTTP请求 | `respx` |

```python
# ✅ 推荐
def test_api(mocker):
    mock_get = mocker.patch("httpx.Client.get")
    mock_get.return_value = httpx.Response(200, json={"price": 15.5})
    result = fetch_quote("000001")
    mock_get.assert_called_once_with("https://api.example.com/quote?symbol=000001")

# ❌ 禁止：unittest.mock
from unittest.mock import patch  # 不要使用
```

---

## 测试类型

### PIT (Point-in-Time) 测试

量化系统核心测试，验证无未来数据泄露。

```python
@pytest.mark.pit
def test_no_future_data_in_features(sample_quotes):
    features = calculate_features(sample_quotes, as_of=date(2024, 1, 15))
    assert features["date"].max() <= date(2024, 1, 15)

@pytest.mark.pit
def test_signal_uses_only_past_data():
    signal_date = date(2024, 1, 15)
    signals = generate_signals(as_of=signal_date)
    for signal in signals:
        assert signal.data_date < signal_date
```

### 快照测试

**使用规则**：输出结构复杂（>3个字段）且需要防止意外变更时用快照；简单断言（≤3个字段）或含随机/时间值时不用。

| 场景 | 适用 |
|------|------|
| 回测报告 | ✅ 多字段摘要 |
| 信号输出 | ✅ 策略信号列表 |
| 简单断言 | ❌ 用 `assert` 更清晰 |
| 含随机/时间值 | ❌ 每次都变 |

```python
from inline_snapshot import snapshot

def test_backtest_output():
    result = run_backtest(...)
    assert result.summary == snapshot({
        "total_return": 0.156,
        "sharpe_ratio": 1.23,
    })
```

### 异步测试

```python
@pytest.mark.asyncio
async def test_async_data_fetch():
    result = await fetch_data_async("000001")
    assert result is not None

# 异步 + 参数化
@pytest.mark.asyncio
@pytest.mark.parametrize("symbol,expected_sid", [
    ("000001", 1000001),
    ("000002", 1000002),
])
async def test_resolve_sid_async(symbol, expected_sid):
    sid = await async_resolve_sid(symbol)
    assert sid == expected_sid
```

### 参数化测试（减少重复）

**当测试逻辑相同，只是输入/输出不同时，必须使用参数化测试**：

```python
# ❌ 错误：重复代码
def test_read_filter_by_sids_1(self, store, sample_df):
    store.write("adj_factor", sample_df, 2024)
    df = store.read("adj_factor", sids=[1000001])
    assert len(df) == 3

# ✅ 正确：参数化测试
@pytest.mark.parametrize("sids,expected_count", [
    ([1000001], 3),           # 单个 SID
    ([1000002], 1),           # 另一个 SID
    ([1000001, 1000002], 4),  # 多个 SID
    ([], 0),                  # 空 SID 列表
])
def test_read_filter_by_sids(self, store, sample_df, sids, expected_count):
    store.write("adj_factor", sample_df, 2024)
    df = store.read("adj_factor", sids=sids)
    assert len(df) == expected_count
```

---

## Parquet Store 测试

```python
@pytest.fixture
def store(tmp_path):
    """临时目录的ParquetStore"""
    return QuoteParquetStore(base_path=tmp_path / "quotes")

def test_partitioned_write(store, sample_quotes):
    store.save(sample_quotes, partition_by="symbol")
    assert (store.base_path / "symbol=000001").exists()
```

**不需要测**：Parquet格式正确性（那是Polars的责任）

---

## Fixture规范

| 前缀 | 用途 | 作用域 |
|------|------|--------|
| `sample_*` | 标准测试数据 | module（只读） |
| `empty_*` | 空数据/边界测试 | function |
| `mock_*` | Mock对象 | function |
| `*_conn` | 内存数据库连接 | function |

---

## Marker 规范

| Marker | 用途 | 运行时机 |
|--------|------|----------|
| `@pytest.mark.unit` | 单元测试（无外部依赖） | 每次提交/CI |
| `@pytest.mark.integration` | 多组件协作测试 | CI |
| `@pytest.mark.e2e` | 端到端完整流程 | CI/手动 |
| `@pytest.mark.slow` | 耗时测试 | CI/手动 |
| `@pytest.mark.smoke` | 冒烟测试，核心功能 | 每次提交 |
| `@pytest.mark.benchmark` | 性能基准测试 | 手动/定期 |
| `@pytest.mark.pit` | PIT数据正确性验证 | CI |
| `@pytest.mark.data` | 需要数据fixtures | 按需 |
| `@pytest.mark.external` | 调用外部API（Tushare等） | 手动/CI |
| `@pytest.mark.observability` | 可观测性堆栈测试 | 按需/CI |

### 使用示例

```python
# 单元测试 - 必须添加
@pytest.mark.unit
def test_dataset_config_validation():
    ...

# 可观测性测试
@pytest.mark.integration
@pytest.mark.observability
class TestObservabilityStack:
    ...

# PIT 测试
@pytest.mark.pit
def test_no_future_data_leakage(sample_quotes):
    ...
```

---

## 覆盖率要求

**项目覆盖率标准（统一 80%）**：

| 指标 | 要求 | 配置位置 |
|------|------|----------|
| 分支覆盖率 | >= 80% | `pyproject.toml`: fail_under = 80 |
| CI 阈值 | >= 80% | `.github/workflows/ci.yml`: `--cov-fail-under=80` |
| 本地阈值 | >= 80% | `pixi.toml` test-cov-xml: `--cov-fail-under=80` |
| 新增代码 | >= 85% | CI 自动检查 |

### 覆盖率检查流程

```bash
# 本地开发时快速检查
pytest tests/unit/ -m "not slow" --cov

# 提交前完整检查
pytest --cov --cov-report=html --cov-report=term-missing

# 查看 HTML 报告
open htmlcov/index.html
```

---

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
```

---

## 并发测试配置

**项目已配置 pytest-xdist 并发测试** (`-n auto`)：

**注意事项**：
- 测试必须独立，不能有共享状态
- 使用 `tmp_path` 而非固定路径
- 避免使用全局变量或单例

**预期提速**：2-4倍

---

## 测试隔离性

```python
# ✅ 正确：每个测试独立准备数据
def test_feature_a(store):
    store.write(sample_data_a)
    result = store.read("a")
    assert result == expected_a

def test_feature_b(store):
    store.write(sample_data_b)  # 独立准备
    result = store.read("b")
    assert result == expected_b

# ❌ 错误：依赖执行顺序
def test_feature_a(store):
    global shared_state = "a"  # 不要使用全局状态
```

---

## 可观测性测试控制

### 环境变量

```bash
# 禁用可观测性测试（默认）
export DITTO_TEST_OBSERVABILITY=disabled

# 启用可观测性测试
export DITTO_TEST_OBSERVABILITY=enabled
export DITTO_OBSERVABILITY_TEST_MODE=docker
```

### Marker 组合使用

```python
# 可观测性 + 集成测试
@pytest.mark.integration
@pytest.mark.observability
class TestObservabilityStack:
    ...
```

### 运行命令

```bash
# 跳过可观测性测试
pytest -m "not observability"

# 只运行可观测性测试
pytest -m observability
```

---

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

## 检测问题命令（提交前必跑）

```bash
grep -r "assert True" tests/          # 假测试检测
grep -r "assert False" tests/
pytest --collect-only 2>&1 | grep "import mismatch"  # import冲突
grep -r "from unittest.mock" tests/   # 应迁移到pytest-mock
grep -r "@patch" tests/
```

---

## 完整检查命令

```bash
pixi run -e dev check             # 开发时（lint + fmt + type + test --fast）
pixi run -e dev pre-commit-run    # 提交前（pre-commit hooks）
pixi run -e dev ci                # CI 完整（lint + fmt --check + type --all + test --cov-xml）
```

---

## 类型检查（Pyright）

**配置**：
- 源码：`pyproject.toml` [tool.pyright] 段（standard + strict 模式）
- 测试：`pyright.tests.json`（basic 模式，宽松）

```bash
pixi run -e dev type          # 源码检查（strict + warnings）
pixi run -e dev type --tests  # 测试检查（basic 模式）
pixi run -e dev type --all    # 完整检查（源码 + 测试）
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
