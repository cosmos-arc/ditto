---
date: 2026-03-31
plan_type: refactor
status: active
origin: docs/plans/2026-03-31-hybrid-plane-v2-migration-plan.md
depth: deep
last_audit: 2026-03-31
---

# Phase 2: Engine 平面成型实施计划 (Units 2a + 2b + 2c)

**目标**：将 Ditto 从 5 包分层架构迁移至 Hybrid 平面架构（新增 ditto_data + ditto_analytics，ditto_kernel 改名 ditto_engine）。
**前置**：Phase 0.5 + Phase 1 已完成（4228 tests ✅, 8/8 arch-check ✅）
**验收**：每个 PR 后 `pixi run -e dev check` 全通过 + arch-check 全通过。

## 确认的设计决策

1. **specs.py + errors.py 留在 engine** — analytics → engine 单向依赖，无循环
2. **Strangler 模式** — 先建新包 + re-export 兼容层，再逐步迁移消费者，最后删除旧路径
3. **quality 零跨包依赖** — 纯 polars/pydantic/loguru，迁移风险极低
4. **errors.py 整体迁移** — 包含 Derived* (7个) + DataHub* (12个) 共 19 个错误类，零外部导入

## 最终依赖图

```
port → engine → kernel
port → analytics → engine → kernel
port → datahub(data) → kernel, infra
analytics → engine.specs + engine.errors（单向）
engine → datahub.errors（re-export chain: engine.errors → datahub.errors → data.errors）
```

## PR 结构（6 个 PR）

---

### PR 2a-1: 创建 ditto_data + 迁移 quality 模块

**目标**：建立 ditto_data 包，迁移 quality + errors，保留 re-export 兼容层。

#### Step 1: 创建 ditto_data 包

| 操作 | 文件 |
|------|------|
| CREATE | `packages/data/pyproject.toml` — name=ditto-data, deps=[ditto-kernel] |
| CREATE | `packages/data/src/ditto_data/__init__.py` — 空 |
| CREATE | `packages/data/src/ditto_data/py.typed` — 空 |
| CREATE | `packages/data/tests/__init__.py` — 空 |

#### Step 2: 复制 quality 模块到 ditto_data

从 `packages/data/src/ditto_data/quality/` 复制 12 个文件到 `packages/data/src/ditto_data/quality/`。

**内部 import 重写**（`ditto_kernel.quality` → `ditto_data.quality`）：
- `__init__.py` — 15 处 import
- `spec.py` — 1 处（severity）
- `engine.py` — 7 处
- `report.py` — 1 处
- `checkers/__init__.py` — 7 处
- `checkers/statistical.py`, `technical.py`, `business.py` — 各 1 处
- `checkers/cross_source.py` — 2 处

**config.py 无需修改**：line 52 的 `Path(__file__)` 死代码路径在当前和迁移后均不解析。

#### Step 3: 迁移 errors.py 到 ditto_data

从 `packages/data/src/ditto_data/errors.py` 复制到 `packages/data/src/ditto_data/errors.py`。
原文件改为 re-export shim：
```python
from ditto_data.errors import *  # noqa: F401,F403
from ditto_data.errors import __all__  # noqa: F401
```

#### Step 4: 转换 ditto_kernel.quality 为 re-export shim

`packages/data/src/ditto_data/quality/__init__.py` 改为 re-export ditto_data.quality 的所有符号。
删除 quality 子目录中所有非 `__init__.py` 文件。

#### Step 5: 更新包配置

| 文件 | 变更 |
|------|------|
| `pixi.toml` [pypi-dependencies] | 添加 `ditto-data = { path = "packages/data", editable = true }` |
| `packages/engine/pyproject.toml` | deps 添加 `ditto-data`（re-export 兼容需要） |
| `packages/data/pyproject.toml` | deps 添加 `ditto-data`（errors re-export 需要） |
| `pyproject.toml` [basedpyright] extraPaths | 添加 `"packages/data/src"` |
| `pyproject.toml` [pytest] pythonpath | 添加 `"packages/data/src"` |
| `pyproject.toml` [pytest] testpaths | 添加 `"packages/data"` |
| `pyright.tests.json` extraPaths | 添加 `"packages/data/src"` |

