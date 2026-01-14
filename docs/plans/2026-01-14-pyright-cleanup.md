# Pyright 类型检测全面清零优化计划

**日期**: 2026-01-14
**状态**: 进行中（批次 0、1、2、3 已完成）
**目标**: 彻底清零所有 pyright 错误（116 个）

---

## 执行摘要

当前项目有 **116 个 pyright 错误**，分布在 39 个文件中。本计划采用**按模块分批处理**的方式，分 6 个批次逐步清零所有错误。

| 模块 | 错误数 | 占比 |
|------|--------|------|
| packages/datahub | 73 | 63% |
| apps/port | 33 | 28% |
| packages/foundation | 10 | 9% |
| packages/core | 0 | 0% |

---

## 错误类型分析

| 错误类型 | 数量 | 优先级 |
|---------|------|--------|
| reportUnusedImport | 18 | 低（可自动修复） |
| reportUnknownVariableType | 14 | 中（需类型注解） |
| reportUnknownMemberType | 11 | 中（需类型注解） |
| reportUnnecessaryIsInstance | 7 | 低（可删除） |
| reportPrivateUsage | 5 | 高（架构调整） |
| reportUnusedFunction | 2 | 低（可删除） |
| 其他 | 9 | 低 |

---

## 分批实施方案

### ✅ 批次 0: 准备阶段 - 创建第三方库 Stub

**目标**: 为 OpenTelemetry 创建类型 stub，消除系统性 Unknown 错误

**状态**: 已完成（2026-01-14）

**文件**:
- [x] [typings/opentelemetry/trace.pyi](typings/opentelemetry/trace.pyi)
- [x] [typings/opentelemetry/metrics.pyi](typings/opentelemetry/metrics.pyi)

**stub 内容**:
```python
# typings/opentelemetry/trace.pyi
from typing import Any

class TracerProvider:
    def shutdown(self, timeout_ms: int = 30000) -> None: ...
    def force_flush(self, timeout_ms: int = 30000) -> bool: ...

# typings/opentelemetry/metrics.pyi
from typing import Any

class MeterProvider:
    def shutdown(self, timeout_ms: int = 30000) -> None: ...
    def force_flush(self, timeout_ms: int = 30000) -> bool: ...
```

**预期**: 消除 ~5 个错误

**验证命令**:
```bash
pixi run -e dev pyright packages/foundation/src/ditto_foundation/observability/__init__.py
```

---

### ✅ 批次 1: DataHub 简单错误清理

**目标**: 清理 Unused Import + Unnecessary checks

**状态**: 已完成（2026-01-14）

**文件** (13 个):
1. [packages/datahub/src/ditto_datahub/alerts/wechat.py](../packages/datahub/src/ditto_datahub/alerts/wechat.py)
2. [packages/datahub/src/ditto_datahub/dq/report.py](../packages/datahub/src/ditto_datahub/dq/report.py)
3. [packages/datahub/src/ditto_datahub/dq/engine.py](../packages/datahub/src/ditto_datahub/dq/engine.py)
4. [packages/datahub/src/ditto_datahub/repositories/bars.py](../packages/datahub/src/ditto_datahub/repositories/bars.py)
5. [packages/datahub/src/ditto_datahub/repositories/calendar.py](../packages/datahub/src/ditto_datahub/repositories/calendar.py)
6. [packages/datahub/src/ditto_datahub/repositories/index.py](../packages/datahub/src/ditto_datahub/repositories/index.py)
7. [packages/datahub/src/ditto_datahub/repositories/security.py](../packages/datahub/src/ditto_datahub/repositories/security.py)
8. [packages/datahub/src/ditto_datahub/repositories/universe.py](../packages/datahub/src/ditto_datahub/repositories/universe.py)
9. [packages/datahub/src/ditto_datahub/sources/tushare/client.py](../packages/datahub/src/ditto_datahub/sources/tushare/client.py)
10. [packages/datahub/src/ditto_datahub/runtime/pit_helper.py](../packages/datahub/src/ditto_datahub/runtime/pit_helper.py)
11. [packages/datahub/src/ditto_datahub/stores/parquet_store_base.py](../packages/datahub/src/ditto_datahub/stores/parquet_store_base.py)
12. [packages/datahub/src/ditto_datahub/stores/security_store.py](../packages/datahub/src/ditto_datahub/stores/security_store.py)
13. [packages/datahub/src/ditto_datahub/runtime/sql_engine.py](../packages/datahub/src/ditto_datahub/runtime/sql_engine.py)

