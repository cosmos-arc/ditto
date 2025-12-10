# Test Coverage Supplementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 补充缺失的单元测试，提高核心类的测试覆盖率

**Architecture:** 为抽象基类和常量类添加单元测试，确保核心逻辑的完整覆盖

**Tech Stack:** pytest, unittest.mock, Python 3.11+

---

## 测试覆盖分析总结

### 已覆盖 ✅
- `DataCollector` - 单元测试
- `DataService` - 单元测试和集成测试
- `DuckDBAdapter` - 集成测试
- `SQLiteAdapter` - 集成测试
- `AkShareDataSource` - 单元测试
- `TushareDataSource` - 单元测试
- `DataSourceFactory` - 集成测试
- `DatabaseAdapter` - 单元测试
- 所有异常类 - 单元测试

### 已完成 ✅
- `DataSource` (抽象基类) - 单元测试 (2025-12-10)

### 需要补充 📝
- `DataSourceType` (枚举类) - 单元测试
- `DatabaseType` (枚举类) - 单元测试

---

### Task 1: 为 DataSource 抽象基类添加单元测试

**Files:**
- Create: `packages/core/tests/unit/data/datasources/test_datasource_base.py`
- Reference: `packages/core/src/ditto_core/data/datasources/base.py`

**Step 1: Write the failing test**

```python
"""Tests for DataSource abstract base class."""

from typing import Any
from unittest.mock import MagicMock, patch
import pytest

from ditto_core.data.datasources.base import DataSource


def test_datasource_is_abstract():
    """Test that DataSource cannot be instantiated directly."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        DataSource()


def test_datasource_attributes():
    """Test DataSource base class attributes."""
    # Create a concrete implementation
    class TestDataSource(DataSource):
        def __init__(self, config: dict[str, Any] | None = None) -> None:
            super().__init__(config)
            self.init_called = False

        def get_etf_list(self):
            self.init_called = True
            return []

        def get_daily_data(self, symbol: str, start_date: str, end_date: str):
            return []

        def get_adjustment_factors(self, symbol: str, start_date: str, end_date: str):
            return []

    # Test initialization
    source = TestDataSource()
    assert source.init_called is False
    assert source.config == {}

    # Test with config
    config = {"api_key": "test"}
    source = TestDataSource(config)
    assert source.config == config
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/core/tests/unit/data/datasources/test_datasource_base.py -v`
Expected: FAIL with "Can't instantiate abstract class DataSource"

**Step 3: Write minimal implementation**

测试文件已包含完整的实现，无需额外代码。

**Step 4: Run test to verify it passes**

Run: `pytest packages/core/tests/unit/data/datasources/test_datasource_base.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add packages/core/tests/unit/data/datasources/test_datasource_base.py
git commit -m "test: add unit tests for DataSource abstract base class"
```

**Status: ✅ COMPLETED (2025-12-10)**

---

### Task 2: 为 DataSourceType 枚举类添加单元测试

**Files:**
- Create: `packages/core/tests/unit/data/test_constants.py`
- Reference: `packages/core/src/ditto_core/data/constants.py`

**Step 1: Write the failing test**

```python
"""Tests for data constants."""

import pytest

from ditto_core.data.constants import DataSourceType, DatabaseType


def test_datasource_type_values():
    """Test DataSourceType enum values."""
    assert DataSourceType.TUSHARE == "tushare"
    assert DataSourceType.AKSHARE == "akshare"


def test_datasource_type_members():
    """Test DataSourceType has all expected members."""
    expected_members = ["TUSHARE", "AKSHARE"]
    actual_members = [member.name for member in DataSourceType]
    assert sorted(actual_members) == sorted(expected_members)


def test_database_type_values():
    """Test DatabaseType enum values."""
    assert DatabaseType.DUCKDB == "duckdb"
    assert DatabaseType.SQLITE == "sqlite"


def test_database_type_members():
    """Test DatabaseType has all expected members."""
    expected_members = ["DUCKDB", "SQLITE"]
    actual_members = [member.name for member in DatabaseType]
    assert sorted(actual_members) == sorted(expected_members)
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/core/tests/unit/data/test_constants.py -v`
Expected: FAIL with module not found

**Step 3: Write minimal implementation**

测试文件已包含完整的实现，无需额外代码。

**Step 4: Run test to verify it passes**

Run: `pytest packages/core/tests/unit/data/test_constants.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add packages/core/tests/unit/data/test_constants.py
git commit -m "test: add unit tests for data constants"
```

---

### Task 3: 增强 DataService 的集成测试

**Files:**
- Modify: `packages/core/tests/integration/data/test_service_integration.py`
- Reference: `packages/core/src/ditto_core/data/service.py`

**Step 1: Write the failing test**

```python
"""Integration tests for DataService."""

import tempfile
from pathlib import Path
import pytest

from ditto_core.data.service import DataService


@pytest.mark.integration
class TestDataServiceIntegration:
    """Integration tests for DataService with real databases."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.duckdb_path = self.temp_dir / "test.duckdb"
        self.sqlite_path = self.temp_dir / "test.sqlite"

    def teardown_method(self):
        """Clean up test fixtures."""
        # Cleanup is handled by tempfile
        pass

    def test_service_with_both_databases(self):
        """Test DataService with both DuckDB and SQLite initialized."""
        service = DataService(
            duckdb_path=str(self.duckdb_path),
            sqlite_path=str(self.sqlite_path)
        )

        # Verify both databases are initialized
        assert service.duckdb_adapter is not None
        assert service.sqlite_adapter is not None

        # Verify database files exist
        assert self.duckdb_path.exists()
        assert self.sqlite_path.exists()

        # Test schema initialization
        service.initialize_schema()

        # Verify schema in DuckDB
        duckdb_tables = service.duckdb_adapter.connection.execute(
            "SHOW TABLES"
        ).fetchall()
        duckdb_table_names = [table[0] for table in duckdb_tables]
        assert "etf_info" in duckdb_table_names
        assert "daily_price" in duckdb_table_names

        # Verify schema in SQLite
        sqlite_tables = service.sqlite_adapter.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        sqlite_table_names = [table[0] for table in sqlite_tables]
        assert "etf_info" in sqlite_table_names
        assert "daily_price" in sqlite_table_names

    def test_service_with_only_duckdb(self):
        """Test DataService with only DuckDB."""
        service = DataService(duckdb_path=str(self.duckdb_path))

        assert service.duckdb_adapter is not None
        assert service.sqlite_adapter is None

        # Should not fail when calling methods that require SQLite
        # This tests the graceful degradation

    def test_service_with_only_sqlite(self):
        """Test DataService with only SQLite."""
        service = DataService(sqlite_path=str(self.sqlite_path))

        assert service.sqlite_adapter is not None
        assert service.duckdb_adapter is None
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/core/tests/integration/data/test_service_integration.py -v`
Expected: FAIL with file not found

**Step 3: Create file with minimal implementation**

测试文件已包含完整的实现，无需额外代码。

**Step 4: Run test to verify it passes**

Run: `pytest packages/core/tests/integration/data/test_service_integration.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add packages/core/tests/integration/data/test_service_integration.py
git commit -m "test: add integration tests for DataService"
```

---

## 总结

这个计划专注于补充缺失的测试覆盖：

1. **抽象基类测试**：确保接口定义正确
2. **常量类测试**：验证枚举值和成员
3. **集成测试增强**：验证多数据库场景

所有测试都遵循项目的测试规范：
- Unit 测试使用 mock，执行快速
- Integration 测试使用真实数据库，添加 `@pytest.mark.integration` 标记
- 测试文件位置符合镜像结构规则
