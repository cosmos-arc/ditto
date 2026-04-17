# V1 Sprint Final Fix Plan

## 概述

- **Sprint**: V1 Sprint | **Phase**: Final Review Fix
- **创建**: 2026-04-13
- **范围**: feat/v1-sprint 分支合并前最终修复
- **来源**: 6 维度并行代码审查 + 手动深度审查

## 问题总览

| 优先级 | 数量 | 说明 |
|--------|------|------|
| **P1 Critical** | 4 | 阻塞合并的功能性缺陷 |
| **HIGH** | 7 | 必须修复的质量/正确性问题 |
| **MEDIUM** | 12 | 建议修复的改进项 |
| **LOW** | 6 | 可选优化 |
| **误报** | 4 | TYPE_CHECKING(5处)、MomentumIndicator、部分成交、warm-up |

### 误报说明

| # | 原始发现 | 排除原因 |
|---|---------|---------|
| E1 | TYPE_CHECKING 5 处违规 | 全部是标准 Python 用法，`from __future__ import annotations` 已启用，仅用于类型注解 |
| E2 | MomentumIndicator 前瞻风险 | 标准动量计算，前瞻取决于调用方传入的 frame，非 indicator 本身缺陷 |
| E3 | 部分成交状态只看本次 | 代码库使用 all-or-nothing fill 模型，不存在部分成交状态 |
| E4 | execution_delay warm-up 日被当失败 | PlanningStep 返回 `skipped()` (success=True)，主循环正确处理为 skipped |

---

## Phase 1: Critical Bug Fixes (P1 — 阻塞合并)

> **目标**: 修复 4 个会导致运行时崩溃或数据错误的 P1 缺陷

### F1: 修复 artifact file_path 读写契约不一致 `[L]`

**问题**: 写入侧保存具体文件路径 `/.../run_id/backtest_report.json`，读取侧当目录拼接 `backtest_report.json/nav.parquet/manifest.json`，导致所有 artifact 查询静默返回 None。

**修复方案**: 统一契约 — `file_path` 存储的是 **artifact 目录**（run_id 对应的输出目录），写入时保存 `output_dir`，读取时按目录 + 文件名拼接。

**文件**:
- `packages/app/src/ditto_app/process/execution/backtest_process.py:474` — 改存 `output_dir` 而非 `written["backtest_report"]`
- `packages/app/src/ditto_app/query/backtest.py:180,193` — 已按目录拼接，无需改动
- `packages/app/src/ditto_app/query/backtest_trade.py:94` — 已按目录拼接，无需改动
- `packages/app/src/ditto_app/process/execution/replay_process.py:137` — 已按目录拼接，无需改动

**验收**:
- [x] 写入后 `record.file_path` 是目录路径
- [x] `get_report()`, `get_nav_series()`, `get_trades()` 正确读取 artifact
- [x] replay 正确加载 manifest 和 report
- [x] 单元测试覆盖写读一致性

---

### F2: 修复 strategy_run 旧库迁移缺 parent_run_id `[M]`

**问题**: `_MIGRATIONS` 只补 `progress_pct/config` 等列，不补 `parent_run_id`。`init_schema()` 在迁移前创建索引 `idx_strategy_run_parent_run_id`，从旧库升级直接 "no such column"。

**修复方案**: 在 `_MIGRATIONS` 中增加 `parent_run_id` 列迁移，并调整 `init_schema()` 的执行顺序 — 先迁移再建索引。

**文件**:
- `packages/data/src/ditto_data/storage/metadata/strategy_run_store.py:63-84` — 在 `_MIGRATIONS` 中添加 `parent_run_id TEXT NOT NULL DEFAULT ''`
- `packages/data/src/ditto_data/storage/metadata/strategy_run_store.py:200-214` — Writer `init_schema()` 调整为: `CREATE TABLE IF NOT EXISTS` → `_run_migrations()` → `CREATE INDEX`
- `packages/data/src/ditto_data/storage/metadata/strategy_run_store.py:318-332` — Reader `init_schema()` 同步调整
- `packages/data/tests/unit/metadata/test_strategy_run_store_unit.py:291` — 修复 "旧 schema" DDL，移除 `parent_run_id` 和 `config_json` 以覆盖真实旧库

