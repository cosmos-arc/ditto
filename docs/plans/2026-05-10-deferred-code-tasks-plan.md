# 延后项代码级任务计划

> 创建：2026-05-10
> 基线：`docs/plans/2026-05-10-deferred-items-design.md` 决策
> 分支：`remediation/cross-module-b1-b7`（继续）
> 策略：严格顺序执行，每批次通过 `pixi run -e dev check` 后进入下一批次
> 范围：仅代码级 4 项，架构级 3 Phase 记录里程碑不拆解

---

## 概述

- **目标**：执行延后项决策中的 4 项代码级修复
- **验收**：每批次 `pixi run -e dev check` 通过（lint + fmt + type + test + arch-check + arch-smells）

### 依赖关系

```
T1 (K.2 佣金常量清理) ──┐
T2 (K.6 DecisionFrame 删除) ──┤── 无依赖，可任意顺序
T3 (EX.4 DiffContext) ────────┘
T4 (大文件 Facade 拆分 ×7) ── 独立，T4.1-T4.7 按难度递增
```

---

## T1：K.2 `DEFAULT_COMMISSION_RATE` 附带清理 `[M]`

### 源码现状

| 符号 | 位置 | 生产消费者 | 测试消费者 |
|------|------|-----------|-----------|
| `DEFAULT_COMMISSION_RATE` | `kernel/trading.py:29` | 5 包（execution/risk/backtest/strategy/application）✅ | 多处 |
| `default_price_limit_pct()` | `kernel/trading.py:146` | **零** | `execution/tests/.../test_rules_unit.py` 14 处 |
| `_DEFAULT_COMMISSION_RATE` | `apps/models/backtest.py:18` | Pydantic `CostConfigRequest` default | 有注释说明 workaround |

### 任务清单

- [ ] T1.1：删除 `default_price_limit_pct()` 死代码 `[S]`
  - 从 `kernel/trading.py` 删除函数体和 `__all__` 导出
  - 将函数迁移到 `execution/tests/unit/execution_legacy/test_rules_unit.py` 作为测试本地 fixture
  - 文件：`kernel/trading.py`, `execution/tests/.../test_rules_unit.py`
  - 验收：`rg "default_price_limit_pct" packages/kernel/` → 0；`rg "from ditto_kernel.trading import.*default_price_limit_pct" packages/` → 0

- [ ] T1.2：apps 副本同步 guard 强化 `[S]`
  - `apps/models/backtest.py` 现有注释已说明 Pydantic + `from __future__ import annotations` workaround
  - 添加值同步断言：`assert _DEFAULT_COMMISSION_RATE == 0.0003`（编译期常量校验）
  - 文件：`apps/models/backtest.py`
  - 验收：注释清晰说明值必须与 `ditto_kernel.trading.DEFAULT_COMMISSION_RATE` 同步

- [ ] T1.3：验证 `[S]`
  - `pixi run -e dev check`

---

## T2：K.6 DecisionFrame 死 Protocol 删除 `[S]`

### 源码现状

| 定义 | 位置 | 类型 | 外部消费者 |
|------|------|------|-----------|
| `DecisionFrame(Protocol)` | `kernel/strategy.py:57` | Protocol (instruments/signals/scores properties) | **零**（grep 确认无外部导入） |
| `type DecisionFrame = pl.DataFrame` | `strategy/alpha/protocols.py:14` | 类型别名 | 全部 pipeline stage |

两者结构不兼容。kernel Protocol 从未被使用，strategy 的 `pl.DataFrame` + `validate_frame()` 是实际契约。

### 任务清单

- [x] T2.1：删除 kernel `DecisionFrame` Protocol `[S]`
  - 删除 `kernel/strategy.py` 中 `DecisionFrame` class 定义（line 57-78）
  - 从 `kernel/strategy.py` 的 `__all__` 移除 `"DecisionFrame"`
  - 从 `kernel/__init__.py` 的 import 和 `__all__` 移除 `"DecisionFrame"`
  - 文件：`kernel/strategy.py`, `kernel/__init__.py`
  - 验收：`rg "DecisionFrame" packages/kernel/` → 0；strategy 包所有 DecisionFrame 引用不受影响

