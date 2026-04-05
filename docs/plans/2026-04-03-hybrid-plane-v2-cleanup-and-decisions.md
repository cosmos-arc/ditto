# Hybrid Plane v2 重构收尾 — 清理 + 决策记录

> **状态**: ✅ 已完成（2026-04-03）
> 所有 3 个 Phase 已执行完毕。本文档作为历史记录保留。

## Context

Hybrid Plane v2 架构重构已基本完成（Phase 0-5），但源码审计发现以下残留问题：
- **鬼目录/过期文件**：`packages/core/`、stale egg-info、过期的 pyright 配置
- **测试错位**：11 个 analytics 测试仍在 engine 包中，1 个 data 测试仍在 kernel 中
- **设计偏离未记录**：6 项已落地的架构决策与原始设计文档不一致，需正式记录

本计划不涉及行为变更，仅清理残留 + 记录决策。

---

## Phase 1: 鬼目录与过期文件清理 [S×3，可并行] ✅ 已完成

### Task 1.1: 删除 `packages/core/` 鬼目录 + 清理关联配置 `[S]`

**现状**：`packages/core/` 含 131 个 .pyc + stale egg-info，零 .py 源码，零 `ditto_kernel` import。

- `rm -rf packages/core/`
- 编辑 `pyright.tests.json`：移除 `extraPaths` 中的 3 个过期路径
  - `"packages/core/src"` (L7)
  - `"packages/datahub/src"` (L9)
  - `"apps/port/src"` (L12)
- 清理 `.claude/settings.local.json`：移除引用 `packages/core/data/sqlite/` 的 bash 权限条目 (L78-79)

**验收**：`pixi run -e dev lint && pixi run -e dev type` 通过；`ls packages/core` 报错

### Task 1.2: 删除 stale `ditto_data.egg-info/` `[S]`

- `rm -rf packages/data/src/ditto_data.egg-info/`

**验收**：`ls packages/data/src/ditto_data.egg-info` 报错

### Task 1.3: 删除 interfaces registry 中的鬼目录 `[S]`

- `rm -rf apps/interfaces/src/ditto_interfaces/registry/core/`（仅含 `__pycache__`）
- `rm -rf apps/interfaces/src/ditto_interfaces/registry/datahub/`（仅含 `__pycache__`）

**验收**：`pixi run -e dev arch-check` 通过

---

## Phase 2: 测试归位 [S + M + S，顺序执行] ✅ 已完成

### Task 2.1: 迁移 kernel `test_provider.py` → data `[S]`

**现状**：`packages/kernel/tests/unit/test_provider.py`（125 行，5 测试）测试 `ditto_data.provider`，与 kernel 无关。

- `mv packages/kernel/tests/unit/test_provider.py packages/data/tests/unit/test_provider_protocol.py`
- 无需改 import（已 import from `ditto_data.provider`）

**验收**：`pixi run -e dev pytest packages/data/tests/unit/test_provider_protocol.py -v` 通过

### Task 2.2: 迁移 5 个 engine 根级孤儿测试 → analytics `[M]`

**现状**：`packages/engine/tests/unit/engine/` 下 5 个文件测试 `ditto_analytics.*`，应迁到 analytics。

| 源文件 | 目标 | Import 修改 |
|--------|------|-------------|
| `test_evaluation_metrics_unit.py` | `analytics/tests/unit/evaluation/` | 无 |
| `test_factor_context_unit.py` | `analytics/tests/unit/factors/` | 无 |
| `test_publication_safety_unit.py` | `analytics/tests/unit/` | 无 |
| `test_research_unit.py` | `analytics/tests/unit/` | `ditto_engine.errors` → `ditto_data.errors` |
| `test_factor_definitions.py` | `analytics/tests/unit/factors/` | `ditto_engine.specs` → `ditto_kernel.specs` |

- 创建目标目录 + `__init__.py`
- 移动文件 + 修复 2 个文件的 import

**验收**：`pixi run -e dev pytest packages/analytics/tests/unit/ -v` 通过

### Task 2.3: 迁移 6 个 evaluation 孤儿测试 → analytics `[S]`

**现状**：`packages/engine/tests/unit/engine/evaluation/` 下 6 个文件全 import from `ditto_analytics.*`。

- 移动 `test_evaluation_attribution_unit.py`、`test_evaluation_regime_unit.py`、`test_evaluator_unit.py`、`test_factor_exposure_unit.py`、`test_fama_macbeth_unit.py`、`test_metrics_unit.py` → `analytics/tests/unit/evaluation/`
- 无需改 import