**修复策略**:
- **Unused Import**: 直接删除未使用的导入
- **Unnecessary isinstance**: 删除多余的类型检查（类型已收窄）
- **Private Usage**: 创建公共属性访问方法

**实际结果**: 消除 40 个错误

**Commits**:
- `54feea0` feat(batch-1): 清理 DataHub 简单 pyright 错误

**验证命令**:
```bash
pixi run -e dev pyright packages/datahub/src 2>&1 | tail -1
```

---

### ✅ 批次 2: DataHub 类型注解增强

**目标**: 为 Unknown 类型添加显式注解

**状态**: 已完成（2026-01-14）

**文件** (7 个):
1. [packages/datahub/src/ditto_datahub/dq/models.py](../packages/datahub/src/ditto_datahub/dq/models.py) - 5 个错误
2. [packages/datahub/src/ditto_datahub/dq/checkers/business.py](../packages/datahub/src/ditto_datahub/dq/checkers/business.py) - 7 个错误
3. [packages/datahub/src/ditto_datahub/runtime/freeze_manager.py](../packages/datahub/src/ditto_datahub/runtime/freeze_manager.py) - 11 个错误
4. [packages/datahub/src/ditto_datahub/sources/tushare/transformer.py](../packages/datahub/src/ditto_datahub/sources/tushare/transformer.py) - 11 个错误
5. [packages/datahub/src/ditto_datahub/sources/tushare/http_utils.py](../packages/datahub/src/ditto_datahub/sources/tushare/http_utils.py)
6. [packages/datahub/src/ditto_datahub/stores/security_store.py](../packages/datahub/src/ditto_datahub/stores/security_store.py)
7. [packages/datahub/src/ditto_datahub/types.py](../packages/datahub/src/ditto_datahub/types.py)

**修复策略**:
- **Unknown Variable Type**: 添加显式类型注解
- **Unknown Member Type**: 为 list/dict 添加元素类型
- **Lambda Type Unknown**: 为 lambda 参数添加类型
- **Unused Function**: 删除未使用的函数

**示例修复**:
```python
# Before
conditions = []

# After
conditions: list[dict[str, Any]] = []

# Before
manifests.sort(key=lambda m: m.created_at, reverse=True)

# After
from typing import cast
manifests.sort(key=lambda m: cast(str, m.created_at), reverse=True)
```

**实际结果**: 消除全部 33 个错误（DataHub 100% 清零）

**Commits**:
- `2bb36bc` feat(batch-2): 增强 DataHub 类型注解清零 pyright 错误

---

### ✅ 批次 3: Foundation 层清理

**目标**: 清理 foundation 模块的所有错误

**状态**: 已完成（2026-01-14）

**文件** (6 个):
1. [packages/foundation/src/ditto_foundation/observability/__init__.py](../packages/foundation/src/ditto_foundation/observability/__init__.py) - 3 个错误
2. [packages/foundation/src/ditto_foundation/observability/metrics.py](../packages/foundation/src/ditto_foundation/observability/metrics.py)
3. [packages/foundation/src/ditto_foundation/observability/testing.py](../packages/foundation/src/ditto_foundation/observability/testing.py) - 2 个错误
4. [packages/foundation/src/ditto_foundation/observability/tracing.py](../packages/foundation/src/ditto_foundation/observability/tracing.py)
5. [packages/foundation/src/ditto_foundation/app_initializer.py](../packages/foundation/src/ditto_foundation/app_initializer.py) - 2 个错误
6. [packages/foundation/src/ditto_foundation/util/dates.py](../packages/foundation/src/ditto_foundation/util/dates.py) - 1 个错误

**修复策略**:
- **OpenTelemetry stub 扩展**: 创建完整的 SDK/API 类型层次结构
- **Private Usage → Public**: `_get_in_memory_exporter/reader` 改为公共函数
- **类型注解**: 添加显式类型注解（如 `errors: list[str] = []`）

**实际结果**: 消除全部 101 个错误（Foundation 层 100% 清零）

**新增 Stub 文件**:
- `typings/opentelemetry/sdk/trace.pyi`
- `typings/opentelemetry/sdk/resources.pyi`
- `typings/opentelemetry/sdk/trace/export/in_memory_span_exporter.pyi`

---

### 批次 4: Port 应用层清理

**目标**: 清理 apps/port 的所有错误

