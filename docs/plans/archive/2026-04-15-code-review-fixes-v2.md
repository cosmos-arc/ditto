# Code Review 修复计划（V2）

## 概述

- **来源**: `feat/v1-sprint` 6 维度并行审查
- **创建**: 2026-04-15
- **范围**: 3 Critical + 15 Major + 27 Minor → 精简为可执行任务
- **排除**: API 认证（Q3，用户明确不需要）

## 审查发现修正

探索阶段对部分审查结论进行了修正：

| 原结论 | 修正 | 原因 |
|--------|------|------|
| C3: `_safe_float` 移至 kernel/math | **降级为 Minor** | 仅 1 处调用、1 个包消费，不满足 Kernel 准入标准（需 2+ 包消费） |
| m5: status 端点 `backtest/trading: False` | **升级为 Major** | 发现更严重问题：`main.py` 中 3 处版本号 `"0.1.0"` 与 `ditto_kernel.__version__ = "0.2.0"` 不一致 |
| M-4: 3 个过期 importlinter ignore | **需验证** | 探索发现所有 ignore 均有活跃消费者，需运行 `lint-imports` 确认实际 unmatched 项 |
| K6: alternative.py 缺测试 | **调整** | 核心问题是 docstring 提到 "sentiment" 但无对应因子定义 |

---

## 任务清单

### Phase 1: Quick Fixes（全部 S 级，可并行）

#### 1.1 移除 `CostConfig` 死 re-export `[S]`

- **来源**: R2
- **文件**: `packages/app/src/ditto_app/command/__init__.py`
- **操作**: 删除 `from ditto_app.contracts import CostConfig` 和 `__all__` 中的 `"CostConfig"`
- **验证**: `pixi run -e dev arch-check` 通过；grep 确认无消费者
- **测试**: 无需新测试（死代码删除）

#### 1.2 移除 kernel 未消费的 re-export `[S]`

- **来源**: R3
- **文件**: `packages/kernel/src/ditto_kernel/__init__.py`
- **操作**: 从 `__all__` 和 import 中移除 `ImpactModel`、`pearson_correlation`
- **验证**: grep 确认全库无 `from ditto_kernel import ImpactModel` 或 `from ditto_kernel import pearson_correlation` 的消费者
- **测试**: 无需新测试

#### 1.3 修复 `/api/v1/status` + 版本号统一 `[S]`

- **来源**: m5（升级）
- **文件**: `interfaces/src/ditto_interfaces/main.py`
- **操作**:
  1. `backtest: False` → `backtest: True`，`trading: False` → `trading: True`
  2. 3 处硬编码 `"0.1.0"` 改为从 `ditto_kernel.__version__` 读取（所有层依赖 kernel）
- **验证**: `pixi run -e dev check`
- **测试**: 更新 `test_main_routes_integration.py` 中版本号相关断言

#### 1.4 清理 `.importlinter` 过期 ignore `[S]`

- **来源**: M-4
- **文件**: `.importlinter`
- **操作**: 运行 `pixi run -e dev arch-check`，查看 unmatched_ignore_imports 警告，移除无匹配的 ignore 条目
- **验证**: `pixi run -e dev arch-check` 无 warn
- **测试**: 无需新测试

#### 1.5 `_is_rebalance_day` 防御性检查 `[S]`

- **来源**: Q2
- **文件**: `packages/engine/src/ditto_engine/backtest/engine.py`
- **操作**:
  1. 在 `__init__` 中构建 `self._trading_day_index: dict[str, int] = {d: i for i, d in enumerate(trading_days)}`
  2. `_is_rebalance_day` 中 `self._trading_days.index(date)` → `self._trading_day_index[date]`（O(n) → O(1)）
  3. 添加 `.get(date)` 防御性检查，fallback 为 daily rebalance
- **验证**: `pixi run -e dev check`
- **测试**: 更新 `test_engine_loop_unit.py` 中 rebalance 相关测试

#### 1.6 `alternative.py` docstring 修正 + 编译验证测试 `[S]`