#### Step 6: 更新 .importlinter

- `root_packages` 添加 `ditto_data`
- `acyclic-packages` ancestors 添加 `ditto_data`
- 新增 `data-boundary` contract（data → engine/port forbidden）
- 更新 `core-must-not-depend-on-datahub`：forbidden 添加 `ditto_data.**`，ignore 添加 `ditto_kernel.** -> ditto_data.quality` + `ditto_data.errors`
- 更新 `foundation-isolation`：forbidden 添加 `ditto_data.**`
- `datahub-boundary`：无变化

**验证**：`pixi run -e dev check` — 4228 tests 全通过（re-export 兼容）

---

### PR 2a-2: 迁移 quality 消费者 + 清理 core quality

**目标**：所有消费者切换到 `ditto_data.quality`，删除 core re-export shim。

#### Step 1: 更新 Port 源码导入（10 文件）

`ditto_kernel.quality` → `ditto_data.quality`：
- `interfaces/src/ditto_interfaces/registry/core/quality.py`
- `interfaces/src/ditto_interfaces/registry/core/golden.py`
- `interfaces/src/ditto_interfaces/registry/infra/config.py`
- `interfaces/src/ditto_interfaces/services/ingestion/quality/service.py`
- `interfaces/src/ditto_interfaces/services/ingestion/quality/l3_batch_service.py`
- `interfaces/src/ditto_interfaces/services/ingestion/quality/reconciliation_service.py`
- `interfaces/src/ditto_interfaces/jobs/tasks/dq_batch.py`
- `interfaces/src/ditto_interfaces/jobs/tasks/monitoring.py`
- `interfaces/src/ditto_interfaces/jobs/context.py`

#### Step 2: 更新 E2E 测试导入（7 文件）

`tests/e2e/conftest.py`, `test_quality.py`, `test_pipeline.py`, `test_query.py`,
`test_ingestion.py`, `test_reporter_unit.py`, `reporter.py`

#### Step 3: 更新 Port 测试导入

`interfaces/tests/` 下所有引用 `ditto_kernel.quality` 的测试文件（~8 文件）

#### Step 4: 迁移 quality 测试文件

移动 `packages/engine/tests/unit/quality/` 整个目录到 `packages/data/tests/unit/quality/`
（含 `checkers/` 子目录和 `fixtures/`）

#### Step 5: 更新 DataHub 测试导入

`packages/data/tests/unit/models/test_common_unit.py`: `ditto_kernel.quality.severity` → `ditto_data.quality.severity`

#### Step 6: 清理

- 删除 `packages/data/src/ditto_data/quality/` 整个目录
- `packages/engine/pyproject.toml` deps 移除 `ditto-data`
- `.importlinter` `core-must-not-depend-on-datahub` 移除 `ditto_kernel.** -> ditto_data.quality` ignore
- `pyproject.toml` per-file-ignores: `packages/data/src/ditto_data/quality/golden.py` → `packages/data/src/ditto_data/quality/golden.py`

**验证**：`pixi run -e dev check` + `grep -rn "ditto_kernel.quality" packages/ apps/ tests/ --include="*.py"` 返回 0

---

### PR 2b-1: 创建 ditto_analytics + 迁移 expression/materialization/compile_cache

**目标**：建立 ditto_analytics 包，迁移 13 个源文件，保留 re-export 兼容层。

#### Step 1: 创建 ditto_analytics 包

| 操作 | 文件 |
|------|------|
| CREATE | `packages/analytics/pyproject.toml` — name=ditto-analytics, deps=[ditto-kernel, ditto-core] |
| CREATE | `packages/analytics/src/ditto_analytics/__init__.py` — 顶层 re-export 所有公开符号 |
| CREATE | `packages/analytics/src/ditto_analytics/py.typed` — 空 |
| CREATE | `packages/analytics/tests/__init__.py` — 空 |

