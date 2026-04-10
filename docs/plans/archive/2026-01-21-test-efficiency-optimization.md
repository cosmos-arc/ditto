# 测试效率与边界问题综合优化计划

## 执行摘要

基于对项目测试的完整审查（1928 个测试用例），发现了**单元测试耗时严重超标**（部分测试耗时 3+ 秒，规范要求 <500ms）、**测试边界混淆**、**SQLite 文件锁**、**inline-snapshot 并行冲突**等关键问题。

本计划提供**系统化修复方案**，预期将测试运行时间从 **~74s（单元测试）降低到 <10s**，并建立清晰的测试边界规范。

---

## 问题概览

### 问题统计

| 类别 | 严重程度 | 影响范围 | 预期损失 |
|------|---------|---------|---------|
| **单元测试耗时超标** | P0 - 严重 | 9+ 个测试 >3s | 每次运行 +60s |
| **SQLite 文件锁** | P0 - 严重 | 所有集成测试 | Windows 清理失败 |
| **测试边界混淆** | P1 - 中等 | `test_bars_store_unit.py` | 架构不清晰 |
| **inline-snapshot 并行冲突** | P1 - 中等 | 快照测试 | 无法并行 |
| **可观测性外部依赖** | P2 - 低 | 集成测试 | 网络连接失败 |

### 耗时数据分析

**最慢的单元测试**（超过规范要求）：
```
3.06s - test_source_unit.py::test_fetch_calendar_api_error_raises
3.05s - test_source_unit.py::test_fetch_adj_factor_api_error_raises
3.05s - test_source_unit.py::test_fetch_list_status_data_returns_empty_dataframe_on_api_error
3.05s - test_source_unit.py::test_fetch_suspend_data_returns_empty_dataframe_on_api_error
3.04s - test_source_unit.py::test_fetch_fund_adj_api_error_raises
3.04s - test_source_unit.py::test_fetch_stock_basic_api_error_raises
3.04s - test_source_unit.py::test_fetch_calendar_api_error_raises
3.03s - test_source_unit.py::test_fetch_st_data_returns_empty_dataframe_on_api_error
3.00s - test_cache_ttl_unit.py::test_individual_ttl_get_stats
9.00s - test_cache_ttl_unit.py (3 个测试总计)
2.20s - test_cache_runtime_unit.py::test_set_with_custom_ttl
1.54s - test_dates_property_unit.py::TestNormalizeDateProperties::test_datetime_to_string_roundtrip
```

**规范要求**：
- 单元测试：<500ms
- 集成测试：<5s

---

## 一、P0 级别问题：单元测试耗时严重超标

### 问题 1.1：真实 `time.sleep()` 导致测试慢

**影响文件**：
- [packages/data/tests/unit/runtime/test_cache_ttl_unit.py](packages/data/tests/unit/runtime/test_cache_ttl_unit.py)
- [packages/data/tests/unit/runtime/test_cache_runtime_unit.py](packages/data/tests/unit/runtime/test_cache_runtime_unit.py)

**问题代码**：
```python
# ❌ 错误：真实等待 3 秒
def test_individual_ttl(time_machine: None) -> None:
    with time_machine_lib.travel(0, tick=False):  # tick=False 导致真实等待
        cache = DataCache(ttl_seconds=300)
        cache.set("key1", "value1", ttl=2)

        time.sleep(3)  # ❌ 真实等待 3 秒！

        assert cache.get("key1") is None
```

**根本原因**：
1. `time_machine_lib.travel(0, tick=False)` 表示使用 `time_machine` 库，但 `tick=False` 导致时间不会自动前进
2. `time.sleep(3)` 是真实的系统调用，未被 `time_machine` 拦截
3. `fake_time` fixture 已在 `conftest.py` 中定义，但未被使用

**修复方案**：

