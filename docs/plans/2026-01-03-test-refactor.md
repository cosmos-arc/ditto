# 测试代码全面重构计划

## 任务目标

基于 `.claude/rules/python-test.md` 的测试规范和 `pyproject.toml` 的测试配置，全面重构 Ditto 量化系统的测试代码，修复所有问题并增加 property-based 测试。

## 执行进度

| 阶段 | 状态 | 完成时间 | Commit |
|------|------|---------|--------|
| Phase 1 | ✅ 完成 | 2026-01-03 | fake_time, time_machine refactor, external marker |
| Phase 2 | ✅ 完成 | 2026-01-03 | pytest-mock unification |
| Phase 3 | ✅ 完成 | 2026-01-03 | @pytest.mark.pit marker |
| Phase 4 | ✅ 完成 | 2026-01-03 | Property-based tests (Date Utils, DQ Statistical, PIT Helper) |
| Phase 5 | ✅ 完成 | 2026-01-03 | Memory DB migration (9 个文件迁移, 2 个文件改造) |

### Phase 1: 消除硬编码 sleep ✅

**完成内容**:
1. ✅ 添加 `fake_time` fixture 到 `packages/datahub/tests/conftest.py` 和 `apps/server/tests/conftest.py`
2. ✅ 重构缓存测试 (`test_cache_ttl.py`, `test_cache.py`) 使用 `time_machine`
3. ✅ 标记 E2E 测试为 `@pytest.mark.external`

**实际方案**:
- 使用 `time_machine` 库（项目中已安装）而非自定义 `fake_time`
- `time_machine` 可以正确处理第三方库（如 `cachebox`）的时间函数

**Commits**:
- `test: add fake_time fixture to eliminate hardcoded sleep`
- `test: use time_machine for cache TTL tests`
- `test: mark external E2E tests with @pytest.mark.external`

### Phase 2: 统一 Mock 使用 ✅

**完成内容**:
1. ✅ `test_source.py`: 24 个测试方法改用 `mocker` fixture
2. ✅ `test_client.py`: 2 个测试方法改用 `mocker` fixture
3. ✅ `test_pipeline_store.py`: 保持 `mock.patch.object`（上下文管理器需求）

**实际方案**:
- 大多数测试使用 `mocker.patch()` 替代 `with mock.patch()`
- 保留 `with mock.patch.object()` 用于需要上下文管理器的场景

**Commit**:
- `test: unify mock usage to pytest-mock`

### Phase 3: 添加 PIT 标记 ✅

**完成内容**:
1. ✅ `test_bars_repository.py`: 标记 `TestBarsRepository`
2. ✅ `test_universe_repository.py`: 标记 `TestUniverseRepository`
3. ✅ `test_index_repository.py`: 标记 `TestIndexRepositoryWithMocks`
4. ✅ `test_security_store.py`: 标记 2 个测试类
5. ✅ `test_universe_store.py`: 标记 2 个测试类
6. ✅ `test_index_weight_store.py`: 标记 2 个测试类

**总计**: 78 个 PIT 测试已标记

**Commit**:
- `test: add @pytest.mark.pit marker to PIT tests`

### Phase 4: 增加 Property 测试 ✅

**完成内容**:
1. ✅ `test_dates_property.py`: 7 个 property tests for `normalize_date()`
2. ✅ `test_statistical_property.py`: 6 个 property tests for Z-score invariants
3. ✅ `test_pit_helper_property.py`: 13 个 property tests for PIT query generation

**新增文件**:
- `packages/foundation/tests/unit/util/test_dates_property.py`
- `packages/datahub/tests/unit/dq/checkers/test_statistical_property.py`
- `packages/datahub/tests/unit/runtime/test_pit_helper_property.py`

### Phase 5: 内存数据库单元测试迁移 ✅

**完成内容**:
1. ✅ 创建 `packages/datahub/tests/unit/conftest.py` (内存数据库 fixtures)
2. ✅ 迁移 SQLite 内存数据库测试 (4 个文件)
3. ✅ 迁移 Parquet Store 测试 (3 个文件)
4. ✅ 改造临时文件测试 (2 个文件)