**文件** (8 个):
1. [apps/port/src/ditto_port/jobs/flows/daily.py](../apps/port/src/ditto_port/jobs/flows/daily.py)
2. [apps/port/src/ditto_port/jobs/flows/repair.py](../apps/port/src/ditto_port/jobs/flows/repair.py) - 6 个错误
3. [apps/port/src/ditto_port/jobs/tasks/dq_batch.py](../apps/port/src/ditto_port/jobs/tasks/dq_batch.py) - 9 个错误
4. [apps/port/src/ditto_port/middleware.py](../apps/port/src/ditto_port/middleware.py)
5. [apps/port/src/ditto_port/services/ingestion/backfill.py](../apps/port/src/ditto_port/services/ingestion/backfill.py) - 14 个错误
6. [apps/port/src/ditto_port/services/ingestion/config/datasets.py](../apps/port/src/ditto_port/services/ingestion/config/datasets.py)
7. [apps/port/src/ditto_port/services/ingestion/result_utils.py](../apps/port/src/ditto_port/services/ingestion/result_utils.py) - 3 个错误
8. [apps/port/src/ditto_port/services/ingestion/security_mapper.py](../apps/port/src/ditto_port/services/ingestion/security_mapper.py)

**修复策略**:
- **Unnecessary Cast**: 删除不必要的 `cast()` 调用
- **Unknown Variable Type**: 添加泛型类型注解
- **Unknown Member Type**: 指标类型声明

**示例修复**:
```python
# Before
dates_by_year = defaultdict(list)

# After
from collections import defaultdict
dates_by_year: defaultdict[int, list[str]] = defaultdict(list)

# Before
from concurrent.futures import ThreadPoolExecutor

# After
from concurrent.futures import Future, ThreadPoolExecutor
```

**预期**: 消除全部 33 个错误（Port 层 100% 清零）

---

### 批次 5: 验证与收尾

**目标**: 全面验证，确保所有模块清零

**验证命令**:
```bash
# 1. 完整 pyright 检查
pixi run -e dev pyright

# 2. 按模块检查
pixi run -e dev pyright packages/datahub/src
pixi run -e dev pyright packages/foundation/src
pixi run -e dev pyright apps/port/src

# 3. 测试验证
pixi run -e dev pytest -m unit
pixi run -e dev pytest -m integration

# 4. 完整 CI 检查
pixi run -e dev ci-check
```

**成功标准**:
- `pixi run -e dev pyright` 输出: `0 errors, 0 warnings, 0 informations`
- 所有测试通过
- 代码覆盖率 >= 80%

---

## 关键文件优先级

| 文件 | 错误数 | 优先级 | 批次 |
|------|--------|--------|------|
| [freeze_manager.py](../packages/datahub/src/ditto_datahub/runtime/freeze_manager.py) | 11 | 高 | 2 |
| [transformer.py](../packages/datahub/src/ditto_datahub/sources/tushare/transformer.py) | 11 | 高 | 2 |
| [backfill.py](../apps/port/src/ditto_port/services/ingestion/backfill.py) | 14 | 高 | 4 |
| [business.py](../packages/datahub/src/ditto_datahub/dq/checkers/business.py) | 7 | 中 | 2 |
| [dq_batch.py](../apps/port/src/ditto_port/jobs/tasks/dq_batch.py) | 9 | 中 | 4 |

---

## 时间估计

| 批次 | 工作量 | 累计进度 | 错误减少 |
|------|--------|----------|----------|
| 0 (准备) | 0.5h | 0% | 116 → 116 |
| 1 (DataHub 简单) | 2h | 21% | 116 → 91 |
| 2 (DataHub 类型) | 4h | 56% | 91 → 51 |
| 3 (Foundation) | 1.5h | 65% | 51 → 41 |
| 4 (Port) | 3h | 93% | 41 → 8 |
| 5 (验证) | 1h | 100% | 8 → 0 |
| **总计** | **12h** | **100%** | **116 → 0** |

---

## 风险控制

### 1. 分批隔离
- **每批独立提交**: 每完成一个批次，创建一个 commit
- **独立 PR**: 每批可独立合并到 main
- **回滚友好**: 如果某批引入问题，可独立回滚

### 2. 测试覆盖
- **单元测试优先**: 每修改一个文件，运行对应的单元测试
- **集成测试**: 每完成一批，运行完整的集成测试
- **烟雾测试**: 每批完成后，运行 `pytest -m smoke`

### 3. 代码审查
- **关键修改需要审查**: 类型注解变更、API 修改
- **自动化检查**: 所有 PR 必须通过 CI 检查
- **预提交钩子**: 确保 pre-commit 通过

---

## 相关文档

- [Python 核心规范](../../.claude/rules/core.md)
- [测试规范](../../.claude/rules/python-test.md)
- [pyproject.toml](../../pyproject.toml) - Pyright 配置

---

## 变更记录

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-01-14 | 创建计划 | Claude |
