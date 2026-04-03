# Hybrid Plane v2 最终清理 — 遗留项归零

**状态**: ✅ 已完成
**日期**: 2026-04-03
**前置**: `2026-04-03-hybrid-plane-v2-cleanup-and-decisions.md` (已完成)
**验证**: `pixi run -e dev check` 全部通过 (4367 passed, 0 failed) + `pixi run -e dev arch-check` (20 kept, 0 broken)

## 概述

前序计划覆盖了鬼目录、测试归位、ADR 和 importlinter。本计划覆盖**全部剩余项**，目标 100% 完成：
- 清除所有 re-export shim（开发期无需兼容）
- 消除所有架构违规
- 统一 DataHub → Data 命名
- 同步所有 CLAUDE.md / AGENTS.md / README.md

**原则**：开发期不考虑兼容性，所有废弃代码直接删除。

---

## Phase 1: Re-export Shim 清除 [L]

### Task 1.1: 删除 `engine/specs.py` shim + 迁移消费者 `[L]`

**现状**：`engine/specs.py` 纯转发到 `ditto_kernel.specs`，有 21 个消费者。

**消费者迁移映射**：

| 消费者类型 | 文件数 | 迁移目标 |
|-----------|--------|---------|
| app 源码 | 2 | `from ditto_kernel.specs import ...` |
| data 测试 | 4 | `from ditto_kernel.specs import ...` |
| engine 测试 | 1 | `from ditto_kernel.specs import ...` |
| interfaces 测试 | 14 | `from ditto_kernel.specs import ...` |

**操作**：
1. 逐一替换 21 个文件的 `from ditto_engine.specs import ...` → `from ditto_kernel.specs import ...`
2. 删除 `packages/engine/src/ditto_engine/specs.py`
3. 编辑 `packages/engine/src/ditto_engine/__init__.py`：移除 specs 相关 import + `__all__` 条目

**验收**：`grep -rn "from ditto_engine.specs" packages/ apps/ --include="*.py"` 返回 0

### Task 1.2: 删除 `engine/errors.py` shim + 迁移消费者 `[S]`

**现状**：`engine/errors.py` 纯转发到 `ditto_data.errors`，仅 1 个消费者。

**操作**：
1. 修改 `packages/engine/tests/unit/test_errors_unit.py`：`from ditto_engine.errors` → `from ditto_data.errors`
2. 删除 `packages/engine/src/ditto_engine/errors.py`
3. 编辑 `packages/engine/src/ditto_engine/__init__.py`：移除 errors 相关 import + `__all__` 条目

**验收**：`grep -rn "from ditto_engine.errors" packages/ apps/ --include="*.py"` 返回 0

---

## Phase 2: 架构合规修复 [M]

### Task 2.1: 消除 analytics → infra 跨层依赖 `[S]`

**现状**：`analytics/research/domain.py` 导入 `ditto_infra.foundation.logger`，违反 CLAUDE.md。

唯一的 logger 使用：`_apply_late_arrival_policy` 中的 `logger.warning("SHIFT policy not implemented...")` — 记录的是"功能未实现"提示。

**操作**：
- 替换 `from ditto_infra.foundation import logger` → `import warnings`
- 替换 `logger.warning(...)` → `warnings.warn(...)` （使用 `stacklevel=2`）
- 验证 analytics CLAUDE.md 更新：移除 infra 依赖说明

**验收**：`grep -rn "from ditto_infra" packages/analytics/src/ --include="*.py"` 返回 0

### Task 2.2: 修复 analytics pyproject.toml 依赖声明 `[S]`

**现状**：声明 `ditto-data`（过宽）且缺少 4 个第三方依赖。

**操作**：
```toml
dependencies = [
    "ditto-data",    # errors 子模块（DerivedNotImplementedError, DerivedValidationError）
    "ditto-kernel",
    "polars",
    "numpy",
    "cachebox",
    "orjson",
]
```

注：`ditto-data` 保留因为 pyproject 无法声明子模块级依赖，importlinter 已在代码层强制约束。

**验收**：`pixi run -e dev type` 通过

### Task 2.3: Kernel RiskScope 顶层导出 `[S]`