**迁移文件列表**:
- `test_calendar_store.py`: 19 个测试
- `test_security_store.py`: 15 个测试
- `test_universe_store.py`: 14 个测试
- `test_index_weight_store.py`: 13 个测试
- `test_bars_store.py`: 25 个测试
- `test_adj_factor_store.py`: 15 个测试
- `test_stock_status_store.py`: 11 个测试
- `test_sqlite_client.py`: 19 个测试 (改造为使用 fixtures)
- `test_ingestion_metadata_store.py`: 7 个测试 (改造为使用 fixtures)

**总计**: ~138 个测试从 `integration/` 迁移到 `unit/`

---

## 问题诊断

| 优先级 | 问题 | 严重程度 | 影响文件 |
|-------|------|---------|---------|
| **P0** | 硬编码 `time.sleep` | 🔴 高 | 7 个文件 |
| **P1** | 使用 `from unittest import mock` | 🟡 中 | 3 个文件 |
| **P2** | PIT 标记未使用 | 🟡 中 | 所有 PIT 测试 |
| **P2.5** | 测试分类错误 | 🟡 中 | 9-11 个文件 |
| **P3** | 缺少 Property 测试 | 🟢 低 | 全部 |

## 重构阶段

### Phase 1: 消除硬编码 sleep (P0)

**目标**: 替换所有 `time.sleep` 为可控的 `fake_time` fixture

#### 1.1 添加 `fake_time` fixture

**文件**:
- `packages/datahub/tests/conftest.py`
- `apps/server/tests/conftest.py`

```python
@pytest.fixture
def fake_time(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """可控的时间 fixture，通过 monkeypatch 替换时间函数。"""
    current_time = [0.0]

    def fake_sleep(seconds: float) -> None:
        current_time[0] += seconds

    def fake_time_func() -> float:
        return current_time[0]

    monkeypatch.setattr("time.sleep", fake_sleep)
    monkeypatch.setattr("time.time", fake_time_func)

    yield
```

#### 1.2 重构缓存测试

**文件**:
- `packages/datahub/tests/unit/runtime/test_cache_ttl.py`
  - 第 16 行: `time.sleep(3)` → 使用 `fake_time`
  - 第 50 行: `time.sleep(3)` → 使用 `fake_time`
  - 第 76 行: `time.sleep(3)` → 使用 `fake_time`
- `packages/datahub/tests/unit/runtime/test_cache.py`
  - 第 129 行: `time.sleep(1.2)` → 使用 `fake_time`

**修改示例**:
```python
# Before
def test_individual_ttl():
    cache = DataCache(ttl_seconds=300)
    cache.set("key1", "value1", ttl=2)
    time.sleep(3)
    assert cache.get("key1") is None

# After
def test_individual_ttl(fake_time):
    cache = DataCache(ttl_seconds=300)
    cache.set("key1", "value1", ttl=2)
    import time
    time.sleep(3)  # fake_time 使其立即完成
    assert cache.get("key1") is None
```

#### 1.3 重构 E2E 测试

**文件**:
- `tests/integration/test_observability_e2e.py`
  - 第 149 行: `time.sleep(20)` → 使用轮询或标记为 `@pytest.mark.external`
  - 第 205 行: `time.sleep(30)` → 使用轮询或标记为 `@pytest.mark.external`

**方案 A: 轮询机制（推荐）**
```python
import httpx

def wait_for_condition(url: str, timeout: float = 30.0) -> bool:
    """轮询等待条件满足。"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = httpx.get(url, timeout=1.0)
            if response.status_code == 200 and has_data(response):
                return True
        except Exception:
            pass
        time.sleep(0.5)  # 使用 fake_time 后无实际等待
    return False
```

**方案 B: 标记为外部测试**
```python
@pytest.mark.integration
@pytest.mark.external
def test_metrics_export(self, victoria_metrics_endpoint: str, http_client: httpx.Client):
    """此测试需要外部服务运行。"""
    # 标记后 CI 可以跳过
```

