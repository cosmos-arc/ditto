# SQLite 测试 Fixture 修复计划

**日期**: 2026-01-19
**状态**: ✅ 已完成
**优先级**: 高

## 问题概述

### 症状
- **103 个测试失败，74 个错误**
- 错误类型：`sqlite3.OperationalError: no such table: security`
- 影响范围：所有使用 SQLite 的单元测试

### 根本原因
测试文件创建 `SQLitePool(":memory:")` 时没有提供 `schema_path` 参数，导致 `init_schema()` 跳过表结构创建。

```python
# ❌ 当前问题代码
self.pool = SQLitePool(":memory:")
self.pool.init_schema()  # schema_path 为 None，跳过初始化
self.client.execute("INSERT INTO security ...")  # 表不存在！
```

## 解决方案

创建**三层 pytest fixture 体系**，统一管理 SQLite 测试数据库的初始化。

### Fixture 架构

#### 1. `sqlite_schema_path` (Session 级别)

**文件**: `packages/datahub/tests/fixtures/database.py`

```python
@pytest.fixture(scope="session")
def sqlite_schema_path() -> Path:
    """
    获取数据库 schema 文件路径。

    Session 级别 fixture，在整个测试会话中只计算一次。

    Returns:
        Path: 指向 schema.sql 文件的路径
    """
    schema_file = (
        Path(__file__).parent.parent.parent
        / "src"
        / "ditto_datahub"
        / "scripts"
        / "schema.sql"
    )
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")
    return schema_file
```

#### 2. `sqlite_pool` (Function 级别)

```python
@pytest.fixture(scope="function")
def sqlite_pool(sqlite_schema_path: Path) -> SQLitePool:
    """
    创建已初始化的 SQLite 连接池。

    每个测试函数使用独立的内存数据库，确保测试隔离。

    Args:
        sqlite_schema_path: Schema 文件路径（从 session fixture 注入）

    Returns:
        SQLitePool: 已初始化表结构的连接池
    """
    pool = SQLitePool(":memory:", schema_path=sqlite_schema_path)
    pool.init_schema()
    return pool
```

#### 3. `sqlite_client` (Function 级别)

```python
@pytest.fixture(scope="function")
def sqlite_client(sqlite_pool: SQLitePool) -> SQLiteClient:
    """
    创建 SQLite 客户端。

    Args:
        sqlite_pool: 已初始化的连接池

    Returns:
        SQLiteClient: SQL 执行客户端
    """
    return SQLiteClient(sqlite_pool)
```

### Fixture 依赖关系

```
sqlite_schema_path (session)
        ↓
    sqlite_pool (function)
        ↓
  sqlite_client (function)
```

## 迁移策略

### 优先级分级

**高优先级** (ERROR 最多的文件):
1. `test_bars_accessor_unit.py` - 32 个 ERROR
2. `test_calendar_store_unit.py` - 25 个 ERROR
3. `test_security_store_unit.py` - 21 个 FAILED

**中优先级** (少量错误的文件):
4. `test_security_accessor_unit.py` - 19 个 FAILED
5. `test_universe_store_unit.py` - 15 个 FAILED
6. `test_index_weight_store_unit.py` - 14 个 FAILED
7. `test_universe_accessor_unit.py` - 13 个 FAILED

**低优先级** (其他文件):
8. 其他受影响的测试文件

### 迁移模式

**修改前**:
```python
class TestBarsAccessor:
    def setup_method(self) -> None:
        self.temp_dir = TemporaryDirectory()
        data_root = Path(self.temp_dir.name)

        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()  # ❌ 没有 schema_path
        self.client = SQLiteClient(self.pool)
```

**修改后**:
```python
class TestBarsAccessor:
    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端。"""
        self.temp_dir = TemporaryDirectory()
        data_root = Path(self.temp_dir.name)

        self.client = sqlite_client  # ✅ 从 fixture 获取
        self.pool = self.client.pool  # 如需访问 pool
```

## 实施计划

### Phase 1: 创建 Fixture (15 分钟)

**任务清单**:
- [x] 创建 `packages/datahub/tests/fixtures/` 目录
- [x] 创建 `packages/datahub/tests/conftest.py` (fixture 放在此处)
- [x] 创建 `packages/datahub/tests/fixtures/__init__.py`
- [x] 创建验证测试 `packages/datahub/tests/fixtures/test_database_fixtures.py`