```python
# ✅ 方案 1：使用 time_machine 的虚拟时间（推荐）
def test_individual_ttl(time_machine: None) -> None:
    with time_machine_lib.travel(0, tick=True):  # ✅ tick=True
        cache = DataCache(ttl_seconds=300)
        cache.set("key1", "value1", ttl=2)

        # ✅ 验证未过期
        assert cache.get("key1") == "value1"

        # ✅ 虚拟时间前进 2 秒（无需真实等待）
        time_machine.move_to(2)

        # ✅ 已过期
        assert cache.get("key1") is None

# ✅ 方案 2：使用 fake_time fixture
def test_individual_ttl(fake_time):  # ✅ 注入 fake_time fixture
    cache = DataCache(ttl_seconds=300)
    cache.set("key1", "value1", ttl=2)

    # ✅ fake_time 使 time.sleep 立即返回
    time.sleep(3)

    assert cache.get("key1") is None
```

**修复文件清单**：
1. `packages/data/tests/unit/runtime/test_cache_ttl_unit.py` (3 个测试)
2. `packages/data/tests/unit/runtime/test_cache_runtime_unit.py` (1 个测试)
3. 确保所有使用 `time.sleep()` 的测试都使用 `time_machine.move_to()` 或 `fake_time` fixture

**预期效果**：
- 单个测试：3s → <0.1s (**30x 提速**)
- 4 个测试总计：~9s → <0.5s

---

### 问题 1.2：SQLite 连接未正确关闭（Windows 文件锁）

**错误信息**：
```
PermissionError: [WinError 32] 另一个程序正在使用此文件，无法访问
: 'C:\\Users\\...\\AppData\\Local\\Temp\\tmpp0ofnqpk\\meta\\hub.sqlite'
```

**影响范围**：所有使用 SQLite 的集成测试

**根本原因**：
1. `SQLitePool.close()` 只关闭**当前线程**的连接
2. DuckDB 的连接可能未正确关闭
3. Windows 文件系统对文件锁的处理更严格

**修复方案**：

```python
def teardown_method(self) -> None:
    """Clean up test environment."""
    try:
        if hasattr(self, "engine"):
            self.engine.close()
    except Exception:
        pass
    try:
        if hasattr(self, "pool"):
            self.pool.close()
            # ✅ 确保连接完全关闭
            del self.pool
    except Exception:
        pass
    # ✅ 垃圾回收，给 Windows 文件系统时间释放锁
    import gc
    gc.collect()
    # ✅ 延迟清理（如果需要）
    import time
    time.sleep(0.1)  # 给文件系统时间释放锁
```

**或者使用 autouse fixture**（更优雅）：

```python
# packages/data/tests/integration/conftest.py
@pytest.fixture(autouse=True)
def ensure_sqlite_cleanup():
    """确保 SQLite 连接在测试后正确关闭"""
    yield
    import gc
    gc.collect()
```

**影响文件**：
1. [packages/data/tests/integration/runtime/test_sql_engine_injection_integration.py](packages/data/tests/integration/runtime/test_sql_engine_injection_integration.py)
2. [packages/data/tests/integration/runtime/test_sql_engine_integration.py](packages/data/tests/integration/runtime/test_sql_engine_integration.py)
3. 所有使用 `SQLitePool` 的集成测试

---

### 问题 1.3：可观测性测试连接外部服务

**错误信息**：
```
ConnectionError: HTTPConnectionPool(host='localhost', port=8428):
Max retries exceeded with url: /opentelemetry/v1/metrics
```

**问题**：集成测试尝试连接 VictoriaMetrics (localhost:8428)，但服务未运行

**修复方案**（使用内存 Registry）：

```python
# ❌ 错误：连接真实服务
@pytest.mark.integration
def test_metrics_integration():
    # 连接 localhost:8428
    response = requests.get("http://localhost:8428/api/v1/query")
    assert response.status_code == 200

# ✅ 正确：使用内存 Registry
from prometheus_client import CollectorRegistry, Counter

@pytest.mark.integration
def test_metrics_integration():
    # ✅ 使用内存 Registry（与真实数据隔离）
    registry = CollectorRegistry()

    # 创建被测组件，注入测试 Registry
    counter = Counter("api_requests_total", "Total API requests", registry=registry)
    counter.labels(method="GET", endpoint="/api/quote").inc()

    # ✅ 验证指标已发射
    metric_value = registry.get_sample_value("api_requests_total", {
        "method": "GET",
        "endpoint": "/api/quote"
    })

    assert metric_value == 1.0
```