#### 验证命令
```bash
pytest packages/datahub/tests/unit/runtime/test_cache*.py -v
pytest tests/integration/test_observability_e2e.py -v
grep -r "time\.sleep" packages/*/tests apps/*/tests tests/  # 应无结果（除注释）
```

---

### Phase 2: 统一 Mock 使用 (P1)

**目标**: 将所有 `from unittest import mock` 替换为 `mocker` fixture

#### 2.1 修复 `test_source.py`

**文件**: `packages/datahub/tests/unit/sources/tushare/test_source.py`

**修改**:
```python
# Before (第 4 行)
from unittest import mock

# Before (第 34 行)
with mock.patch("ditto_datahub.sources.tushare.client.pro_api") as mock_api:

# After
def test_fetch_calendar_returns_dataframe(
    self,
    monkeypatch: pytest.MonkeyPatch,
    mocker: pytest.MockFixture,  # 新增
) -> None:
    # ...
    mock_api = mocker.patch("ditto_datahub.sources.tushare.client.pro_api")
    mock_api.return_value.query.return_value = mock_response
```

**影响**: 约 24 个测试方法

#### 2.2 修复其他文件

**文件**:
- `packages/datahub/tests/integration/stores/test_pipeline_store.py` (约第 112 行)
- `packages/datahub/tests/unit/sources/tushare/test_client.py` (待确认)

#### 验证命令
```bash
pytest packages/datahub/tests/unit/sources/tushare/ -v
pytest packages/datahub/tests/integration/stores/test_pipeline_store.py -v
grep -r "from unittest import mock\|import mock" packages/*/tests  # 应无结果
```

---

### Phase 3: 添加 PIT 标记 (P2)

**目标**: 为涉及 Point-in-Time 逻辑的测试添加 `@pytest.mark.pit` 标记

#### 3.1 需要标记的文件

| 文件 | 测试数量估算 |
|------|-------------|
| `packages/datahub/tests/unit/runtime/test_pit_helper.py` | ~36 个 |
| `packages/datahub/tests/unit/repositories/test_bars.py` | ~5 个 (knowledge_date 相关) |
| `packages/foundation/tests/unit/util/test_dates.py` | ~2 个 |

#### 3.2 标记示例

```python
@pytest.mark.pit
def test_asof_join_respects_knowledge_date():
    """测试 asof join 使用 knowledge_date。"""
    # ...
```

#### 验证命令
```bash
pytest -m pit --collect-only  # 应显示所有 PIT 测试
pytest -m pit -v  # 运行所有 PIT 测试
```

---

### Phase 4: 增加 Property 测试 (P3)

**目标**: 使用 Hypothesis 为关键计算逻辑添加 property-based 测试

#### 4.1 Date Utils Property Tests

**新文件**: `packages/foundation/tests/unit/util/test_dates_property.py`

```python
from hypothesis import given, strategies as st
from datetime import date, datetime

class TestNormalizeDateProperties:
    @given(st.datetimes(min_value=datetime(2000, 1, 1)))
    def test_datetime_roundtrip(self, dt: datetime):
        """datetime -> normalize -> parse 应该无损。"""
        from ditto_foundation.util.dates import normalize_date
        result = normalize_date(dt)
        assert result == dt.strftime("%Y-%m-%d")

    @given(st.dates(min_value=date(2000, 1, 1)))
    def test_date_roundtrip(self, d: date):
        """date -> normalize -> parse 应该无损。"""
        from ditto_foundation.util.dates import normalize_date
        result = normalize_date(d)
        assert result == d.strftime("%Y-%m-%d")
```

#### 4.2 DQ Statistical Checker Property Tests

**新文件**: `packages/datahub/tests/unit/dq/checkers/test_statistical_property.py`