#### Step 2: 迁移 expression/ （8 个文件 → `ditto_analytics/expression/`）

**内部 import 重写**（仅改 analytics 内部互引）：
- `analyzer.py`: `ditto_kernel.engine.expression.ast` → `ditto_analytics.expression.ast`；`ditto_kernel.engine.materialization.contracts` → `ditto_analytics.materialization.contracts`
- `ast.py`: `ditto_kernel.engine.expression.diagnostics` → `ditto_analytics.expression.diagnostics`
- `codegen.py`: expression 内部互引 → `ditto_analytics.expression.*`；`ditto_kernel.engine.specs` **保持不变**
- `compiler.py`: expression/materialization 内部互引 → `ditto_analytics.*`；`ditto_kernel.engine.specs` **保持不变**
- `lexer.py`, `parser.py`: expression 内部互引 → `ditto_analytics.expression.*`

**关键**：所有 `from ditto_kernel.engine.specs import ...` 保持不变（analytics → engine 单向依赖）。

#### Step 3: 迁移 materialization/ （4 个文件 → `ditto_analytics/materialization/`）

- `contracts.py`: `ditto_kernel.engine.materialization.models` → `ditto_analytics.materialization.models`；`ditto_kernel.engine.specs` **保持不变**
- `planner.py`: 同上模式
- `models.py`: 无外部 ditto import
- `__init__.py`: 内部互引 → `ditto_analytics.materialization.*`；specs **保持不变**

#### Step 4: 迁移 compile_cache.py → `ditto_analytics/compile_cache.py`

- `ditto_kernel.engine.expression` → `ditto_analytics.expression`
- `ditto_kernel.engine.materialization` → `ditto_analytics.materialization`
- `ditto_kernel.engine.specs` **保持不变**

#### Step 5: 转换 engine 为 re-export shim

- `packages/analytics/src/ditto_analytics/expression/` → 仅保留 `__init__.py` re-export shim
- `packages/analytics/src/ditto_analytics/materialization/` → 仅保留 `__init__.py` re-export shim
- `packages/analytics/src/ditto_analytics/compile_cache.py` → re-export shim
- `packages/engine/src/ditto_engine/__init__.py` — analytics 相关 import 改为从 `ditto_analytics` re-export

#### Step 6: 更新包配置

| 文件 | 变更 |
|------|------|
| `pixi.toml` [pypi-dependencies] | 添加 `ditto-analytics = { path = "packages/analytics", editable = true }` |
| `packages/engine/pyproject.toml` | deps 添加 `ditto-analytics` |
| `pyproject.toml` [basedpyright] extraPaths | 添加 `"packages/analytics/src"` |
| `pyproject.toml` [pytest] pythonpath | 添加 `"packages/analytics/src"` |
| `pyproject.toml` [pytest] testpaths | 添加 `"packages/analytics"` |
| `pyright.tests.json` extraPaths | 添加 `"packages/analytics/src"` |

#### Step 7: 更新 .importlinter

- `root_packages` 添加 `ditto_analytics`
- `acyclic-packages` ancestors 添加 `ditto_analytics`
- 新增 `analytics-no-datahub-import`（analytics → datahub forbidden）
- 新增 `analytics-must-not-depend-on-port`（analytics → port forbidden）
- 更新 `foundation-isolation`：forbidden 添加 `ditto_analytics.**`

**验证**：`pixi run -e dev check` — 全部通过（re-export 兼容）

---

### PR 2b-2: 迁移 analytics 消费者 + 清理 engine re-export

**目标**：所有消费者切换到 `ditto_analytics`，删除 engine re-export shim。

#### Step 1: 更新 Port 源码导入

