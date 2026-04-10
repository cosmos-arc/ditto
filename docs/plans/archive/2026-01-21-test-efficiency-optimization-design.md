# 测试效率与边界优化设计文档

## 元数据

| 属性 | 值 |
|------|-----|
| **创建日期** | 2026-01-21 |
| **状态** | 设计阶段 |
| **优先级** | P0 + P1 + P2（全部） |
| **预期耗时** | ~6h |
| **负责人** | Claude Code |

---

## 1. 设计目标

### 1.1 性能目标

| 指标 | 当前值 | 目标值 | 提升 |
|------|--------|--------|------|
| 单元测试耗时 | ~74s | <10s | **7.4x** |
| 最慢单元测试 | 3.06s | <0.5s | **6x** |
| 并行加速比 | 1x | 2-4x | **2-4x** |
| 总体测试耗时 | ~120s | <30s | **4x** |

### 1.2 质量目标

- ✅ 清晰的测试边界规范
- ✅ 无 SQLite 文件锁错误
- ✅ inline-snapshot 并行兼容
- ✅ 测试隔离性更好
- ✅ 开发反馈循环更快

---

## 2. 整体架构

### 2.1 分层修复策略

```
┌─────────────────────────────────────────────────────┐
│          测试基础设施层                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ pyproject   │  │ conftest.py │  │ test.py     │ │
│  │ .toml       │  │ (共享)      │  │ (命令封装)  │ │
│  └─────────────┘  └─────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────┘
           ↓                  ↓                  ↓
┌─────────────────────────────────────────────────────┐
│          测试修复层                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ P0: 慢速测试 │  │ P1: 边界混淆 │  │ P2: 性能优化 │ │
│  │ time.sleep  │  │ 迁移测试文件 │  │ 并行配置    │ │
│  │ SQLite 锁   │  │ Snapshot    │  │ 慢速分析    │ │
│  └─────────────┘  └─────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 2.2 核心原则

1. **基础设施先行**：先修改 `pyproject.toml` 和 `conftest.py`，让所有测试受益
2. **快速反馈优先**：P0 修复立即见效（9s → 0.5s）
3. **边界规范固化**：P1 确保未来不再引入同类问题
4. **持续优化**：P2 建立性能基线

---

## 3. P0 级别修复 - 慢速测试与资源清理

### 3.1 time.sleep 虚拟化

**问题**：`test_cache_ttl_unit.py` 和 `test_cache_runtime_unit.py` 使用真实 `time.sleep(3)`

**根本原因**：
- `time_machine_lib.travel(0, tick=False)` 导致时间不会自动前进
- `time.sleep()` 是真实的系统调用，未被拦截
- `fake_time` fixture 已存在但未被使用

**修复方案**：

```python
# packages/data/tests/unit/runtime/conftest.py

@pytest.fixture
def frozen_time(time_machine):
    """提供完全控制的虚拟时间（替代真实 sleep）"""
    with time_machine.travel(0, tick=True):
        yield time_machine
```

```python
# ❌ 修复前
def test_individual_ttl(time_machine: None) -> None:
    with time_machine_lib.travel(0, tick=False):
        cache.set("key1", "value1", ttl=2)
        time.sleep(3)  # 真实等待 3 秒

# ✅ 修复后
def test_individual_ttl(frozen_time) -> None:
    cache.set("key1", "value1", ttl=2)
    frozen_time.move_to(2)  # 虚拟前进 2 秒，立即返回
    assert cache.get("key1") is None
```

**影响文件**：
- `packages/data/tests/unit/runtime/test_cache_ttl_unit.py`
- `packages/data/tests/unit/runtime/test_cache_runtime_unit.py`

**预期效果**：9s → 0.5s（**18x 提速**）

---

### 3.2 SQLite 连接池清理

**问题**：Windows 上 `PermissionError: [WinError 32]` 文件锁未释放

**根本原因**：
- `SQLitePool.close()` 只关闭当前线程的连接
- DuckDB 连接可能未正确关闭
- Windows 文件系统对文件锁处理更严格

**修复方案**：

```python
# packages/data/tests/integration/conftest.py

@pytest.fixture(autouse=True)
def ensure_sqlite_cleanup():
    """确保 SQLite 连接在测试后正确关闭"""
    yield
    import gc
    gc.collect()
```

**或者更彻底的清理**：

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
            del self.pool
    except Exception:
        pass
    import gc
    gc.collect()
    import time
    time.sleep(0.1)  # 给 Windows 文件系统时间释放锁
```

**影响文件**：
- `packages/data/tests/integration/conftest.py`
- 所有使用 `SQLitePool` 的集成测试

---

### 3.3 可观测性内存 Registry

**问题**：集成测试尝试连接 VictoriaMetrics (localhost:8428)，但服务未运行

**修复方案**：

```python
# packages/*/tests/integration/conftest.py

@pytest.fixture
def metrics_registry():
    """提供内存 Registry（不依赖外部服务）"""
    from prometheus_client import CollectorRegistry
    registry = CollectorRegistry()
    yield registry
    registry.clear()  # 清理
```

```python
# ❌ 修复前
@pytest.mark.integration
def test_metrics_integration():
    response = requests.get("http://localhost:8428/api/v1/query")
    assert response.status_code == 200

# ✅ 修复后
@pytest.mark.integration
def test_metrics_integration(metrics_registry):
    counter = Counter("api_requests_total", "Total API requests", registry=metrics_registry)
    counter.labels(method="GET", endpoint="/api/quote").inc()

    metric_value = metrics_registry.get_sample_value("api_requests_total", {
        "method": "GET",
        "endpoint": "/api/quote"
    })

    assert metric_value == 1.0
```

