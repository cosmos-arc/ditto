# Hybrid Plane V2 迁移收尾 — 实施计划 ✅ COMPLETED

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 清理 Hybrid Plane V2 迁移遗留的 7 类问题（配置路径残留、re-export shim、文档不同步、R8 孤立规则、build 残留），实现源码级完全收敛。

**Architecture:** 本次为纯收尾工作，无架构变更。核心操作分三组：配置路径修正（pixi.toml / CI）、shim 消费迁移（跨包 import 路径直接化）、文档/规则同步。

**Tech Stack:** Python import 路径替换、TOML/YAML 配置编辑、importlinter 规则维护

---

## 背景与问题清单

基于 2026-04-02 源码级审计，Phase 0.5~5 全部功能实现已完成，但存在以下收尾遗留：

| # | 问题 | 严重度 | 根因 |
|---|------|--------|------|
| I1 | `pixi.toml` dev/server 命令引用 `ditto_port` 旧路径 | **高** — 阻断本地开发 | Phase 4d 重命名遗漏 |
| I2 | `ci.yml` 变更检测 + 测试路径引用 `apps/port/` | **高** — 阻断 CI | Phase 4d 重命名遗漏 |
| I3 | `e2e-validation.yml` 路径引用 `apps/port/` | **中** — 阻断 E2E 触发 | Phase 4d 重命名遗漏 |
| I4 | `PULL_REQUEST_TEMPLATE.md` 影响范围引用 `apps/port` | **低** — 文档残留 | Phase 4d 重命名遗漏 |
| I5 | `ditto_port.egg-info/` build 残留 | **低** — 不影响运行 | Phase 4d 目录重命名后未清理 |
| I6 | ~14 处消费端通过 re-export shim 间接引用 | **中** — Strangler 模式未收尾 | Phase 2/3 shim 未消费完 |
| I7 | `ditto_data/models/__init__.py` 通过 shim 导入 factors/features | **中** | 同上 |
| I8 | `CLAUDE.md` 架构图缺少 `packages/app/` | **低** — 文档不同步 | Phase 4 新增包未同步 |
| I9 | `.importlinter` R8 规则引用不存在的 `app.command` | **低** — 孤立规则 | R8 规则先于模块创建 |
| I10 | `Phase 2d (TradingOrchestrator)` 未实施 | **信息** — 有意裁剪 | 实施时范围决策 |

---

## PR 1: 配置路径修正 `[M]`

**目标**：修复所有 `ditto_port` / `apps/port` 旧路径引用，恢复本地开发和 CI 正常运行。

### Task 1: 修复 pixi.toml 入口点

**Files:**
- Modify: `pixi.toml:207,210`

**Step 1: 更新 dev 和 server 命令**

将第 207 行和第 210 行的 `apps.port.src.ditto_port.main:app` 替换为 `apps.interfaces.src.ditto_interfaces.main:app`。

**Step 2: 验证**

Run: `pixi run -e dev dev --help`（或手动检查 granian 能否找到模块）
Expected: 命令不再报模块找不到错误

**Step 3: Commit**

```bash
git add pixi.toml
git commit -m "fix: pixi.toml 入口点 ditto_port → ditto_interfaces"
```

---

### Task 2: 修复 ci.yml 路径引用

**Files:**
- Modify: `.github/workflows/ci.yml:45,166`

**Step 1: 更新变更检测路径（第 45 行）**

`'apps/port/**/*.py'` → `'apps/interfaces/**/*.py'`

**Step 2: 更新测试路径（第 166 行）**

`apps/port/tests/unit/` → `apps/interfaces/tests/unit/`

**Step 3: 验证**

检查文件内容确认两处替换正确。

**Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "fix: ci.yml 路径 apps/port → apps/interfaces"
```

---

### Task 3: 修复 e2e-validation.yml + PULL_REQUEST_TEMPLATE.md

**Files:**
- Modify: `.github/workflows/e2e-validation.yml:10`
- Modify: `.github/PULL_REQUEST_TEMPLATE.md:21`

**Step 1: 更新 e2e-validation.yml 第 10 行**

`'apps/port/**'` → `'apps/interfaces/**'`

**Step 2: 更新 PULL_REQUEST_TEMPLATE.md 第 21 行**

```
- [ ] `apps/port` - 后端服务
```
→
```
- [ ] `packages/app` - 应用编排层
- [ ] `apps/interfaces` - Server 应用（API/CLI/Jobs）
```

同时将过时的 `packages/foundation` 改为 `packages/infra`。

**Step 3: Commit**

```bash
git add .github/workflows/e2e-validation.yml .github/PULL_REQUEST_TEMPLATE.md
git commit -m "fix: e2e + PR template 路径更新"
```

---

### Task 4: 删除 ditto_port.egg-info

**Files:**
- Delete: `apps/interfaces/src/ditto_port.egg-info/` (整个目录，5 个文件)

**Step 1: 确认目录内容**

```
apps/interfaces/src/ditto_port.egg-info/
├── PKG-INFO
├── SOURCES.txt
├── dependency_links.txt
├── entry_points.txt
└── top_level.txt
```

**Step 2: 删除目录**

```bash
rm -rf apps/interfaces/src/ditto_port.egg-info/
```

**Step 3: 验证**

```bash
ls apps/interfaces/src/ditto_port.egg-info 2>&1
# Expected: No such file or directory
```

**Step 4: Commit**

```bash
git add -u apps/interfaces/src/ditto_port.egg-info/
git commit -m "chore: 删除 ditto_port.egg-info build 残留"
```

---

### Task 5: PR 1 集成验证

**Step 1: 运行完整检查**

Run: `pixi run -e dev check`
Expected: lint + type + test 全通过

**Step 2: 运行 arch-check**

Run: `pixi run -e dev arch-check`
Expected: 21/21 contracts 通过

---

## PR 2: Re-export Shim 清理 `[L]`

**目标**：将所有通过 `ditto_data.errors`、`ditto_data.models.factors`、`ditto_data.models.features` 间接引用的消费端迁移到权威路径，然后删除 shim 文件。

**shim 依赖链：**

```
权威定义位置:
  ditto_data.errors          ← 数据错误层级
  ditto_analytics.models.factors   ← 因子元数据
  ditto_analytics.models.features  ← 指标元数据

shim 文件:
  ditto_data/errors.py         → re-export ditto_data.errors
  ditto_data/models/factors.py  → re-export ditto_analytics.models.factors
  ditto_data/models/features.py → re-export ditto_analytics.models.features

消费端（需迁移）:
  跨包 — ditto_engine (1), ditto_app (4)  → 必须改
  同包 — ditto_data src (4), tests (4) → 改为权威路径更清晰
  同包 — ditto_data models/__init__ (1) → 改为权威路径
```

### Task 6: 迁移 ditto_engine 错误引用

**Files:**
- Modify: `packages/core/src/ditto_engine/engine/errors.py`

**Step 1: 更新 import 路径**

```python
# 旧:
from ditto_data.errors import (
    DerivedDependencyError,
    ...
)

