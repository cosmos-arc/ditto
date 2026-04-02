# 测试效率与边界优化实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 修复测试耗时超标、SQLite 文件锁、测试边界混淆、inline-snapshot 并行冲突等问题，将单元测试耗时从 74s 降低到 <10s。

**架构:** 采用分层修复策略：先修复测试基础设施层（pyproject.toml、conftest.py），再修复具体测试问题。

**技术栈:** pytest、time_machine、pytest-xdist、inline-snapshot、prometheus_client

---

## 实施原则

- **TDD 流程**: RED → GREEN → REFACTOR
- **小步提交**: 每完成一个子任务立即 commit
- **测试优先**: 先写/修改测试，确保失败，再修复
- **性能验证**: 每次修复后运行 `pytest --durations=10` 验证提速效果

---

## 任务列表

### 任务 1: P0.1 - 创建 frozen_time fixture

**目标:** 提供虚拟时间 fixture，替代真实的 time.sleep()

**文件:**
- Modify: `packages/data/tests/unit/runtime/conftest.py`
- Test: 由后续任务使用

**Step 1: 读取现有 conftest.py**

```bash
# 检查是否已有 frozen_time fixture
cat packages/data/tests/unit/runtime/conftest.py
```

**Step 2: 添加 frozen_time fixture**

在 `packages/data/tests/unit/runtime/conftest.py` 中添加：

```python
@pytest.fixture
def frozen_time(time_machine):
    """提供完全控制的虚拟时间（替代真实 sleep）

    使用方式:
        def test_cache_expires(frozen_time):
            cache.set("key", "value", ttl=2)
            frozen_time.move_to(2)  # 虚拟前进 2 秒
            assert cache.get("key") is None
    """
    with time_machine.travel(0, tick=True):
        yield time_machine
```

**Step 3: 验证 fixture 可被收集**

```bash
pixi run -e dev pytest packages/data/tests/unit/runtime/conftest.py::frozen_time --collect-only
```

Expected: FIXTURE 被收集

**Step 4: 提交**

```bash
git add packages/data/tests/unit/runtime/conftest.py
git commit -m "feat(runtime): add frozen_time fixture for virtual time control"
```

---

### 任务 2: P0.1 - 修复 test_cache_ttl_unit.py

**目标:** 使用 frozen_time 替代真实 time.sleep(3)

**文件:**
- Modify: `packages/data/tests/unit/runtime/test_cache_ttl_unit.py`

**Step 1: 读取现有测试**

```bash
# 查看当前测试实现
cat packages/data/tests/unit/runtime/test_cache_ttl_unit.py
```

**Step 2: 运行测试确认当前耗时**

```bash
pixi run -e dev pytest packages/data/tests/unit/runtime/test_cache_ttl_unit.py --durations=5
```

Expected: 测试通过，但耗时 >3 秒

**Step 3: 修改测试使用 frozen_time**

找到所有使用 `time.sleep()` 的测试函数，修改为：

```python
# ❌ 修复前
def test_individual_ttl(time_machine: None) -> None:
    with time_machine_lib.travel(0, tick=False):
        cache = DataCache(ttl_seconds=300)
        cache.set("key1", "value1", ttl=2)
        time.sleep(3)  # 真实等待 3 秒
        assert cache.get("key1") is None

# ✅ 修复后
def test_individual_ttl(frozen_time) -> None:
    cache = DataCache(ttl_seconds=300)
    cache.set("key1", "value1", ttl=2)

    # 验证未过期
    assert cache.get("key1") == "value1"

    # 虚拟时间前进 2 秒（立即返回）
    frozen_time.move_to(2)

    # 已过期
    assert cache.get("key1") is None
```

对所有类似测试应用相同模式：
- 移除 `with time_machine_lib.travel(...)` 上下文
- 参数从 `time_machine: None` 改为 `frozen_time`
- `time.sleep(n)` 改为 `frozen_time.move_to(n)`

**Step 4: 运行测试验证通过**

```bash
pixi run -e dev pytest packages/data/tests/unit/runtime/test_cache_ttl_unit.py -v
```

Expected: 所有测试通过

**Step 5: 验证提速效果**

```bash
pixi run -e dev pytest packages/data/tests/unit/runtime/test_cache_ttl_unit.py --durations=5
```

Expected: 每个测试 <0.1s（原来 3s）

**Step 6: 提交**