- **来源**: K6
- **文件**: `packages/analytics/src/ditto_analytics/factors/alternative.py`
- **操作**:
  1. docstring 从 "margin trading, pledge, and sentiment" 改为 "margin trading and pledge"
  2. 新增 `tests/unit/factors/test_alternative_factors_unit.py`，验证 3 个 FactorSpec 的 expression 可被编译器成功解析
- **验证**: `pixi run -e dev check`
- **测试**: 新增 1 个测试文件（~30 行）

---

### Phase 2: Constants & PIT（S-M 级，可并行）

#### 2.1 `DEFAULT_INITIAL_CASH` 常量化 `[M]`

- **来源**: C2
- **文件**: 新增 `packages/app/src/ditto_app/config.py` 中的常量；修改 9 个消费点
- **操作**:
  1. 在 `ditto_app.config` 添加 `DEFAULT_INITIAL_CASH: float = 1_000_000.0`
  2. 替换 9 处硬编码（interfaces 3 处 + app 6 处）
- **消费点清单**:

  | # | 文件 | 行 | 类型 |
  |---|------|----|------|
  | 1 | `interfaces/models/backtest.py` | 176 | Pydantic Field default |
  | 2 | `interfaces/cli/commands/strategy.py` | 88 | Typer Option default |
  | 3 | `interfaces/jobs/flows/backtest.py` | 43 | 函数参数默认值 |
  | 4 | `app/command/backtest.py` | 43 | dataclass field |
  | 5 | `app/process/execution/backtest_process.py` | 101 | dataclass field |
  | 6 | `app/query/comparison.py` | 139 | 函数参数默认值 |
  | 7 | `app/process/execution/comparison.py` | 25 | 函数参数默认值 |
  | 8 | `app/process/execution/replay_process.py` | 173 | dict.get fallback |
  | 9 | `app/query/comparison.py` | 226 | _safe_float fallback |

- **验证**: `pixi run -e dev check`；grep 确认无残留 `1_000_000.0`（排除 instrument ID range）
- **测试**: 更新受影响的测试断言

#### 2.2 `_ROLLING_BUILDERS` 添加 `closed="left"` 双重保障 `[S]`

- **来源**: P1
- **文件**: `packages/analytics/src/ditto_analytics/expression/codegen.py`
- **操作**: 在 `_ROLLING_BUILDERS` 的 7 个 lambda 中，对 `rolling_*` 调用添加 `closed="left"` 参数（`count` 无 closed 参数，跳过）
- **验证**: `pixi run -e dev check`；运行因子测试确认无回归
- **测试**: 无需新测试（现有因子测试覆盖）

---

### Phase 3: Clone Elimination（M 级）

#### 3.1 提取 fx/commodity 共享 bars handler `[M]`

- **来源**: C1
- **文件**:
  - 新增 `interfaces/src/ditto_interfaces/api/routes/_bars_handler.py`
  - 修改 `interfaces/src/ditto_interfaces/api/routes/fx.py`
  - 修改 `interfaces/src/ditto_interfaces/api/routes/commodity.py`
- **技术方案**:
  1. 定义 `BarQueryProtocol`（Protocol），统一 5 个 facade 方法签名
  2. 实现 `async def handle_bars_post(query_ids, facade, col_name, to_bar_fn) -> APIResponse`
  3. fx.py / commodity.py 各自缩减为 ~15 行的薄包装
- **验证**: `pixi run -e dev check`；手动测试 fx/commodity bars API
- **测试**: 新增 `_bars_handler` 的单元测试（mock Protocol 实现）

---

### Phase 4: Function Decomposition（M-L 级，可并行）

#### 4.1 `daily_ingestion_flow` 拆分 `[M]`

- **来源**: K1
- **文件**: `interfaces/src/ditto_interfaces/jobs/flows/daily.py`
- **操作**:
  1. 提取 `_submit_tier_tasks(trade_date, source, force) -> tuple[list, list]`（T0+T1 提交编排）
  2. 提取 `_build_flow_summary(trade_date, t0_results, t1_results, dqc_results) -> dict`（结果聚合）
  3. `daily_ingestion_flow` 缩减为 ~40 行的顶层编排
- **验证**: `pixi run -e dev check`
- **测试**: 更新 `test_daily_flow` 相关测试

#### 4.2 `eod_flow` 拆分 + 告警上下文管理器 `[M]`