# 新:
from ditto_data.errors import (
    DerivedDependencyError,
    ...
)
```

同时更新模块 docstring（第 4 行）：
```python
# 旧: Canonical definitions live in ditto_data.errors
# 新: Canonical definitions live in ditto_data.errors
```

**Step 2: 验证**

Run: `pixi run -e dev type`
Expected: 零新增 error

**Step 3: Commit**

```bash
git add packages/core/src/ditto_engine/engine/errors.py
git commit -m "refactor: engine errors 引用 ditto_data.errors 权威路径"
```

---

### Task 7: 迁移 ditto_app 错误引用

**Files:**
- Modify: `packages/app/src/ditto_app/process/ingestion.py:23`
- Modify: `packages/app/src/ditto_app/config.py:24`
- Modify: `packages/app/src/ditto_app/process/materialization.py:31`
- Modify: `packages/app/src/ditto_app/query/research.py:22`

**Step 1: 逐文件更新 import**

| 文件 | 旧 import | 新 import |
|------|-----------|-----------|
| `process/ingestion.py:23` | `from ditto_data.errors import AmbiguousTickerError, IdentifierNotFoundError` | `from ditto_data.errors import AmbiguousTickerError, IdentifierNotFoundError` |
| `config.py:24` | `from ditto_data.errors import DatasetNotFoundError` | `from ditto_data.errors import DatasetNotFoundError` |
| `process/materialization.py:31` | `from ditto_data.errors import DerivedNotFoundError, DerivedValidationError` | `from ditto_data.errors import DerivedNotFoundError, DerivedValidationError` |
| `query/research.py:22` | `from ditto_data.errors import DerivedNotFoundError, DerivedValidationError` | `from ditto_data.errors import DerivedNotFoundError, DerivedValidationError` |

**Step 2: 验证**

Run: `pixi run -e dev type`
Expected: 零新增 error

**Step 3: Commit**

```bash
git add packages/app/src/ditto_app/
git commit -m "refactor: app 层错误引用 ditto_data.errors 权威路径"
```

---

### Task 8: 迁移 ditto_data 内部错误引用

**Files:**
- Modify: `packages/data/src/ditto_data/stores/metadata/calendar/calendar_reader.py:18`
- Modify: `packages/data/src/ditto_data/services/metadata/instrument.py:16`
- Modify: `packages/data/src/ditto_data/services/derived/artifact_reader.py:12`
- Modify: `packages/data/src/ditto_data/services/derived/query_service.py:9`

**Step 1: 逐文件更新 import**

每个文件的 `from ditto_data.errors import ...` → `from ditto_data.errors import ...`

**Step 2: 验证**

Run: `pixi run -e dev type`
Expected: 零新增 error

**Step 3: Commit**

```bash
git add packages/data/src/ditto_data/
git commit -m "refactor: datahub 内部引用 ditto_data.errors 权威路径"
```

---

### Task 9: 迁移 datahub 测试错误引用

**Files:**
- Modify: `packages/data/tests/unit/test_errors_unit.py:3`
- Modify: `packages/data/tests/unit/services/test_derived_query_service.py:13`
- Modify: `packages/data/tests/unit/services/test_artifact_reader_unit.py:9`
- Modify: `packages/data/tests/unit/services/test_metadata_service_identifier_resolution_unit.py:7`

**Step 1: 逐文件更新 import**

每个文件的 `from ditto_data.errors import ...` → `from ditto_data.errors import ...`

**Step 2: 验证**

Run: `pixi run -e dev test --unit`
Expected: 全通过

**Step 3: Commit**

```bash
git add packages/data/tests/
git commit -m "refactor: datahub 测试引用 ditto_data.errors 权威路径"
```

---

### Task 10: 迁移 datahub/models/__init__.py factors/features 引用

**Files:**
- Modify: `packages/data/src/ditto_data/models/__init__.py:27,41`

**Step 1: 更新 factors import（第 27 行）**

```python
# 旧:
from ditto_data.models.factors import (...)

# 新:
from ditto_analytics.models.factors import (...)
```

**Step 2: 更新 features import（第 41 行）**

```python
# 旧:
from ditto_data.models.features import (...)

# 新:
from ditto_analytics.models.features import (...)
```

**Step 3: 验证**

Run: `pixi run -e dev type`
Expected: 零新增 error

**Step 4: Commit**

```bash
git add packages/data/src/ditto_data/models/__init__.py
git commit -m "refactor: datahub models 引用 ditto_analytics.models 权威路径"
```

---

### Task 11: 删除 re-export shim 文件

**Files:**
- Delete: `packages/data/src/ditto_data/errors.py`
- Delete: `packages/data/src/ditto_data/models/factors.py`
- Delete: `packages/data/src/ditto_data/models/features.py`

**Step 1: 全局验证零消费者**

```bash
# 确认 errors shim 无消费者
grep -rn "from ditto_data.errors import" packages/ apps/ --include="*.py"
# Expected: 0 结果

# 确认 factors shim 无消费者
grep -rn "from ditto_data.models.factors import" packages/ apps/ --include="*.py"
# Expected: 0 结果

