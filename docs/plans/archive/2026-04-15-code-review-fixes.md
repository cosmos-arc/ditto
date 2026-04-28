# Code Review 审查修复计划

## 概述
- Sprint: V1 RC Closeout
- 创建: 2026-04-15
- 来源: `/ditto-review` 6 维度并行审查

## 审查结果摘要

| 维度 | Critical | Important | Suggestion |
|------|----------|-----------|------------|
| 架构 | 0 | 0 | 0 |
| PIT | 0 | 0 | 0 |
| 规约 | 0 | 2 | 10 |
| 可维护 | 1 | 6 | 7 |
| 质量 | 0 | 0 | 2 |
| 文档 | 0 | 3 | 3 |

---

## Phase 1: Critical + 文档速修 (合并前)

### Task 1.1: 拆分 `_evaluate_impl` 181 行超长函数 `[L]`
- **来源**: C-1 (Critical) + I-1 规约 Important
- **文件**: `packages/analytics/src/ditto_analytics/evaluation/evaluator.py`
- **方案**: 将 `_evaluate_impl` 拆分为 4 个私有方法：
  1. `_compute_ic_metrics()` — Rank IC + Pearson IC + IC decay + autocorrelation + turnover IR + GK IR
  2. `_compute_quantile_metrics()` — Quantile returns + Long-Short + annual returns + net returns
  3. `_compute_optional_analysis()` — Fama-MacBeth + factor exposure + regime IC + performance attribution
  4. `_assemble_report()` — 组装 FactorEvaluationReport
- **验收**: 每个方法 ≤ 60 行；`_evaluate_impl` 缩减为 ~30 行编排代码；现有测试全部通过
- **测试**: `packages/analytics/tests/unit/evaluation/test_evaluator_unit.py` 已覆盖，确保回归

### Task 1.2: README Phase 3 状态更新 `[S]`
- **来源**: D-1 (Important)
- **文件**: `README.md:213`
- **方案**: 将 `V1 Sprint Phase 3 — Run Lineage / Replayability（规划中）` 改为 `(done)`
- **验收**: README 中 Phase 3 标记为 done

### Task 1.3: dq-summary docstring 更新 `[S]`
- **来源**: D-5 (Suggestion)
- **文件**: `interfaces/src/ditto_interfaces/api/routes/ingestion.py:99-102`
- **方案**: 更新 docstring，移除"Sprint 5 接入"引用，标注为 V1 占位
- **验收**: docstring 反映当前状态，不包含过期引用

---

## Phase 2: 代码质量改善

### Task 2.1: 提取通用 `raise_business_error()` 函数 `[M]`
- **来源**: I-3 (Important)
- **文件**:
  - `interfaces/src/ditto_interfaces/api/errors.py` — 新增函数
  - `interfaces/src/ditto_interfaces/api/routes/backtest.py:78` — 删除 `_raise_backtest_error`
  - `interfaces/src/ditto_interfaces/api/routes/trade.py:62` — 删除 `_raise_trade_error`
  - `interfaces/src/ditto_interfaces/api/routes/strategy.py:47` — 删除 `_raise_strategy_error`
- **方案**: 在 `errors.py` 中新增：
  ```python
  def raise_business_error(exc: ValueError, *, conflict_keywords: tuple[str, ...] = ()) -> Never:
      """将业务 ValueError 映射为 APIError 并抛出."""
      msg = str(exc)
      msg_lower = msg.lower()
      if "not found" in msg_lower:
          raise NotFoundError(msg) from exc
      if any(kw in msg_lower for kw in conflict_keywords):
          raise ConflictError(msg) from exc
      raise BadRequestError(msg) from exc
  ```
  - backtest: `raise_business_error(exc)` (默认 conflict_keywords 含 "transition")
  - trade: `raise_business_error(exc, conflict_keywords=("transition",))`
  - strategy: `raise_business_error(exc, conflict_keywords=("conflict",))`
- **验收**: 3 处重复消除；现有测试通过
- **测试**: `interfaces/tests/unit/api/test_errors_unit.py` + 各路由测试

### Task 2.2: 拆分 `_execute_backtest` 104 行函数 `[M]`
- **来源**: I-1 (Important)
- **文件**: `packages/app/src/ditto_app/process/execution/backtest_process.py:217`
- **方案**: 提取 3 个私有方法：
  1. `_build_engine_config()` — 构建 EngineConfig (行 222-236)
  2. `_build_engine_options()` — 构建 EngineOptions 含 clock/event_bus/cancel/progress (行 238-290)
  3. `_post_process()` — 持久化审计/产物 + 更新状态 (行 304-320)
- **验收**: `_execute_backtest` 缩减为 ~30 行；现有测试通过
- **测试**: `packages/app/tests/unit/process/strategy/test_backtest_service_unit.py`

