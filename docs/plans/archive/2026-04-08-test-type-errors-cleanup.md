# 测试类型错误全量清理方案

**日期**: 2026-04-08
**状态**: 待实施
**分支**: `refactor/phase4-app-layer-extraction`

## 背景

`pixi run -e dev type --tests` 暴露 73 个类型错误，原因：之前 `extraPaths` 配置不完整导致这些测试文件未被 basedpyright 检查。现在配置已修复，需要全量清理。

## 错误分布

- **26 个文件**受影响（25 个测试文件 + 1 个生产文件）
- **73 个错误**，按类型分为 13 个模式组
- 所有修改都是类型精度修正，不改变运行时行为

## 修复方案

### G1: `reportOptionalSubscript` — DB fetchall 结果（13 个）

**根因**: DuckDB stubs 中 `fetchall()` 返回类型包含 `None`，导致 `row[0]` 报错。

**修复**: 列表推导加 `if row is not None` 过滤。

| 文件 | 数量 |
|------|------|
| `interfaces/tests/unit/test_conftest_unit.py` | 10 |
| `interfaces/tests/unit/test_db_fixtures_unit.py` | 3 |

```python
# 前
table_names = [row[0] for row in tables]
# 后
table_names = [row[0] for row in tables if row is not None]
```

---

### G2: `reportIndexIssue` — `dict[str, object]` 嵌套索引（10 个）

**根因**: `_invoke_flow` / `_invoke_research_build_flow` 参数和返回类型用 `object`，嵌套索引 `result["key"]["subkey"]` 时第二层索引报错。

**修复**: `object` → `Any`。

| 文件 | 数量 |
|------|------|
| `interfaces/tests/integration/flows/test_research_dataset_integration.py` | 5 |
| `interfaces/tests/integration/flows/test_derived_publication_integration.py` | 3 |
| `interfaces/tests/integration/flows/test_derived_materialization_query_repair_integration.py` | 2 |

```python
# 前
def _invoke_research_build_flow(**kwargs: object) -> dict[str, object]:
# 后
from typing import Any
def _invoke_research_build_flow(**kwargs: Any) -> dict[str, Any]:
```

---

### G3: `.errors` → `.issues`（4 个）

**根因**: `DQResult` 没有 `.errors` 属性，正确属性名是 `.issues`。

**修复**: 替换属性名。

| 文件 | 数量 |
|------|------|
| `interfaces/tests/e2e/test_pipeline.py` (L236, 272, 317, 466) | 4 |

```python
# 前
f"质量阶段: 检查应通过, 错误: {dq_result.errors}"
# 后
f"质量阶段: 检查应通过, 错误: {dq_result.issues}"
```

---

### G4: `__name__` → `.name`（4 个）

**根因**: Prefect `Flow`/`Task` 类的 type stubs 没有 `__name__` 属性，有 `.name` 属性。

**修复**: 替换属性名。

| 文件 | 数量 |
|------|------|
| `interfaces/tests/unit/jobs/flows/test_backfill_unit.py` (L209, 369) | 2 |
| `interfaces/tests/unit/jobs/flows/test_daily_unit.py` (L125) | 1 |
| `interfaces/tests/unit/jobs/flows/test_deploy_unit.py` (L25) | 1 |

```python
# 前
assert backfill_flow.__name__ == "backfill"
# 后
assert backfill_flow.name == "backfill"
```

---

### G5: Object not callable — `_prefect_runner` / `_invoke_flow`（5 个）

**根因**: helper 函数参数类型为 `object`，`getattr()` 返回 `object`，调用时报 "not callable"。

**修复**: 参数和返回类型改为 `Any`。

| 文件 | 数量 |
|------|------|
| `interfaces/tests/unit/jobs/tasks/test_monitoring_unit.py` | 1 |
| `interfaces/tests/integration/flows/test_derived_materialization_query_repair_integration.py` | 1 |
| `interfaces/tests/integration/flows/test_derived_publication_integration.py` | 1 |
| `interfaces/tests/integration/flows/test_research_dataset_integration.py` | 1 |
| `interfaces/tests/unit/jobs/flows/test_materialization_flows_unit.py` | 1 |

```python
# 前
def _prefect_runner(entrypoint):
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))
# 后
from typing import Any, Callable
def _prefect_runner(entrypoint: Any) -> Callable[..., Any]:
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))
```

---

### G6: `InstrumentId` NewType 不匹配（3 个）

**根因**: `InstrumentId = NewType("InstrumentId", int)` 是名义类型，`int` 字面量不兼容。

**修复**: 用 `InstrumentId()` 构造。

| 文件 | 数量 |
|------|------|
| `interfaces/tests/unit/models/test_metadata_unit.py` (L111, 135, 152) | 3 |

```python
# 前
Instrument(instrument_id=1, ...)
# 后
Instrument(instrument_id=InstrumentId(1), ...)
```

---

### G7: Generator return type / bare return（4 个）

**根因**: fixture 函数的 yield/return 注解不匹配 Generator 协议。