```bash
git add packages/data/tests/unit/runtime/test_cache_ttl_unit.py
git commit -m "fix(runtime): use frozen_time in cache_ttl tests (3s → 0.1s)"
```

---

### 任务 3: P0.1 - 修复 test_cache_runtime_unit.py

**目标:** 使用 frozen_time 替代真实 time.sleep(1.2)

**文件:**
- Modify: `packages/data/tests/unit/runtime/test_cache_runtime_unit.py`

**Step 1: 读取现有测试**

```bash
cat packages/data/tests/unit/runtime/test_cache_runtime_unit.py
```

**Step 2: 运行测试确认当前耗时**

```bash
pixi run -e dev pytest packages/data/tests/unit/runtime/test_cache_runtime_unit.py::test_set_with_custom_ttl --durations=5
```

**Step 3: 修改测试使用 frozen_time**

找到 `test_set_with_custom_ttl` 函数，修改：

```python
# ❌ 修复前
def test_set_with_custom_ttl(time_machine: None) -> None:
    with time_machine_lib.travel(0, tick=False):
        cache.set("key", "value", ttl=1)
        time.sleep(1.2)  # 真实等待
        assert cache.get("key") is None

# ✅ 修复后
def test_set_with_custom_ttl(frozen_time) -> None:
    cache.set("key", "value", ttl=1)

    # 虚拟时间前进 1.2 秒（立即返回）
    frozen_time.move_to(1.2)

    assert cache.get("key") is None
```

**Step 4: 运行测试验证**

```bash
pixi run -e dev pytest packages/data/tests/unit/runtime/test_cache_runtime_unit.py -v
```

Expected: 所有测试通过

**Step 5: 验证提速效果**

```bash
pixi run -e dev pytest packages/data/tests/unit/runtime/test_cache_runtime_unit.py --durations=5
```

Expected: 每个测试 <0.1s（原来 1.2s）

**Step 6: 提交**

```bash
git add packages/data/tests/unit/runtime/test_cache_runtime_unit.py
git commit -m "fix(runtime): use frozen_time in cache_runtime tests (1.2s → 0.1s)"
```

---

### 任务 4: P0.2 - 添加 SQLite 清理 fixture

**目标:** 确保 SQLite 连接在测试后正确关闭（Windows 兼容）

**文件:**
- Modify: `packages/data/tests/integration/conftest.py`
- Modify: `packages/foundation/tests/integration/conftest.py`（如果存在）
- Modify: `packages/core/tests/integration/conftest.py`（如果存在）
- Modify: `apps/port/tests/integration/conftest.py`

**Step 1: 检查现有 conftest.py**

```bash
# 查看所有集成测试 conftest
ls -la packages/*/tests/integration/conftest.py apps/*/tests/integration/conftest.py 2>/dev/null || true
```

**Step 2: 为每个集成测试 conftest 添加清理 fixture**

在每个 `packages/*/tests/integration/conftest.py` 和 `apps/*/tests/integration/conftest.py` 中添加：

```python
@pytest.fixture(autouse=True)
def ensure_sqlite_cleanup():
    """确保 SQLite 连接在测试后正确关闭（Windows 兼容）"""
    yield
    import gc
    gc.collect()
```

**Step 3: 验证 fixture 可被收集**

```bash
pixi run -e dev pytest packages/data/tests/integration/conftest.py::ensure_sqlite_cleanup --collect-only
```

**Step 4: 提交**

```bash
git add packages/*/tests/integration/conftest.py apps/*/tests/integration/conftest.py
git commit -m "feat(tests): add SQLite cleanup fixture for Windows compatibility"
```

---

### 任务 5: P0.3 - 添加 metrics_registry fixture

**目标:** 提供内存 Registry，不依赖外部 VictoriaMetrics 服务

**文件:**
- Modify: `packages/*/tests/integration/conftest.py`
- Modify: `apps/*/tests/integration/conftest.py`

**Step 1: 添加 metrics_registry fixture**

在每个集成测试 `conftest.py` 中添加：

```python
@pytest.fixture
def metrics_registry():
    """提供内存 Registry（不依赖外部服务）

    使用方式:
        def test_metrics(metrics_registry):
            counter = Counter("api_requests", registry=metrics_registry)
            counter.inc()
            value = metrics_registry.get_sample_value("api_requests", {})
            assert value == 1.0
    """
    from prometheus_client import CollectorRegistry
    registry = CollectorRegistry()
    yield registry
    registry.clear()
```

