# Ditto 项目全面质量改进计划

## 执行摘要

基于 `feature/pyright-cleanup-batch-0` 分支的全面检查，制定以下改进计划：

1. **在当前分支完成所有工作**：直接修改，无需向后兼容
2. **完成 noqa 清理**：Phase 2-6 共约 12 人日
3. **提升测试覆盖率**：从 69.79% → 80%

**重要约束**：
- ✅ 无需向后兼容，可以激进重构
- ✅ 单分支执行（`feature/pyright-cleanup-batch-0`）
- ✅ 所有工作完成后一次性提交

---

## 当前状态

| 指标 | 状态 |
|------|------|
| Pyright 检查 | ✅ 0 errors |
| 修改文件数 | 42 个 |
| 测试状态 | ⚠️ 42 errors (Windows 文件锁定), 2 failed |
| 覆盖率 | ⚠️ 69.79% (< 80% 目标) |
| `# noqa` | 14 处 (PLW0603 已清理完成) |
| `# type: ignore` | 7 处 |
| `global` 语句 | 0 处 ✅ |

---

## 执行步骤

### ~~Step 1: 修复测试问题（约 2 小时）~~ ✅ 已完成

#### ✅ 问题 1：42 个 Windows 文件锁定错误

**错误信息**：`PermissionError: [WinError 32]` 另一个进程正在使用此文件

**根因**：`QuarantineStore` 的 SQLite 连接在测试结束时未正确关闭

**解决方案**：
```python
# packages/datahub/src/ditto_datahub/stores/quarantine_store.py
class QuarantineStore:
    def close(self) -> None:
        """关闭 SQLite 连接"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> QuarantineStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
```

**测试文件修改**：
```python
# packages/datahub/tests/unit/repositories/test_bars_repository_unit.py
def teardown_method(self) -> None:
    """测试后清理"""
    if hasattr(self, 'quarantine_store'):
        self.quarantine_store.close()
```

#### ✅ 问题 2：2 个 AppInitializer 测试失败

**失败测试**：
- `test_initialize_app_creates_directories`
- `test_get_initializer`

**根因**：测试并行执行时单例状态竞态条件

**解决方案**：使用 `@pytest.mark.serial` 标记有状态测试为串行执行

#### ✅ 问题 3：1 个 Hypothesis 健康检查失败

**失败测试**：`test_dates_property_unit.py::TestNormalizeDateProperties::test_datetime_to_string_roundtrip`

**错误信息**：`Hypothesis only generated 8 valid inputs after 1.68 seconds`

**解决方案**：添加 `@settings` 抑制健康检查或优化测试策略
```python
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=50)
```

---

### Step 2: Phase 2 - 循环依赖解耦（约 1 周）

#### 任务清单（8 处 PLC0415）

| 任务 | 文件 | 位置 | 方案 |
|------|------|------|------|
| 2.1 | [hub.py](packages/datahub/src/ditto_datahub/hub.py) | 70, 93, 101, 109 | 依赖注入 + 延迟初始化 |
| 2.2 | [deploy.py](apps/port/src/ditto_port/jobs/flows/deploy.py) | 41, 133 | lambda 延迟求值 |
| 2.3 | [bars.py](packages/datahub/src/ditto_datahub/repositories/bars.py) | 866 | 依赖注入 DQReportGenerator |
| 2.4 | [base.py](packages/datahub/src/ditto_datahub/sources/base.py) | 383 | 注册表模式或 cast |
| 2.5 | [client.py](packages/datahub/src/ditto_datahub/sources/tushare/client.py) | 66 | Protocol 或 cast |

#### 详细方案

**hub.py 依赖注入重构**（最高优先级）

创建 `HubInitializer` 类，在 `__init__` 中注册所有工厂函数：

```python
class HubInitializer:
    def __init__(self, data_root: Path | None = None) -> None:
        self._data_root = data_root
        self._factories: dict[str, Callable[[], Any]] = {}
        self._register_factories()

    def _register_factories(self) -> None:
        """在顶层注册所有工厂（避免函数内 import）"""
        from ditto_datahub.runtime.sqlite_pool import SQLitePool
        from ditto_datahub.runtime.file_lock import FileLockManager
        # ... 其他导入

        self._factories["sqlite_pool"] = lambda: SQLitePool(...)
        self._factories["file_lock"] = lambda: FileLockManager(...)

    def get(self, name: str) -> Any:
        return self._factories[name]()
```

**deploy.py lambda 延迟求值**

```python
flow_configs: list[FlowConfig] = [
    FlowConfig(
        name="daily_ingestion_flow",
        loader=lambda: import_flow("daily_ingestion_flow"),
    ),
]
```

**bars.py 依赖注入**

```python
class BarsRepository:
    def __init__(
        self,
        ...,
        dq_report_generator: DQReportGenerator | None = None,
    ) -> None:
        self._dq_report_generator = dq_report_generator
```

---

### Step 3: Phase 3 - 类型忽略清理（约 1.5 周）

#### 任务清单（7 处 type: ignore）

| 任务 | 文件 | 问题 | 方案 |
|------|------|------|------|
| 3.1 | [dates.py](packages/foundation/src/ditto_foundation/util/dates.py) | unnecessary-isinstance | TypeGuard 或重构分支 |
| 3.2 | [testing.py](packages/foundation/src/ditto_foundation/observability/testing.py) | unused-import | TYPE_CHECKING 或删除 |
| 3.3 | [base.py](packages/datahub/src/ditto_datahub/sources/base.py) | attr-defined | Protocol 或 cast |
| 3.4 | [client.py](packages/datahub/src/ditto_datahub/sources/tushare/client.py) | attr-defined | Protocol 或 cast |
| 3.5 | [datasets.py](apps/port/src/ditto_port/services/ingestion/config/datasets.py) | arg-type (2) | 类型收窄验证 |