**影响文件**：
- 所有使用可观测性的集成测试

**预期效果**：
- 移除网络依赖
- 测试更快、更稳定

---

## 二、P1 级别问题：测试边界混淆

### 问题 2.1：`test_bars_store_unit.py` 边界混淆

**文件**：[packages/data/tests/unit/stores/test_bars_store_unit.py](packages/data/tests/unit/stores/test_bars_store_unit.py)

**问题描述**：
- 标记为单元测试（`@pytest.mark.unit`）
- 但使用**真实文件 I/O** 和 **真实 Parquet 操作**

**违反规范**：
```python
# ❌ 单元测试使用真实组件
class TestBarsStore:
    def setup_method(self) -> None:
        self.temp_dir = TemporaryDirectory()  # ❌ 真实文件系统
        self.store = BarsStore(Path(self.temp_dir.name))  # ❌ 真实 Parquet
```

**单元测试 vs 集成测试判断标准**：

| 测试维度 | 单元测试 ✅ | 集成测试 ✅ |
|---------|-----------|-------------|
| **测试目标** | 单个类的原子功能 | 系统/外部的"接缝"处 |
| **依赖策略** | **完全 Mock** | **真实组件** |
| **数据持久化** | 不关心 | 关键（验证写入/读取） |
| **外部调用** | Mock HTTP 调用 | 真实 Client + Mock 响应 |
| **典型场景** | 算法逻辑、状态机 | DAO、HTTP Client |
| **速度** | 快（毫秒级） | 慢（秒级，有真实 IO） |
| **资源隔离** | Mock（无状态） | `:memory:` / `tmp_path` |

**修复方案 1：迁移到集成测试**（推荐）

```bash
# 1. 移动文件
mv packages/data/tests/unit/stores/test_bars_store_unit.py \
   packages/data/tests/integration/stores/test_bars_store_integration.py

# 2. 更新文件名
```

**修复方案 2：重构为纯单元测试**（如果需要保留在 unit 目录）

```python
# ✅ 纯单元测试：Mock 所有依赖
@pytest.mark.unit
class TestBarsStore:
    def test_write_and_read(self, mocker):
        """Test write and read operations."""
        # ✅ Mock polars.read_parquet 和 df.write_parquet
        mock_read_parquet = mocker.patch("polars.read_parquet")
        mock_write_parquet = mocker.patch("polars.DataFrame.write_parquet")

        # Mock 返回值
        mock_read_parquet.return_value = pl.DataFrame({
            "sid": [100000001],
            "trade_date": [date(2024, 1, 1)],
            "close": [11.0],
        })

        store = BarsStore(Path("/test/path"))

        # 执行测试
        result = store.read("stock_daily", start_date="2024-01-01", end_date="2024-01-31")

        # ✅ 验证调用，而非真实 IO
        mock_read_parquet.assert_called_once()
```

**建议**：迁移到集成测试，因为 BarsStore 的核心价值就是与文件系统的"接缝"验证。

---

### 问题 2.2：`test_sql_engine_injection_integration.py` Schema 初始化失败

**文件**：[packages/data/tests/integration/runtime/test_sql_engine_injection_integration.py](packages/data/tests/integration/runtime/test_sql_engine_injection_integration.py)

**问题描述**：未提供 `schema_path`，导致 `init_schema()` 跳过表初始化

**错误代码**：
```python
def setup_method(self) -> None:
    self.temp_dir = TemporaryDirectory()
    self.data_root = Path(self.temp_dir.name)

    # ❌ 未提供 schema_path
    self.pool = SQLitePool(str(db_path))
    self.pool.init_schema()  # ❌ 不会初始化任何表

    # ❌ CalendarStore 尝试加载 trading_calendar 表时失败
    self.calendar_store = CalendarStore(sqlite_client)
```

**修复方案**：

