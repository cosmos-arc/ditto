# Phase 4 代码审查全量修复计划

## 概述

- **分支**: `refactor/phase4-app-layer-extraction`
- **创建**: 2026-04-08
- **来源**: 6 维度并行审查结果（架构/PIT/规约/可维护/质量/文档）
- **范围**: 0 Critical、26 Warning、25 Info — 全部修复

## 技术方案

### 核心决策

1. **P0 架构违规**：混合策略 — 枚举/值对象提升到 `ditto_kernel`，复合类型通过 `ditto_app` facade 解耦
2. **超长文件拆分**：仅 `ingestion_coordinator.py`（953 行），其他 >700 行文件不在本次范围
3. **依赖关系**：Task 1-3（架构）顺序执行；Task 4-6（P1）可并行；Task 7-11（P2）可并行

### 架构迁移策略（P0 #1）

```
Phase A: 纯类型 → kernel（零风险）
  InstrumentIngestParams, MacroCategory, MacroFrequency
  IdentifierError + DataError + NoIdentifierProvidedError + AmbiguousTickerError

Phase B: 拆分类型 → kernel（需拆分）
  Dataset 枚举体 → kernel; property/method → 保留 data
  DQLevel + DQSeverity + DQIssue + DQResult → kernel.quality 子模块

Phase C: 复合类型 → app facade（需定义 Protocol）
  QualityEngine → app.process.quality Protocol
  DataSource → 已有 ditto_data.sources.base.DataSource ABC（保留不动，更新 importlinter）
  DataStoreSettings → app.config 重新导出
```

---

## 任务清单

### Phase A: P0 架构修复（顺序执行）

- [ ] Task 1: 纯类型提升到 kernel `[M]`
  - 将 `InstrumentIngestParams`（17行 frozen dataclass）、`MacroCategory`（21行 StrEnum）、`MacroFrequency`（15行 StrEnum）从 `ditto_data.models` 迁移到 `ditto_kernel`
  - 将 `IdentifierError` + `DataError` + `NoIdentifierProvidedError` + `AmbiguousTickerError` 从 `ditto_data.errors` 迁移到 `ditto_kernel.exceptions`
  - `ditto_data` 保留 re-export（`from ditto_kernel import InstrumentIngestParams`）以保持向后兼容
  - 更新 interfaces 中 5 个文件的 import 路径为 `from ditto_kernel import ...`
  - 验收: `pixi run -e dev check` 全通过；importlinter 通过；interfaces 零 `from ditto_data.models/errors` 导入（IdentifierError 系列和 InstrumentIngestParams/Macro*）
  - 文件:
    - `packages/kernel/src/ditto_kernel/types.py`（新建或扩展，放置 InstrumentIngestParams）
    - `packages/kernel/src/ditto_kernel/enums.py`（扩展，放置 MacroCategory/MacroFrequency）
    - `packages/kernel/src/ditto_kernel/exceptions.py`（新建，放置异常层级）
    - `packages/data/src/ditto_data/models/ingestion.py`（删除 InstrumentIngestParams，添加 re-export）
    - `packages/data/src/ditto_data/models/macro.py`（删除枚举，添加 re-export）
    - `packages/data/src/ditto_data/errors.py`（删除异常类，添加 re-export）
    - `interfaces/src/ditto_interfaces/cli/executor.py`（更新 import）
    - `interfaces/src/ditto_interfaces/jobs/flows/backfill.py`（更新 import）
    - `interfaces/src/ditto_interfaces/models/macro.py`（更新 import）
    - `interfaces/src/ditto_interfaces/api/utils/identifier.py`（更新 import）

