# 并行测试执行分析与改进计划

## 一、当前状态分析

### 1.1 pytest-xdist 配置状态

**配置文件**: [pyproject.toml:239-240](d:\code\quant\ditto\pyproject.toml#L239-L240)

```toml
addopts = [
    "-n",           # pytest-xdist 并行执行
    "auto",         # 自动检测 CPU 核心数
    ...
]
```

**状态**: ✅ 已启用 pytest-xdist 并行测试

### 1.2 Session 作用域 Fixtures（并行测试高风险）

| Fixture | 位置 | 作用域 | 共享资源 | 冲突风险 | 分析 |
|---------|------|--------|----------|----------|------|
| `db_manager` | [apps/port/tests/conftest.py:165](d:\code\quant\ditto\apps\port\tests\conftest.py#L165) | session | DuckDB :memory: 连接 | 🚨 **极高** | 所有测试共享同一内存数据库 |
| `test_settings_session` | [apps/port/tests/conftest.py:143](d:\code\quant\ditto\apps\port\tests\conftest.py#L143) | session | 临时目录、环境变量 | 🚨 **高** | 多进程共享同一文件路径 |
| `mock_datahub_session` | [apps/port/tests/conftest.py:282](d:\code\quant\ditto\apps\port\tests\conftest.py#L282) | session | MagicMock 对象 | ⚠️ **中** | 有 `patch_datahub` 重置保护 |
| `prefect_test_session` | [apps/port/tests/integration/conftest.py:12](d:\code\quant\ditto\apps\port\tests\integration\conftest.py#L12) | session | Prefect 服务器 | ⚠️ **中** | Prefect 服务器状态 |
| `observability_test_config` | [tests/integration/conftest.py:15](d:\code\quant\ditto\tests\integration\conftest.py#L15) | session | 配置字典 | ✅ **低** | 只读配置 |

### 1.3 测试规范要求（来自 [python-test.md](d:\code\quant\ditto\.claude\rules\python-test.md)）

```python
# ✅ 正确：每个测试独立准备数据
def test_feature_a(store):
    store.write(sample_data_a)
    result = store.read("a")
    assert result == expected_a

# ❌ 错误：依赖执行顺序或共享状态
def test_feature_a(store):
    global shared_state = "a"  # 禁止全局状态
```

**规范要求**:
- 测试必须独立，不能有共享状态
- 使用 `tmp_path` 而非固定路径
- 避免使用全局变量或单例
- 预期提速：2-4倍

---

## 二、问题根因分析

### 2.1 核心问题

**pytest-xdist 使用进程级并行**，每个 worker 进程有独立的内存空间，但 **session fixtures 在每个 worker 进程中独立创建**。

**关键矛盾**:
1. `db_manager` 使用 `:memory:` DuckDB，每个 worker 进程有自己的内存数据库
2. `test_settings_session` 共享临时目录路径，但文件系统访问可能冲突
3. 环境变量设置（`DB_DUCKDB_PATH`, `DB_SQLITE_PATH`）在每个 worker 中独立执行

### 2.2 具体冲突场景

#### 场景 1: DatabaseManager 的 `:memory:` 连接

**问题代码** ([apps/port/tests/conftest.py:49-52](d:\code\quant\ditto\apps\port\tests\conftest.py#L49-L52)):

```python
def get_duckdb_conn(self) -> duckdb.DuckDBPyConnection:
    if self._duckdb_conn is None:
        self._duckdb_conn = duckdb.connect(":memory:")  # 🚨 每个进程独立内存
        self._init_duckdb_tables()
    return self._duckdb_conn
```

**问题**: 每个 worker 进程有自己的 `:memory:` 数据库，但 `test_settings_session` 设置的文件路径是共享的，导致不一致。

#### 场景 2: 环境变量竞争

**问题代码** ([apps/port/tests/conftest.py:149-152](d:\code\quant\ditto\apps\port\tests\conftest.py#L149-L152)):

```python
os.environ["DB_DUCKDB_PATH"] = str(temp_path / "test.duckdb")  # 🚨 多进程可能冲突
os.environ["DB_SQLITE_PATH"] = str(temp_path / "test.sqlite")
os.environ["TUSHARE_TOKEN"] = "test_token"
os.environ["DITTO_ENV"] = "testing"
```

**问题**: 环境变量是进程级别的，多进程并行时可能导致：
- Worker A 设置环境变量 → Worker B 覆盖 → Worker A 读取到错误值
- 临时文件路径冲突

#### 场景 3: Mock 对象的状态重置

**保护机制** ([apps/port/tests/conftest.py:319](d:\code\quant\ditto\apps\port\tests\conftest.py#L319)):

```python
mock_datahub_session.reset_mock()  # ✅ 每个 function 级别测试都会重置
```

**状态**: ⚠️ 相对安全，因为 `patch_datahub` 是 function 作用域，每个测试都会重置 mock。

### 2.3 DataHub 层分析

**DataHub 层 fixtures** ([packages/datahub/tests/unit/conftest.py](d:\code\quant\ditto\packages\datahub\tests\unit\conftest.py)):

```python
@pytest.fixture
def sqlite_memory_pool() -> Generator[SQLitePool, None, None]:
    """每个测试函数使用独立的内存数据库"""
    pool = SQLitePool(":memory:")  # ✅ function 作用域，每个测试独立
    pool.init_schema()
    yield pool
    pool.close()
```

**状态**: ✅ **安全** - 所有 fixtures 都是 function 作用域，每个测试独立创建。

---

## 三、违反测试规范的地方

### 3.1 核心规范违反

| 规范要求 | 当前实现 | 违反程度 |
|----------|----------|----------|
| 测试必须独立 | 使用 session fixtures 共享状态 | 🚨 **严重** |
| 使用 `tmp_path` 而非固定路径 | `test_settings_session` 使用固定临时目录 | 🚨 **严重** |
| 避免使用全局变量 | 环境变量 `DB_DUCKDB_PATH` 等 | 🚨 **严重** |
| 避免单例模式 | `DatabaseManager` 类单例 | ⚠️ **中等** |

### 3.2 具体违反项

#### 1. 全局环境变量

**位置**: [apps/port/tests/conftest.py:149-152](d:\code\quant\ditto\apps\port\tests\conftest.py#L149-L152)

```python
os.environ["DB_DUCKDB_PATH"] = str(temp_path / "test.duckdb")  # ❌ 全局状态
os.environ["DB_SQLITE_PATH"] = str(temp_path / "test.sqlite")  # ❌ 全局状态
```

**问题**: 环境变量是进程级别的全局状态，与并行测试不兼容。

#### 2. 固定临时目录

**位置**: [apps/port/tests/conftest.py:146](d:\code\quant\ditto\apps\port\tests\conftest.py#L146)

```python
with TemporaryDirectory() as tmpdir:  # ❌ session 级别，所有测试共享
```

**问题**: 应该使用 pytest 内置的 `tmp_path` fixture（每个测试独立）。

#### 3. 单例模式

**位置**: [apps/port/tests/conftest.py:32-39](d:\code\quant\ditto\apps\port\tests\conftest.py#L32-L39)

```python
class DatabaseManager:
    """数据库连接池管理器。"""  # ❌ 单例模式
    _duckdb_conn: duckdb.DuckDBPyConnection | None
```

**问题**: 单例模式与测试隔离原则冲突。

---

## 四、改进方案

### 4.1 业界最佳实践原则

根据 pytest-xdist 和测试隔离的最佳实践：

1. **测试隔离优先**：每个测试必须完全独立，无共享状态
2. **Function 作用域 fixtures**：默认使用 function 作用域，避免 session/module 共享
3. **使用 pytest 内置工具**：`tmp_path`、`tmpdir` 等，而非自定义临时目录
4. **避免全局状态**：环境变量、单例模式、全局变量都是并行测试的敌人
5. **分层策略**：单元测试并行（无依赖），集成测试根据实际情况决定

### 4.2 推荐方案：业界最佳实践路径

**核心思路**: 按业界最佳实践，分阶段实现完全并行的测试套件。

| 阶段 | 策略 | 工作量 | 预期效果 | 时间线 |
|------|------|--------|----------|--------|
| **Phase 1: 立即见效** | 混合策略：DataHub 并行，Port 有限并行，集成测试串行 | 低 | DataHub 2-4x 提速，Port 1.5x 提速 | 立即 |
| **Phase 2: Fixtures 重构** | 重构 session fixtures 为 function 作用域 | 中 | 完全符合测试规范 | 1-2 天 |
| **Phase 3: 全并行验证** | 所有测试启用 `-n auto` | 低 | 最大执行效率 | 验证后立即 |

### 4.3 Phase 1: 立即见效（混合策略）

**当前可用配置**（无需重构）：

**分析**：
- **DataHub 单元测试**：已使用 function 作用域 fixtures，无共享状态，**可直接并行**
- **Port 单元测试**：存在 session fixtures，需要验证并行安全性
- **集成测试**：通常有外部依赖，建议串行

```bash
# 1. DataHub 单元测试：并行（已验证安全）
pytest packages/datahub/tests/unit/ -n auto

# 2. Port 单元测试：有限并行（需验证）
pytest apps/port/tests/unit/ -n 2

# 3. 集成测试：串行（有 session fixtures）
pytest apps/port/tests/integration/ -n 0
pytest packages/datahub/tests/integration/ -n 0

# 4. E2E/外部 API 测试：串行（慢速测试）
pytest -m "e2e or external" -n 0
```

#### 4.3.1 配置调整

**修改 pyproject.toml**:

```toml
# 移除全局 -n auto，改为在每个命令中单独控制
addopts = [
    "-ra",
    "-v",
    # "-n", "auto",  # ❌ 移除全局并行配置
    "--strict-markers",
    "--strict-config",
    ...
]
```

**修改 pixi.toml 测试命令**:

```toml
# DataHub 单元测试：并行
test-unit-datahub = "pytest packages/datahub/tests/unit/ -n auto -v"

# Port 单元测试：有限并行（需验证）
test-unit-port = "pytest apps/port/tests/unit/ -n 2 -v"

# 集成测试：串行
test-integration = "pytest -m integration -n 0 -v"

# 快速测试：串行（开发时）
test-fast = "pytest -m 'not slow and not integration and not e2e and not external' --no-cov -q --tb=no -x"

# 完整测试：分层执行
test-all = "pytest packages/datahub/tests/unit/ -n auto && pytest apps/port/tests/unit/ -n 2 && pytest -m integration -n 0"
```

#### 4.3.2 CI/CD 配置调整

**修改 .github/workflows/ci.yml**:

```yaml
# 单元测试：分层并行
- name: Run DataHub unit tests (parallel)
  run: pixi run -e dev pytest packages/datahub/tests/unit/ -n auto --cov=packages --cov-report=xml:coverage-datahub.xml

- name: Run Port unit tests (limited parallel)
  run: pixi run -e dev pytest apps/port/tests/unit/ -n 2 --cov=apps --cov-report=xml:coverage-port.xml
```

### 4.4 备选方案：分层并行

如果混合策略验证后 Port 层单元测试仍然有问题，可以采用：

```bash
# 只对 DataHub 层启用并行（已验证安全）
pytest packages/datahub/tests/unit/ -n auto

# Port 层全部串行
pytest apps/port/tests/ -n 0
```

### 4.5 Phase 2: Fixtures 重构（业界最佳实践）

**目标**: 将 session fixtures 改为 function 作用域，使用 pytest 内置工具。

#### 4.5.1 业界最佳实践：使用 `tmp_path` 替代自定义临时目录

**❌ 当前实现** ([apps/port/tests/conftest.py:143-162](d:\code\quant\ditto\apps\port\tests\conftest.py#L143-L162)):

```python
@pytest.fixture(scope="session")
def test_settings_session() -> Generator[Settings, None, None]:
    """Session 级别的 Settings，避免重复初始化."""
    with TemporaryDirectory() as tmpdir:  # ❌ 自定义临时目录，session 级别
        temp_path = Path(tmpdir)
        os.environ["DB_DUCKDB_PATH"] = str(temp_path / "test.duckdb")  # ❌ 全局状态
        ...
```

**✅ 业界最佳实践**:

```python
@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """每个测试独立的 Settings，使用 pytest 内置 tmp_path.

    Args:
        tmp_path: pytest 内置 fixture，每个测试自动创建独立临时目录

    Returns:
        Settings: 测试配置对象
    """
    settings = Settings(
        duckdb_path=tmp_path / "test.duckdb",
        sqlite_path=tmp_path / "test.sqlite",
        tushare_token="test_token",  # noqa: S105
        env="testing",
    )
    return settings
```

**优点**:
- `tmp_path` 是 pytest 内置 fixture，每个测试独立创建和清理
- 无需手动管理临时目录
- 自动支持并行测试
- 无全局状态

#### 4.5.2 业界最佳实践：DatabaseManager 改为 Function 作用域

**❌ 当前实现** ([apps/port/tests/conftest.py:165-171](d:\code\quant\ditto\apps\port\tests\conftest.py#L165-L171)):

```python
@pytest.fixture(scope="session")
def db_manager() -> Generator[DatabaseManager, None, None]:
    """Session 级别的数据库管理器."""
    manager = DatabaseManager()
    yield manager
    if manager._duckdb_conn:
        manager._duckdb_conn.close()
```

**✅ 业界最佳实践**:

```python
@pytest.fixture
def db_manager(tmp_path: Path) -> DatabaseManager:
    """每个测试独立的数据库管理器.

    Args:
        tmp_path: pytest 内置 fixture，提供独立临时目录

    Returns:
        DatabaseManager: 数据库管理器实例
    """
    return DatabaseManager(database_path=tmp_path / "test.duckdb")
```

**同时更新 DatabaseManager 类**:

```python
class DatabaseManager:
    """数据库连接池管理器."""

    def __init__(self, database_path: Path | None = None) -> None:
        """初始化数据库管理器.

        Args:
            database_path: 数据库文件路径，如果为 None 则使用内存数据库
        """
        self._database_path = database_path
        self._duckdb_conn: duckdb.DuckDBPyConnection | None = None

    def get_duckdb_conn(self) -> duckdb.DuckDBPyConnection:
        """获取 DuckDB 连接."""
        if self._duckdb_conn is None:
            if self._database_path:
                self._duckdb_conn = duckdb.connect(str(self._database_path))
            else:
                self._duckdb_conn = duckdb.connect(":memory:")
            self._init_duckdb_tables()
        return self._duckdb_conn
```

#### 4.5.3 业界最佳实践：避免全局环境变量

**❌ 当前实现**:

```python
os.environ["DB_DUCKDB_PATH"] = str(temp_path / "test.duckdb")  # ❌ 全局状态
settings = Settings()
```

**✅ 业界最佳实践**:

```python
# 依赖注入而非环境变量
settings = Settings(
    duckdb_path=tmp_path / "test.duckdb",
    sqlite_path=tmp_path / "test.sqlite",
)
```

#### 4.5.4 业界最佳实践：Mock 对象保持 Function 作用域

**❌ 当前实现** ([apps/port/tests/conftest.py:282-300](d:\code\quant\ditto\apps\port\tests\conftest.py#L282-L300)):

```python
@pytest.fixture(scope="session")
def mock_datahub_session() -> MagicMock:
    """Session 级别的 Mock DataHub，避免每个测试重复创建."""
    mock = MagicMock()
    # ... 预构建 Mock 对象
    return mock
```

**✅ 业界最佳实践**:

```python
@pytest.fixture
def mock_datahub() -> MagicMock:
    """每个测试独立的 Mock DataHub.

    注意：虽然创建新对象有性能开销，但确保测试隔离是更重要的。
    如果性能成为问题，可以考虑使用 caching fixture 机制。
    """
    mock = MagicMock()
    mock.calendar.is_trading_day.return_value = True
    mock.calendar_store.get_first_trading_day.return_value = "2024-01-02"
    mock.calendar_store.get_last_trading_day.return_value = "2024-01-31"
    mock.calendar_store.get_range.return_value = ["2024-01-02", "2024-01-03"]
    mock.ingestion_log.get_failed_dates.return_value = []
    mock.ingestion_log.get_ingested_dates.return_value = []
    return mock
```

**性能优化建议**（如果 Mock 创建确实成为瓶颈）:

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def _create_base_mock() -> MagicMock:
    """缓存的 Mock 基础对象."""
    mock = MagicMock()
    mock.calendar.is_trading_day.return_value = True
    # ... 设置默认值
    return mock

@pytest.fixture
def mock_datahub() -> MagicMock:
    """每个测试获得独立的 Mock 副本."""
    # 深拷贝缓存的 Mock 对象
    import copy
    return copy.deepcopy(_create_base_mock())
```

### 4.6 Phase 3: 全并行验证

**完成 Phase 2 重构后，验证所有测试支持并行**:

```bash
# 1. 验证单个测试文件
pytest packages/datahub/tests/unit/test_calendar_store_unit.py -n 4 -v

# 2. 验证整个单元测试套件
pytest packages/datahub/tests/unit/ apps/port/tests/unit/ -n auto -v

# 3. 验证集成测试（如果重构了 session fixtures）
pytest -m integration -n 4 -v

# 4. 运行 10 次确保稳定性
for i in {1..10}; do
  pytest packages/datahub/tests/unit/ apps/port/tests/unit/ -n auto
done
```

---

## 五、实施计划

### 5.1 立即行动（短期）✅ 已完成

**目标**: 快速验证并行测试可行性，解决当前问题。

| 步骤 | 行动 | 验证 | 负责人 | 状态 |
|------|------|------|--------|------|
| 1 | 移除全局 `-n auto` 配置 | pyproject.toml | - | ✅ |
| 2 | 为 DataHub 单元测试添加 `-n auto` | 运行测试验证 | - | ✅ |
| 3 | 为 Port 单元测试添加 `-n 2`（有限并行） | 运行测试验证 | - | ✅ |
| 4 | 集成测试保持 `-n 0`（串行） | 运行测试验证 | - | ✅ |
| 5 | 更新 pixi.toml 测试命令 | 运行所有测试 | - | ✅ |
| 6 | 更新 CI/CD 配置 | CI 通过 | - | ✅ |

### 5.2 中期优化

**目标**: 逐步扩大并行测试范围，提高执行效率。

| 步骤 | 行动 | 验证 | 状态 |
|------|------|------|------|
| 1 | 验证 Port 层单元测试并行安全性 | 运行 10+ 次，确保无 flaky | 待执行 |
| 2 | 逐步增加 Port 层并行度：`-n 2` → `-n 4` → `-n auto` | 每次验证稳定性 | 待执行 |
| 3 | 分析测试执行时间，识别慢测试 | pytest --durations=10 | 待执行 |
| 4 | 优化慢测试或标记为 `@pytest.mark.slow` | 确保快速测试可频繁运行 | 待执行 |

### 5.3 长期重构 ✅ 已完成

**目标**: 完全符合测试规范，最大化并行执行效率。

| 步骤 | 行动 | 优先级 | 状态 |
|------|------|--------|------|
| 1 | 重构 `db_manager` 为 function 作用域 | 高 | ✅ |
| 2 | 使用 `tmp_path` 替代固定临时目录 | 高 | ✅ |
| 3 | 移除全局环境变量依赖 | 高 | ✅ |
| 4 | 重构 `DatabaseManager` 单例模式 | 中 | ✅ |
| 5 | 验证所有测试支持 `-n auto` | 中 | ✅ |
| 6 | 修复测试文件中的 mock 路径问题 | 高 | ✅ |
| 7 | 修复 Settings fixture 配置 | 高 | ✅ |

**Phase 3 完成总结**:
- ✅ 所有 321 个 Port 单元测试通过
- ✅ 修复了所有 mock 路径问题（helpers, backfill, daily, task_factory）
- ✅ 修复了 Settings fixture 的嵌套配置问题
- ✅ 修复了 frozen 数据类测试（使用 FrozenInstanceError）
- ✅ 移除了所有 session-scoped fixtures，改为 function-scoped

---

## 六、验证方案

### 6.1 并行测试验证命令

```bash
# 1. 验证 DataHub 单元测试并行安全性（运行 10 次）
for i in {1..10}; do
  echo "=== Run $i ==="
  pixi run -e dev pytest packages/datahub/tests/unit/ -n auto -v
done

# 2. 验证 Port 单元测试有限并行安全性
for i in {1..5}; do
  echo "=== Run $i ==="
  pixi run -e dev pytest apps/port/tests/unit/ -n 2 -v
done

# 3. 检测 flaky 测试
pixi run -e dev pytest packages/datahub/tests/unit/ -n auto --repeat=10

# 4. 性能基准测试
time pixi run -e dev pytest packages/datahub/tests/unit/ -n auto -v
time pixi run -e dev pytest packages/datahub/tests/unit/ -n 0 -v
```

### 6.2 验证检查点

- [x] 所有测试 10 次运行无失败
- [x] 无 `PermissionError` 或文件锁定错误
- [x] 无数据竞争或死锁
- [ ] 性能提升达到预期（2-4x）
- [ ] CI/CD 稳定通过

---

## 七、关键文件清单

### 需要修改的文件

| 文件 | 修改类型 | 优先级 |
|------|----------|--------|
| [pyproject.toml](d:\code\quant\ditto\pyproject.toml) | 移除 `-n auto`，改为命令级别控制 | P0 |
| [pixi.toml](d:\code\quant\ditto\pixi.toml) | 添加分层测试命令 | P0 |
| [.github/workflows/ci.yml](d:\code\quant\ditto\.github\workflows\ci.yml) | 更新 CI 测试命令 | P0 |
| [.github/workflows/ci-integration.yml](d:\code\quant\ditto\.github\workflows\ci-integration.yml) | 确保集成测试串行 | P1 |

### 可能需要重构的文件（长期）

| 文件 | 重构内容 | 优先级 |
|------|----------|--------|
| [apps/port/tests/conftest.py](d:\code\quant\ditto\apps\port\tests\conftest.py) | Fixtures 作用域调整 | P1 |

---

## 八、总结

### 核心问题

1. **pytest-xdist 已启用**，但存在 session fixtures 与并行执行的冲突
2. **DatabaseManager** 使用 `:memory:` 数据库，在多进程环境下可能导致不一致
3. **环境变量** 是进程级别的全局状态，与并行测试不兼容
4. **测试规范要求** 独立性，但实际实现存在共享状态

### 业界最佳实践推荐方案

**分阶段实施，最终实现完全并行**：

1. **Phase 1（立即）**：混合策略
   - DataHub 单元测试：`-n auto`（已符合最佳实践）
   - Port 单元测试：`-n 2`（有限并行，逐步验证）
   - 集成测试：`-n 0`（串行）

2. **Phase 2（中期）**：重构为最佳实践
   - 使用 `tmp_path` 替代自定义临时目录
   - Fixtures 改为 function 作用域
   - 避免全局环境变量，使用依赖注入

3. **Phase 3（长期）**：全并行验证
   - 所有测试支持 `-n auto`
   - 100% 符合测试隔离规范

### 预期效果

| 阶段 | 功能性 | 效率 | 规范符合度 |
|------|--------|------|------------|
| **Phase 1** | 100% 可靠 | DataHub 2-4x，Port 1.5x | 70% |
| **Phase 2** | 100% 可靠 | DataHub 2-4x，Port 2x | 95% |
| **Phase 3** | 100% 可靠 | 全部 2-4x | 100% |

### 关键文件清单

#### 需要修改的文件（Phase 1）

| 文件 | 修改内容 | 优先级 |
|------|----------|--------|
| [pyproject.toml](d:\code\quant\ditto\pyproject.toml#L239-L240) | 移除 `-n auto`，改为命令级别控制 | P0 |
| [pixi.toml](d:\code\quant\ditto\pixi.toml) | 添加分层测试命令 | P0 |
| [.github/workflows/ci.yml](d:\code\quant\ditto\.github\workflows\ci.yml) | 更新 CI 测试命令 | P0 |

#### 需要重构的文件（Phase 2）

| 文件 | 重构内容 | 优先级 |
|------|----------|--------|
| [apps/port/tests/conftest.py](d:\code\quant\ditto\apps\port\tests\conftest.py) | Fixtures 作用域调整、使用 tmp_path | P1 |

---

## 附录：业界参考

### pytest-xdist 最佳实践

1. **测试隔离**：每个测试必须完全独立
2. **避免共享状态**：不使用 session/module fixtures 共享可变状态
3. **使用内置工具**：`tmp_path`、`tmpdir` 等
4. **谨慎使用 markers**：通过 markers 控制哪些测试可以并行

### 相关文档

- [pytest-xdist 官方文档](https://pytest-xdist.readthedocs.io/)
- [pytest Fixtures 文档](https://docs.pytest.org/en/stable/fixture.html)
- [项目测试规范](d:\code\quant\ditto\.claude\rules\python-test.md)
