# 质量检查跳过清理计划

## Context

项目审计发现 228 处质量检查跳过。经分类分析，绝大多数合理（测试中故意触发类型错误、有安全保护的 SQL f-string 等）。本计划聚焦可修复项：消除不必要的抑制、补充缺失的类型注解、修复循环依赖、清理 `Any` 类型滥用。

**状态：已完成** (2026-04-08)

---

## Part A: 质量检查抑制清理（5 个 Task）

### Task 1: 移除 instrument_reader.py 中不必要的 `reportPrivateUsage=false` ✅

**文件**: `packages/data/src/ditto_data/storage/metadata/instrument/instrument_reader.py`

**操作**: 删除第 1 行 `# pyright: reportPrivateUsage=false`

**结果**: 所有私有成员访问均为同类内访问，移除后无类型错误。

### Task 2: 修复 observability 循环依赖 ✅

**文件**:
- `packages/infra/src/ditto_infra/foundation/observability/__init__.py`
- `packages/infra/src/ditto_infra/foundation/observability/testing.py`

**操作**:
1. `__init__.py` 中将 `from .testing import ...` 改为 `__getattr__` 延迟导入
2. `testing.py` 中保留 `# noqa: PLC0415`（延迟导入）
3. 保留 `# noqa: S110`（shutdown 失败不应阻断测试重置）
4. 从 `__all__` 中移除 testing 相关导出（`__getattr__` 动态提供）

### Task 3: 补充 Prefect Future 类型注解 ✅

**文件**: `interfaces/src/ditto_interfaces/jobs/flows/daily.py`

**操作**:
- 导入 `from prefect.futures import PrefectFuture`
- `t0_futures`, `t1_futures`, `level_futures`, `current_level_futures`: `list[Any]` → `list[PrefectFuture[dict[str, object]]]`
- `dqc_future: Any` → `dqc_future: PrefectFuture[dict[str, Any]]`
- `dqc_results: Any` → `dqc_results: dict[str, Any]`
- 添加 `cast(str, ...)` 解决 dict.get 返回 object 的类型窄化问题
- 保留 `# pyright: ignore` 用于 Prefect submit/result 的类型 stub 限制

### Task 4: 清理 pyproject.toml 零影响配置 ✅

**文件**: `pyproject.toml`

**操作**:
1. ✅ 移除 `ignore-fully-untyped = true`（无完全无注解函数，该配置无效果）
2. ❌ `N803`, `N806` **保留**（实际发现 13 处违规：numpy 矩阵变量、科学计算常量等）
3. `N818` 保留（`DittoException` 基类命名是设计选择）

### Task 5: Part A 验证 ✅

`pixi run -e dev check` — All checks passed!

---

## Part B: ANN401 Any 类型清理（4 个 Task）

### Task 6: `client: Any` → `SQLiteClient` + `cache: Any` → `DataCache[Any] | None` ✅

**影响**: 22 个 Reader/Writer 文件（`packages/data/src/ditto_data/storage/`）

**模式**: `__init__(self, client: Any, cache: Any | None = None)` → `__init__(self, client: SQLiteClient, cache: DataCache[Any] | None = None)`

**实际修改**: 20 个文件（2 个 technical_indicator 文件使用 `data_root` 而非 `client`，跳过）

**导入**: 每个文件添加 `from ditto_data.storage.sqlite_client import SQLiteClient` 和 `from ditto_infra.foundation.cache import DataCache`（如需）。

### Task 7: 其他 Any 注解修复 ✅

| 文件 | 修复 |
|------|------|
| `strategy_artifact_store.py` | `row: Any` → `row: sqlite3.Row` |
| `strategy_spec_store.py` | `row: Any` → `row: sqlite3.Row` |
| `strategy_run_store.py` | `row: Any` → `row: sqlite3.Row` |
| `metadata_service.py` | `list_date: Any` → `list_date: date \| str \| None` |
| `metadata/instrument.py` | `list_date: Any` → `list_date: date \| str \| None` |
| `instrument_writer.py` | `list_date: Any` → `list_date: date \| str \| None` |
| `tushare/adapters/metal.py` | `_client: Any` → `_client: TushareClient \| None` |
| `tushare/adapters/fx.py` | `_client: Any` → `_client: TushareClient \| None` |
| `metadata/universe.py` | `rebalance_reader/writer: Any` → 具体类型 |
| `dq_batch.py` | `metadata_service: Any` → `MetadataQueryFacade` |
| `execution_audit_service.py` | `record: Any` → 联合类型 |
| `cli/utils/output.py` | `item: Any` → `BaseModel`（用 `Sequence` 解决协变问题） |
| `api/routes/source.py` | `source: Any` / `-> Any` → `DataSource` |
| `t0_meta.py` | 保留 `-> Any`（Prefect Task 泛型限制）|

### Task 8: 保留 Any 的合理场景 + 内联标注 ✅

在 16 处合理使用 `Any` 的位置添加了 `# noqa: ANN401` 及原因说明：

| 场景 | 文件数 | 原因 |
|------|--------|------|
| OTel API 约束 | 6 | Span/Gauge/CallbackOptions 类型不完整 |
| Pydantic validator | 6 | model_validator/field_validator 前置模式 |
| orjson 序列化 | 1 | 接受任意 JSON 兼容对象 |
| Command Protocol | 1 | Handler 返回类型多变 |
| loguru formatter | 2 | 回调签名约束 |
| Prefect Task | 1 | 泛型无法精确表达返回类型 |
| 泛型缓存 | 1 | 需运行时类型 |
| 多态返回 | 2 | 返回多种 Reader/Writer 实例 |

### Task 9: 移除 ANN401 全局忽略 + 验证 ✅

**操作**:
1. ✅ 从 `[tool.ruff.lint.ignore]` 中移除 `ANN401`
2. ✅ 添加 `"typings/**/*.pyi" = ["ANN401"]` per-file-ignore（第三方 stub）
3. ✅ `pixi run -e dev check` 验证通过

---

## 与计划的偏差

| 计划项 | 实际结果 | 原因 |
|--------|----------|------|
| N803/N806 移除 | **保留** | 实际有 13 处违规（计划误判为零） |
| `__all__` 保留 testing 导出 | **移除** | pyright strict 模式下 `__getattr__` + `__all__` 会报 `reportUnsupportedDunderAll` |
| `t0_meta.py` → `Task[..., dict[str, object]]` | **保留 `-> Any`** | 导致 daily.py 10 个类型推断错误，回退 |
| `cli/utils/output.py` 用 `list[BaseModel]` | **改用 `Sequence[BaseModel]`** | `list` 是不变的，子类实例无法赋值给 `list[BaseModel]` |
| golden.py ticker_val/tickers_raw | **保留 Any + noqa** | 模型验证器回调签名约束 |

---

## 验证

- `pixi run -e dev check` — **All checks passed!** (lint + fmt + type + test + arch-check)