- [x] T2.2：更新 kernel CLAUDE.md `[S]`
  - 从 kernel CLAUDE.md 类型清单移除 `DecisionFrame` 行
  - 从 barrel Stable/Candidate 表移除
  - 文件：`packages/kernel/CLAUDE.md`

- [x] T2.3：验证 `[S]`
  - `pixi run -e dev check`
  - `rg "DecisionFrame" packages/strategy/` → 确认 strategy 的 DecisionFrame 正常

---

## T3：EX.4 `compute_diff` 引入 DiffContext `[M]`

### 源码现状

- `compute_diff` 定义：`execution/target_diff.py:157`，10 个参数，`# noqa: PLR0913`
- 单一调用点：`execution/planner.py:116`（`SimpleExecutionPlanner.plan()` 方法）
- 内部辅助 `_instrument_diff` 有 7 个参数（自然分组中的一部分）

### 任务清单

- [ ] T3.1：定义 DiffContext frozen dataclass `[S]`
  - 在 `execution/target_diff.py` 中新增：
  ```python
  @dataclass(frozen=True)
  class DiffContext:
      # Portfolio state
      target: TargetPortfolioLike
      account_view: AccountView
      pending_delta: dict[InstrumentId, int]
      # Scope + Market data
      all_instruments: set[InstrumentId]
      instrument_rules: dict[InstrumentId, InstrumentRules]
      market_snapshots: dict[InstrumentId, MarketSnapshot]
      default_lot_size: int
      # Policy
      locked_instruments: set[InstrumentId]
      pre_check_fn: Callable[
          [InstrumentId, int, dict[InstrumentId, MarketSnapshot]],
          BlockedOrder | None,
      ]
  ```
  - 添加到 `__all__`
  - 文件：`execution/target_diff.py`

- [ ] T3.2：重构 compute_diff 签名 `[S]`
  - `compute_diff(ctx: DiffContext, make_order: _MakeOrderFn) -> tuple[list[Order], list[BlockedOrder]]`
  - 内部从 `ctx.xxx` 读取参数
  - `_instrument_diff` 签名同步简化（接受 DiffContext 子集或独立参数）
  - 文件：`execution/target_diff.py`

- [ ] T3.3：更新调用端 `[S]`
  - `planner.py:116` 处构建 DiffContext 实例并调用新签名
  - 文件：`execution/planner.py`

- [ ] T3.4：更新测试 `[S]`
  - 搜索所有 `compute_diff` 测试调用点，更新为 DiffContext 构建
  - 文件：`execution/tests/`

- [ ] T3.5：验证 `[S]`
  - `pixi run -e dev check`

---

## T4：大文件 Facade 拆分（7 文件按难度递增）

### 策略

- **Facade 模式**：原文件保留为 re-export facade，公共 API 零破坏
- **每个文件独立拆分、独立验证**
- **B9-DATA.2 `errors.py` 已有成功先例**（606 LOC → 4 域文件 + facade）

---

### T4.1：config.py 拆分 `[M]` — 难度：低

**文件**：`application/config.py` (615 LOC)

**拆分方案**：

| 新文件 | 内容 | 预估 LOC |
|--------|------|----------|
| `config/specs.py` | `DatasetSpec` model + `INGESTION_SPECS` 常量（line 64-536） | ~470 |
| `config/queries.py` | `get_datasets_by_tier` / `get_dataset_config` / `iter_tier_datasets` / `get_all_datasets` / `get_parallel_datasets`（line 537-583） | ~50 |
| `config.py` (facade) | Protocol + `now_iso` + `TaskTier` + `T1ConfigSpec` + `create_t0_config` / `create_t1_config` + re-export | ~145 |

- [x] T4.1.1：创建 `config/` 包目录
  - `config/__init__.py`（保留 Protocol/enums/helpers，从 specs/queries re-export）
  - 文件：`application/config.py` → `config/__init__.py` + `config/specs.py` + `config/queries.py`