**需要改的 import（analytics 相关）**：
- `interfaces/src/ditto_interfaces/registry/datahub/derived.py`: `ditto_kernel.engine` → `ditto_analytics.compile_cache`
- `interfaces/src/ditto_interfaces/services/derived/__init__.py`: `ditto_kernel.engine` → `ditto_analytics`
- `interfaces/src/ditto_interfaces/services/derived/materialization_orchestrator.py`: materialization types → `ditto_analytics.materialization`
- `interfaces/src/ditto_interfaces/services/derived/cascade_protocol.py`: materialization → `ditto_analytics.materialization`
- `interfaces/src/ditto_interfaces/services/derived/publication.py`: `ditto_kernel.engine.materialization.models` → `ditto_analytics.materialization.models`
- `interfaces/src/ditto_interfaces/services/derived/manifest_builder.py`: materialization → `ditto_analytics.materialization`
- `interfaces/src/ditto_interfaces/services/derived/input_preparation.py`: materialization → `ditto_analytics.materialization`

**保持不变的 import**（engine 保留模块）：
- `ditto_kernel.engine.specs` — specs 留在 engine
- `ditto_kernel.engine.publication_safety` — 不迁移
- `ditto_kernel.engine.research` — 不迁移
- `ditto_kernel.engine.errors` — 不迁移

#### Step 2: 更新 Port 测试导入（~14 文件）

所有 `ditto_kernel.engine.materialization.*` → `ditto_analytics.materialization.*`
所有 `ditto_kernel.engine.expression.*` → `ditto_analytics.expression.*`
所有 `ditto_kernel.engine.compile_cache` → `ditto_analytics.compile_cache`
**保持** `ditto_kernel.engine.specs` / `publication_safety` / `research` 不变

#### Step 3: 更新 DataHub 测试导入（6 文件）

- `test_derived_query_service.py`: materialization.models → analytics
- `test_compile_cache_service_unit.py`: materialization + compile_cache → analytics
- `test_artifact_persistence_service_unit.py`: materialization → analytics；specs **保持**
- `test_derived_artifact_writer_unit.py`: materialization → analytics；specs **保持**
- `test_artifact_reader_unit.py`: specs **保持**
- `test_derived_artifact_reader_unit.py`: specs **保持**

#### Step 4: 迁移 engine 测试文件

移动以下测试到 `packages/analytics/tests/unit/`：
- `test_expression_engine_unit.py`
- `test_expression_parser_unit.py`
- `test_expression_type_check_unit.py`
- `test_expression_diagnostics_unit.py`
- `test_materialization_models_unit.py`
- `test_operator_golden_data.py`

保留在 `packages/engine/tests/unit/engine/`（测试 engine 内部模块）：
- `test_specs_unit.py`
- `test_factor_definitions.py` — 更新 import：`ditto_kernel.engine.expression.compiler` → `ditto_analytics.expression.compiler`

#### Step 5: 清理 engine re-export shim

- 删除 `packages/analytics/src/ditto_analytics/expression/` 目录
- 删除 `packages/analytics/src/ditto_analytics/materialization/` 目录
- 删除 `packages/analytics/src/ditto_analytics/compile_cache.py`
- 从 `engine/__init__.py` 移除所有 analytics 相关 import 和 `__all__` 条目
- `packages/engine/pyproject.toml` deps 移除 `ditto-analytics`

#### Step 6: 更新 .importlinter

- 更新 `core-must-not-depend-on-datahub` ignore_imports — 移除 `ditto_kernel.** -> ditto_data.quality`（已在 2a-2 移除）

**验证**：
- `pixi run -e dev check`
- `grep -rn "ditto_kernel.engine.expression\|ditto_kernel.engine.materialization\|ditto_kernel.engine.compile_cache" packages/ apps/ tests/ --include="*.py"` 返回 0

---

### PR 2c-1: ditto_kernel → ditto_engine 机械改名

**目标**：全库替换包名。

#### Step 1: 重命名源码目录

`packages/kernel/src/ditto_kernel/` → `packages/engine/src/ditto_engine/`

#### Step 2: 更新包声明

| 文件 | 变更 |
|------|------|
| `packages/engine/pyproject.toml` | name: `ditto-engine` |
| `pixi.toml` [pypi-dependencies] | `ditto-core` → `ditto-engine` |
| `packages/analytics/pyproject.toml` | deps: `ditto-core` → `ditto-engine` |