- **来源**: K2
- **文件**: `interfaces/src/ditto_interfaces/jobs/flows/eod.py`
- **操作**:
  1. 提取 `_handle_ingestion_result(trade_date, result) -> dict | None`（失败检查 + 告警）
  2. 提取 `_run_materialization(trade_date) -> tuple[dict | None, bool]`（物化执行 + 告警）
  3. 消除 2 处重复的 `make_app_container() → alert → close` 模式
- **验证**: `pixi run -e dev check`
- **测试**: 更新 `test_eod_flow_unit.py`

#### 4.3 `get_source_data` 拆分 `[S]`

- **来源**: K3
- **文件**: `interfaces/src/ditto_interfaces/api/routes/source.py`
- **操作**:
  1. 提取 `_infer_asset_class(facade, dataset) -> AssetClass`
  2. 提取 `_resolve_source_ticker(facade, params, asset_class, source) -> str`
- **验证**: `pixi run -e dev check`
- **测试**: 新增/更新 source 路由测试

#### 4.4 `process_pending` 循环体提取 `[M]`

- **来源**: K4
- **文件**: `packages/engine/src/ditto_engine/execution/brokerage.py`
- **操作**:
  1. 提取 `_process_single_ticket(ticket, bars, trade_date, step_time) -> FillEvent | None`
  2. 提取 `_is_order_executable(ticket, position, iid, trade_date, trading_rule) -> bool`
  3. `process_pending` 缩减为简单的循环 + 收集器
- **验证**: `pixi run -e dev check`
- **测试**: 更新 brokerage 相关测试

#### 4.5 `providers.py` 按领域拆分 `[L]`

- **来源**: K5
- **文件**:
  - 新增 `packages/app/src/ditto_app/providers_market.py`（市场数据查询：10 方法）
  - 新增 `packages/app/src/ditto_app/providers_strategy.py`（策略相关：12 方法）
  - 新增 `packages/app/src/ditto_app/providers_portfolio.py`（组合/交易：6 方法）
  - 修改 `packages/app/src/ditto_app/providers.py`（保留 CommandProvider + ProcessProvider + BuilderFactory + `get_app_providers()` 聚合）
- **操作**:
  1. `AppQueryProvider`（222 行，22 方法）按领域拆为 3 个 Provider
  2. `get_app_providers()` 聚合所有 Provider
  3. `providers.py` 从 758 行降至 ~350 行
- **验证**: `pixi run -e dev check`；`pixi run -e dev arch-check`
- **测试**: 更新 `test_providers_unit.py`

---

### Phase 5: SQL Safety（M 级）

#### 5.1 `_build_where_clause` 白名单校验 `[M]`

- **来源**: Q1
- **文件**: `packages/data/src/ditto_data/services/trade_service.py`
- **操作**:
  1. 定义 `ALLOWED_ORDER_BY = frozenset({"signal_date ASC", "signal_date DESC", "snapshot_date ASC", "trade_date ASC", ...})`
  2. 定义 `ALLOWED_COLUMNS = frozenset({"signal_date", "snapshot_date", "trade_date", "intent_id", ...})`
  3. 在 `_build_where_clause` 入口添加白名单校验，不匹配时抛 `ValueError`
- **验证**: `pixi run -e dev check`
- **测试**: 新增白名单校验的单元测试（合法/非法输入）

---

## 执行顺序

```
Phase 1 (Quick Fixes) ─── 6 个 S 级任务，全部可并行
    │
Phase 2 (Constants & PIT) ─── 2 个任务，可并行
    │
Phase 3 (Clone Elimination) ─── 1 个 M 级任务
    │
Phase 4 (Function Decomposition) ─── 5 个任务，可并行
    │
Phase 5 (SQL Safety) ─── 1 个 M 级任务
```

**依赖关系**:
- Phase 1 各任务之间无依赖
- Phase 2 各任务之间无依赖
- Phase 3 依赖 Phase 1 完成（避免 merge conflict）
- Phase 4 各任务之间无依赖
- Phase 5 独立于 Phase 4

## 工作量估算