**验收**:
- [x] 从不含 `parent_run_id` 的旧表升级成功
- [x] 索引 `idx_strategy_run_parent_run_id` 正确创建
- [x] 测试覆盖: 旧 schema → 迁移 → 新列可用
- [x] `pixi run -e dev check` 通过

---

### F3: 修复 replay report 序列化/反序列化 schema 不匹配 `[L]`

**问题**: 序列化写出的 `period` 是 list `["start", "end"]`，replay 按 dict 读 `.get("start")` 直接 crash。`rebalance_freq` 和 `nav_series` 未写入 JSON，replay 静默退化为 daily + final_nav。

**修复方案**: 对齐两侧契约。

**方案 A (推荐)**: 修改序列化侧，写出符合反序列化期望的格式：
- `period` → `{"start": ..., "end": ...}` (dict)
- 添加 `rebalance_freq` 字段
- 添加 `nav_series` 字段 (从 Parquet 数据同步)

**方案 B**: 修改反序列化侧适配当前序列化格式。

**文件**:
- `packages/app/src/ditto_app/process/execution/backtest_serialization.py:37-44` — 修改 `period` 为 dict，添加 `rebalance_freq` 和 `nav_series`
- `packages/app/tests/unit/process/execution/test_replay_process_unit.py:69` — 测试 fixture 已匹配新格式，无需改动
- `packages/engine/tests/integration/backtest/test_reproducibility.py` — 验证端到端 replay

**验收**:
- [x] 序列化 JSON 包含 `period: {start, end}`, `rebalance_freq`, `nav_series`
- [x] replay 正确解析 period、freq、nav_series
- [x] 端到端 replay 验证通过
- [x] `pixi run -e dev check` 通过

---

### F4: 修复 Universe PUT 端点 `[M]`

**问题**: PUT `/universes/{id}` 调用 `create_universe()` 做 INSERT，对已有 universe 必崩 IntegrityError (500)。缺少 preset 不可修改守卫。请求模型缺少成员列表和 effective date。

**修复方案**:
1. `UniverseWriter` 添加 `update_metadata(universe_id, name, description)` 方法 (UPDATE SQL)
2. `MetadataService` 添加 `update_universe()` 委托
3. `UpdateCustomUniverseHandler` 调用 `update_universe()` + preset 守卫
4. `UpdateUniverseRequest` 扩展可选 `members` 字段 + effective_date
5. 成员更新走 `replace_constituents()` + version 递增

**文件**:
- `packages/data/src/ditto_data/storage/metadata/universe/universe_writer.py` — 添加 `update_metadata()` 方法
- `packages/data/src/ditto_data/services/metadata_service.py` — 添加 `update_universe()`
- `packages/app/src/ditto_app/command/universe.py:71-91` — 改用 `update_universe()` + preset guard
- `interfaces/src/ditto_interfaces/models/universe.py:40-46` — 扩展 `UpdateUniverseRequest`
- `interfaces/src/ditto_interfaces/api/routes/universe.py:91-108` — 传递 members

**验收**:
- [x] PUT 已有 universe 返回 200 (而非 500)
- [x] PUT preset universe 返回 403
- [x] PUT 带 members 时触发 `replace_constituents()` + version 递增
- [x] 单元测试覆盖: update / preset guard / members update
- [x] `pixi run -e dev check` 通过

---

## Phase 2: High Priority Fixes (HIGH — 合并前必须)

> **目标**: 修复影响正确性和可维护性的 HIGH 级问题

### F5: 默认费率模型改为 AShareFeeModel `[S]`

**问题**: `SimpleFeeModel` 只算佣金，缺少印花税 (sell 0.05%) 和过户费。默认回测低估交易成本。

**修复**: `service_factory.py:145` 和 `brokerage.py:28` 的默认从 `SimpleFeeModel()` 改为 `AShareFeeModel()`。

**文件**:
- `packages/app/src/ditto_app/builders/service_factory.py:145`
- `packages/engine/src/ditto_engine/execution/reality/brokerage.py:28`

**验收**:
- [x] 无显式 fee_model 时默认使用 AShareFeeModel
- [x] 现有测试中 `SimpleFeeModel` 引用更新
- [x] `pixi run -e dev check` 通过