```python
def setup_method(self) -> None:
    """Set up test environment."""
    self.temp_dir = TemporaryDirectory()
    self.data_root = Path(self.temp_dir.name)

    # ✅ 使用 fixture 或显式提供 schema_path
    schema_path = Path(__file__).parent.parent.parent.parent \
        / "src" / "ditto_data" / "scripts" / "schema.sql"

    self.pool = SQLitePool(str(db_path), schema_path=schema_path)
    self.pool.init_schema()
```

**或者创建共享 fixture**（更好）：

```python
# packages/data/tests/integration/conftest.py
@pytest.fixture
def sqlite_pool_with_schema(sqlite_schema_path: Path, tmp_path: Path) -> SQLitePool:
    """创建已初始化 schema 的 SQLite 连接池（集成测试专用）"""
    db_path = tmp_path / "meta" / "hub.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    pool = SQLitePool(str(db_path), schema_path=sqlite_schema_path)
    pool.init_schema()
    yield pool
    pool.close()
```

---

## 三、P1 级别问题：inline-snapshot 并行冲突

### 问题 3.1：inline-snapshot 与 pytest-xdist 的兼容性

**用户反馈**：inline-snapshot 的测试不能并行

**问题分析**：

1. **快照文件写入冲突**：多个并行测试进程同时写入同一个 `__snapshots__` 目录
2. **快照更新模式需要串行**：`--snapshot-update` 模式下需要独占访问
3. **文件锁竞争**：Windows 文件系统限制更严格

**当前 scripts/test.py 处理**：
```python
# snapshot 模式不并行，避免兼容性问题
if has_snapshot:
    cmd.append("--snapshot-update")
    return cmd  # ❌ 完全串行，没有使用 -n 参数
```

**问题**：
- 所有测试在 snapshot 模式下串行运行
- 没有区分 snapshot 测试和非 snapshot 测试
- 无法利用并行加速非 snapshot 测试

---

### 解决方案：Snapshot Marker（推荐）

#### 方案概述

使用 `@pytest.mark.snapshot` 标记所有使用 inline-snapshot 的测试，然后：
- **非 snapshot 测试**：并行运行
- **snapshot 测试**：串行运行

#### 步骤 1：添加 Snapshot Marker

**文件**：`pyproject.toml`

```toml
[tool.pytest.ini_options]
markers = [
    "unit: Mark test as a unit test",
    "integration: Mark test as an integration test",
    "slow: Mark test as slow running (skip with -m 'not slow')",
    "serial: Mark test that must run serially",
    "snapshot: Mark test that uses inline-snapshot (must run serially)",  # ✅ 新增
]
```

#### 步骤 2：标记使用 Snapshot 的测试

```python
# ✅ 在使用 snapshot 的测试文件中
@pytest.mark.snapshot  # ✅ 添加 snapshot marker
@pytest.mark.unit
def test_backtest_output():
    result = run_backtest(...)
    assert result.summary == snapshot({
        "total_return": 0.156,
        "sharpe_ratio": 1.23,
    })
```

#### 步骤 3：更新 scripts/test.py

**文件**：`scripts/test.py`

```python
def build_pytest_command() -> list[str]:
    """根据参数构建 pytest命令"""
    args = sys.argv[1:]
    cmd = ["pytest", "-v"]

    has_snapshot = "--snapshot" in args
    has_unit = "--unit" in args
    has_integration = "--integration" in args
    has_fast = "--fast" in args
    has_cov = "--cov" in args
    has_cov_xml = "--cov-xml" in args

    paths = [
        arg for arg in args
        if arg.startswith("-") is False
        and arg
        not in ["--snapshot", "--unit", "--integration", "--fast", "--cov", "--cov-xml"]
    ]

    # ✅ Snapshot模式：只运行 snapshot 测试（串行）
    if has_snapshot:
        cmd.append("--snapshot-update")
        cmd.extend(["-m", "snapshot"])  # ✅ 只运行 snapshot 测试
        if paths:
            cmd.extend(paths)
        return cmd

    # 覆盖率相关
    if has_cov_xml:
        cmd.extend([
            "--cov",
            "--cov-report=xml",
            "--cov-report=term-missing",
            "--cov-fail-under=80",
        ])
    elif has_cov:
        cmd.extend(["--cov", "--cov-report=html", "--cov-report=term-missing"])

    # 测试类型选择
    if has_integration:
        # ✅ 集成测试：串行（排除 snapshot）
        cmd.extend(["-m", "integration and not snapshot", "-n", "0"])
    elif has_fast:
        # ✅ 快速测试：跳过 slow/integration/snapshot
        cmd.extend(["-m", "not slow and not integration and not snapshot", "--no-cov", "-q"])
    elif has_unit:
        # ✅ 单元测试：并行（排除 snapshot 和 integration）
        cmd.extend(["-m", "unit and not snapshot and not integration", "-n", "auto"])
    else:
        # ✅ 默认：先并行运行非 snapshot 测试
        cmd.extend(["-m", "not snapshot and not integration", "-n", "auto"])

    # 添加路径参数
    if paths:
        cmd.extend(paths)

    return cmd
```