| Phase | 任务数 | 总量级 | 预估 |
|-------|--------|--------|------|
| Phase 1 | 6 | 6S | ~1h |
| Phase 2 | 2 | 1S + 1M | ~30min |
| Phase 3 | 1 | 1M | ~30min |
| Phase 4 | 5 | 2S + 2M + 1L | ~3h |
| Phase 5 | 1 | 1M | ~20min |
| **合计** | **15** | | **~5.5h** |

## 验收标准

- [x] `pixi run -e dev check` 通过（lint + type + test --fast）
- [x] `pixi run -e dev arch-check` 无 warn（24 contracts kept, 0 broken）
- [x] `pixi run -e dev test` 单元测试全量通过（5411 passed, 0 failed）
- [x] grep 确认无残留 `1_000_000.0`（排除 instrument ID range）
- [x] 所有新增/修改的公开 API 有对应测试

## 任务执行状态

### Phase 1: Quick Fixes

| # | 任务 | 状态 | 备注 |
|---|------|------|------|
| 1.1 | 移除 CostConfig 死 re-export | ✅ 完成 | 删除 `__init__.py` 中的 re-export + `__all__` 条目 |
| 1.2 | 移除 kernel 未消费 re-export | ✅ 完成 | 移除 `ImpactModel`、`pearson_correlation` |
| 1.3 | 修复 status 端点 + 版本号统一 | ✅ 完成 | N812 修复 + 3 处 `ditto_version` 统一 + 测试更新 |
| 1.4 | 清理 importlinter 过期 ignore | ✅ 完成 | 运行 arch-check 确认无 warn |
| 1.5 | `_is_rebalance_day` 防御性检查 | ✅ 完成 | O(n) → O(1) dict lookup + 防御性 `.get()` |
| 1.6 | `alternative.py` docstring 修正 | ✅ 完成 | 移除 "sentiment" + 新增编译验证测试 |

### Phase 2: Constants & PIT

| # | 任务 | 状态 | 备注 |
|---|------|------|------|
| 2.1 | `DEFAULT_INITIAL_CASH` 常量化 | ✅ 完成 | 新增常量 + 9 处替换 + `__all__` 导出 |
| 2.2 | `_ROLLING_BUILDERS` closed="left" | ⏭️ 跳过 | `shift(1)` 已提供 PIT 安全，无需额外 `closed` 参数 |

### Phase 3: Clone Elimination

| # | 任务 | 状态 | 备注 |
|---|------|------|------|
| 3.1 | 提取 fx/commodity 共享 bars handler | ✅ 完成 | 新增 `shared_bars.py` + `_BarFacade` Protocol + 5 个测试 |

### Phase 4: Function Decomposition

| # | 任务 | 状态 | 备注 |
|---|------|------|------|
| 4.1 | `daily_ingestion_flow` 拆分 | ⏭️ 跳过 | 已评估：函数结构清晰，拆分反而增加间接层 |
| 4.2 | `eod_flow` 拆分 | ⏭️ 跳过 | 已评估：已充分分解，拆分收益低于成本 |
| 4.3 | `get_source_data` 拆分 | ✅ 完成 | 提取 `_infer_asset_class` + `_resolve_source_ticker` + 9 个测试 |
| 4.4 | `process_pending` 循环体提取 | ✅ 完成 | 提取 `_is_order_executable` + `_process_single_ticket` + 7 个测试 |
| 4.5 | `providers.py` 按领域拆分 | 📌 延期 | L 级重构，需独立 PR 处理（758 行 → ~350 行） |

### Phase 5: SQL Safety

| # | 任务 | 状态 | 备注 |
|---|------|------|------|
| 5.1 | `_build_where_clause` 白名单校验 | ✅ 完成 | `_ALLOWED_ORDER_BY` + `_ALLOWED_COLUMNS` + 13 个测试 |

### 总结

- **完成**: 11/15 任务
- **跳过**: 3/15 任务（有充分技术理由）
- **延期**: 1/15 任务（L 级，需独立 PR）
- **新增测试文件**: 5 个（test_shared_bars_handler_unit.py, test_source_route_unit.py, test_brokerage_helpers_unit.py, test_trade_service_unit.py, test_alternative_factors_unit.py）
- **修复附带问题**: Protocol 类型对齐（`_BarFacade` ← `InstrumentCodeQueryFacade.get_valid_codes`）