**现状**：`RiskScope` 定义在 `enums.py`，被 data 和 engine 消费，但未从 `__init__.py` 导出。

**操作**：
- 编辑 `packages/kernel/src/ditto_kernel/__init__.py`：`from ditto_kernel.enums import ...` 增加 `RiskScope`
- 在 `__all__` 中增加 `"RiskScope"`

**验收**：`python -c "from ditto_kernel import RiskScope"` 成功

---

## Phase 3: Ghost 目录清理 [S]

### Task 3.1: 删除 `data/stores/` 鬼目录 `[S]`

**现状**：`packages/data/src/ditto_data/stores/` 含 1.2MB `__pycache__`，零 `.py` 源码，零导入。

**操作**：`rm -rf packages/data/src/ditto_data/stores/`

**验收**：`ls packages/data/src/ditto_data/stores` 报错

### Task 3.2: 修复脚本中的过期路径 `[S]`

**现状**：3 个脚本引用 `packages/datahub/` 路径。

| 文件 | 修复 |
|------|------|
| `scripts/check_code_size.py:140` | `"datahub"` → `"data"` |
| `scripts/analyze_slow_tests.py:66,79` | `"datahub"` → `"data"` |
| `.claude/commands/architecture-audit.py` | 全量更新 `datahub` → `data` 引用（8 处） |

**验收**：`grep -rn "packages/datahub" scripts/ .claude/ --include="*.py"` 返回 0

---

## Phase 4: DataHubError → DataError 重命名 [M]

### Task 4.1: 重命名基异常类 DataHubError → DataError `[M]`

**现状**：`DataHubError` 在 3 个文件中共 26 处引用。

| 文件 | 引用数 | 操作 |
|------|--------|------|
| `packages/data/src/ditto_data/errors.py` | 10 | 类名定义 + 8 个子类 `DataHubError` 基类 + `__all__` + docstring |
| `packages/data/tests/unit/test_errors_unit.py` | 13 | isinstance + 构造 + docstring |
| `packages/data/tests/unit/test_data_source_errors_unit.py` | 3 | isinstance |

**操作**：
1. `errors.py` 中 `class DataHubError` → `class DataError`（+ docstring `"Data layer base exception."` + `__all__`）
2. `errors.py` 中 8 个子类 `(DataHubError)` → `(DataError)`
3. 2 个测试文件中所有 `DataHubError` → `DataError`
4. 全局搜索确认无遗漏：`grep -rn "DataHubError" packages/ apps/ --include="*.py"`
5. 模块 docstring `"DataHub exception classes."` → `"Data layer exception classes."`

**验收**：`grep -rn "DataHubError" packages/ apps/ --include="*.py"` 返回 0

---

## Phase 5: DataHub 命名全面清理 [XL → 3 并行任务]

### Task 5.1: 源码 docstring/comment 清理 `[L]`

**范围**：`packages/` + `apps/` 下 `.py` 文件中的 "DataHub" / "datahub" 引用（~50 文件, ~150 行）

**操作模式**：逐文件替换，保持语义不变：
- `"""DataHub 配置模块"""` → `"""Data 配置模块"""`
- `DataHub 层` → `Data 层`
- `DataHub Service` → `Data Service`
- `from DataHub` / `DataHub 创建` → `Data 层` / `Data 初始化`
- `packages/datahub/` 路径 → `packages/data/`
- `ditto-datahub` → `ditto-data`
- `.claude/rules/datahub.md` 引用 → `.claude/rules/data.md`（如已重命名）

**重点文件**：
- `packages/data/src/ditto_data/` 下 ~30 个源文件的 module docstring
- `packages/data/src/ditto_data/di/` 下 7 个 Provider docstring
- `packages/data/src/ditto_data/storage/` 下 ~18 个设计文档引用注释
- `packages/kernel/src/ditto_kernel/` 下 3 个"预期跨层使用"注释
- `packages/engine/src/ditto_engine/` 下 2 个注释
- `packages/app/src/ditto_app/` 下 3 个注释
- `apps/interfaces/src/ditto_interfaces/` 下 5 个注释
- 各 `tests/` 下的 conftest 和 test 文件 docstring (~10 文件)

