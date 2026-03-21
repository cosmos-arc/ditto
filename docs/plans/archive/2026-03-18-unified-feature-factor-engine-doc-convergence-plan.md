# Unified Feature/Factor Engine Doc Convergence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 收敛 unified-feature-factor-engine 的当前真相源，产出单一完整主设计文档，并将不再使用的历史设计文档直接归档。

**Architecture:** 以 `docs/design/unified-feature-factor-engine/main-design.md` 作为唯一完整设计入口，`README.md` 只承担导航与状态说明，ADR 保留为决策附录与专题细化。历史评审、分析、优化与过期计划统一移入 `archive/`，同时修复仓库内所有旧路径引用，避免“入口已变但链接仍指向旧文档”的漂移。

**Tech Stack:** Markdown, ripgrep, apply_patch, pixi

---

### Task 1: 冻结归档范围与当前真相源

**Files:**
- Modify: `docs/design/unified-feature-factor-engine/README.md`
- Create: `docs/plans/2026-03-18-unified-feature-factor-engine-doc-convergence-plan.md`

**Step 1: 明确归档范围**

归档以下历史设计文档：

- `docs/design/unified-feature-factor-engine/issues.md`
- `docs/design/unified-feature-factor-engine/design-analysis-report.md`
- `docs/design/unified-feature-factor-engine/optimization-review.md`
- `docs/design/unified-feature-factor-engine/optimization-backlog.md`
- `docs/design/unified-feature-factor-engine/revision-questdb-hot-layer.md`
- `docs/design/unified-feature-factor-engine/technical-debt-review-2026-03-14.md`
- `docs/design/unified-feature-factor-engine/review-2026-03-15.md`

**Step 2: 冻结当前真相源**

收敛为以下入口：

- `docs/design/unified-feature-factor-engine/main-design.md`
- `docs/design/unified-feature-factor-engine/README.md`
- `docs/design/unified-feature-factor-engine/decisions/00-index.md`
- `docs/plans/2026-03-18-unified-engine-convergence-plan.md`
- `docs/plans/unified-feature-factor-engine-remaining-tasks.md`

**Step 3: 运行路径扫描**

Run: `rg -n 'unified-feature-factor-engine|main-design|remediation-design|phase-6-hardening|issues.md|optimization-review.md' docs/design docs/plans packages/core/src/ditto_core/engine/README.md`

Expected: 能定位所有旧入口引用，便于后续统一修复。

### Task 2: 重写完整主设计文档

**Files:**
- Modify: `docs/design/unified-feature-factor-engine/main-design.md`
- Modify: `packages/core/src/ditto_core/engine/README.md`

**Step 1: 统一主设计结构**

新的主设计必须显式分出：

- 文档状态与真相源
- 系统边界与非目标
- 领域语义与当前支持矩阵
- 表达式/执行/存储/查询/物化/发布/research 全链路
- 已落地 / 预留 / 暂缓
- ADR 对应关系

**Step 2: 移除旧根模型漂移**

从主设计中移除会误导当前实现的旧口径：

- `FeatureSpec / FactorSpec` 作为根模型
- 旧模块落点
- 与当前 `DerivedSpec`、`PUBLISHED`、artifact-first 不一致的表述

**Step 3: 运行文档一致性检查**

Run: `rg -n 'FeatureSpec|FactorSpec|2026-03-13-unified-feature-factor-engine-remediation-design.md|draft / active / deprecated / archived' docs/design/unified-feature-factor-engine/main-design.md packages/core/src/ditto_core/engine/README.md`

Expected: 旧口径从当前主入口中消失，保留的仅限历史说明。

### Task 3: 归档历史设计文档并修复引用

**Files:**
- Modify: `docs/design/unified-feature-factor-engine/README.md`
- Modify: `docs/plans/unified-feature-factor-engine-remaining-tasks.md`
- Modify: `docs/plans/2026-03-17-unified-feature-factor-engine-debt-closure-plan.md`
- Modify: `docs/design/unified-feature-factor-engine/decisions/computation/adr-039-expression-cache-persistence.md`
- Modify: `docs/design/unified-feature-factor-engine/archive/*`（如需补说明）
- Move: `docs/design/unified-feature-factor-engine/issues.md`
- Move: `docs/design/unified-feature-factor-engine/design-analysis-report.md`
- Move: `docs/design/unified-feature-factor-engine/optimization-review.md`
- Move: `docs/design/unified-feature-factor-engine/optimization-backlog.md`
- Move: `docs/design/unified-feature-factor-engine/revision-questdb-hot-layer.md`
- Move: `docs/design/unified-feature-factor-engine/technical-debt-review-2026-03-14.md`
- Move: `docs/design/unified-feature-factor-engine/review-2026-03-15.md`

**Step 1: 归档文件**

将历史设计文档移动到：

- `docs/design/unified-feature-factor-engine/archive/`

**Step 2: 更新 README 导航**

README 只保留：

- 当前真相源
- 阅读顺序
- 归档文档列表
- ADR 索引与 deferred 清单

**Step 3: 修复仓库内旧链接**

Run: `rg -n 'docs/design/unified-feature-factor-engine/(issues|design-analysis-report|optimization-review|optimization-backlog|revision-questdb-hot-layer|technical-debt-review-2026-03-14|review-2026-03-15)\\.md|docs/plans/2026-03-13-unified-feature-factor-engine-remediation-design.md|docs/plans/2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md' docs/design docs/plans`

Expected: 仅保留 archive 路径或新的当前入口路径。

### Task 4: 最终验证

**Files:**
- Verify: `docs/design/unified-feature-factor-engine/README.md`
- Verify: `docs/design/unified-feature-factor-engine/main-design.md`
- Verify: `docs/plans/unified-feature-factor-engine-remaining-tasks.md`

**Step 1: 断链与关键入口检查**

Run: `rg -n '2026-03-13-unified-feature-factor-engine-remediation-design.md|2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md' docs/design/unified-feature-factor-engine docs/plans`

Expected: 不再出现指向已迁移旧路径的当前入口引用。

**Step 2: 运行项目快速校验**

Run: `pixi run -e dev check`

Expected: exit 0

**Step 3: 汇报结果**

报告以下结果：

- 当前唯一真相源
- 新增或重写的主设计入口
- 已归档的历史设计文档清单
- 仍保留的 deferred/remaining tasks