### Task 2.3: 简化 `_submit_flow` / `_run_in_process` 间接层 `[S]`
- **来源**: S-1 (Suggestion)
- **文件**: `interfaces/src/ditto_interfaces/api/routes/backtest.py:160-191`
- **方案**: 合并 `_submit_flow` 和 `_run_in_process` 为单一 `_run_backtest_flow()` 函数
- **验收**: 消除不必要的间接层；现有测试通过
- **测试**: `interfaces/tests/unit/api/routes/test_backtest_trigger_unit.py`

### Task 2.4: 降低 `coordinator.py` 嵌套深度 (6→3) `[M]`
- **来源**: 规约 Important
- **文件**: `packages/app/src/ditto_app/process/ingestion/coordinator.py:~444`
- **方案**: 在 `_run_post_ingest_hooks` 中使用 early return 提前返回正常路径
- **验收**: 最大嵌套 ≤ 3 层；现有测试通过
- **测试**: `packages/app/tests/unit/process/ingestion/test_range_process_unit.py`

### Task 2.5: 降低 `runtime_builder.py` 嵌套深度 (6→3) `[M]`
- **来源**: 规约 Important
- **文件**: `packages/app/src/ditto_app/builders/runtime_builder.py:~168`
- **方案**: 将 `_deserialize_constraint` / `_deserialize_param_constraint` 中的深层嵌套通过提取局部变量或辅助方法简化
- **验收**: 最大嵌套 ≤ 3 层；现有测试通过
- **测试**: `packages/app/tests/unit/process/strategy/test_runtime_builder_unit.py`

---

## Phase 3: 文档完善

### Task 3.1: 补充 CLAUDE.md API 路由分组表 `[M]`
- **来源**: D-2 (Important)
- **文件**: `interfaces/CLAUDE.md:131-136`
- **方案**: 补充完整的 14 个路由模块到路由分组表
- **验收**: 表格覆盖所有已注册路由模块

### Task 3.2: 响应模型添加 Field description `[M]`
- **来源**: D-4 (Suggestion)
- **文件**:
  - `interfaces/src/ditto_interfaces/models/trade.py` — TradeIntentResponse, FillResponse, PositionSnapshotResponse, PnlSummaryResponse, ComparisonMetricsResponse
  - `interfaces/src/ditto_interfaces/models/lineage.py` — ManifestDiffResponse, ReplayResponse
  - `interfaces/src/ditto_interfaces/models/backtest.py` — RunResponse, TradeResponse, AuditRecordResponse, BenchmarkNavResponse
- **方案**: 为响应模型关键字段添加 `Field(description=...)`，特别是 ComparisonMetricsResponse 的 12 个指标（含单位说明如 bps、%）
- **验收**: OpenAPI 文档中响应字段有描述

### Task 3.3: Sprint 5 补充计划文档 `[S]`
- **来源**: D-3 (Important)
- **文件**: `docs/plans/` — 新建
- **方案**: 基于 commit `914713c1` 的变更，补充 Sprint 5 实施计划（交易 API 分页 + 成交幂等 + 偏差报告 + CORS 配置）
- **验收**: 文档包含功能列表、验收标准、实现状态

---

## Phase 4: 可维护性改善（后续迭代）

### Task 4.1: `RuntimeProvider` 按子域拆分 `[L]`
- **来源**: I-5 (Important)
- **文件**: `packages/data/src/ditto_data/di/runtime.py`
- **方案**: 按 Storage/Service/ReaderWriter 拆分为多个 Provider
- **注意**: DI Provider 是 Composition Root 模式，当前可接受。此项为长期优化。
- **验收**: 每个 Provider ≤ 20 个方法；DI 容器正常工作

### Task 4.2: `MetadataService.__init__` 参数精简 `[M]`
- **来源**: I-6 (Important)
- **文件**: `packages/data/src/ditto_data/services/metadata_service.py:67`
- **方案**: 引入子服务 Facade/Builder 减少 17 个构造参数
- **注意**: 当前保留参数以保证 DI 和测试兼容性，长期优化。
- **验收**: 构造参数 ≤ 8 个；向后兼容

### Task 4.3: `to_*_response` 映射统一模式评估 `[S]`
- **来源**: I-4 (Important)
- **方案**: 评估 Pydantic `from_attributes=True` 或 `model_validate()` 是否能减少样板
- **注意**: 当前 DTO 和 Response 字段名/类型不完全一致，需谨慎评估。此项为可选优化。

---

## 执行顺序