```python
from hypothesis import given, strategies as st
from polars.testing.parametric import column, dataframes
import polars as pl

class TestZScoreProperties:
    @given(
        dataframes(
            cols=[
                column("sid", dtype=pl.Int64, min_value=100000001, max_value=999999999),
                column("close", dtype=pl.Float64, min_value=0.01, max_value=10000.0),
            ],
            min_size=10,
            max_size=100,
        )
    )
    def test_zscore_invariants(self, df: pl.DataFrame):
        """Z-score 计算应该满足不变式。"""
        mean = df["close"].mean()
        std = df["close"].std()

        if std > 0:
            zscores = df.with_columns(
                ((pl.col("close") - mean) / std).alias("zscore")
            )
            # 均值接近 0，标准差接近 1
            assert abs(zscores["zscore"].mean()) < 0.1
            assert abs(zscores["zscore"].std() - 1.0) < 0.1
            assert zscores["zscore"].is_finite().all()
```

#### 4.3 PIT Helper Property Tests

**新文件**: `packages/datahub/tests/unit/runtime/test_pit_helper_property.py`

```python
from hypothesis import given, strategies as st
from polars.testing.parametric import column, dataframes
import polars as pl

class TestAsOfJoinProperties:
    @given(
        signals=dataframes(
            cols=[
                column("decision_date", dtype=pl.Date),
                column("sid", dtype=pl.Int64),
                column("signal", dtype=pl.Float64),
            ],
            min_size=5,
        ),
        prices=dataframes(
            cols=[
                column("trade_date", dtype=pl.Date),
                column("knowledge_date", dtype=pl.Date),
                column("sid", dtype=pl.Int64),
                column("close", dtype=pl.Float64),
            ],
            min_size=10,
        ),
    )
    def test_asof_join_no_future_leak(self, signals: pl.DataFrame, prices: pl.DataFrame):
        """asof join 不应该泄露未来信息。"""
        result = signals.join_asof(
            prices,
            left_on="decision_date",
            right_on="knowledge_date",
            by="sid",
            strategy="backward",
        )
        if result.height > 0:
            assert (result["knowledge_date"] <= result["decision_date"]).all()
```

#### 验证命令
```bash
pytest packages/foundation/tests/unit/util/test_dates_property.py -v
pytest packages/datahub/tests/unit/dq/checkers/test_*_property.py -v
pytest packages/ -m "not slow" --hypothesis-seed=0
```

---

### Phase 5: 内存数据库单元测试迁移 (P2.5)

**目标**: 将使用内存数据库（SQLite `:memory:`）或临时目录（`tmp_path`）的测试从 `integration/` 迁移到 `unit/`