| 文件 | 数量 | 修复 |
|------|------|------|
| `interfaces/tests/e2e/conftest.py` (L349, 361) | 2 | 修正 fixture 返回注解 |
| `interfaces/tests/integration/conftest.py` (L77, 132) | 2 | 删除多余 bare `return` + 修正 `clear` 调用 |

---

### G8: 零散修正（3 个）

| 文件 | 错误 | 修复 |
|------|------|------|
| `interfaces/tests/unit/test_middleware_unit.py` (L88) | `InitErrorDetails` 参数类型 | 修正 dict 结构匹配 `InitErrorDetails` |
| `interfaces/tests/unit/test_request_id_propagation.py` (L108) | `Any \| None` 传给 `str` | 加 `assert` 收窄或 `str()` 转换 |
| `interfaces/tests/integration/ingestion/flows/test_repair_integration.py` (L61) | `object` 与 `Literal[2]` 比较 | 确认变量类型或加 `cast` |

---

### G9: `.path` on `BaseRoute`（3 个）

**根因**: `app.routes` 类型为 `list[BaseRoute]`，`.path` 仅在 `Route` 子类上。`hasattr` 不被 basedpyright 识别为类型守卫。

**修复**: `isinstance(route, Route)`。

| 文件 | 数量 |
|------|------|
| `interfaces/tests/unit/api/routes/test_debug_route.py` (L14, 28) | 2 |
| `interfaces/tests/integration/test_main_routes_integration.py` (L107) | 1 |

```python
# 前
[route.path for route in app.routes if hasattr(route, "path")]
# 后
from starlette.routing import Route
[route.path for route in app.routes if isinstance(route, Route)]
```

---

### G10: `"in" operator` on `str | None`（10 个）

**根因**: `MockNotificationSender.last_sent_content` 类型为 `str | None`，`in` 操作符右侧不接受 `None`。

**修复**: 每个 assert 前加 `assert sender.last_sent_content is not None`。

| 文件 | 数量 |
|------|------|
| `interfaces/tests/unit/notifications/test_manager_unit.py` | 10（5 个测试方法，每个方法加 1 次断言） |

```python
# 前
assert "Alert: Test error occurred" in sender.last_sent_content
assert "Level: error" in sender.last_sent_content
# 后
assert sender.last_sent_content is not None
assert "Alert: Test error occurred" in sender.last_sent_content
assert "Level: error" in sender.last_sent_content
```

---

### G11: CLI factory `Callable` 签名（4 个）

**根因**: `create_daily_command` 返回 `Callable[[typer.Context, str, bool], None]`，basedpyright 严格匹配泛型参数，`mocker.Mock()` 不满足 `typer.Context`。

**修复**: 工厂返回类型放宽为 `Callable[..., None]`。

| 文件 | 数量 |
|------|------|
| `interfaces/src/ditto_interfaces/cli/commands/factory.py` | 3 个函数签名（L108, L146, L190） |
| `interfaces/tests/unit/cli/test_factory_unit.py` | 4 个调用点自动修复 |

```python
# 前
def create_daily_command(...) -> Callable[[typer.Context, str, bool], None]:
# 后
def create_daily_command(...) -> Callable[..., None]:
```

> **注意**: 这是唯一涉及生产代码的修改。`Callable[..., None]` 是更宽松的类型，对于工厂函数来说是合理的——调用方通过 CLI 框架注入参数，不需要精确签名约束。

---

### G12: `reset_for_testing` import path（2 个）

**根因**: 类型检查器无法解析 `ditto_infra.foundation` 的 re-export chain。

**修复**: 改为直接导入路径。

| 文件 | 数量 |
|------|------|
| `interfaces/tests/conftest.py` (L192) | 1 |
| `interfaces/tests/integration/ingestion/conftest.py` (L12) | 1 |

```python
# 前
from ditto_infra.foundation import reset_for_testing
# 后
from ditto_infra.foundation.observability import reset_for_testing
```

---

### G13: 额外修正（2 个）

| 文件 | 错误 | 修复 |
|------|------|------|
| `interfaces/tests/e2e/test_quality.py` (L322) | `warning_count` 不存在 | `DQResult` 用 `warn_count`，修正属性名 |
| `interfaces/tests/e2e/test_storage.py` (L321) | `pytest.MockerFixture` unknown | `from pytest_mock import MockerFixture` |

---

## 实施顺序

按依赖关系和风险分组，建议 3 个 commit：

1. **Commit 1 — 纯类型注解修正**（G1, G2, G4, G5, G6, G7, G8, G12, G13）
   - 46 个错误，仅测试文件，零风险
   - `object` → `Any`、`None` 守卫、属性名修正、import path

2. **Commit 2 — 测试逻辑适配**（G3, G9, G10, G11）
   - 21 个错误
   - G3: `.errors` → `.issues`（运行时也正确）
   - G9: `isinstance` 守卫（更严格的类型检查）
   - G10: `is not None` 断言
   - G11: factory.py 返回类型放宽（唯一生产文件改动）

3. **Commit 3 — 验证**
   - 运行 `pixi run -e dev type --tests` 确认 0 error
   - 运行 `pixi run -e dev test` 确认测试通过

## 验证标准

```bash
pixi run -e dev type --tests   # 0 errors
pixi run -e dev test           # 全部通过
```