- [x] T4.1.2：迁移 DatasetSpec + INGESTION_SPECS → `config/specs.py`

- [x] T4.1.3：迁移 accessor 函数 → `config/queries.py`

- [x] T4.1.4：config.py 保留为 facade（re-export）

- [x] T4.1.5：更新全库 import + 验证
  - `pixi run -e dev check`

---

### T4.2：research.py 拆分 `[M]` — 难度：低

**文件**：`application/queries/research.py` (603 LOC)

**拆分方案**：

| 新文件 | 内容 | 预估 LOC |
|--------|------|----------|
| `queries/research_helpers.py` | `_sanitize_table_name` / `_normalize_trade_dates` / `_attach_known_at` / `_pit_join` / `_source_value_column` / `_manifest_hash` / `_build_dataset_report` / `_collect_null_counts` / `_coerce_date`（line 450-602） | ~150 |
| `queries/research.py` (facade) | `ResearchDatasetFacade` + `_DatasetSnapshotContract` + hydration helpers + re-export helpers | ~460 |

- [x] T4.2.1：提取底部 154 LOC 纯函数 → `queries/research_helpers.py`

- [x] T4.2.2：research.py 导入并 re-export helpers

- [x] T4.2.3：更新全库 import + 验证
  - `pixi run -e dev check`

---

### T4.3：capital.py 拆分 `[M]` — 难度：低

**文件**：`data/sources/tushare/adapters/capital.py` (725 LOC)

**拆分方案**（按子域分组）：

| 新文件 | 内容 | 预估 LOC |
|--------|------|----------|
| `adapters/capital_market.py` | `fetch_valuation_metrics` / `fetch_dividend` / `fetch_margin_trading` / `fetch_pledge_ratio`（line 44-370） | ~330 |
| `adapters/capital_index.py` | `fetch_index_weight` / `fetch_index_composition`（line 371-507） | ~140 |
| `adapters/capital_corporate.py` | `fetch_corporate_actions` / `fetch_share_buyback` / `fetch_rights_issue`（line 508-725） | ~220 |
| `adapters/capital.py` (facade) | `CapitalTushareAdapter` class 委托各子模块 + re-export | ~50 |

- [x] T4.3.1：提取 valuation/dividend/margin/pledge → `capital_market.py`

- [x] T4.3.2：提取 index_weight/index_composition → `capital_index.py`

- [x] T4.3.3：提取 corporate_actions/share_buyback/rights_issue → `capital_corporate.py`

- [x] T4.3.4：capital.py 保留为 facade（委托 + re-export）

- [x] T4.3.5：更新全库 import + 验证
  - `pixi run -e dev check`

---

### T4.4：runtime_builder.py 拆分 `[M]` — 难度：中

**文件**：`application/builders/runtime_builder.py` (627 LOC)

**拆分方案**：

| 新文件 | 内容 | 预估 LOC |
|--------|------|----------|
| `builders/deserialization.py` | `_deserialize_strategy_spec` / `_deserialize_constraints` / `_deserialize_param_constraints` / `_deserialize_scorer` / `_deserialize_selector` / `_deserialize_execution` / `_deserialize_cost_model` / `_deserialize_constraint` / `_deserialize_param_constraint`（line 166-320） | ~174 |
| `builders/template_builders.py` | `_build_etf_rotation_config` / `_build_etf_trend_swing_config` / `_build_stock_selection_trend_config` / `_build_stock_sector_rotation_config` + `_resolve_top_k` / `_resolve_scoring_method` / `_resolve_rebalance_frequency`（line 427-627） | ~200 |
| `builders/runtime_builder.py` (facade) | `StrategyRuntimeBuilder` / `PublishedStrategyRuntime` + `_inject_template_constraints` / `_compile_signal_expressions` / `_build_pipeline` / `_build_alpha_stages` / `_build_portfolio_stages` + re-export | ~250 |

- [x] T4.4.1：提取反序列化段 → `builders/deserialization.py`