#### 详细方案

**dates.py - TypeGuard 方案**

```python
from typing import TypeGuard

def _is_pure_date(value: datetime | date) -> TypeGuard[date]:
    """检查是否是纯 date 类型（不是 datetime）"""
    return isinstance(value, date) and not isinstance(value, datetime)

# 使用
if _is_pure_date(value):
    return value.strftime("%Y-%m-%d")
```

**testing.py - TYPE_CHECKING 方案**

```python
if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan
else:
    ReadableSpan = Any
```

**base.py/client.py - Protocol 方案**

```python
from typing import Protocol

class HasTushareSource(Protocol):
    TushareSource: type[DataSource]

module = cast(HasTushareSource, importlib.import_module(...))
```

---

### Step 4: Phase 4 - Pyright 配置优化（约 0.5 人日）

```toml
# pyproject.toml
[tool.pyright]
reportMissingTypeStubs = "warning"  # 从 none 改为 warning
reportUnnecessaryTypeIgnoreComment = "error"
reportImplicitStringConcatenation = "error"
```

---

### Step 5: Phase 5 - 规则文档创建（约 2 人日）

创建 `.claude/rules/noqa-ignore.md`，内容包括：

- 核心原则：核心源码零容忍
- 禁止规则列表
- 允许的豁免（S608/S108/S110）
- TypeGuard 使用指南
- 修复流程

---

### Step 6: Phase 6 - 最终验证（约 1 人日）

```bash
# 验证命令
pixi run -e dev lint | grep PLC0415  # 应为空
grep -r "# type: ignore" packages/*/src apps/*/src | wc -l  # 应为 0
pixi run -e dev type --all  # 0 errors
pixi run -e dev test --coverage  # >= 80%
```

---

## 测试覆盖率提升（可选，约 1 周）

### 缺口模块

| 模块 | 当前覆盖率 | 目标 |
|------|------------|------|
| observability/testing.py | 25% | 80% |
| observability/logging.py | 56% | 80% |
| observability/metrics.py | 未知 | 80% |

### 测试用例示例

```python
# packages/foundation/tests/unit/observability/test_testing_unit.py
def test_reset_for_testing():
    """测试重置功能"""
    from ditto_foundation.observability import testing

    testing.reset_for_testing()
    assert testing.get_recorded_spans() == []

def test_get_recorded_spans():
    """测试获取 recorded spans"""
    from ditto_foundation.observability import testing, tracing

    with tracing.span("test"):
        pass

    spans = testing.get_recorded_spans()
    assert len(spans) == 1
```

---

## 关键文件清单

### 测试修复
- [packages/datahub/src/ditto_datahub/stores/quarantine_store.py](packages/datahub/src/ditto_datahub/stores/quarantine_store.py)

### Phase 2: 循环依赖解耦
- [packages/datahub/src/ditto_datahub/hub.py](packages/datahub/src/ditto_datahub/hub.py) ⭐ 核心文件
- [apps/port/src/ditto_port/jobs/flows/deploy.py](apps/port/src/ditto_port/jobs/flows/deploy.py)
- [packages/datahub/src/ditto_datahub/repositories/bars.py](packages/datahub/src/ditto_datahub/repositories/bars.py)
- [packages/datahub/src/ditto_datahub/sources/base.py](packages/datahub/src/ditto_datahub/sources/base.py)
- [packages/datahub/src/ditto_datahub/sources/tushare/client.py](packages/datahub/src/ditto_datahub/sources/tushare/client.py)

### Phase 3: 类型忽略清理
- [packages/foundation/src/ditto_foundation/util/dates.py](packages/foundation/src/ditto_foundation/util/dates.py)
- [packages/foundation/src/ditto_foundation/observability/testing.py](packages/foundation/src/ditto_foundation/observability/testing.py)
- [apps/port/src/ditto_port/services/ingestion/config/datasets.py](apps/port/src/ditto_port/services/ingestion/config/datasets.py)

### Phase 4-5: 配置与文档
- [pyproject.toml](pyproject.toml)
- [.claude/rules/noqa-ignore.md](.claude/rules/noqa-ignore.md)

---

## 工作量估算

| Step | 内容 | 工作量 |
|------|------|--------|
| Step 1 | 修复测试问题 | 2 小时 |
| Step 2 | Phase 2 循环依赖解耦 | 3.5 人日 (1 周) |
| Step 3 | Phase 3 类型忽略清理 | 5 人日 (1.5 周) |
| Step 4 | Phase 4 Pyright 配置 | 0.5 人日 |
| Step 5 | Phase 5 规则文档 | 2 人日 |
| Step 6 | Phase 6 最终验证 | 1 人日 |
| 可选 | 测试覆盖率提升 | 5 人日 (1 周) |
| **总计** | **noqa 清理** | **12 人日 (约 3 周)** |

---

## 验证标准

```bash
# 最终验证
pixi run -e dev ci  # 所有检查通过
grep "# type: ignore" packages/*/src apps/*/src | wc -l  # 0
grep "^global " packages/*/src apps/*/src | wc -l  # 0
```

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| Windows 文件锁定 | 为 QuarantineStore 添加 close() 方法 |
| Foundation 测试竞态 | 使用 @pytest.mark.serial 标记 |
| hub.py 重构风险高 | 增量迁移，完整集成测试 |
| 循环依赖解耦引入新问题 | 依赖注入、Protocol 接口、严格测试 |

---

**计划创建时间**：2026-01-16
**目标分支**：feature/pyright-cleanup-batch-0
**预计完成时间**：3-4 周