#### 步骤 4：更新 pyproject.toml 默认配置

```toml
[tool.pytest.ini_options]
addopts = [
    "-ra",
    "-v",
    # ✅ 默认并行运行，排除 snapshot 测试
    "-n", "auto",
    # ✅ 按文件分发，减少冲突（loadfile 或 loadscope）
    "--dist", "loadfile",
    "--strict-markers",
    "--strict-config",
    "--durations=10",
]
```

**说明**：
- `loadfile`: 同一测试文件中的测试会分配到同一个 worker
- 适用于快照测试分散在不同文件中的场景
- 不需要修改测试代码（如果不想添加 marker）

---

#### 步骤 5：创建新命令（可选）

**文件**：`scripts/test.py`

```python
# ✅ 新增：单独运行 snapshot 测试的命令
if __name__ == "__main__":
    import sys

    if "--snapshot-only" in sys.argv:
        # ✅ 只运行 snapshot 测试（串行）
        sys.argv.remove("--snapshot-only")
        cmd = ["pytest", "-v", "-m", "snapshot", "--snapshot-update"]
        sys.exit(subprocess.run(cmd).returncode)
    else:
        # 正常流程
        sys.exit(main())
```

---

### 备选方案 2：使用 `--dist=loadfile`

如果不想添加 marker，只需修改 `pyproject.toml`：

```toml
[tool.pytest.ini_options]
addopts = [
    "-ra",
    "-v",
    "-n", "auto",
    # ✅ 按测试文件分发，同一文件的测试串行运行
    "--dist", "loadfile",
    "--strict-markers",
    "--durations=10",
]
```

**说明**：
- `loadfile`: 同一测试文件中的所有测试会在同一个 worker 进程中串行运行
- 不同测试文件的测试可以并行运行
- 适用于快照测试集中在少数文件中的场景

---

### 备选方案 3：conftest.py 自动检测

**文件**：`packages/*/tests/conftest.py`

```python
import pytest
import os

def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """根据 snapshot 模式自动调整并行配置"""
    # ✅ 检测是否在 snapshot 更新模式
    is_snapshot_mode = "--snapshot-update" in os.sys.argv

    if is_snapshot_mode:
        # ✅ Snapshot 模式：强制所有测试串行运行
        for item in items:
            item.add_marker(pytest.mark.serial)
```

---

## 四、P2 级别问题：其他优化

### 问题 4.1：`test_source_unit.py` 慢速测试原因调查

**耗时**：~3.05s per test

**需要进一步调查**：
1. `respx_mock` 设置是否高效
2. TushareSource 初始化开销（rate limiter、client）
3. 是否存在隐式网络超时

**调查步骤**：
```bash
# 运行单个测试并分析耗时
pixi run -e dev pytest \
  packages/data/tests/unit/sources/tushare/test_source_unit.py::TestTushareSourceCalendar::test_fetch_calendar_api_error_raises \
  --durations=10 -vv --tb=short
```

---

## 五、修复实施计划

### 优先级 P0 - 立即修复（测试耗时）