```
Phase 1 (合并前):
  1.1 拆分 _evaluate_impl ─┐
  1.2 README 更新 ──────────┼── 可并行
  1.3 docstring 更新 ───────┘
         │
         ▼
Phase 2 (代码质量):
  2.1 raise_business_error ─┐
  2.2 _execute_backtest ────┼── 可并行
  2.3 _submit_flow ─────────┤
  2.4 coordinator 嵌套 ─────┤
  2.5 runtime_builder 嵌套 ─┘
         │
         ▼
Phase 3 (文档):
  3.1 CLAUDE.md 路由表 ──┐
  3.2 Field description ──┼── 可并行
  3.3 Sprint 5 文档 ──────┘
         │
         ▼
Phase 4 (后续迭代):
  4.1 RuntimeProvider 拆分
  4.2 MetadataService 精简
  4.3 to_*_response 评估
```

---

## Phase 5: GitHub PR #62 Code Review 修复 (8 issues, score >= 25)

> 来源: GitHub PR #62 5 维度并行审查 (CLAUDE.md 合规 / Bug 扫描 / Git 历史 / 历史 PR 评论 / 代码注释合规)

### Task 5.1: TOCTOU 竞态 — `update_intent_status` SQL 缺状态前置条件 `[H]`
- **评分**: 85/100
- **来源**: Git 历史审查 + Bug 扫描
- **文件**: `packages/data/src/ditto_data/services/trade_service.py:66`
- **问题**: `_UPDATE_INTENT_STATUS = "UPDATE trade_intents SET status = ? WHERE intent_id = ?"` 无状态前置条件。R5 修复 (commit 6763d86) 在 `strategy_run_store.py` 添加了 `WHERE status NOT IN ('cancelled', 'completed', 'failed')` 消除 TOCTOU 竞态，但 `trade_service.py` 被遗漏。两个并发 API 请求可能同时通过应用层状态转换校验并覆盖彼此的写入。
- **方案**:
  1. 将 `_UPDATE_INTENT_STATUS` 拆为两个 SQL：`_UPDATE_INTENT_STATUS_TRANSITION` (带 `AND status IN (...)` 前置条件) 和 `_UPDATE_INTENT_STATUS_DIRECT` (无前置条件，仅用于幂等更新)
  2. `update_intent_status` 方法增加 `expected_current: tuple[str, ...] | None` 参数，传入时使用带前置条件的 SQL 并检查 `cursor.rowcount`
  3. `RecordFillHandler` 和 `UpdateIntentStatusHandler` 调用时传入预期的当前状态集合
- **验收**: 并发测试中状态转换不会被覆盖；现有测试通过
- **测试**: `packages/data/tests/unit/services/test_trade_service_unit.py` — 新增 `test_update_status_with_transition_guard` + `test_update_status_conflicting_transition_raises`

### Task 5.2: `ComparisonQueryFacade` DI 未注入 `market_facade` `[H]`
- **评分**: 90/100
- **来源**: Git 历史审查
- **文件**: `packages/app/src/ditto_app/providers.py:499-508`
- **问题**: T11 修复 (commit 9eb2195) 添加了 `_build_actual_navs_full` 实现使用 `MarketQueryFacade` 注入真实收盘价重建 NAV，但 DI provider 从未注入 `market_facade`，导致完整实现成为死代码。对比端点始终走 `_build_actual_navs_simple`（仅扣手续费），产生误导性的 NAV 相关性、最大偏差、跟踪误差等指标。
- **方案**: 在 `comparison_query_facade` provider 方法中添加 `market_facade: MarketQueryFacade` 参数并传入构造函数
- **验收**: `ComparisonQueryFacade` 接收到 `market_facade`；对比端点使用完整 NAV 重建
- **测试**: `packages/app/tests/unit/query/test_comparison_unit.py` — 验证 DI 注入正确

### Task 5.3: `intent_quantity=None` 过早标记 `filled` `[M]`
- **评分**: ~75/100
- **来源**: Git 历史审查
- **文件**: `packages/app/src/ditto_app/command/trade.py:190`
- **问题**: `_determine_fill_status` 中 `if intent_quantity is None or cumulative_qty >= intent_quantity: return "filled"` — 当 `quantity=None`（有效值，schema 允许 NULL）时，第一次部分成交后 intent 立即被标记为 `filled`，阻止后续成交（因为 `_validate_intent_match` 检查 `status not in {"pending", "partially_filled"}`）。
- **方案**: 当 `intent_quantity is None` 时返回 `"partially_filled"` 而非 `"filled"`，让调用者通过 `UpdateIntentStatusHandler` 显式标记终态
- **验收**: `quantity=None` 的 intent 不会自动标记为 filled；后续 fill 可正常录入
- **测试**: `packages/app/tests/unit/command/test_trade_unit.py` — 新增 `test_determine_fill_status_none_quantity_returns_partial`