#### Step 3: 全库 import 替换

所有 `.py` 文件中 `ditto_kernel` → `ditto_engine`。

**预估影响范围**：
- packages/engine/src/ — ~50 处（模块内部互引）
- packages/engine/tests/ — ~60 处
- interfaces/src/ — ~30 处
- interfaces/tests/ — ~20 处
- packages/data/src/ — ~5 处
- packages/data/tests/ — ~10 处
- packages/analytics/src/ — ~5 处（specs/errors 引用）
- packages/analytics/tests/ — ~5 处

使用三遍方法确保完整性：
1. 自动替换所有 `ditto_kernel` → `ditto_engine`
2. `pixi run -e dev type` — basedpyright 报错定位遗漏
3. `pixi run -e dev test` — 运行时 import 失败定位遗漏

#### Step 4: 更新 .importlinter

所有 `ditto_kernel` → `ditto_engine`：
- root_packages, layered-architecture, kernel-isolation, foundation-isolation
- datahub-boundary, core-must-not-depend-on-datahub（改名：engine-must-not...）, datahub-must-not-depend-on-core（改名：...-engine）
- data-boundary, analytics contracts, acyclic-packages

#### Step 5: 更新配置文件

| 文件 | 变更 |
|------|------|
| `pyproject.toml` [commitizen] version_files | `ditto_kernel/__init__.py` → `ditto_engine/__init__.py` |
| `pyproject.toml` [ruff] per-file-ignores | `ditto_kernel.` → `ditto_engine.` 路径 |

**验证**：`pixi run -e dev check` + `grep -rn "ditto_kernel" packages/ apps/ tests/ --include="*.py"` 返回 0

---

### PR 2c-2: 文档更新 + 最终验证

#### Step 1: 更新 CLAUDE.md

| 文件 | 变更 |
|------|------|
| `CLAUDE.md` | 架构图：添加 analytics/data 包，core→engine |
| `packages/engine/CLAUDE.md` | 模块结构移除 quality/，所有 ditto_kernel → ditto_engine |
| `packages/data/CLAUDE.md` | 更新 errors 引用路径 |
| 新建 `packages/analytics/CLAUDE.md` | analytics 模块规范 |
| 新建 `packages/data/CLAUDE.md` | data 模块规范 |

#### Step 2: 更新 README / AGENTS.md

`packages/engine/README.md`, `packages/engine/AGENTS.md` — ditto_kernel → ditto_engine

#### Step 3: 最终验证

```bash
pixi run -e dev check
pixi run -e dev test
pixi run -e dev type --all
pixi run -e dev arch-check
grep -rn "ditto_kernel" packages/ apps/ tests/ --include="*.py"
```

---

## .importlinter 最终状态

```ini
root_packages = ditto_infra, ditto_data, ditto_engine, ditto_interfaces, ditto_kernel, ditto_data, ditto_analytics

# 主分层：port → engine → datahub → infra
# analytics 和 data 由独立 forbidden contract 管理
layers = ditto_interfaces, ditto_engine, ditto_data, ditto_infra

# engine 隔离
engine-must-not-depend-on-datahub: engine → {datahub, data} forbidden (ignore: errors re-export)
datahub-must-not-depend-on-engine: datahub → engine forbidden

# analytics 隔离
analytics-no-datahub-import: analytics → datahub forbidden
analytics-must-not-depend-on-port: analytics → port forbidden

# data 隔离
data-boundary: data → {engine, port} forbidden

# kernel/infra 隔离：不变
# port-boundary：不变
# acyclic-packages：7 ancestors
```

## 风险缓解

| 风险 | 缓解 |
|------|------|
| 消费者遗漏 | re-export shim 确保零破坏直到清理 PR；grep 验证 |
| 循环依赖 | specs.py 留 engine 确保 analytics 单向依赖；acyclic contract 验证 |
| 2c 机械改名遗漏 | 三遍方法：自动替换 → type check → test |
| 测试计数回归 | golden test 基线 + 每个 PR 后 `pixi run -e dev test` |