- [ ] Task 2: Dataset 枚举 + DQ 值对象簇提升到 kernel `[L]`
  - **Dataset**: 将枚举成员定义提升到 `ditto_kernel.enums.Dataset`；`asset_class`/`date_schedule`/`supports_instrument_ingestion()`/`is_basic_dataset()`/`is_calendar_dataset()`/`get_asset_class()` 保留在 `ditto_data.models.common.Dataset`（继承 kernel 枚举并扩展方法）
  - **DQ 值对象簇**: 在 `ditto_kernel.quality` 新建子模块，提升 `DQLevel`、`DQSeverity`、`DQIssue`（10行）、`DQResult`（43行），合计约 75 行，零 polars 依赖
  - `ditto_data` 保留 re-export
  - 更新 interfaces 中 3 个文件的 import（t0_meta.py, dq_batch.py, daily.py 用 Dataset；dq_batch.py, monitoring.py 用 DQIssue/DQResult）
  - 验收: `pixi run -e dev check` 全通过；importlinter 通过；kernel 零外部依赖
  - 文件:
    - `packages/kernel/src/ditto_kernel/enums.py`（扩展 Dataset 枚举体）
    - `packages/kernel/src/ditto_kernel/quality.py`（新建，DQLevel/DQSeverity/DQIssue/DQResult）
    - `packages/data/src/ditto_data/models/common.py`（Dataset 继承 kernel 枚举，保留方法）
    - `packages/data/src/ditto_data/quality/spec.py`（DQIssue/DQResult 改为 re-export）
    - `packages/data/src/ditto_data/quality/severity.py`（DQLevel/DQSeverity 改为 re-export）
    - `packages/kernel/src/ditto_kernel/__init__.py`（更新 __all__）
    - interfaces 中 5 个文件（更新 import）

- [ ] Task 3: 复合类型通过 app facade 解耦 `[L]`
  - **QualityEngine**: 在 `ditto_app.process.quality` 中定义 `QualityEngineProtocol`（仅暴露 `check()` 签名），interfaces 的 `context.py` 改为依赖 Protocol
  - **DataSource**: 当前 `ditto_data.sources.base.DataSource` 已是 ABC（700行），interfaces 的 `source.py` 导入它是合理的（interfaces 允许依赖 data.sources）。更新 importlinter `interfaces-boundary` 合约的 allow_indirect_imports，或在合约中显式豁免 `data.sources.base.DataSource`
  - **DataStoreSettings**: 在 `ditto_app.config` 中添加 re-export `DataStoreSettings`，interfaces 的 `init.py` 改为从 `ditto_app.config` 导入
  - 验收: `pixi run -e dev check` 全通过；importlinter 全部合约通过；interfaces 零直接导入 `ditto_data.quality`/`ditto_data.config`（允许 data.sources）
  - 文件:
    - `packages/app/src/ditto_app/process/quality.py`（添加 QualityEngineProtocol）
    - `packages/app/src/ditto_app/config.py`（添加 DataStoreSettings re-export）
    - `interfaces/src/ditto_interfaces/jobs/context.py`（QualityEngine → Protocol）
    - `interfaces/src/ditto_interfaces/cli/commands/init.py`（DataStoreSettings → from ditto_app.config）
    - `.importlinter`（更新合约豁免）

### Phase B: P1 快速修复（可并行）

- [ ] Task 4: 死代码与空目录清理 `[S]`
  - 删除 `packages/data/src/ditto_data/query/` 空目录（含 `__pycache__`）
  - 清理 `scripts/analyze_slow_tests.py:66-86` 旧包名（`core` → `kernel`，`foundation` → `infra`，删除 `apps/port` 循环，添加 `interfaces`）
  - 清理 `.claude/settings.local.json` 中 `apps/port` 相关规则条目
  - 验收: `packages/data/src/ditto_data/query/` 目录不存在；analyze_slow_tests.py 无旧包名引用
  - 文件:
    - `packages/data/src/ditto_data/query/`（删除）
    - `scripts/analyze_slow_tests.py`
    - `.claude/settings.local.json`

- [ ] Task 5: 文档断链修复 `[M]`
  - `architecture.md:56` — 移除不存在的 `engine.md` 引用
  - `01_system_design.md:475` — 移除不存在的 `datahub.md` 行，替换为当前有效引用
  - `01_system_design.md` 全文 — 将 `apps/web/`、`datahub`、`core` 等旧引用更新为当前架构名称
  - 验收: 文档中无断链引用（不存在文件的链接）
  - 文件:
    - `.claude/rules/architecture.md`
    - `docs/design/01_system_design.md`