# 确认 features shim 无消费者
grep -rn "from ditto_data.models.features import" packages/ apps/ --include="*.py"
# Expected: 0 结果
```

**Step 2: 删除 shim 文件**

```bash
rm packages/data/src/ditto_data/errors.py
rm packages/data/src/ditto_data/models/factors.py
rm packages/data/src/ditto_data/models/features.py
```

**Step 3: 验证**

Run: `pixi run -e dev check`
Expected: lint + type + test 全通过

Run: `pixi run -e dev arch-check`
Expected: 21/21 contracts 通过

**Step 4: Commit**

```bash
git add -u packages/data/src/ditto_data/
git commit -m "refactor: 删除 datahub re-export shim（errors/factors/features）"
```

---

## PR 3: 文档同步 + 规则清理 `[M]`

**目标**：更新 CLAUDE.md 架构图反映最终包结构，清理 importlinter 孤立 R8 规则。

### Task 12: 更新 CLAUDE.md 架构图

**Files:**
- Modify: `CLAUDE.md:241-258`

**Step 1: 更新项目架构附录**

```text
ditto/
├── packages/           # 核心包
│   ├── infra/        # 基础设施
│   ├── kernel/       # 共享内核（零业务行为类型）
│   ├── datahub/       # 数据访问层
│   ├── data/          # 数据质量 + 错误定义
│   ├── analytics/     # 表达式编译 + 物化
│   ├── app/           # 应用编排层（CQRS: query/process/builders）
│   └── core/          # 核心引擎（→ ditto_engine）
├── apps/              # 应用
│   ├── interfaces/    # Server 应用（API/CLI/Jobs）
│   └── web/           # Web 应用
├── config/            # 环境配置（按环境分组）
│   ├── development/
│   ├── testing/
│   └── production/
└── docs/              # 文档
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md 架构图补充 packages/app/"
```

---

### Task 13: 清理 importlinter 孤立 R8 app.command 规则

**Files:**
- Modify: `.importlinter`

**背景**：R8 互斥矩阵中有 5 个 contract 引用 `ditto_app.command.**`，但 `app/command/` 目录不存在。这些规则当前不会产生误报（因为 forbidden_modules 匹配空集 = 0 violations），但属于死规则，应清理。

**决策**：删除引用 `app.command` 的 5 个 contract，保留 `app.query` ↔ `app.process` 和 `app.builders` ↔ `app.command` 等有意义的规则。最终保留：

| Contract | Source | Forbidden | 保留理由 |
|----------|--------|-----------|---------|
| `r8-query-no-process` | app.query | app.process | ✅ 读写分离 |
| `r8-query-no-builders` | app.query | app.builders | ✅ 只读不装配 |
| `r8-builders-no-query` | app.builders | app.query | ✅ 装配不查询 |

删除的 contract：

| Contract | 原因 |
|----------|------|
| `r8-query-no-command` | app.command 不存在 |
| `r8-command-no-query` | app.command 不存在 |
| `r8-command-no-process` | app.command 不存在 |
| `r8-builders-no-command` | app.command 不存在 |

同时更新注释中的 R8 矩阵（第 192-197 行），移除 command 相关行。

**Step 1: 删除 4 个 contract 块**

删除 `[importlinter:contract:r8-query-no-command]`、`[importlinter:contract:r8-command-no-query]`、`[importlinter:contract:r8-command-no-process]`、`[importlinter:contract:r8-builders-no-command]` 四个完整块。

**Step 2: 更新 R8 矩阵注释**

```ini
# 矩阵：
#   app.query     -X-> app.process, app.builders  (只读)
#   app.process   ->  app.query                   (允许协调)
#   app.builders  -X-> app.query                  (只装配)
#   process <-> builders 允许双向
#
# 注：app.command 模块尚未创建，相关 R8 规则在模块创建时补充
```

**Step 3: 验证**

Run: `pixi run -e dev arch-check`
Expected: 全部 contracts 通过（现在应该是 17 个而非 21 个）

**Step 4: Commit**

```bash
git add .importlinter
git commit -m "refactor: 移除 importlinter 孤立 R8 app.command 规则"
```

---

### Task 14: 更新迁移计划文档状态

**Files:**
- Modify: `docs/plans/2026-03-31-hybrid-plane-v2-migration-plan.md`

**Step 1: 更新进度表**

- 将 `| 4-5 | 路线图剩余 | ⏳ Phase 3 完成，Phase 4-5 待规划 |` 更新为已完成状态
- 添加 Phase 2d 正式裁剪说明
- 更新完成标准 checklist 中剩余项

**Step 2: Commit**

```bash
git add docs/plans/2026-03-31-hybrid-plane-v2-migration-plan.md
git commit -m "docs: 更新迁移计划状态 — Phase 4-5 完成 + Phase 2d 裁剪说明"
```

---

### Task 15: 最终集成验证

**Step 1: 运行完整 check**

Run: `pixi run -e dev check`
Expected: lint + type + test 全通过

**Step 2: 运行 arch-check**

Run: `pixi run -e dev arch-check`
Expected: 全部 contracts 通过（17 个）

**Step 3: 全局残留验证**

```bash
# 确认 Python 源码零 ditto_port 残留
grep -rn "ditto_port" packages/ apps/ --include="*.py"
# Expected: 0 结果