| 任务 | 文件 | 修复方案 | 预期效果 | 工作量 |
|------|------|---------|---------|-------|
| 修复 time.sleep(3) | `test_cache_ttl_unit.py` | 使用 `time_machine.move_to()` | 9s → 0.5s | 30min |
| 修复 time.sleep(1.2) | `test_cache_runtime_unit.py` | 使用 `time_machine.move_to()` | 1.2s → 0.1s | 15min |
| 修复 SQLite 清理 | 集成测试 conftest | 添加 `gc.collect()` | 移除 PermissionError | 30min |
| 修复可观测性测试 | 集成测试 | 使用内存 Registry | 移除网络依赖 | 1h |

**总计**：~2.5h 工作量，预期单元测试从 74s → <10s

---

### 优先级 P1 - 近期修复（边界规范）

| 任务 | 文件 | 修复方案 | 工作量 |
|------|------|---------|-------|
| 迁移边界混淆测试 | `test_bars_store_unit.py` | 移动到 `integration/` | 30min |
| 修复 Schema 初始化 | `test_sql_engine_injection_integration.py` | 添加 `schema_path` fixture | 15min |
| 实现 Snapshot Marker | `pyproject.toml`, `scripts/test.py` | 添加 marker 和命令逻辑 | 1h |

**总计**：~2h 工作量

---

### 优先级 P2 - 长期优化（性能提升）

| 任务 | 方案 | 预期效果 |
|------|------|---------|
| 并行测试配置 | 单元测试默认并行，按 `loadfile` 分发 | 2-4x 提速 |
| 调查 test_source_unit.py | 分析慢速原因并优化 | 3s → <0.5s |
| Prefect 装饰器 Mock | 在 conftest 中统一 Mock | 避免触发完整引擎 |

---

## 六、测试规范强化

### 单元测试 vs 集成测试边界（强化版）

**核心判断标准**：**是否测试系统与外部的"接缝"处**

| 测试维度 | 单元测试 ✅ | 集成测试 ✅ | 判断依据 |
|---------|-----------|-------------|----------|
| **测试目标** | 单个类的原子功能 | 系统/外部的"接缝"处 | 类自身逻辑 vs 接口契约 |
| **依赖策略** | **完全 Mock** | **真实组件** | 隔离逻辑 vs 验证连接 |
| **数据持久化** | 不关心 | 关键（验证写入/读取） | DAO 写入数据库 |
| **外部调用** | Mock HTTP 调用 | 真实 Client + Mock 响应 | API 响应解析 |
| **典型场景** | 算法逻辑、状态机、数据转换 | DAO、HTTP Client、消息队列 | 内部逻辑 vs 外部接口 |
| **速度** | 快（毫秒级） | 慢（秒级，有真实 IO） | 无 IO vs 有 IO |
| **资源隔离** | Mock（无状态） | `:memory:` / `tmp_path` | 临时资源，与真实数据隔离 |

---

### 资源隔离策略（强制要求）

| 资源类型 | 单元测试 | 集成测试 |
|---------|---------|-------------|
| **SQLite** | Mock SQLitePool | `:memory:` 数据库 |
| **文件** | Mock 文件操作 | `tmp_path` fixture |
| **HTTP** | `respx.mock()` | 真实 Client + Mock 响应 |
| **可观测性** | Mock Registry | 内存 CollectorRegistry |
| **时间** | `fake_time` / `time_machine` | 真实时间或 `time_machine` |

---

### 禁止模式（绝对禁止）

| ❌ 禁止 | ✅ 正确 | 原因 |
|---------|---------|------|
| 单元测试中使用 `TemporaryDirectory()` | Mock 文件操作 | 单元测试应无真实 IO |
| 单元测试中使用真实 SQLite | Mock SQLitePool | 单元测试应完全隔离 |
| 集成测试连接外部服务 | 使用内存 Mock | 集成测试应可重复 |
| `time.sleep(n)` 等待真实时间 | `time_machine.move_to(n)` | 测试应快速、确定性 |
| `assert True` | 验证具体行为 | 假测试无价值 |

---

## 七、并行测试配置建议

### 当前配置分析

**文件**：`pyproject.toml`

```toml
[tool.pytest.ini_options]
addopts = [
    "-ra",
    "-v",
    # "-n", "auto",  # ❌ 已移除全局并行配置
    "--strict-markers",
    "--durations=10",
]
```