**验收**：`pixi run -e dev pytest packages/analytics/tests/unit/evaluation/ -v` 通过

### Task 2.4: 清理 engine 空测试目录 `[S]`

**依赖**：Task 2.2 + 2.3

- 移动后 `engine/tests/unit/engine/` 仅剩 `test_specs_unit.py`（测试 engine 自己的 specs，不是孤儿）
- `rm -rf packages/engine/tests/unit/engine/evaluation/`（移走测试后只剩 `__init__.py` + `__pycache__`）
- 清理 `__pycache__`

**验收**：`pixi run -e dev pytest packages/engine/tests/ -v` 通过

---

## Phase 3: 文档与配置 [S×2，可并行] ✅ 已完成

### Task 3.1: 创建 ADR-0006 记录 6 项架构决策 `[S]`

**文件**：`docs/adr/0006-hybrid-plane-v2-accepted-deviations.md`

记录以下已接受的偏离设计决策：

| ID | 设计文档 | 实际实现 | 接受理由 |
|----|---------|---------|---------|
| D1 | `interfaces/http/` | `interfaces/api/` | FastAPI routes，非通用 HTTP handler |
| D2 | 各包 `di.py`，app 为 Composition Root | Data 有 `di/`，App 有 `providers.py`，interfaces 为 CR | app 层保持 DI 框架无关 |
| D3 | analytics 不依赖 data | 仅 import `ditto_data.errors` 的 2 个错误类 | CLAUDE.md 已记录为允许范围 |
| D4 | `kernel/provider.py` | `ditto_data/provider.py` | BarQuery/InstrumentQuery 是数据层值对象，需要 polars |
| D5 | `apps/app/` | `packages/app/` | 与其他 packages 一致；apps/ 专放可部署应用 |
| D6 | `app/shared/` + `app/registry/` | 顶层扁平结构 + registry 在 interfaces | 当前体量下更简洁 |

另记录：`ditto_infra.foundation` 在 `analytics/research/domain.py` 中的未文档化依赖需补充到 CLAUDE.md。

### Task 3.2: 补充 importlinter 缺失规则 `[S]`

**文件**：`.importlinter`

添加 Phase 2a/5 计划但未实现的 2 条规则（用 `ignore_imports` 锁定现有违规）：

```ini
[importlinter:contract:data-storage-no-model-import]
name = Data storage must not import data models directly
type = forbidden
source_modules = ditto_data.storage.**
forbidden_modules = ditto_data.models.**
ignore_imports =
    ditto_data.storage.** -> ditto_data.models.common
    ditto_data.storage.** -> ditto_data.models.storage
    ditto_data.storage.** -> ditto_data.models.enums
unmatched_ignore_imports_alerting = warn

[importlinter:contract:data-sources-no-storage-import]
name = Data sources must not import data storage
type = forbidden
source_modules = ditto_data.sources.**
forbidden_modules = ditto_data.storage.**
unmatched_ignore_imports_alerting = warn
```

**验收**：`pixi run -e dev arch-check` 通过

---

## 不在本计划范围

| 项目 | 原因 |
|------|------|
| 39 处 "datahub" 注释残留 | 纯文档，优先级低，触及文件时顺手改 |
| `query/contracts.py` 缺失 | 功能已在 `provider.py` 中，无需拆分 |
| DI 架构重构（`di.py` → `app registry`） | 已接受当前设计（ADR D2），功能性正确 |
| analytics `research/domain.py` 中 `ditto_infra` 依赖 | ADR 中记录，不阻塞 |

---

## 执行顺序

```
Phase 1 (并行):  1.1 ─┐
                   1.2 ─┤→ Phase 3 (并行): 3.1 ─┐
                   1.3 ─┘                       3.2 ─┤→ 全局验证
Phase 2 (顺序):  2.1 → 2.2 → 2.3 → 2.4 ────────────┘
```

**总计**：9 个任务（6×S + 2×M + 1×S），预计可合并为 2-3 个 PR。

**实施记录**（2026-04-03）：
- Phase 1: 4 个空壳目录已删除，3 条过期 pyright extraPaths 已清理，2 条 stale bash 权限已移除
- Phase 2: 12 个测试文件归位（kernel→data 1 个，engine→analytics 11 个），2 个 import 修复已完成
- Phase 3: ADR-0006 已创建，2 条 importlinter 新规则已添加（20 contracts, 0 broken）
- 最终验证: `pixi run -e dev check` + `arch-check` 全部通过

---

## 最终验证

```bash
pixi run -e dev check    # lint + fmt + type + test --fast
pixi run -e dev arch-check
```