- [ ] Task 6: 嵌套深度重构 `[M]`
  - `list_date_inference.py:180-199` — 提取 `_find_earliest_trade_date(df) -> date | None` 方法，将 8 层嵌套降至 3 层
  - 考虑将 while 循环体提取为 `_search_earliest_date_in_batches(source_ticker, asset_class) -> date | None`
  - 验收: `_infer_list_date_for_instrument` 最大嵌套 ≤ 3 层；现有测试全部通过
  - 文件:
    - `packages/app/src/ditto_app/process/list_date_inference.py`

### Phase C: P2 质量改进（可并行）

- [ ] Task 7: PIT 改进 `[M]`
  - `derived_benchmark.py:172` — 为 `rolling_mean` 添加注释说明 PIT 安全机制（`shift(1)` 已消除 look-ahead）
  - `forward_return_service.py` — 添加环境检查装饰器 `@require_offline_context`，在非 testing/development 环境调用 `compute()` 时抛出 `RuntimeError`；或在 `compute()` 方法中检查 `ENVIRONMENT`，生产环境直接 raise
  - `data_feed.py:167` — 为 `_ensure_prev_close()` 添加 docstring 说明首日 `prev_close = close` 的边界行为
  - `docs/design/03_engine_design.md` — 在文档中的 rolling 示例添加 `WARNING: 以下为简化示例，实际使用时必须指定 closed="left" 或 shift(1)` 标注
  - 验收: forward_return_service 在生产环境调用时抛出异常（有测试覆盖）；文档示例有 PIT 警告
  - 文件:
    - `scripts/benchmarks/derived_benchmark.py`
    - `packages/app/src/ditto_app/query/forward_return_service.py`
    - `packages/engine/src/ditto_engine/backtest/data_feed.py`
    - `docs/design/03_engine_design.md`

- [ ] Task 8: 编码规约修复 `[S]`
  - `test_security_unit.py:144` — 将 `import json` + `json.dumps` 改为 `import orjson` + `orjson.dumps`
  - `quality.py:775` — 将 `TODO(TECH-DEBT)` 转化为 issue 跟踪（在代码中保留 TODO 但关联 issue 编号），或实现基础告警框架
  - 验收: 测试文件中零 `import json`；TECH-DEBT TODO 有明确的跟踪机制
  - 文件:
    - `packages/data/tests/unit/models/test_security_unit.py`
    - `packages/app/src/ditto_app/process/quality.py`

- [ ] Task 9: ingestion_coordinator.py 拆分 `[L]`
  - 当前 953 行，拆分为：
    - `ingestion_coordinator.py` — 核心编排（`ingest_date`、`ingest_range`、`ingest_by_instrument` + error handling），目标 ≤ 400 行
    - `_fetch_handlers.py` — 提取 `_fetch_data()` 和 `_fetch_by_dataset()` 的 Dataset→lambda 映射（消除重复）
    - `_commodity_fetcher.py` — 提取 `_fetch_commodity_daily()`（65 行 FRED/Tushare 双源逻辑）
  - 同时改善 `except Exception` 密度：在 `_try_fetch_data()` 和 `_try_fetch_data_by_instrument()` 中将 `except Exception` 收窄为具体异常类型（`httpx.NetworkError`、`httpx.TimeoutException`、`SourceFetchError`、`ValueError`）
  - 验收: `ingestion_coordinator.py` ≤ 500 行；`except Exception` 数量减少至 ≤ 5 处；现有测试全部通过
  - 文件:
    - `packages/app/src/ditto_app/process/ingestion_coordinator.py`（重构）
    - `packages/app/src/ditto_app/process/_fetch_handlers.py`（新建）
    - `packages/app/src/ditto_app/process/_commodity_fetcher.py`（新建）
    - `packages/app/tests/unit/process/ingestion/`（更新测试 import）

- [ ] Task 10: 薄弱测试补充 `[M]`
  - `test_research_facade_unit.py` — 补充边界情况断言（空输入、无效参数、返回值结构验证），目标 assert/test ratio ≥ 1.5
  - `test_coordinator_factory_unit.py` — 补充 `create_coordinator()` 的参数组合断言
  - `test_derived_query_facade_port_unit.py` — 补充 facade 委托调用的返回值验证
  - 验收: 三个文件的 assert/test ratio ≥ 1.5；新增测试覆盖边界情况
  - 文件:
    - `packages/app/tests/unit/query/test_research_facade_unit.py`
    - `packages/app/tests/unit/process/ingestion/test_coordinator_factory_unit.py`
    - `packages/app/tests/unit/process/derived/test_derived_query_facade_port_unit.py`