**移除全局并行的原因**（根据注释）：
> "移除全局并行配置，改为命令级别控制（支持分层并行策略）"

---

### 推荐配置

```toml
[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["packages/*/tests", "apps/*/tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
pythonpath = [
    "packages/core/src",
    "packages/foundation/src",
    "packages/data/src",
    "apps/port/src",
]

filterwarnings = ["error", "ignore::UserWarning", "ignore::DeprecationWarning"]

markers = [
    "unit: Mark test as a unit test",
    "integration: Mark test as an integration test",
    "slow: Mark test as slow running (skip with -m 'not slow')",
    "serial: Mark test that must run serially",
    "snapshot: Mark test that uses inline-snapshot (must run serially)",  # ✅ 新增
]

log_cli = true
log_cli_level = "INFO"
asyncio_mode = "strict"

addopts = [
    "-ra",
    "-v",
    # ✅ 默认并行运行，但排除 snapshot 测试
    "-n", "auto",
    # ✅ 按文件分发，减少冲突（loadfile 或 loadscope）
    "--dist", "loadfile",
    "--strict-markers",
    "--strict-config",
    "--durations=10",
]
```

---

### 分层并行策略

**命令级别控制**（通过 scripts/test.py）：

```bash
# ✅ 单元测试：并行运行（默认）
pixi run test --unit

# ✅ 集成测试：串行运行
pixi run test --integration

# ✅ 快速测试：并行，跳过 slow/integration/snapshot
pixi run test --fast

# ✅ Snapshot 测试：串行运行
pixi run test --snapshot

# ✅ 全部测试：智能并行
pixi run test
```

---

## 八、验证检查清单

### 提交前检查

- [ ] 运行 `pixi run -e dev test --unit` - 确保单元测试通过且快速
- [ ] 运行 `pixi run -e dev test --integration` - 确保集成测试通过
- [ ] 运行 `pixi run -e dev pytest --durations=20` - 确保无慢速测试
- [ ] 检查无 `PermissionError` 文件锁错误
- [ ] 验证 `pytest --collect-only` 无 import 冲突

---

### CI 检查

- [ ] 并行测试不出现 `xdist` 冲突
- [ ] Snapshot 测试串行运行且通过
- [ ] 覆盖率 >= 80%
- [ ] 无 SQLite 文件锁错误

---

## 九、预期成果

### 性能提升

| 指标 | 修复前 | 修复后 | 提升 |
|------|-------|-------|------|
| 单元测试耗时 | ~74s | <10s | **7.4x** |
| 最慢单个测试 | 3.06s | <0.5s | **6x** |
| 并行加速比 | 1x（串行） | 2-4x | **2-4x** |
| 总体测试耗时 | ~120s | <30s | **4x** |

---

### 质量提升

- ✅ 清晰的测试边界规范
- ✅ 无 SQLite 文件锁错误
- ✅ inline-snapshot 并行兼容
- ✅ 测试隔离性更好
- ✅ 开发反馈循环更快

---

## 十、后续优化

### P3 - 持续优化

| 任务 | 方案 | 优先级 |
|------|------|-------|
| 调查 test_source_unit.py 慢速原因 | 性能分析 | 低 |
| 统一 Prefect 装饰器 Mock | conftest.py 自动 Mock | 中 |
| 使用 `pytest-benchmark` 建立性能基准 | 性能回归检测 | 低 |
| 考虑使用 `pytest-parallel` 替代 xdist | 更细粒度并行控制 | 低 |

---

## 附录 A：相关资源

### 内部文档

- [测试规范](../.claude/rules/python-test.md)
- [架构规范](../.claude/rules/architecture.md)
- [工作流规范](../.claude/rules/workflow.md)

### 外部资源

- [inline-snapshot GitHub](https://github.com/15r10nk/inline-snapshot)
- [pytest-xdist 文档](https://pytest-xdist.readthedocs.io/)
- [pytest 最佳实践](https://docs.pytest.org/)

---

## 附录 B：变更日志

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-01-21 | 1.0 | 初始版本，完整测试审查和分析 |

---

**文档所有者**: Claude Code
**最后更新**: 2026-01-21
**状态**: 待实施