### Task 5.4: `_validate_params` 死代码清理 `[M]`
- **评分**: ~50/100
- **来源**: 代码注释合规审查
- **文件**: `packages/app/src/ditto_app/process/execution/strategy_run_process.py:229-236`
- **问题**: `validate_spec_params` 已改为返回 `None` + 直接抛 `ValueError`，但 `_validate_params` 仍使用旧模式 `errors = validate_spec_params(spec); if errors: raise ValueError(...)` — `if errors:` 分支永远为 False，是死代码。
- **方案**: 简化为直接调用 `validate_spec_params(spec)`，移除死代码分支
- **验收**: 行为不变（`validate_spec_params` 自身抛 ValueError）；代码更清晰
- **测试**: 现有测试通过

### Task 5.5: `validate_frame` docstring 与实现矛盾 `[H]`
- **评分**: 100/100
- **来源**: 代码注释合规审查
- **文件**: `packages/engine/src/ditto_engine/alpha/frame.py:33-50`
- **问题**: docstring 三处错误描述：(1) "debug 模式（默认）下执行校验" — 实际无条件执行 (2) "缺少列时抛出 AssertionError" — 实际抛 ValueError (3) "release 模式下为 no-op" — 实际不是 no-op。`Raises:` 段正确写了 ValueError，但与上方描述矛盾。
- **方案**: 重写 docstring，移除关于 debug/release 模式的错误描述，正确反映无条件校验 + ValueError 行为
- **验收**: docstring 与实现一致
- **测试**: 无需新测试

### Task 5.6: `artifacts_map` 空时 `StopIteration` 崩溃 `[M]`
- **评分**: ~40/100
- **来源**: Git 历史审查
- **文件**: `packages/app/src/ditto_app/process/execution/backtest_process.py:517`
- **问题**: `next(iter(artifacts_map.values()))` 在 `artifacts_map` 为空时抛出未处理的 `StopIteration`。
- **方案**: 添加空检查，空 map 时直接返回（不持久化产物记录）
- **验收**: 空 artifacts 不崩溃；正常情况行为不变
- **测试**: `packages/app/tests/unit/process/strategy/test_backtest_service_unit.py` — 新增 `test_persist_artifact_empty_map_no_error`

### Task 5.7: `get_or_create` 路径未传 `config_json` `[M]`
- **评分**: 75/100
- **来源**: Git 历史审查
- **文件**: `packages/app/src/ditto_app/process/execution/backtest_process.py:199-208`
- **问题**: `BacktestService.run()` 的 get_or_create 模式在创建新记录时不传 `config_json`。API 流程中由 `BacktestRunHandler` 预写入 config_json，但 CLI/Prefect 直接触发的回测会创建空 config_json 记录，破坏可复现性。
- **方案**: 在 `create_run` 调用处序列化 `BacktestServiceConfig` 的关键字段为 JSON 字符串并传入
- **验收**: CLI 触发的回测也有完整 config_json；retry 可正确恢复配置
- **测试**: `packages/app/tests/unit/process/strategy/test_backtest_service_unit.py` — 新增 `test_run_creates_record_with_config_json`

### Task 5.8: `_recompute_positions` 全量查询性能 `[M]`
- **评分**: ~50/100
- **来源**: Git 历史审查
- **文件**: `packages/app/src/ditto_app/command/trade.py:196`
- **问题**: `self._service.list_fills(strategy_id=strategy_id)` 不传 `end_date`，每次 fill 录入都全量拉取策略所有历史成交。`TradeService.list_fills` 已支持 `end_date` 参数。
- **方案**: 传入 `end_date=snapshot_date` 限制查询范围
- **验收**: 仅查询 snapshot_date 之前的成交；行为不变（ManualTracker.compute_positions 内部也按日期过滤）
- **测试**: 现有测试通过

---

## 更新后的执行顺序

```
Phase 5 (PR Review 修复):
  5.5 validate_frame docstring ─── 最简，秒修
  5.4 _validate_params 死代码 ──── 秒修
  5.8 _recompute_positions ─────── 一行改动
  5.6 artifacts_map 空检查 ──────── 小改动
  5.3 intent_quantity=None ──────── 逻辑修正
  5.1 TOCTOU 竞态修复 ──────────── SQL + 方法签名变更
  5.2 ComparisonQueryFacade DI ──── 一行改动
  5.7 get_or_create config_json ─── 序列化 + 传参
```

## 全局验收

- [x] `pixi run -e dev check` 全部通过
- [x] `pixi run -e dev arch-check` 24 条合约保持
- [x] 现有 5416 个测试无回归（25 skipped 为 e2e 数据缺失）
- [x] 新增代码覆盖率 ≥ 80%