**Step 2: 验证 fixture 可被收集**

```bash
pixi run -e dev pytest packages/data/tests/integration/conftest.py::metrics_registry --collect-only
```

**Step 3: 提交**

```bash
git add packages/*/tests/integration/conftest.py apps/*/tests/integration/conftest.py
git commit -m "feat(tests): add metrics_registry fixture for isolated observability tests"
```

---

### 任务 6: P1.2 - 添加 sqlite_schema_path 和 sqlite_pool_with_schema fixture

**目标:** 提供已初始化 schema 的 SQLite 连接池

**文件:**
- Modify: `packages/data/tests/integration/conftest.py`

**Step 1: 检查 schema.sql 位置**

```bash
# 找到 schema.sql 文件
find packages/data -name "schema.sql" -type f
```

Expected: 找到 schema.sql 路径（通常是 `packages/data/src/ditto_data/scripts/schema.sql`）

**Step 2: 添加 fixtures**

在 `packages/data/tests/integration/conftest.py` 中添加：

```python
from pathlib import Path
from ditto_data.db.sqlite_pool import SQLitePool

@pytest.fixture
def sqlite_schema_path() -> Path:
    """获取 schema.sql 路径"""
    return Path(__file__).parent.parent.parent.parent \
        / "src" / "ditto_data" / "scripts" / "schema.sql"

@pytest.fixture
def sqlite_pool_with_schema(sqlite_schema_path: Path, tmp_path: Path) -> SQLitePool:
    """创建已初始化 schema 的 SQLite 连接池

    使用方式:
        def test_something(sqlite_pool_with_schema):
            # 表已经初始化，可以直接使用
            ...
    """
    db_path = tmp_path / "meta" / "hub.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    pool = SQLitePool(str(db_path), schema_path=sqlite_schema_path)
    pool.init_schema()
    yield pool
    pool.close()
```

**Step 3: 验证 fixture 可被收集**

```bash
pixi run -e dev pytest packages/data/tests/integration/conftest.py::sqlite_pool_with_schema --collect-only
```

**Step 4: 提交**

```bash
git add packages/data/tests/integration/conftest.py
git commit -m "feat(tests): add sqlite_pool_with_schema fixture for integration tests"
```

---

### 任务 7: P1.1 - 迁移 test_bars_store_unit.py 到集成测试

**目标:** 将边界混淆的单元测试迁移到集成测试目录

**文件:**
- Move: `packages/data/tests/unit/stores/test_bars_store_unit.py`
- To: `packages/data/tests/integration/stores/test_bars_store_integration.py`

**Step 1: 确认源文件存在**

```bash
ls -la packages/data/tests/unit/stores/test_bars_store_unit.py
```

**Step 2: 创建目标目录**

```bash
mkdir -p packages/data/tests/integration/stores
```

**Step 3: 移动文件**

```bash
git mv packages/data/tests/unit/stores/test_bars_store_unit.py \
        packages/data/tests/integration/stores/test_bars_store_integration.py
```

**Step 4: 修改文件内的 marker**

打开文件，将 `@pytest.mark.unit` 改为 `@pytest.mark.integration`：

```python
# ❌ 修复前
@pytest.mark.unit
class TestBarsStore:
    ...

# ✅ 修复后
@pytest.mark.integration
class TestBarsStore:
    ...
```

**Step 5: 验证测试可被收集**

```bash
pixi run -e dev pytest packages/data/tests/integration/stores/test_bars_store_integration.py --collect-only
```

**Step 6: 运行测试验证通过**

```bash
pixi run -e dev pytest packages/data/tests/integration/stores/test_bars_store_integration.py -v
```

**Step 7: 提交**

```bash
git add packages/data/tests/unit/stores packages/data/tests/integration/stores
git commit -m "refactor(tests): migrate test_bars_store to integration tests"
```

---

### 任务 8: P1.3 - 添加 snapshot marker 定义

**目标:** 在 pyproject.toml 中添加 snapshot marker

**文件:**
- Modify: `pyproject.toml`

**Step 1: 读取现有 markers 配置**

```bash
# 查看当前 markers
grep -A 10 "markers =" pyproject.toml
```

**Step 2: 添加 snapshot marker**

在 `[tool.pytest.ini_options]` 的 `markers` 列表中添加：

```toml
[tool.pytest.ini_options]
markers = [
    "unit: Mark test as a unit test",
    "integration: Mark test as an integration test",
    "slow: Mark test as slow running (skip with -m 'not slow')",
    "serial: Mark test that must run serially",
    "snapshot: Mark test that uses inline-snapshot (must run serially)",  # 添加这行
]
```

