# 测试性能优化实施方案

## 一、问题概述

### 1.1 性能基线

| 指标 | 当前值 | 问题 |
|------|--------|------|
| 总执行时间 | 343秒 (5.7分钟) | ❌ 过慢 |
| 最慢测试 setup | 16-18秒/测试 | ❌ 瓶颈 |
| 主要瓶颈 | `apps/server/tests/integration/ingestion/flows/` | 需要优化 |

### 1.2 根因分析

| 问题 | 影响 | 优先级 |
|------|------|--------|
| Prefect Test Harness 重复初始化 | 8-10秒/测试 | P0 |
| 数据库连接重复创建 | 4-6秒/测试 | P0 |
| Settings 重复初始化 | 2-3秒/测试 | P1 |
| 模块导入延迟 | 1-2秒/测试 | P2 |

---

## 二、优化策略

### 核心原则
- **激进优化**：不考虑向后兼容，直接使用最优方案
- **渐进式**：分阶段实施
- **可验证**：每个优化可测量
- **遵循约束**：TDD、覆盖率 >= 80%

---

## 三、实施计划

### Phase 1: Session-Scoped Prefect Harness (P0)

**目标**：减少 8-10秒/测试

**文件修改**：

1. **修改** `apps/server/tests/integration/conftest.py`：
```python
"""集成测试共享配置。"""

from collections.abc import Generator
import pytest
from prefect.testing.utilities import prefect_test_harness


@pytest.fixture(scope="session")
def prefect_test_session() -> Generator[None, None, None]:
    """Session 级别的 Prefect test harness。"""
    with prefect_test_harness():
        yield
```

> **注意**：Prefect 3.x 使用 ContextVar 自动管理上下文隔离，不需要手动重置 context。
> 旧的 `context.copy()` / `context.clear()` API 在 Prefect 3.x 中已被移除。

2. **删除** 各测试文件中的重复 `setup_prefect` fixture：
   - `apps/server/tests/integration/ingestion/flows/test_daily_integration.py` (删除第 16-20 行)
   - `apps/server/tests/integration/ingestion/flows/test_repair_integration.py`
   - `apps/server/tests/integration/ingestion/flows/test_backfill_integration.py`
   - `apps/server/tests/integration/ingestion/flows/test_deploy_integration.py`

3. **添加** `@pytest.mark.usefixtures("prefect_test_session")` 到各测试类

**验证**：
```bash
pixi run -e dev pytest apps/server/tests/integration/ingestion/flows/ -v --durations=10
# 预期：setup 时间从 16-18秒 减少到 6-8秒
```

---

### Phase 2: 数据库连接池化 (P0)

**目标**：减少 4-6秒/测试

**文件修改**：

1. **修改** `apps/server/tests/conftest.py`，替换现有的数据库 fixtures：

```python
"""数据库连接池化管理。"""

from collections.abc import Generator
import duckdb
import pytest
import sqlite3


class DatabaseManager:
    """数据库连接池管理器。"""

    def __init__(self):
        self._duckdb_conn = None
        self._sqlite_conn = None

    def get_duckdb_conn(self) -> duckdb.DuckDBPyConnection:
        if self._duckdb_conn is None:
            self._duckdb_conn = duckdb.connect(":memory:")
            self._init_duckdb_tables()
        return self._duckdb_conn

    def _init_duckdb_tables(self) -> None:
        """初始化 DuckDB 表结构。"""
        conn = self._duckdb_conn
        conn.execute("""
            CREATE TABLE IF NOT EXISTS etf_list (
                symbol VARCHAR, name VARCHAR, market VARCHAR,
                category VARCHAR, establish_date DATE, fund_manager VARCHAR,
                tracking_index VARCHAR, knowledge_date DATE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_price_raw (
                symbol VARCHAR, date DATE, open_price DOUBLE, high_price DOUBLE,
                low_price DOUBLE, close_price DOUBLE, volume BIGINT,
                amount DOUBLE, knowledge_date DATE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_price_adjusted (
                symbol VARCHAR, date DATE, open DOUBLE, high DOUBLE,
                low DOUBLE, close DOUBLE, volume BIGINT, knowledge_date DATE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS adjustment_factors (
                symbol VARCHAR, ex_date DATE, adj_factor DOUBLE, knowledge_date DATE
            )
        """)

    def clean_duckdb(self) -> None:
        """清理数据。"""
        if self._duckdb_conn:
            self._duckdb_conn.execute("DELETE FROM etf_list")
            self._duckdb_conn.execute("DELETE FROM daily_price_raw")
            self._duckdb_conn.execute("DELETE FROM daily_price_adjusted")
            self._duckdb_conn.execute("DELETE FROM adjustment_factors")


@pytest.fixture(scope="session")
def db_manager() -> Generator[DatabaseManager, None, None]:
    """Session 级别的数据库管理器。"""
    manager = DatabaseManager()
    yield manager
    if manager._duckdb_conn:
        manager._duckdb_conn.close()


@pytest.fixture
def clean_duckdb(db_manager: DatabaseManager) -> duckdb.DuckDBPyConnection:
    """提供清理后的连接。"""
    db_manager.clean_duckdb()
    return db_manager.get_duckdb_conn()
```