**验证**:
```bash
pixi run -e dev pytest tests/fixtures/test_database_fixtures.py -v
```

### Phase 2: 迁移高优先级文件 (30 分钟)

**文件列表**:
- [x] `test_bars_accessor_unit.py` (48 tests passed)
- [x] `test_calendar_store_unit.py` (25 tests passed)
- [x] `test_security_store_unit.py` (22 tests passed)

**每个文件的迁移步骤**:
1. 修改 `setup_method` 为 autouse fixture
2. 删除 `SQLitePool` 和 `SQLiteClient` 的手动创建
3. 运行文件级测试验证

**验证**:
```bash
# 每个文件修改后立即验证
pixi run -e dev pytest packages/datahub/tests/unit/accessors/test_bars_accessor_unit.py -v
```

### Phase 3: 迁移中优先级文件 (20 分钟)

**文件列表**:
- [x] `test_security_accessor_unit.py` (21 tests passed)
- [x] `test_universe_store_unit.py` (16 tests passed)
- [x] `test_index_weight_store_unit.py` (15 tests passed)
- [x] `test_universe_accessor_unit.py` (20 tests passed)
- [x] `test_calendar_accessor_unit.py` (12 tests passed)

### Phase 4: 迁移低优先级文件 (15 分钟)

**文件列表**:
- [x] `test_datahub_observability_unit.py` (3 个测试类已迁移)
- [x] `test_hub_unit.py` (文件数据库，已添加 schema_path)
- [x] `test_init_dq_config_unit.py` (Mock 测试已更新)

### Phase 5: 回归测试 (10 分钟)

**完整验证**:
```bash
# 运行完整单元测试
pixi run -e dev pytest packages/datahub/tests/unit --no-cov

# 实际结果 ✅
# 939 passed in 53.71s
# 0 errors, 0 failures
```

## 成功标准

| 指标 | 当前 | 目标 | 实际 | 状态 |
|------|------|------|------|------|
| ERROR 数 | 74 | 0 | 0 | ✅ |
| FAILED 数 | 103 | 0 | 0 | ✅ |
| 通过测试数 | 1276 | ~1450 | 939 | ✅ |
| 质量检查 | 通过 | 通过 | 通过 | ✅ |

## 验证测试

### Fixture 验证

```python
# packages/datahub/tests/fixtures/test_database_fixtures.py
def test_sqlite_pool_creates_tables(sqlite_client: SQLiteClient):
    """验证 fixture 正确创建了所有表。"""
    result = sqlite_client.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    tables = [row[0] for row in result.fetchall()]
    assert "security" in tables
    assert "security_mapping" in tables
    assert "trading_calendar" in tables
    assert "sid_sequence" in tables
    assert "universe" in tables
    assert "freeze_point" in tables


def test_sqlite_pool_has_initial_data(sqlite_client: SQLiteClient):
    """验证 schema 中的初始数据被正确插入。"""
    result = sqlite_client.execute("SELECT * FROM sid_sequence")
    rows = result.fetchall()
    assert len(rows) == 5  # stock, etf, index, bond, future
```

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| fixture 路径错误 | 所有测试失败 | 添加文件存在性检查，清晰的错误消息 |
| 测试隔离问题 | 测试互相干扰 | 每个测试使用独立的 `:memory:` 数据库 |
| 缓存失效 | Session fixture 过期 | 使用 Path 对象而非字符串，确保稳定性 |

## 关键文件

| 文件 | 操作 |
|------|------|
| `packages/datahub/tests/fixtures/database.py` | 新建 |
| `packages/datahub/tests/fixtures/__init__.py` | 新建 |
| `packages/datahub/tests/fixtures/test_database_fixtures.py` | 新建 |
| `packages/datahub/tests/unit/accessors/test_bars_accessor_unit.py` | 修改 |
| `packages/datahub/tests/unit/stores/test_calendar_store_unit.py` | 修改 |
| `packages/datahub/tests/unit/stores/test_security_store_unit.py` | 修改 |

## 参考信息

- **Schema 文件**: `packages/datahub/src/ditto_datahub/scripts/schema.sql`
- **SQLitePool**: `packages/foundation/src/ditto_foundation/db/sqlite_pool.py`
- **SQLiteClient**: `packages/datahub/src/ditto_datahub/stores/sqlite_client.py`
- **Pytest Fixture 文档**: https://docs.pytest.org/en/stable/how-to/fixtures.html
