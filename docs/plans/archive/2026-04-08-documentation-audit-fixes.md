# Documentation Audit Fixes

## 概述
- Sprint: documentation-cleanup | Phase: audit-fixes
- 创建: 2026-04-08
- 来源: 全库文档审计（README / CLAUDE.md / .claude rules/commands）

## 背景

对项目内所有 README.md（38 个）、CLAUDE.md（8 个）、.claude/rules（10 个）、.claude/commands（6 个）进行了与源码的交叉审计。发现 **13 个 README 过时、7 个 CLAUDE.md 过时、5 个 rules 过时、2 个 commands 过时**，含 1 个 CRITICAL 问题。

修复分三阶段，按影响程度降序执行。

---

## Phase 1 — CRITICAL / HIGH（虚假声明 + 结构性错误）

### Task 1: Analytics CLAUDE.md — 移除虚假 infra 依赖声明 `[S]`
- 验收: `analytics → ditto_infra.foundation.logger` 依赖声明被移除或修正为实际状态
- 文件: `packages/analytics/CLAUDE.md`
- 说明: grep 确认 analytics 源码无任何 `from ditto_infra` import。需移除该依赖声明，或补充实际 import。同时修正 `analytics → infra` 范围描述（importlinter 实际允许全部 infra，不仅 logger）。

### Task 2: Engine README.md — 修正目录结构与虚构模块 `[M]`
- 验收: `stages/` → `builtins/`，`spec.py` → `specs.py`，`orchestrator/` 引用全部移除
- 文件: `packages/engine/README.md`
- 说明: v0.10.0 changelog 中 "orchestrator module added" 需删除。

### Task 3: ditto_engine/README.md — 同步修正 `[M]`
- 验收: `orchestrator/` 模块描述移除，`spec.py` → `specs.py`
- 文件: `packages/engine/src/ditto_engine/README.md`

### Task 4: ditto_engine/alpha/README.md — 目录结构重写 `[M]`
- 验收: `stages/` → `builtins/`，`spec.py` → `specs.py`，`risk_lock.py` 移除（合并入 `filtering.py`）
- 文件: `packages/engine/src/ditto_engine/alpha/README.md`

### Task 5: ditto_engine/portfolio/README.md — 移除不存在的 stages.py `[S]`
- 验收: `stages.py` 引用移除，`AllocationStage`/`ConstraintStage` 描述修正为实际位置
- 文件: `packages/engine/src/ditto_engine/portfolio/README.md`

### Task 6: App README.md — 重建 process/ 文件列表 `[M]`
- 验收: 移除 6 个不存在的文件（`ingestion.py`, `materialization.py`, `strategy.py`, `data_writer.py`, `list_date_inference.py`, `result_handler.py`），补充 6 个遗漏文件（`auto_init.py`, `backfill_handler.py`, `backtest_serialization.py`, `certification_rules.py`, `factor_orthogonalization.py`, `materialization_dependencies.py`, `materialization_helpers.py`, `runtime_input_provider.py`），`_reexports.py` → `types.py`
- 文件: `packages/app/README.md`

### Task 7: Data sources/README.md — 全面重写 `[L]`
- 验收: 版本更新；移除 AkShare 引用；`TushareSource` → `StockTushareAdapter`/`TushareClient`；更新架构描述为 adapters/processors 模式；移除过时的测试覆盖率声明
- 文件: `packages/data/src/ditto_data/sources/README.md`

### Task 8: Data sources/tushare/README.md — 文件结构重写 `[L]`
- 验收: `source.py` → `tushare_source.py`；utils 移入子目录；补充 adapters/processors 文档；移除不存在的 `IMPLEMENTATION_SUMMARY.md`；更新 import 示例
- 文件: `packages/data/src/ditto_data/sources/tushare/README.md`

### Task 9: Interfaces README.md — 修正引用与结构 `[M]`
- 验收: `errors.py` → `exceptions.py`；补全 CLI commands 列表（`init.py`, `factory.py`, `strategy.py`）；补全 models 列表；移除不存在的 re-export shims
- 文件: `interfaces/README.md`

### Task 10: Engine CLAUDE.md — 修正测试目录 `[S]`
- 验收: `tests/unit/strategy/` → `tests/unit/alpha/`；补充 `tests/unit/quality/` 和 `tests/unit/engine/`；移除不存在的 `tests/integration/` 引用
- 文件: `packages/engine/CLAUDE.md`

### Task 11: Kernel CLAUDE.md — 补充遗漏类型 `[S]`
- 验收: `RiskScope`（INSTRUMENT/PORTFOLIO）加入类型表；补充 `test_clock.py`/`test_events.py` 到测试列表
- 文件: `packages/kernel/CLAUDE.md`

---

## Phase 2 — MEDIUM（规则文件引用修正）

### Task 12: core.md — 修正过时的类名和路径引用 `[M]`
- 验收: `class Data` → `MarketService`/`MetadataService`；`SecurityStore`/`BarsStore` → reader/writer 模式；`FileLockManager`/`SQLitePool` 归属修正为 Infra
- 文件: `.claude/rules/core.md`