**影响文件**：
- 所有使用可观测性的集成测试

---

## 4. P1 级别修复 - 边界规范与 Snapshot 兼容

### 4.1 测试边界迁移

**问题**：`test_bars_store_unit.py` 标记为单元测试，但使用真实文件 I/O

**判断标准**：

| 测试维度 | 单元测试 ✅ | 集成测试 ✅ |
|---------|-----------|-------------|
| **测试目标** | 单个类的原子功能 | 系统/外部的"接缝"处 |
| **依赖策略** | **完全 Mock** | **真实组件** |
| **数据持久化** | 不关心 | 关键（验证写入/读取） |
| **外部调用** | Mock HTTP 调用 | 真实 Client + Mock 响应 |
| **典型场景** | 算法逻辑、状态机 | DAO、HTTP Client |
| **速度** | 快（毫秒级） | 慢（秒级，有真实 IO） |
| **资源隔离** | Mock（无状态） | `:memory:` / `tmp_path` |

**修复方案**：

```bash
# 迁移边界混淆的单元测试
mv packages/data/tests/unit/stores/test_bars_store_unit.py \
   packages/data/tests/integration/stores/test_bars_store_integration.py
```

---

### 4.2 Schema 初始化 Fixture

**问题**：`test_sql_engine_injection_integration.py` 未提供 `schema_path`，导致表初始化失败

**修复方案**：

```python
# packages/data/tests/integration/conftest.py

@pytest.fixture
def sqlite_schema_path() -> Path:
    """获取 schema.sql 路径"""
    return Path(__file__).parent.parent.parent.parent \
        / "src" / "ditto_data" / "scripts" / "schema.sql"

@pytest.fixture
def sqlite_pool_with_schema(sqlite_schema_path: Path, tmp_path: Path) -> SQLitePool:
    """创建已初始化 schema 的 SQLite 连接池"""
    db_path = tmp_path / "meta" / "hub.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    pool = SQLitePool(str(db_path), schema_path=sqlite_schema_path)
    pool.init_schema()
    yield pool
    pool.close()
```

---

### 4.3 Snapshot Marker 机制

**问题**：inline-snapshot 与 pytest-xdist 并行冲突

**修复方案**：

```toml
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "snapshot: Mark test that uses inline-snapshot (must run serially)",
]
```

```python
# scripts/test.py
def build_pytest_command() -> list[str]:
    has_snapshot = "--snapshot" in args

    if has_snapshot:
        cmd.append("--snapshot-update")
        cmd.extend(["-m", "snapshot"])  # 只运行 snapshot 测试
        return cmd

    # 默认模式：排除 snapshot 测试并行运行
    cmd.extend(["-m", "not snapshot", "-n", "auto", "--dist", "loadfile"])
```

```python
# 使用 snapshot 的测试文件
@pytest.mark.snapshot  # 添加 snapshot marker
@pytest.mark.unit
def test_backtest_output():
    result = run_backtest(...)
    assert result.summary == snapshot({
        "total_return": 0.156,
        "sharpe_ratio": 1.23,
    })
```

---

## 5. P2 级别优化 - 并行配置与性能监控

### 5.1 并行测试配置

```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = [
    "-ra",
    "-v",
    "-n", "auto",           # 默认并行
    "--dist", "loadfile",   # 同文件测试串行（避免 snapshot 冲突）
    "--strict-markers",
    "--strict-config",
    "--durations=10",       # 报告最慢的 10 个测试
]
```

### 5.2 分层策略

| 命令 | Marker | 并行 | 说明 |
|------|--------|------|------|
| `pixi run test --unit` | `unit and not snapshot` | ✅ auto | 单元测试并行 |
| `pixi run test --integration` | `integration and not snapshot` | ❌ 0 | 集成测试串行 |
| `pixi run test --fast` | `not slow and not integration and not snapshot` | ✅ auto | 快速测试 |
| `pixi run test --snapshot` | `snapshot` | ❌ 0 | Snapshot 串行 |

### 5.3 慢速测试分析

```bash
# 新增 scripts/analyze_slow_tests.py
pixi run analyze-slow-tests  # 报告 >500ms 的单元测试
```

---

## 6. 测试规范更新

需要在 [`.claude/rules/python-test.md`](.claude/rules/python-test.md) 中新增：

1. **单元测试 vs 集成测试判断标准**（详细表格）
2. **资源隔离策略**（SQLite、文件、HTTP、可观测性、时间）
3. **禁止模式**（`time.sleep`、`TemporaryDirectory` 等）
4. **测试耗时规范**（<500ms 单元，<5s 集成）
5. **Snapshot Marker 使用规范**

---

## 7. 验证检查清单

### 提交前检查

- [ ] 运行 `pixi run -e dev test --unit` - 确保单元测试通过且快速
- [ ] 运行 `pixi run -e dev test --integration` - 确保集成测试通过
- [ ] 运行 `pixi run -e dev pytest --durations=20` - 确保无慢速测试
- [ ] 检查无 `PermissionError` 文件锁错误
- [ ] 验证 `pytest --collect-only` 无 import 冲突

### CI 检查

- [ ] 并行测试不出现 `xdist` 冲突
- [ ] Snapshot 测试串行运行且通过
- [ ] 覆盖率 >= 80%
- [ ] 无 SQLite 文件锁错误

---

## 8. 变更日志

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-01-21 | 1.0 | 初始设计文档 |