2. **删除** 旧的 `duckdb_conn` 和 `populated_databases` fixtures

**验证**：
```bash
# 运行两次验证隔离性
pixi run -e dev pytest apps/server/tests/integration/ingestion/flows/ && \
pixi run -e dev pytest apps/server/tests/integration/ingestion/flows/
```

---

### Phase 3: Settings 缓存 (P1)

**目标**：减少 2-3秒/测试

**修改** `apps/server/tests/conftest.py`：

```python
@pytest.fixture(scope="session")
def test_settings_session() -> Settings:
    """Session 级别的 Settings，避免重复初始化。"""
    from tempfile import TemporaryDirectory
    from pathlib import Path

    temp_dir = TemporaryDirectory()
    temp_path = Path(temp_dir.name)

    os.environ["DB_DUCKDB_PATH"] = str(temp_path / "test.duckdb")
    os.environ["DB_SQLITE_PATH"] = str(temp_path / "test.sqlite")
    os.environ["TUSHARE_TOKEN"] = "test_token"
    os.environ["DITTO_ENV"] = "testing"

    settings = Settings()
    return settings
```

更新所有使用 `test_settings` 的测试改为使用 `test_settings_session`。

---

### Phase 4: 模块导入优化 (P2)

**目标**：减少 1-2秒/测试

**修改** `apps/server/tests/conftest.py`：

```python
def pytest_configure(config):
    """在测试开始前预加载模块。"""
    from ditto_server.ingestion.flows import daily, repair, backfill
```

---

## 四、实施顺序

| Phase | 任务 | 时间 | 提升 | 风险 |
|-------|------|------|------|------|
| 1 | Prefect Harness Session化 | 2h | 50-60% | 低 |
| 2 | 数据库连接池化 | 3h | 25-30% | 中 |
| 3 | Settings 缓存 | 1h | 10-15% | 低 |
| 4 | 模块导入优化 | 1h | 5-10% | 低 |

**总计**：7小时，预期总体性能提升 60-80%

---

## 五、验证流程

### 每个阶段后执行：

```bash
# 1. 运行测试
pixi run -e dev pytest apps/server/tests/integration/ingestion/flows/ -v

# 2. 覆盖率检查
pixi run -e dev pytest apps/server/tests/integration/ingestion/flows/ --cov=ditto_server --cov-report=term-missing

# 3. 性能基准
pixi run -e dev pytest apps/server/tests/integration/ingestion/flows/ --durations=20
```

### 性能对比：

```bash
# 优化前基线
pixi run -e dev pytest apps/server/tests/integration/ingestion/flows/ -v --tb=no > before.txt

# 优化后
pixi run -e dev pytest apps/server/tests/integration/ingestion/flows/ -v --tb=no > after.txt

# 目标：总时间从 ~343秒 减少到 < 100秒
```

---

## 六、关键文件

### 需要修改的文件：

1. `apps/server/tests/integration/conftest.py` - 添加 session fixtures
2. `apps/server/tests/conftest.py` - 数据库连接池、Settings 缓存
3. `apps/server/tests/integration/ingestion/flows/test_daily_integration.py` - 删除重复 setup
4. `apps/server/tests/integration/ingestion/flows/test_repair_integration.py` - 删除重复 setup
5. `apps/server/tests/integration/ingestion/flows/test_backfill_integration.py` - 删除重复 setup
6. `apps/server/tests/integration/ingestion/flows/test_deploy_integration.py` - 删除重复 setup

---

## 七、风险缓解

| 风险 | 缓解措施 |
|------|----------|
| 测试隔离性破坏 | 强制数据清理 |
| Prefect 状态污染 | Context 重置机制 |
| 并行测试冲突 | 使用隔离锁 |