### Task 13: python-test.md — 修正目录结构和 markers `[M]`
- 验收: 目录示例更新为 `storage/`, `services/`, `sources/`, `quality/`；移除 `smoke`/`benchmark` marker 引用；移除根 `tests/` 目录引用；`SecurityStore` → 实际类名
- 文件: `.claude/rules/python-test.md`

### Task 14: config.md — 修正配置路径 `[S]`
- 验收: `DQSettings` 位置修正为 `ditto_data/quality/config.py`；`FileStorageSettings` 路径修正为 `config/storage.py`
- 文件: `.claude/rules/config.md`

### Task 15: architecture.md — 修正 Quality 域路径 `[S]`
- 验收: Quality 域路径从 `ditto_engine/quality/` → `ditto_data/quality/`
- 文件: `.claude/rules/architecture.md`

### Task 16: pit.md — 修正 API 引用和 marker `[S]`
- 验收: `hub.bars.get()` → 实际 `MarketService` API；`@pytest.mark.ingestion` 引用移除或注册
- 文件: `.claude/rules/pit.md`

### Task 17: ditto-dev.md — 修正 skill 引用 `[S]`
- 验收: `code-simplifier:code-simplifier` → `simplify`
- 文件: `.claude/commands/ditto-dev.md`

### Task 18: architecture-audit.py — 修正层违规检查路径 `[S]`
- 验收: `packages.data.stores.` → `packages.data.storage.`
- 文件: `.claude/commands/architecture-audit.py`

---

## Phase 3 — LOW（次要修正 + 目录树补全）

### Task 19: Root README.md — 次要修正 `[S]`
- 验收: `errors.py` → `exceptions.py`；`_reexports.py` → `types.py`；`stores/` 引用移除；`query/` 标注为空
- 文件: `README.md`

### Task 20: Data README.md — 版本与架构图更新 `[S]`
- 验收: 版本号更新；移除 AkShare 引用；架构图中 Runtime 层移除已迁移的 `SQLitePool`/`FileLockManager`
- 文件: `packages/data/README.md`

### Task 21: ditto_data/README.md — 移除不存在目录 `[S]`
- 验收: `stores/` 目录引用移除；`query/` 标注为空
- 文件: `packages/data/src/ditto_data/README.md`

### Task 22: helpers/README.md — pit.py → pit/ 包 `[S]`
- 验收: `pit.py` 文件引用 → `pit/` 包目录描述
- 文件: `packages/data/src/ditto_data/helpers/README.md`

### Task 23: .github/workflows/README.md — 修正引用 `[S]`
- 验收: `deploy.yml` → `deploy.yml.disabled`；`--cov=apps` → 当前配置
- 文件: `.github/workflows/README.md`

### Task 24: CLAUDE.md 目录树补全 — App `[S]`
- 验收: `query/` 补充 `_instrument_code_facade.py`；`builders/` 补充 `_resolution.py`；补充 App→infra scope 限制说明
- 文件: `packages/app/CLAUDE.md`

### Task 25: CLAUDE.md 目录树补全 — Infra `[S]`
- 验收: 测试目录结构修正；补充 App→infra scope 限制说明
- 文件: `packages/infra/CLAUDE.md`

### Task 26: CLAUDE.md 目录树补全 — Data `[S]`
- 验收: 补全 quality/, storage/, sources/, services/, models/ 缺失文件；`query/` 标注为空
- 文件: `packages/data/CLAUDE.md`

### Task 27: CLAUDE.md 目录树补全 — Interfaces `[S]`
- 验收: 补全 cli/、commands/、jobs/、registry/ 缺失文件
- 文件: `interfaces/CLAUDE.md`

### Task 28: CLAUDE.md 目录树补全 — Engine `[S]`
- 验收: 补充 `alpha/context.py`、`alpha/models.py`、`backtest/audit/` 子目录
- 文件: `packages/engine/CLAUDE.md`

### Task 29: pyproject.toml — 清理过时 per-file-ignores `[S]`
- 验收: 移除引用不存在 `packages/data/src/ditto_data/domains/` 路径的 per-file-ignores 条目
- 文件: `pyproject.toml`

---

## 执行统计

| Phase | 任务数 | 复杂度分布 | 预估文件数 |
|-------|--------|-----------|-----------|
| Phase 1 | 11 | 4S + 4M + 2L + 1CRITICAL | 12 |
| Phase 2 | 7 | 4S + 2M | 8 |
| Phase 3 | 11 | 11S | 11 |
| **合计** | **29** | **19S + 6M + 2L** | **31** |

## 依赖关系

```
Phase 1 (并行)
  ├── Task 1-5: Engine/Analytics README/CLAUDE — 无依赖，可并行
  ├── Task 6: App README — 需先确认 App CLAUDE.md 实际文件列表
  ├── Task 7-8: Data sources README — 需先确认实际 adapter/processor 结构
  └── Task 9-11: Interfaces/Engine/Kernel CLAUDE — 无依赖

Phase 2 (并行)
  └── Task 12-18: rules/commands 修正 — 无依赖，可并行

Phase 3 (并行)
  └── Task 19-29: 次要修正 — 无依赖，可并行
```

## 验证

完成后运行：
```bash
pixi run -e dev check
```