# 确认 Python 源码零 ditto_core 残留
grep -rn "ditto_core" packages/ apps/ --include="*.py"
# Expected: 0 结果

# 确认 shim 文件已删除
ls packages/data/src/ditto_data/errors.py 2>&1
# Expected: No such file or directory

ls packages/data/src/ditto_data/models/factors.py 2>&1
# Expected: No such file or directory

ls packages/data/src/ditto_data/models/features.py 2>&1
# Expected: No such file or directory

# 确认 egg-info 已删除
ls apps/interfaces/src/ditto_port.egg-info 2>&1
# Expected: No such file or directory
```

**Step 4: Commit（如有遗漏修复）**

---

## 任务汇总

| Task | 内容 | 复杂度 | PR |
|------|------|--------|-----|
| 1 | 修复 pixi.toml 入口点 | S | PR1 |
| 2 | 修复 ci.yml 路径 | S | PR1 |
| 3 | 修复 e2e-validation.yml + PR template | S | PR1 |
| 4 | 删除 ditto_port.egg-info | S | PR1 |
| 5 | PR 1 集成验证 | S | PR1 |
| 6 | 迁移 engine 错误引用 | S | PR2 |
| 7 | 迁移 app 错误引用 | S | PR2 |
| 8 | 迁移 datahub 内部错误引用 | S | PR2 |
| 9 | 迁移 datahub 测试错误引用 | S | PR2 |
| 10 | 迁移 datahub models/__init__ 引用 | S | PR2 |
| 11 | 删除 re-export shim 文件 | S | PR2 |
| 12 | 更新 CLAUDE.md 架构图 | S | PR3 |
| 13 | 清理 importlinter R8 孤立规则 | S | PR3 |
| 14 | 更新迁移计划文档状态 | S | PR3 |
| 15 | 最终集成验证 | S | PR3 |

**总计**: 15 个 Task，全部 S 级，3 个 PR。

---

## 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
|---|------|------|------|------|
| R1 | shim 删除后有遗漏消费者 | 低 | 中 | Task 11 Step 1 全局 grep 验证零消费者后才删除 |
| R2 | pixi.toml 入口点修改后 granian 启动失败 | 低 | 高 | 手动验证 `pixi run -e dev dev --help` |
| R3 | importlinter contract 删除后暴露新违规 | 低 | 低 | 删除前先运行 arch-check 确认基线 |

---

## Phase 2d (TradingOrchestrator) 裁剪说明

原计划 Phase 2d 要求实现 TradingOrchestrator + 5 个 Runtime Contract + EventBus 隔离 + Stage 契约强类型。该 Unit 在实施过程中被有意的范围裁剪，理由：

1. **当前引擎已稳定运行** — 策略引擎全链路通过 4200+ 测试
2. **Runtime Contract 可渐进添加** — 不阻塞当前开发
3. **Phase 4 App 层已覆盖编排需求** — `ditto_app/process/` + `ditto_app/builders/` 提供了 CQRS 编排结构

**建议**：在后续需要扩展运行时契约（如引入实盘 Runtime Contract）时再独立规划，不作为本次迁移收尾的一部分。