---

### F6: 硬编码日期范围外部化 `[M]`

**问题**: `providers.py:599` 硬编码 `"2020-01-01" ~ "2030-12-31"`，2031 年后静默失效。

**修复**: 从配置读取日期范围，或改为懒加载/按需扩展。

**文件**:
- `packages/app/src/ditto_app/providers.py:599` — 从 settings 读取或改为按需加载
- `interfaces/src/ditto_interfaces/jobs/flows/deploy.py:144-145` — backfill 日期范围配置化

**验收**:
- [x] 日期范围来自配置文件或环境变量
- [x] 超出范围时有明确错误提示而非静默失败
- [x] `pixi run -e dev check` 通过

---

### F7: 修复 on_failure 丢失异常信息 `[S]`

**问题**: `backtest.py:151-154` 中 `on_failure(run_id, "Flow execution failed")` 丢失实际异常信息。

**修复**: 改为 `except Exception as exc:` + `on_failure(run_id, str(exc))`。

**文件**:
- `interfaces/src/ditto_interfaces/api/routes/backtest.py:150-154`

**验收**:
- [x] on_failure 回调包含异常类型和消息
- [x] `pixi run -e dev check` 通过

---

### F8: 提取共享 _build_input_bundle `[M]`

**问题**: `engine.py:457-497` 和 `strategy.py:64-107` 近乎相同的 `StrategyInputBundle` 构建逻辑，无共享真值源。

**修复**: 提取为 `ditto_engine.backtest.steps._input_bundle.build_default_input_bundle(date, strategy_id, run_id, slice_, benchmark_close)`。

**文件**:
- `packages/engine/src/ditto_engine/backtest/steps/_input_bundle.py` — 新建，提取共享函数
- `packages/engine/src/ditto_engine/backtest/engine.py:457-497` — 改为调用共享函数
- `packages/engine/src/ditto_engine/backtest/steps/strategy.py:64-107` — 改为调用共享函数
- `packages/engine/src/ditto_engine/backtest/steps/__init__.py` — 导出

**验收**:
- [x] 两处逻辑合并为单一实现
- [x] 现有 engine 和 strategy step 测试通过
- [x] `pixi run -e dev check` 通过

---

### F9: 拆分 EngineLoop.run() `[M]`

**问题**: `EngineLoop.run()` 91 行，混合 run_id 解析、交易日过滤、主循环、进度跟踪、manifest 构建、结果组装。

**修复**: 提取 `_build_manifest()` 和 `_assemble_result()` 方法。

**文件**:
- `packages/engine/src/ditto_engine/backtest/engine.py:363-453`

**验收**:
- [x] `run()` 方法 ≤ 40 行
- [x] 提取的方法有清晰职责
- [x] 现有测试全部通过
- [x] `pixi run -e dev check` 通过

---

### F10: 修复 factor-aware 路径 run_id 不一致 `[S]`

**问题**: `backtest_process.py` 中 `run()` 和 `_build_factor_aware_bundle_builder()` 各自独立生成 `run_id`，导致 `StrategyInputBundle.run_id` 与 run record 不一致。

**修复**: `_build_factor_aware_bundle_builder()` 接受已解析的 `run_id` 参数，不再本地生成。

**文件**:
- `packages/app/src/ditto_app/process/execution/backtest_process.py:331,391` — 改为参数传入

**验收**:
- [x] factor-aware 回测的 bundle.run_id 与 run record 一致
- [x] `pixi run -e dev check` 通过

---

### F11: 修复 Regime threshold 契约不一致 `[S]`

**问题**: 文档说 threshold × 100 后比较，代码直接比较 0-1 raw_score。用户若按文档设 `bull_threshold=70.0` 将永远无法进入 BULL。

**修复**: 修正 `RegimeConfig` docstring 为实际行为（0-1 直接比较），并在 `_spec_deserializer.py` 中添加 `[0, 1]` 范围校验。

**文件**:
- `packages/engine/src/ditto_engine/alpha/builtins/regime.py:104-105` — 修正 docstring
- `packages/app/src/ditto_app/builders/_spec_deserializer.py:90-94` — 添加范围校验