- [x] T4.4.2：提取策略类型配置 builders → `builders/template_builders.py`

- [x] T4.4.3：runtime_builder.py 保留为 facade

- [x] T4.4.4：更新全库 import + 验证
  - `pixi run -e dev check`

---

### T4.5：tushare_source.py 拆分 `[M]` — 难度：中

**文件**：`data/sources/tushare/tushare_source.py` (777 LOC)

**拆分方案**（按资产域）：

| 新文件 | 内容 | 预估 LOC |
|--------|------|----------|
| `tushare/stock_source.py` | `fetch_calendar` / `fetch_stock_basic` / `fetch_stock_daily` / `fetch_adj_factor` / `fetch_adj_factor_by_ticker` / `fetch_stock_limit` / `fetch_stock_status` / `fetch_st_history`（line 89-303） | ~215 |
| `tushare/etf_index_source.py` | `fetch_etf_basic` / `fetch_etf_daily` / `fetch_fund_adj` / `fetch_index_basic` / `fetch_index_daily` / `fetch_sw_industry`（line 303-487） | ~185 |
| `tushare/fundamental_source.py` | `fetch_balance_sheet` / `fetch_income_statement` / `fetch_cash_flow` / `fetch_dividend` / `fetch_valuation_metrics` / `fetch_margin_trading` / `fetch_pledge_ratio` / `fetch_corporate_actions`（line 488-695） | ~210 |
| `tushare/macro_source.py` | `fetch_macro_indicators` / `fetch_fx_daily` / `fetch_metal_daily` / `fetch_commodities`（line 696-770） | ~75 |
| `tushare/tushare_source.py` (facade) | `TushareSource` class 委托各子模块 + `close` + re-export | ~40 |

- [x] T4.5.1：提取 stock data → `tushare/stock_source.py`

- [x] T4.5.2：提取 ETF/fund/index → `tushare/etf_index_source.py`

- [x] T4.5.3：提取 fundamental/capital → `tushare/fundamental_source.py`

- [x] T4.5.4：提取 macro/FX/commodities → `tushare/macro_source.py`

- [x] T4.5.5：tushare_source.py 保留为 facade

- [x] T4.5.6：更新全库 import + 验证
  - `pixi run -e dev check`

---

### T4.6：market_service.py 拆分 `[M]` — 难度：中高

**文件**：`data/services/market_service.py` (752 LOC)

**拆分方案**：

| 新文件 | 内容 | 预估 LOC |
|--------|------|----------|
| `services/market_queries.py` | `AdjType` / `MarketBarsQuery` / `MarketConstituentsQuery` + `find_bars` / `list_bars` / `_query_bars` + `get_constituents` / `_query_constituents`（line 38-303） | ~265 |
| `services/market_adjustment.py` | `_apply_adjustment` / `_apply_etf_adjustment` + `_enrich_with_status` / `_enrich_with_ticker`（line 417-587） | ~170 |
| `services/market_service.py` (facade) | `MarketService` class + `_load_bars_core` / `_get_bars_reader` / `_resolve_instrument_ids_and_asset_class` / `_parse_dates` + convenience API（`get_stock_bars` / `get_etf_bars` / `get_adj_factors` / `get_stock_status`）+ re-export | ~320 |

- [x] T4.6.1：提取 query types + bars query → `services/market_queries.py`

- [x] T4.6.2：提取 adjustment engine → `services/market_adjustment.py`

- [x] T4.6.3：market_service.py 保留为 facade + core engine + convenience API

- [x] T4.6.4：更新全库 import + 验证
  - `pixi run -e dev check`

---

### T4.7：coordinator.py 拆分 `[L]` — 难度：高

**文件**：`application/processes/ingestion/coordinator.py` (763 LOC)

**拆分方案**：