**Step 3: 验证 marker 注册**

```bash
pixi run -e dev pytest --markers | grep snapshot
```

Expected: `@pytest.mark.snapshot: Mark test that uses inline-snapshot (must run serially)`

**Step 4: 提交**

```bash
git add pyproject.toml
git commit -m "feat(tests): add snapshot marker for inline-snapshot tests"
```

---

### 任务 9: P1.3 + P2.1 - 更新 pyproject.toml 并行配置

**目标:** 配置默认并行运行，排除 snapshot 测试

**文件:**
- Modify: `pyproject.toml`

**Step 1: 读取现有 addopts 配置**

```bash
grep -A 10 "addopts =" pyproject.toml
```

**Step 2: 更新 addopts**

```toml
[tool.pytest.ini_options]
addopts = [
    "-ra",
    "-v",
    "-n", "auto",           # 默认并行运行
    "--dist", "loadfile",   # 同文件测试串行（避免 snapshot 冲突）
    "--strict-markers",
    "--strict-config",
    "--durations=10",       # 报告最慢的 10 个测试
]
```

**Step 3: 验证并行配置**

```bash
# 快速测试：并行运行
pixi run -e dev pytest packages/data/tests/unit/cache -v
```

Expected: 看到 `gw0`, `gw1` 等并行 worker

**Step 4: 提交**

```bash
git add pyproject.toml
git commit -m "feat(tests): enable parallel test execution with xdist"
```

---

### 任务 10: P1.3 + P2.1 - 更新 scripts/test.py 并行策略

**目标:** 实现分层并行策略

**文件:**
- Modify: `scripts/test.py`

**Step 1: 读取现有 test.py**

```bash
cat scripts/test.py
```

**Step 2: 找到 build_pytest_command 函数**

```bash
grep -n "def build_pytest_command" scripts/test.py
```

**Step 3: 修改命令构建逻辑**

找到 `build_pytest_command()` 函数，修改：

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

    # Snapshot模式：只运行 snapshot 测试（串行）
    if has_snapshot:
        cmd.append("--snapshot-update")
        cmd.extend(["-m", "snapshot"])
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
        # 集成测试：串行（排除 snapshot）
        cmd.extend(["-m", "integration and not snapshot", "-n", "0"])
    elif has_fast:
        # 快速测试：跳过 slow/integration/snapshot
        cmd.extend(["-m", "not slow and not integration and not snapshot", "--no-cov", "-q"])
    elif has_unit:
        # 单元测试：并行（排除 snapshot）
        cmd.extend(["-m", "unit and not snapshot", "-n", "auto"])
    else:
        # 默认：并行运行非 snapshot 测试
        cmd.extend(["-m", "not snapshot", "-n", "auto"])

    # 添加路径参数
    if paths:
        cmd.extend(paths)

    return cmd
```

**Step 4: 测试各命令**

```bash
# 测试单元测试命令
pixi run test --unit --dry-run 2>/dev/null | grep "pytest"

# 测试集成测试命令
pixi run test --integration --dry-run 2>/dev/null | grep "pytest"

# 测试 snapshot 命令
pixi run test --snapshot --dry-run 2>/dev/null | grep "pytest"
```

**Step 5: 提交**

```bash
git add scripts/test.py
git commit -m "feat(tests): implement parallel test strategy with snapshot isolation"
```

---

### 任务 11: P2.2 - 创建慢速测试分析脚本

**目标:** 创建报告 >500ms 单元测试的分析脚本

**文件:**
- Create: `scripts/analyze_slow_tests.py`

**Step 1: 创建脚本**

```python
#!/usr/bin/env python
"""分析慢速测试并报告超过阈值的测试"""

import json
import subprocess
import sys
from pathlib import Path

# 性能阈值（秒）
UNIT_TEST_THRESHOLD = 0.5
INTEGRATION_TEST_THRESHOLD = 5.0