**验收**：`grep -rn "DataHub\|datahub" packages/ apps/ --include="*.py"` 返回 0

### Task 5.2: 删除冗余测试 README + 过期迁移文档 `[M]`

**决策**：开发期测试子目录 README 实用性低（开发者直接看 conftest），全量删除减少维护负担。

**操作**：删除以下文件（含过期路径 + "DataHub" 命名）：

**data 测试 README**（12 个）：
- `packages/data/tests/README.md`
- `packages/data/tests/unit/README.md`
- `packages/data/tests/unit/storage/README.md`
- `packages/data/tests/unit/runtime/README.md`
- `packages/data/tests/unit/sources/README.md`
- `packages/data/tests/unit/utils/README.md`
- `packages/data/tests/integration/README.md`
- `packages/data/tests/integration/storage/README.md`
- `packages/data/tests/integration/runtime/README.md`
- `packages/data/tests/integration/sources/README.md`
- `packages/data/tests/integration/sources/tushare/README.md`

**engine 测试 README**（3 个）：
- `packages/engine/tests/README.md`
- `packages/engine/tests/integration/README.md`
- `packages/engine/tests/unit/README.md`

**过期迁移/实现文档**（4 个）：
- `packages/data/MIGRATION_SUMMARY.md`
- `packages/data/tests/integration/sources/tushare/IMPLEMENTATION_SUMMARY.md`
- `packages/data/tests/integration/sources/tushare/QUICK_REFERENCE.md`
- `packages/data/tests/integration/sources/tushare/run_external_tests.bat`
- `packages/data/tests/integration/sources/tushare/run_external_tests.sh`

**验收**：`ls packages/data/tests/README.md packages/engine/tests/README.md` 报错

### Task 5.3: CLAUDE.md / AGENTS.md / README.md 文档同步 `[L]`

**范围**：所有架构文档中的 DataHub/datahub 引用

**操作** — 逐文件修复：

| 文件 | 修复内容 |
|------|---------|
| `packages/data/CLAUDE.md` | 标题 "DataHub 架构规范" → "Data 架构规范"；正文 "DataHub" → "Data" |
| `packages/data/AGENTS.md` | 标题 + DQ config 路径 `packages/datahub/config/dq/` → `packages/data/config/dq/` |
| `packages/data/README.md` | 标题 `ditto-datahub` → `ditto-data`；架构图 + 变更记录 |
| `packages/kernel/CLAUDE.md` | 消费者表 "DataHub, Port" → "Data, Interfaces"；依赖图 "datahub → kernel" → "data → kernel"；DerivedRole 3→4 成员；MaterializationProfile 2→4 成员；新增 RiskScope 行 |
| `packages/kernel/AGENTS.md` | 消费者表 + 依赖图更新 |
| `packages/kernel/README.md` | 架构图 `packages/datahub` → `packages/data` |
| `packages/infra/CLAUDE.md` | 依赖图 `datahub → infra` → `data → infra` |
| `packages/infra/AGENTS.md` | 依赖图更新 |
| `packages/infra/README.md` | 架构图更新 |
| `packages/engine/CLAUDE.md` | 删除 "engine/ 核心引擎（specs、评估指标、publication_safety、research）" 过时行；消费者 "DataHub" → "Data"；测试目录 "strategy/" → "alpha/" |
| `packages/engine/AGENTS.md` | 全量 "DataHub" → "Data" |
| `packages/engine/README.md` | 架构图 + 代码示例 |
| `packages/engine/src/ditto_engine/README.md` | 架构图 + 代码示例 |
| `packages/engine/tests/README.md` | 代码示例 |
| `packages/engine/tests/integration/README.md` | 代码示例 |
| `packages/engine/tests/unit/README.md` | 代码示例 |
| `apps/interfaces/CLAUDE.md` | "DataHub Service/Sources/Stores" → "Data Service/Sources/Storage" |
| `apps/interfaces/AGENTS.md` | 全量更新 |
| `apps/interfaces/README.md` | 架构引用 |
| `packages/analytics/CLAUDE.md` | 消费者引用更新 |
| `packages/app/CLAUDE.md` | 依赖图更新（如有 DataHub 引用） |
| 根 `CLAUDE.md` | 架构图 + 依赖矩阵（如有 DataHub 引用） |

