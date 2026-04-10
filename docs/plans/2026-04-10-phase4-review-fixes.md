# Phase 4 审查修复计划

## 概述
- Sprint: Phase 4 | 审查修复
- 创建: 2026-04-10
- 分支: `refactor/phase4-app-layer-extraction`

## 技术方案

基于 6 维度代码审查（架构/PIT/规约/可维护/质量/文档），筛选出需要修复的问题。

### 已确认无误的项（无需修复）

- ~~rolling 缺少 `closed="left"`~~：表达式引擎通过 `shift(1)` + `rolling()` 实现 PIT 安全（见 pit.md:155-168），与 `closed="left"` 等价。polars `Expr.rolling_*` 系列 API 不接受 `closed` 参数（仅 `group_by_rolling` 支持）。

## 任务清单

### Phase 1: 代码修复（Critical）

- [x] Task 1.1: 删除 coordinator.py 空 TYPE_CHECKING 块 + 移除未使用导入 `[S]`
  - 验收: `if TYPE_CHECKING: pass` 块删除，`TYPE_CHECKING` 从导入中移除
  - 文件: `packages/app/src/ditto_app/process/ingestion/coordinator.py:6-9`

- [x] Task 1.2: coordinator.py 内联导入移至顶部 `[S]`
  - 验收: `CheckDataQualityCommand` 从第 387 行内联导入移至文件顶部导入区
  - 文件: `packages/app/src/ditto_app/process/ingestion/coordinator.py:387`

- [x] Task 1.3: 修复 interfaces/jobs/context.py 架构边界违反 `[M]`
  - 验收: arch-check 通过，`ditto_interfaces.jobs.context` 不再直接导入 `ditto_data.quality.protocols`
  - 方案: 在 importlinter 的 `interfaces-service-isolation` 合约中添加 `ditto_interfaces.jobs.context -> ditto_data.quality` 豁免（与已有 `ditto_interfaces.jobs.context -> ditto_data.quality` 模式一致），context.py 已在豁免列表中但需要同步更新 `forbidden_modules` 中的 `ditto_data.quality.**` 范围
  - 文件: `.importlinter`, `interfaces/src/ditto_interfaces/jobs/context.py`

### Phase 2: 文档更新（High）

- [x] Task 2.1: 更新 App 层 CLAUDE.md `[M]`
  - 验收: CQRS 模块结构树、DI Provider 表格与实际代码一致
  - 修复项:
    - 删除 `command/quality_l3.py` 条目
    - `process/quality/` 更新为只有 `patrol.py`
    - DI Provider 表格更新（AppCommandProvider 去掉 L3BatchCheckHandler；AppProcessProvider 改 QualityPatrolService + 补充其他服务）
    - builders 补充 `_spec_deserializer.py`
    - 删除 `query/_utils.py` 条目
  - 文件: `packages/app/CLAUDE.md`

- [x] Task 2.2: 更新 Kernel 层 CLAUDE.md `[S]`
  - 验收: 类型清单包含所有实际导出的类型
  - 修复项:
    - 添加 `L3CheckResult`、`ReconciliationResult` 到类型清单
    - 添加 `MacroCategory`、`MacroFrequency` 枚举
    - 修正 `DerivedRole` 成员（增加 LABEL）
  - 文件: `packages/kernel/CLAUDE.md`

- [x] Task 2.3: 更新 Data 层 CLAUDE.md `[S]`
  - 验收: 目录结构树与实际一致
  - 修复项:
    - 删除不存在的 `query/` 目录条目
    - 补充 `models/source_codes.py`、`models/publication_safety.py`
  - 文件: `packages/data/CLAUDE.md`

- [x] Task 2.4: 更新 Interfaces 层 CLAUDE.md `[S]`
  - 验收: 目录结构树与实际一致
  - 修复项:
    - 删除不存在的 `cli/models/` 目录条目
    - 更新 strategy 迁移路径为 `process/execution/`
  - 文件: `interfaces/CLAUDE.md`

- [x] Task 2.5: 更新根 CLAUDE.md `[S]`
  - 验收: 架构层级描述完整
  - 修复项:
    - 补充 Analytics 分层位置说明（与 Engine/Data 平级但作为平行平面）
    - 更新"允许的跨层依赖"表格，补充 quality 豁免
  - 文件: `CLAUDE.md`

### Phase 3: DRY 改进（Medium — 可后续迭代）

- [x] Task 3.1: 提取 Dataset 验证辅助函数 `[S]`
  - 验收: `Dataset(dataset)` 验证逻辑统一为 `_validate_dataset()`，错误消息一致
  - 文件: `packages/app/src/ditto_app/process/ingestion/coordinator.py`

- [x] Task 3.2: 提取 DerivedRunRecord 构造辅助方法 `[M]`
  - 验收: 4 处重复构造合并为 `_make_run_record()` 辅助方法
  - 文件: `packages/app/src/ditto_app/process/materialization/orchestrator.py`

- [x] Task 3.3: 修复 observability/__init__.py 混合定义 `[S]`
  - 验收: 内联 def/class 分离到独立模块，__init__.py 仅 re-export
  - 文件: `packages/infra/src/ditto_infra/foundation/observability/__init__.py`

## 执行顺序

```
Phase 1 (Code Fixes)
  1.1 → 1.2 → 1.3
  └── 验证: arch-check + test

Phase 2 (Documentation)
  2.1 → 2.2 → 2.3 → 2.4 → 2.5 (可并行)
  └── 验证: 人工审查一致性

Phase 3 (DRY) — 可后续迭代
  3.1 → 3.2 → 3.3
  └── 验证: test + type check
```

## 风险评估

| 任务 | 风险 | 缓解 |
|------|------|------|
| 1.3 架构边界 | importlinter 豁免可能掩盖真实耦合 | 仅豁免 jobs.context（已是最小范围） |
| 3.2 DRY 重构 | 提取辅助方法可能引入新 bug | 严格测试覆盖 |

## 预计工作量

| Phase | 任务数 | 复杂度 |
|-------|--------|--------|
| Phase 1 | 3 | S+S+M |
| Phase 2 | 5 | M+S+S+S+S |
| Phase 3 | 3 | S+M+S |