**验收**:
- [x] docstring 描述与实际行为一致
- [x] 超出 [0, 1] 的 threshold 值抛出 ValueError
- [x] `pixi run -e dev check` 通过

---

## Phase 3: Medium Priority Improvements

> **目标**: 提升代码质量和文档完整性

### F12: 添加 GET /runs/{id}/report 端点 `[S]`

**问题**: Sprint plan 要求的 report 端点未暴露，app facade 已有 `get_report()`。

**文件**:
- `interfaces/src/ditto_interfaces/api/routes/backtest.py` — 添加 `GET /runs/{run_id}/report`
- `interfaces/tests/unit/api/routes/test_backtest_trigger_unit.py` — 添加测试

**验收**: 端点返回 JSON report 或 404

---

### F13: 拆分 _build_factor_aware_bundle_builder 闭包 `[M]`

**问题**: 59 行嵌套闭包，4 层逻辑，难以测试。

**修复**: 提取为独立方法 `_build_factor_bundle(run_id, date, slice_, spec, expressions)`。

**文件**:
- `packages/app/src/ditto_app/process/execution/backtest_process.py:340-399`

---

### F14: 代码质量批量修复 `[M]`

| # | 文件 | 修复内容 |
|---|------|---------|
| a | `trade.py:19` | 移除无效 `# noqa: RUF100` |
| b | `backtest.py:150` | `# type: ignore` 添加原因注释 |
| c | `backtest.py:171,181` | `# type: ignore` 添加原因注释 |
| d | `signal_snapshot.py:69` | `# type: ignore` 添加原因注释 |
| e | `config.py:34` | `IngestionCoordinatorConfig` 添加 `frozen=True` 或注释 |
| f | `runtime_builder.py` | 添加 `from __future__ import annotations` |
| g | `backtest_process.py` | 添加 `from __future__ import annotations` |
| h | `metadata_service.py` | 添加 `from __future__ import annotations` |

---

### F15: SQL/init_schema 重复消除 `[S]`

**问题**: `SQLiteStrategyRunReader` 和 `SQLiteStrategyRunWriter` 的 `init_schema()` 完全相同。

**修复**: 提取为模块级 `_init_schema(conn)` 函数。

**文件**:
- `packages/data/src/ditto_data/storage/metadata/strategy_run_store.py`

---

### F16: TradeService WHERE 子句构建去重 `[S]`

**问题**: `list_intents()`, `list_fills()`, `list_positions()` 重复 WHERE 构建模式。

**修复**: 提取 `_build_where_clause(filters, order_by)` 辅助函数。

**文件**:
- `packages/data/src/ditto_data/services/trade_service.py`

---

### F17: _compute_total_return 去重 `[S]`

**问题**: `backtest.py` flow 和 `comparison.py` 各自实现相同计算。

**修复**: 提取到共享位置（如 `ditto_app.query._artifact_utils`）。

**文件**:
- `interfaces/src/ditto_interfaces/jobs/flows/backtest.py:176-180`
- `packages/app/src/ditto_app/query/comparison.py:257-265`
- `packages/app/src/ditto_app/query/_artifact_utils.py` — 新建或扩展

---

### F18: 测试 helper 去重 `[M]`

**问题**: `_make_fill` 在 7 个测试文件独立定义，`_make_record` 在 5 个文件重复。

**修复**: 提取到包级 `conftest.py`。

**文件**:
- `packages/engine/tests/unit/backtest/conftest.py` — engine 层共享
- `packages/app/tests/unit/process/execution/conftest.py` — app 层共享
- `packages/data/tests/unit/services/conftest.py` — data 层共享

---

### F19: 文档更新 `[M]`

| # | 内容 | 文件 |
|---|------|------|
| a | README "核心功能" 补充 R1 Regime、R2 FactorBridge、R5 Universe API、R6 CostConfig | `README.md` |
| b | 更新测试计数 4353 → 5138 | `README.md:253` |
| c | 添加 V1 Enhancement 变更记录 | `README.md` |
| d | Regime threshold 文档修正 | `docs/plans/2026-04-11-v1-enhancement-design.md` |
| e | 计划文档添加 "Superseded by" 状态标记 | `docs/plans/2026-04-12-*.md` |

---

### F20: Error handling 改进 `[S]`