- [ ] Task 11: Sprint 文档与辅助文档清理 `[M]`
  - `docs/sprints/backlog.md` — 将 6 处 `[datahub]` 标签更新为 `[data]`
  - `docs/sprints/README.md` — 更新提交前缀示例（`datahub` → `data`）、分支名示例（`feat/datahub-facade` → `feat/data-facade`）、更新 sprint 引用
  - `.factory/commands/ditto-architecture-audit.md` — 更新审计范围描述为当前 6 包 + 1 接口层架构
  - `.claude/rules/core.md` → 重命名为 `.claude/rules/python.md`，并更新 CLAUDE.md、AGENTS.md、noqa-ignore.md、configuration.md 中的引用
  - 验收: Sprint 文档中零 `[datahub]` 标签；`core.md` 文件不存在（已重命名）；所有引用链接有效
  - 文件:
    - `docs/sprints/backlog.md`
    - `docs/sprints/README.md`
    - `.factory/commands/ditto-architecture-audit.md`
    - `.claude/rules/core.md` → `.claude/rules/python.md`（重命名）
    - `CLAUDE.md`
    - `AGENTS.md`
    - `.claude/rules/noqa-ignore.md`
    - `docs/configuration.md`

- [ ] Task 12: 过时注释与 5 层嵌套函数改善 `[S]`
  - `order_book.py:1-6` — 更新 docstring，移除 Phase 0 / Part 2 引用
  - `execution/__init__.py:3-5`、`alpha/__init__.py:4` — 移除 Phase 0 / Phase 2 注释
  - `errors.py:10` — 将 "Core re-exports" 更新为 "Engine re-exports"
  - `errors.py:339-342` — 移除 ditto_interfaces.errors 迁移历史注释
  - 5 层嵌套函数（`comparison.py:104`、`golden.py:99`、`validation.py:15`）— 通过 early-return 模式改善，目标嵌套 ≤ 4 层
  - `coordinator_factory.py:125-137` — 移除未被外部消费的 re-export（EXCHANGE_PREFIX_MAP 除外，auto_init.py 直接导入）
  - 验收: 源码中零 Phase 0/Part 2/Core 引用；5 层嵌套函数降至 ≤ 4 层
  - 文件:
    - `packages/engine/src/ditto_engine/accounting/order_book.py`
    - `packages/engine/src/ditto_engine/execution/__init__.py`
    - `packages/engine/src/ditto_engine/alpha/__init__.py`
    - `packages/data/src/ditto_data/errors.py`
    - `packages/engine/src/ditto_engine/portfolio/comparison.py`
    - `packages/data/src/ditto_data/quality/golden.py`
    - `packages/engine/src/ditto_engine/alpha/validation.py`
    - `packages/app/src/ditto_app/process/coordinator_factory.py`

---

## 执行顺序

```
Phase A (顺序):  Task 1 → Task 2 → Task 3
                  架构迁移有依赖关系，必须顺序

Phase B (并行):  Task 4 ─┐
                  Task 5 ─┤  P1 快速修复，互不依赖
                  Task 6 ─┘

Phase C (并行):  Task 7  ─┐
                  Task 8  ─┤
                  Task 9  ─┤  P2 质量改进，互不依赖
                  Task 10 ─┤
                  Task 11 ─┤
                  Task 12 ─┘

Phase A 完成后 → 运行 `pixi run -e dev check` 全量验证
Phase B 完成后 → 运行 `pixi run -e dev check` 全量验证
Phase C 完成后 → 运行 `pixi run -e dev check` + `pixi run -e dev arch-check` 最终验证
```

## 总估算

| Phase | 任务数 | 复杂度 | 涉及文件 |
|-------|--------|--------|----------|
| A (P0) | 3 | M + L + L | ~25 个文件 |
| B (P1) | 3 | S + M + M | ~10 个文件 |
| C (P2) | 6 | S~L | ~25 个文件 |
| **合计** | **12** | | **~60 个文件** |