| 新文件 | 内容 | 预估 LOC |
|--------|------|----------|
| `ingestion/instrument_ingestion.py` | `ingest_by_instrument` / `_fetch_and_ingest_by_instrument` / `_try_fetch_data_by_instrument` / `_process_fetched_data_by_instrument`（line 554-703） | ~180 |
| `ingestion/post_ingest.py` | `_process_fetched_data` / `_run_post_ingest_hooks` / `_safe_side_effect` / `_update_ingestion_cursor` / `_create_freeze_point`（line 438-553） | ~120 |
| `ingestion/coordinator.py` (facade) | `IngestionCoordinator` + `ingest_date` / `_check_should_skip` / `_is_trading_day_for_dataset` / `_create_skipped_result` / `_fetch_and_ingest` / `_try_fetch_data` / `_handle_fetch_error` / `_write_data_safe` / `ingest_range` / `_fetch_by_dataset` / `_fetch_data` / `backfill_adj_factor` + re-export | ~460 |

**注意**：此文件内部交叉引用较多（post_ingest 回调 coordinator 方法），需行为快照测试先行。

- [x] T4.7.1：添加 coordinator 行为快照测试 `[S]`
  - 确保拆分前有 baseline 测试覆盖核心路径（ingest_date / ingest_range / ingest_by_instrument）
  - 文件：`application/tests/`

- [x] T4.7.2：提取 instrument-level ingestion → `ingestion/instrument_ingestion.py`

- [x] T4.7.3：提取 post-ingest hooks → `ingestion/post_ingest.py`

- [x] T4.7.4：coordinator.py 保留为 facade + core orchestration

- [x] T4.7.5：更新全库 import + 验证
  - `pixi run -e dev check`
  - 行为快照测试全部通过

---

## 验收总清单

每个任务完成后：

- [x] `pixi run -e dev lint` — 零错误
- [x] `pixi run -e dev fmt` — 格式一致
- [x] `pixi run -e dev type` — 零 type error
- [x] `pixi run -e dev test` — 全部通过
- [x] `pixi run -e dev arch-check` — 36/36 contracts kept
- [x] `pixi run -e dev arch-smells` — passed

---

## 任务统计

| 任务 | 复杂度 | 子任务数 | 涉及包 |
|------|--------|---------|--------|
| T1 K.2 佣金清理 | M | 3 | kernel, apps |
| T2 K.6 DecisionFrame 删除 | S | 3 | kernel |
| T3 EX.4 DiffContext | M | 5 | execution |
| T4.1 config.py 拆分 | M | 5 | application |
| T4.2 research.py 拆分 | M | 3 | application |
| T4.3 capital.py 拆分 | M | 5 | data |
| T4.4 runtime_builder.py 拆分 | M | 4 | application |
| T4.5 tushare_source.py 拆分 | M | 6 | data |
| T4.6 market_service.py 拆分 | M | 4 | data |
| T4.7 coordinator.py 拆分 | L | 5 | application |
| **合计** | — | **43** | 4 包 |

---

## 架构级里程碑（仅记录，不拆解）

| Phase | 名称 | 业界对标 | 启动条件 |
|-------|------|---------|---------|
| Phase 1 | Runtime Spine | LEAN `ISynchronizer` + `AlgorithmManager` | T1-T4 全部完成 |
| Phase 2 | OMS Lite | LEAN `OrderTicket` + `OrderEvent` | Phase 1 完成 |
| Phase 3 | Consumer-Owned Ports | NautilusTrader hexagonal | Phase 2 完成 |

详细设计见 `docs/plans/2026-05-10-deferred-items-design.md` §二。

---

## 风险评估

| 风险 | 任务 | 缓解措施 |
|------|------|---------|
| `default_price_limit_pct` 测试迁移遗漏 | T1.1 | 测试文件本地 import 后验证 |
| kernel barrel 移除 DecisionFrame 影响下游 | T2 | grep 确认零外部消费者 + `arch-check` |
| DiffContext 重构破坏 planner 行为 | T3 | 单一调用点 + 测试覆盖 |
| Facade 拆分后 re-export 不完整 | T4.x | 每步 `pixi run -e dev check` + 公共 API 不变验证 |
| coordinator 拆分交叉引用复杂 | T4.7 | 行为快照测试先行 |