| # | 文件 | 修复 |
|---|------|------|
| a | `backtest.py:151` | `except Exception:` → `except Exception as exc:` + `on_failure(run_id, str(exc))` |
| b | `comparison.py:205-206` | 静默返回零 → 添加 logger.warning |
| c | `backtest.py:241-243` | 字符串匹配判错 → 统一使用 `_map_error()` 模式 |

---

### F21: cancel_run error discrimination 统一 `[S]`

**问题**: `backtest.py:241-243` 用字符串匹配 `"not found"` 区分 404/409，`trade.py` 用 `_map_trade_error()` 更规范。

**修复**: 提取共享 `_map_backtest_error()` 函数，统一错误映射。

**文件**:
- `interfaces/src/ditto_interfaces/api/routes/backtest.py`

---

### F22: backtest_process exception lifecycle 提取 `[S]`

**问题**: `mark_failed + raise` 模式在 3 处重复。

**修复**: 提取为 context manager 或 decorator。

**文件**:
- `packages/app/src/ditto_app/process/execution/backtest_process.py`
- `packages/app/src/ditto_app/process/execution/strategy_run_process.py`
- `interfaces/src/ditto_interfaces/jobs/flows/backtest.py`

---

### F23: TODO(R3) 从 docstring 移到函数上方 `[S]`

**文件**: `interfaces/src/ditto_interfaces/api/routes/backtest.py:137`

---

## Phase 4: Structural Improvements (可延后)

> **目标**: 架构级改进，可在后续 Sprint 处理

### F24: MetadataService 拆分 `[L]`

**问题**: 41 方法 + 18 构造参数的 God class。

**建议**: 拆为 `CalendarFacade`, `InstrumentFacade`, `UniverseFacade`，DI 层组合。需评估对现有测试的影响。

---

### F25: RuntimeProvider 拆分 `[L]`

**问题**: 48 个 `@provide` 方法，474 行。

**建议**: 拆为 `RuntimeInfraProvider`, `RuntimeStorageProvider`, `RuntimeServiceProvider`。

---

### F26: IngestionCoordinator 简化 `[L]`

**问题**: 725 行，三种摄取模式有重复错误处理。

**建议**: 提取共享 `_execute_with_hooks()` 消除重复。

---

### F27: Prefect Worker 异步执行 `[XL]`

**问题**: 设计要求 V1 实现 Worker 独立进程异步执行，当前为进程内 fallback。

**建议**: 评估是否延至 V1.1。如 V1 必须实现，需: Prefect Client 提交、Worker 配置、环境切换机制。

---

### F28: dict[str, Any] 类型强化 `[L]`

**问题**: `comparison.py` 和 `replay_process.py` 大量使用 `dict[str, Any]` 传递 report/manifest 数据。

**建议**: 定义 `BacktestReportPayload` 和 `RunManifestPayload` TypedDict 或 dataclass。

---

## 执行顺序

```
Phase 1 (P1 — 阻塞合并)
  F1 artifact file_path ─┐
  F2 strategy_run 迁移  ─┼── 可并行
  F3 replay schema      ─┤
  F4 Universe PUT       ─┘
         │
         ▼
Phase 2 (HIGH — 合并前)
  F5 默认费率模型        ─┐
  F6 硬编码日期          ─┼── 可并行
  F7 on_failure 异常     ─┤
  F8 _build_input_bundle ─┤
  F9 EngineLoop 拆分     ─┤
  F10 run_id 不一致      ─┤
  F11 Regime threshold   ─┘
         │
         ▼
Phase 3 (MEDIUM — 建议修复)
  F12-F23 ── 可并行
         │
         ▼
Phase 4 (Structural — 延后)
  F24-F28 ── 后续 Sprint
```

## 风险评估

| Phase | 风险 | 缓解 |
|-------|------|------|
| Phase 1 | Schema 变更影响现有数据 | F2 添加迁移测试；F1 影响新数据不影响旧数据 |
| Phase 1 | 序列化格式变更不兼容 | F3 同时更新写入和读取侧 |
| Phase 2 | 默认费率变更影响回测结果 | AShareFeeModel 更准确，预期结果变化是正确的 |
| Phase 3 | 低风险，增量改进 | 每个 task 独立验证 |