**规范依据**:
> 内存DB（DuckDB/SQLite :memory:）测试归入 unit/**，因为测的是业务逻辑而非数据库本身。
>
> 临时目录（`tmp_path`）测试同样归入 unit/**，因为测的是 Store 的业务逻辑而非 Parquet 格式本身。

#### 5.1 创建内存数据库 Fixtures

**新文件**: `packages/datahub/tests/unit/conftest.py`

```python
"""Pytest configuration for unit tests.

提供内存数据库 fixtures，支持快速单元测试。
"""

from typing import Generator

import pytest
from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.stores.sqlite_client import SQLiteClient


@pytest.fixture(scope="function")
def sqlite_memory_pool() -> Generator[SQLitePool, None, None]:
    """提供内存 SQLite 数据库池。

    每个测试函数使用独立的内存数据库，测试结束后自动清理。
    """
    pool = SQLitePool(":memory:")
    pool.init_schema()
    yield pool
    pool.close()


@pytest.fixture(scope="function")
def sqlite_client(sqlite_memory_pool: SQLitePool) -> SQLiteClient:
    """提供 SQLite 客户端，基于内存数据库。"""
    return SQLiteClient(sqlite_memory_pool)


@pytest.fixture(scope="function")
def db_client(sqlite_client: SQLiteClient) -> SQLiteClient:
    """数据库客户端别名，方便直接使用。"""
    return sqlite_client
```

#### 5.2 第一阶段：迁移已使用内存数据库的测试

**高优先级**（已经使用 `SQLitePool(":memory:")`，可直接迁移）：

| 源文件 | 目标位置 | 测试数量 | 改动 |
|--------|---------|---------|------|
| `integration/stores/test_calendar_store.py` | `unit/stores/test_calendar_store.py` | ~20 | 使用新 fixture |
| `integration/stores/test_security_store.py` | `unit/stores/test_security_store.py` | ~10 | 使用新 fixture |
| `integration/stores/test_universe_store.py` | `unit/stores/test_universe_store.py` | ~5 | 使用新 fixture |
| `integration/stores/test_index_weight_store.py` | `unit/stores/test_index_weight_store.py` | ~5 | 使用新 fixture |

#### 5.3 第二阶段：迁移使用 tmp_path 的 Parquet Store 测试

**关键理解**:
> `tmp_path` 创建的临时目录与 `:memory:` 数据库本质上相同，都是测试隔离环境。
> 测试的是 Store 的业务逻辑（write/read/delete/get_years），而非 Parquet 格式本身（这是 polars 的责任）。

**高优先级**（使用 `tmp_path` 或 `TemporaryDirectory`，可直接迁移）：

| 源文件 | 目标位置 | 测试数量 | 改动 |
|--------|---------|---------|------|
| `integration/stores/test_bars_store.py` | `unit/stores/test_bars_store.py` | ~30 | 无需改动 |
| `integration/stores/test_adj_factor_store.py` | `unit/stores/test_adj_factor_store.py` | ~10 | 无需改动 |
| `integration/stores/test_stock_status_store.py` | `unit/stores/test_stock_status_store.py` | ~5 | 无需改动 |

**迁移步骤**（以 `test_bars_store.py` 为例）：

1. **确认现有测试已经使用 `tmp_path`**
2. **直接移动文件，无需修改代码**: `git mv ...`
3. **验证测试通过**

**为什么可以迁移？**

以 `BarsStore` 为例，测试验证的是：
- ✅ `write()` 方法正确写入数据
- ✅ `read()` 方法正确读取和过滤数据
- ✅ `delete()` 方法正确删除分区
- ✅ `get_years()` 方法正确返回可用年份
- ✅ `count()` 方法正确统计记录数
- ✅ `on_duplicate` 参数正确处理重复数据

这些都是 **Store 的业务逻辑**，而非 Parquet 格式的正确性（polars 库已经保证了这一点）。

#### 5.4 第三阶段：改造使用临时文件的 SQLite 测试

**中优先级**（可改造为使用 `:memory:`）：

| 源文件 | 问题 | 改造方案 |
|--------|------|---------|
| `integration/stores/test_quarantine_store.py` | 使用 `NamedTemporaryFile` | 改用 `:memory:` |
| `integration/stores/test_ingestion_metadata_store.py` | 使用 `TemporaryDirectory` | 改用 `:memory:` |

#### 5.5 DuckDB 内存数据库支持

**注意**: DuckDB 默认支持内存模式，使用 `duckdb.connect(":memory:")`

**新增 fixture** (在 `packages/datahub/tests/unit/conftest.py`):

```python
import duckdb
import polars as pl


@pytest.fixture(scope="function")
def duckdb_memory() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """提供内存 DuckDB 连接。

    适用于测试 SQL 查询逻辑，不需要持久化。
    """
    con = duckdb.connect(":memory:")
    yield con
    con.close()


@pytest.fixture(scope="function")
def duckdb_memory_with_tables(duckdb_memory: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """提供内存 DuckDB 连接，并初始化测试表。"""
    # 创建测试表
    duckdb_memory.execute("CREATE TABLE test AS SELECT * FROM VALUES (1, 'a'), (2, 'b')")
    return duckdb_memory
```

#### 5.6 不建议迁移的测试

**低优先级**（应该保持为 integration 测试）：

| 类型 | 原因 |
|------|------|
| SQL Engine 测试 | 测试基础设施（DuckDB + SQLite 集成） |
| Runtime 测试 | 测试基础设施组件（连接池、锁、文件锁等） |
| Pipeline Store 测试 | 涉及复杂的跨组件集成逻辑 |

**说明**: 这些测试涉及多个组件的集成或真实的文件系统操作，属于真正的集成测试。

#### 验证命令

```bash
# 迁移后验证
pytest packages/datahub/tests/unit/stores/test_calendar_store.py -v
pytest packages/datahub/tests/unit/stores/test_security_store.py -v
pytest packages/datahub/tests/unit/stores/test_bars_store.py -v
pytest packages/datahub/tests/unit/stores/test_adj_factor_store.py -v
pytest packages/datahub/tests/unit/ -v
pytest packages/datahub/tests/integration/ -v
```

---

## 执行顺序

| 阶段 | 任务 | 估算时间 |
|------|------|---------|
| **Phase 1** | 消除 sleep (P0) | 2.5 小时 |
| **Phase 2** | 统一 Mock (P1) | 1 小时 |
| **Phase 3** | 添加 PIT 标记 (P2) | 1 小时 |
| **Phase 4** | 增加 Property 测试 (P3) | 3 小时 |
| **Phase 5** | 内存数据库单元测试迁移 (P2.5) | 2.5 小时 |
| **总计** | | **10 小时** |

---

## 关键文件清单

### Phase 1-4: 必须修改的文件

1. `packages/datahub/tests/conftest.py` - 添加 `fake_time` fixture
2. `apps/server/tests/conftest.py` - 添加 `fake_time` fixture
3. `packages/datahub/tests/unit/runtime/test_cache_ttl.py` - 消除 sleep
4. `packages/datahub/tests/unit/runtime/test_cache.py` - 消除 sleep
5. `tests/integration/test_observability_e2e.py` - 消除 sleep 或标记 external
6. `packages/datahub/tests/unit/sources/tushare/test_source.py` - 统一 mock
7. `packages/datahub/tests/integration/stores/test_pipeline_store.py` - 统一 mock
8. `packages/datahub/tests/unit/runtime/test_pit_helper.py` - 添加 PIT 标记

### Phase 4: 需要创建的新文件

9. `packages/foundation/tests/unit/util/test_dates_property.py`
10. `packages/datahub/tests/unit/dq/checkers/test_statistical_property.py`
11. `packages/datahub/tests/unit/runtime/test_pit_helper_property.py`

### Phase 5: 内存数据库单元测试迁移

**需要创建的新文件**：
12. `packages/datahub/tests/unit/conftest.py` - 内存数据库 fixtures (SQLite + DuckDB)

**需要迁移的文件**（从 integration/ 到 unit/）：

**SQLite 内存数据库测试**：
13. `packages/datahub/tests/integration/stores/test_calendar_store.py` → `unit/stores/`
14. `packages/datahub/tests/integration/stores/test_security_store.py` → `unit/stores/`
15. `packages/datahub/tests/integration/stores/test_universe_store.py` → `unit/stores/`
16. `packages/datahub/tests/integration/stores/test_index_weight_store.py` → `unit/stores/`

**Parquet Store 测试**（使用 tmp_path，测试业务逻辑）：
17. `packages/datahub/tests/integration/stores/test_bars_store.py` → `unit/stores/`
18. `packages/datahub/tests/integration/stores/test_adj_factor_store.py` → `unit/stores/`
19. `packages/datahub/tests/integration/stores/test_stock_status_store.py` → `unit/stores/`

**需要改造的文件**：
20. `packages/datahub/tests/integration/stores/test_quarantine_store.py` - 改用 `:memory:`
21. `packages/datahub/tests/integration/stores/test_ingestion_metadata_store.py` - 改用 `:memory:`

---

## 验证与质量保证

### 覆盖率目标

| 包 | 目标覆盖率 |
|---|-----------|
| `datahub` | >=80% |
| `foundation` | >=80% |
| `server` | >=80% |

---

## 风险与应对

| 风险 | 应对措施 |
|------|---------|
| 时间抽象引入新 bug | 充分测试 fake_time fixture，保留真实时间测试 |
| Mock 修改破坏测试 | 逐文件修改，每步验证，使用 git 分支 |
| Property 测试不稳定 | 限制 Hypothesis 迭代次数，固定 seed |
| 第三方服务依赖 | 使用 `@pytest.mark.external`，CI 默认跳过 |
| 测试迁移破坏 CI | 先在分支验证，确认测试分类正确后再合并 |
| 内存数据库与真实数据库行为差异 | 保留关键集成测试，内存 DB 只覆盖业务逻辑 |