**验收**：`grep -rni "datahub" packages/*/CLAUDE.md packages/*/AGENTS.md packages/*/README.md apps/*/CLAUDE.md apps/*/AGENTS.md apps/*/README.md CLAUDE.md` 返回 0

---

## Phase 6: importlinter 补充 + 最终验证 [S]

### Task 6.1: importlinter `analytics-isolation` 更新 `[S]`

**现状**：`analytics-isolation` 禁止 `ditto_data.**` 但 `ignore_imports` 只列出 `ditto_data.errors`。Task 2.1 完成后无需修改。但应检查 `analytics → infra` 是否需要新增规则。

**操作**：
- 确认 Task 2.1 已消除 infra 依赖后，检查是否需要新增 `analytics-no-infra` 规则
- 如果已消除则标记完成

**验收**：`pixi run -e dev arch-check` 全部 KEPT

### Task 6.2: 全局验证 `[S]`

```bash
# 零残留验证
grep -rn "DataHubError\|from ditto_engine\.specs\|from ditto_engine\.errors\|from ditto_infra" packages/analytics/src/ --include="*.py"
grep -rni "datahub" packages/ apps/ --include="*.py" --include="*.md"

# 完整 check
pixi run -e dev check
pixi run -e dev arch-check
```

---

## 执行依赖与顺序

```
Phase 1 (顺序):  1.1 → 1.2     — shim 清除（1.2 依赖 1.1 共用 __init__.py）
Phase 2 (并行):  2.1 ─┐
                  2.2 ─┤        — 架构合规
                  2.3 ─┘
Phase 3 (并行):  3.1 ─┐         — ghost + 脚本
                  3.2 ─┘
Phase 4:         4.1            — DataError 重命名（可与 5.x 并行）
Phase 5 (并行):  5.1 ─┐         — DataHub 命名（三个任务互不依赖）
                  5.2 ─┤
                  5.3 ─┘
Phase 6:         6.1 → 6.2      — 集成验证
```

**PR 拆分**（用户确认 3 PR 渐进提交）：
- **PR 1**: Phase 1 + Phase 2 + Phase 3（架构清洁度 — shim 清除 + 合规修复 + ghost 清理）
- **PR 2**: Phase 4 + Phase 5（命名统一 — DataError 重命名 + DataHub→Data 全量清理）
- **PR 3**: Phase 6（最终验证 + importlinter 补充）

---

## 任务清单摘要

| # | Task | 复杂度 | 依赖 |
|---|------|--------|------|
| 1.1 | 删除 engine/specs.py shim + 迁移 21 消费者 | L | - |
| 1.2 | 删除 engine/errors.py shim + 迁移 1 消费者 | S | 1.1 |
| 2.1 | 消除 analytics → infra 依赖 | S | - |
| 2.2 | 修复 analytics pyproject.toml | S | - |
| 2.3 | Kernel RiskScope 顶层导出 | S | - |
| 3.1 | 删除 stores/ 鬼目录 | S | - |
| 3.2 | 修复脚本过期路径 | S | - |
| 4.1 | DataHubError → DataError 重命名 | M | - |
| 5.1 | 源码 docstring/comment 清理 | L | 4.1 |
| 5.2 | 测试 README 清理 | M | - |
| 5.3 | CLAUDE.md/AGENTS.md/README.md 同步 | L | - |
| 6.1 | importlinter 补充 | S | 2.1 |
| 6.2 | 全局验证 | S | ALL |

**总计**：13 个任务（5×S + 3×M + 3×L），3 个 PR。

---

## 不在本计划范围

| 项目 | 原因 |
|------|------|
| `query/contracts.py` 拆分 | 功能已在 `provider.py` 中，无架构问题 |
| `analytics/__init__.py` 空 re-export | 当前消费路径一致（子模块直接导入），不阻塞 |
| DI 重构（`di.py` → 各包） | ADR D2 已接受当前设计 |