def get_durations(test_path: str, count: int = 50) -> dict:
    """运行 pytest 并获取耗时数据"""
    cmd = [
        "pytest",
        test_path,
        "--durations", str(count),
        "--quiet",
        "--tb=no",
        "-v",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    # 解析输出
    durations = {}
    for line in result.stderr.split("\n"):
        if "s setup" in line or "s call" in line:
            # 格式: "2.34s call     tests/unit/test_foo.py::test_bar"
            parts = line.split()
            if len(parts) >= 3:
                duration_str = parts[0].rstrip("s")
                test_name = parts[2]
                try:
                    duration = float(duration_str)
                    durations[test_name] = duration
                except ValueError:
                    continue

    return durations


def analyze_slow_tests() -> None:
    """分析慢速测试并生成报告"""

    # 分析单元测试
    print("🔍 分析单元测试...")
    unit_durations = get_durations("packages/*/tests/unit", count=50)

    slow_unit_tests = {
        name: duration
        for name, duration in unit_durations.items()
        if duration > UNIT_TEST_THRESHOLD
    }

    # 分析集成测试
    print("🔍 分析集成测试...")
    integration_durations = get_durations("packages/*/tests/integration", count=50)

    slow_integration_tests = {
        name: duration
        for name, duration in integration_durations.items()
        if duration > INTEGRATION_TEST_THRESHOLD
    }

    # 生成报告
    print("\n" + "=" * 60)
    print("🐌 慢速测试报告")
    print("=" * 60)

    if slow_unit_tests:
        print(f"\n❌ 单元测试超过 {UNIT_TEST_THRESHOLD}s 阈值 ({len(slow_unit_tests)} 个):")
        for name, duration in sorted(slow_unit_tests.items(), key=lambda x: -x[1]):
            print(f"  {duration:.2f}s - {name}")
    else:
        print(f"\n✅ 所有单元测试符合性能要求 (<{UNIT_TEST_THRESHOLD}s)")

    if slow_integration_tests:
        print(f"\n⚠️  集成测试超过 {INTEGRATION_TEST_THRESHOLD}s 阈值 ({len(slow_integration_tests)} 个):")
        for name, duration in sorted(slow_integration_tests.items(), key=lambda x: -x[1]):
            print(f"  {duration:.2f}s - {name}")
    else:
        print(f"\n✅ 所有集成测试符合性能要求 (<{INTEGRATION_TEST_THRESHOLD}s)")

    # 返回退出码
    if slow_unit_tests or slow_integration_tests:
        print("\n💡 修复建议:")
        print("  - 检查是否有未 mock 的外部依赖")
        print("  - 检查是否有真实的 time.sleep()")
        print("  - 检查是否有重复的 fixture 初始化")
        sys.exit(1)
    else:
        print("\n🎉 所有测试性能良好！")
        sys.exit(0)


if __name__ == "__main__":
    analyze_slow_tests()
```

**Step 2: 添加到 pixi.toml**

```bash
# 在 pixi.toml 的 [feature.dev.tasks] 中添加
pixi add analyze-slow-tests --python-version "3.12" --phase dev
```

或者手动添加到 `pixi.toml`:

```toml
[feature.dev.tasks]
analyze-slow-tests = { cmd = "python scripts/analyze_slow_tests.py", depends_on = ["dev"] }
```

**Step 3: 测试脚本**

```bash
pixi run -e dev analyze-slow-tests
```

**Step 4: 提交**

```bash
git add scripts/analyze_slow_tests.py pixi.toml
git commit -m "feat(tests): add slow test analysis script"
```

---

## 验证检查清单

### 提交前检查

- [ ] 运行 `pixi run -e dev test --unit` - 确保单元测试通过且快速
- [ ] 运行 `pixi run -e dev test --integration` - 确保集成测试通过
- [ ] 运行 `pixi run -e dev pytest --durations=20` - 确保无慢速测试
- [ ] 运行 `pixi run -e dev analyze-slow-tests` - 确保无超阈值测试
- [ ] 检查无 `PermissionError` 文件锁错误
- [ ] 验证 `pytest --collect-only` 无 import 冲突

### CI 检查

- [ ] 并行测试不出现 `xdist` 冲突
- [ ] Snapshot 测试串行运行且通过
- [ ] 覆盖率 >= 80%
- [ ] 无 SQLite 文件锁错误

---

## 预期结果

| 指标 | 修复前 | 修复后 | 提升 |
|------|--------|--------|------|
| 单元测试耗时 | ~74s | <10s | **7.4x** |
| 最慢单元测试 | 3.06s | <0.5s | **6x** |
| 并行加速比 | 1x | 2-4x | **2-4x** |
| 总体测试耗时 | ~120s | <30s | **4x** |

---

## 变更日志

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-01-21 | 1.0 | 初始实施计划 |
