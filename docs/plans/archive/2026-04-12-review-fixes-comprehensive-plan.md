> **Status**: Superseded by [2026-04-13-v1-review-fix-plan.md](./2026-04-13-v1-review-fix-plan.md)

# V1 Sprint Review — Comprehensive Fix Plan

## 概述

- Sprint: V1 Sprint Review Fixes
- 创建: 2026-04-12
- 目标: 修复 Code Review 全部 7 项 Finding（1 Blocking + 2 High + 3 Medium + 1 Process）

## 技术方案

### F1: 架构边界修复（Blocking）

**问题**：`interfaces.models` 直接 import `ditto_data.models` 的 `StrategySpecRecord` / `StrategyRunRecord`，违反 `interfaces-service-isolation` 合同。

**方案**：在 App Query 层引入 DTO，切断 Interfaces → Data 的直接依赖。

```
Before:
  Route → BacktestQueryFacade.list_runs() → list[StrategyRunRecord]  (Data type)
  Route → to_run_response(StrategyRunRecord) → RunResponse           (import Data)

After:
  Route → BacktestQueryFacade.list_runs() → list[RunSummary]         (App DTO)
  Route → to_run_response(RunSummary) → RunResponse                   (no Data import)
```

**App 层 DTO 定义位置**：与 `TradeRecord`（在 `backtest_trade.py` 中）保持一致的模式 — 在对应 query 模块内定义。

- `ditto_app.query.backtest` 中新增 `RunSummary` dataclass
- `ditto_app.query.strategy` 中新增 `StrategySpecInfo` dataclass
- 两个 Query Facade 负责将 Data Record → App DTO 转换

**影响范围**：
- `BacktestQueryFacade` — 返回类型变更
- `StrategyQueryFacade` — 返回类型变更
- `BacktestQueryFacade.get_lineage()` 也返回 `list[StrategyRunRecord]` → `list[RunSummary]`
- `interfaces/models/backtest.py` — 删除 Data import，mapper 签名改用 App DTO
- `interfaces/models/strategy.py` — 删除 Data import，mapper 签名改用 App DTO
- `interfaces/models/__init__.py` — 导出不变

### F2: impact_model 合同对齐（High）

**问题**：API `Literal["none", "linear", "square_root"]` 与 Engine 实际支持的 `"none"` / `"volume_share"` 不一致。

**方案**：API 合同向实现靠拢 — Engine 层只有 `FixedBpsSlippage` 和 `VolumeShareSlippage` 两种实现。

- API `CostConfigRequest.impact_model` 改为 `Literal["none", "volume_share"]`
- App `CostConfig.impact_model` 从 bare `str` 改为 `Literal["none", "volume_share"]`
- 更新相关测试
- `fee_override.py` 保持不变（已经是正确的 none/volume_share 分支）

### F3: Prefect 骨架清理（High）

**问题**：`_submit_flow` 的 `PREFECT_API_URL` 分支是空骨架，两个分支最终都走 `_run_in_process`。

**方案**：删除空骨架分支，简化为单一进程内执行路径，保留清晰的 TODO 文档注释。

```python
def _submit_flow(params, on_failure=None):
    """同步提交 flow — 进程内执行（V1）。
    R3: Prefect Worker 异步提交待实现。
    """
    _run_in_process(params, on_failure)
```

### F4: 协作式取消 + 进度上报（Medium）

**问题**：取消只改 DB 状态，运行中任务不会真正停止；progress 字段从未被更新。

**方案**：三层协作式取消（Engine → App → Interfaces）。

```
Engine 层:
  EngineOptions 新增 should_stop: Callable[[], bool] | None
  EngineLoop.run() 每日迭代前检查 should_stop()

App 层:
  BacktestServiceOptions 新增 run_service (已有)
  BacktestService 创建 should_stop 回调 (轮询 DB 状态)
  BacktestService 在 engine 执行前后更新 progress

Data 层:
  StrategyRunService 新增 update_progress() + is_cancelled() 方法
  StrategyRunWriterProtocol 新增 update_progress() 方法
```

**Progress 上报策略**：
- 每 N 个交易日（或每 10%）更新一次 DB，避免高频写入
- 更新字段：`progress_pct`, `current_step`, `completed_days`, `total_days`

**取消语义**：
- `should_stop()` 返回 True → EngineLoop 跳出循环
- BacktestService 捕获取消后调用 `mark_cancelled()`（而非 `mark_completed()`）
- 已有的 DB 终态保护（SQL `WHERE status NOT IN ('cancelled', 'completed', 'failed')`）确保幂等

### F5: FactorBridge 历史窗口（Medium）

**问题**：bundle builder 只用当前日 `slice_.bars`，ts_* 表达式因缺少历史数据返回 null。

**方案**：利用 `ProviderBackedDataFeed` 已加载的全量 `_bars_df`，在 bundle builder 中传入历史窗口。

```
关键洞察：
  ProviderBackedDataFeed._load_bars() 已将 start_date ~ end_date 的全量行情加载到 _bars_df
  当前 get_slice(date) 只过滤当天返回
  需要新增 get_history(instrument_ids, date, lookback) 方法
```

**实现**：
1. `DataFeed` Protocol 新增 `get_history(instrument_ids, date, lookback_days) -> pl.DataFrame`
2. `ProviderBackedDataFeed` 实现该方法（从 `_bars_df` 过滤）
3. Bundle builder closure 捕获 `data_feed`，在构建 `market_data` 时包含历史窗口
4. 需要确定 `lookback_days` 的来源（编译表达式时最大窗口？或固定默认值？）

**注意**：`FactorBridge.compute_signals()` 的 rank 归一化是截面操作，但如果输入是多日数据，需要确保只在当日截面上做 rank（用 `trade_date` 过滤）。

### F6: Trade API 路径文档同步（Medium）

**问题**：实现用 `/trade` 前缀，sprint plan 写的是扁平路径。

**方案**：以实际实现为准，更新 sprint plan 文档。`/trade` 前缀的 RESTful 设计更优，与 `/backtests` 对称。

### F7: 文档清理（Process）

**方案**：本次修复完成后统一提交或清理两个未跟踪计划文档。

---

## 任务清单

### Phase 1: 架构边界 + 合同对齐（阻塞 CI）

- [ ] Task 1.1: 定义 App 层 `RunSummary` DTO `[S]`
  - 验收: `ditto_app.query.backtest.RunSummary` frozen dataclass，字段覆盖 `to_run_response` 所需全部字段
  - 文件: `packages/app/src/ditto_app/query/backtest.py`

- [ ] Task 1.2: 定义 App 层 `StrategySpecInfo` DTO `[S]`
  - 验收: `ditto_app.query.strategy.StrategySpecInfo` frozen dataclass，字段覆盖 `to_strategy_response` 所需全部字段
  - 文件: `packages/app/src/ditto_app/query/strategy.py`

- [ ] Task 1.3: `BacktestQueryFacade` 返回 `RunSummary` 替代 `StrategyRunRecord` `[M]`
  - 验收: `list_runs()` / `get_run()` / `get_lineage()` 全部返回 `RunSummary`；内部转换逻辑正确
  - 文件: `packages/app/src/ditto_app/query/backtest.py`

- [ ] Task 1.4: `StrategyQueryFacade` 返回 `StrategySpecInfo` 替代 `StrategySpecRecord` `[M]`
  - 验收: `list_specs()` / `get_spec()` 全部返回 `StrategySpecInfo`；内部转换逻辑正确
  - 文件: `packages/app/src/ditto_app/query/strategy.py`

- [ ] Task 1.5: interfaces mapper 改用 App DTO，删除 Data import `[S]`
  - 验收: `interfaces/models/backtest.py` 和 `interfaces/models/strategy.py` 无 `ditto_data` import
  - 文件: `interfaces/src/ditto_interfaces/models/backtest.py`, `interfaces/src/ditto_interfaces/models/strategy.py`

- [ ] Task 1.6: impact_model 合同对齐 `[S]`
  - 验收: API `Literal["none", "volume_share"]`，App `Literal["none", "volume_share"]`，测试通过
  - 文件: `interfaces/src/ditto_interfaces/models/backtest.py`, `packages/app/src/ditto_app/contracts.py`

- [ ] Task 1.7: Phase 1 验证 `[S]`
  - 验收: `pixi run -e dev arch-check` 通过，`pixi run -e dev check` 通过

### Phase 2: 协作式取消 + 进度上报

- [ ] Task 2.1: `StrategyRunWriterProtocol` 新增 `update_progress()` 方法 `[S]`
  - 验收: Protocol 定义含 `update_progress(run_id, *, progress_pct, current_step, completed_days, total_days) -> bool`
  - 文件: `packages/data/src/ditto_data/services/strategy/strategy_run_service.py`

- [ ] Task 2.2: `StrategyRunService` 实现 `update_progress()` + `is_cancelled()` `[S]`
  - 验收: `update_progress()` 委托给 writer；`is_cancelled()` 通过 reader.get() 检查 status
  - 文件: `packages/data/src/ditto_data/services/strategy/strategy_run_service.py`

- [ ] Task 2.3: `RunLifecycleService` Protocol 扩展 `[S]`
  - 验收: 新增 `is_cancelled(run_id) -> bool` 和 `update_progress(run_id, ...) -> bool`
  - 文件: `packages/app/src/ditto_app/process/execution/strategy_types.py`

- [ ] Task 2.4: `EngineOptions` 新增 `should_stop` 回调 `[S]`
  - 验收: `should_stop: Callable[[], bool] | None = None`
  - 文件: `packages/engine/src/ditto_engine/backtest/engine.py`

- [ ] Task 2.5: `EngineLoop.run()` 支持协作式取消 `[M]`
  - 验收: 每日迭代前检查 `should_stop()`；返回 `EngineResult` 中标记是否被取消
  - 文件: `packages/engine/src/ditto_engine/backtest/engine.py`
  - 测试: `packages/engine/tests/unit/backtest/test_engine_loop_unit.py`

- [ ] Task 2.6: `BacktestService` 接入取消 + 进度 `[M]`
  - 验收:
    - `BacktestServiceOptions` 新增 `total_days: int | None = None`
    - `_execute_backtest()` 构造 `should_stop` 回调（轮询 `run_service.is_cancelled()`）
    - 每日迭代后更新 progress（通过 `run_service.update_progress()`）
    - 检测到取消时调用 `mark_cancelled()` 而非 `mark_completed()`
  - 文件: `packages/app/src/ditto_app/process/execution/backtest_process.py`
  - 测试: `packages/app/tests/unit/process/execution/test_backtest_process_unit.py`

- [ ] Task 2.7: Phase 2 单元测试 `[M]`
  - 验收: EngineLoop 取消测试 + BacktestService 进度测试通过
  - 文件: `packages/engine/tests/unit/backtest/`, `packages/app/tests/unit/process/execution/`

### Phase 3: FactorBridge 历史窗口

- [ ] Task 3.1: `DataFeed` Protocol 新增 `get_history()` 方法 `[S]`
  - 验收: `get_history(instrument_ids: list[InstrumentId], as_of_date: str, lookback_days: int) -> pl.DataFrame`
  - 文件: `packages/engine/src/ditto_engine/backtest/data_feed.py`

- [ ] Task 3.2: `ProviderBackedDataFeed` 实现 `get_history()` `[M]`
  - 验收: 从 `_bars_df` 过滤 `instrument_id IN (...) AND trade_date < as_of_date`，按 date desc limit lookback_days
  - 文件: `packages/engine/src/ditto_engine/backtest/data_feed.py`
  - 测试: `packages/engine/tests/unit/backtest/test_data_feed_unit.py`

- [ ] Task 3.3: Bundle builder 接入历史窗口 `[M]`
  - 验收:
    - `BacktestServiceOptions` 新增 `lookback_days: int = 20`
    - Bundle builder closure 捕获 `data_feed` + `lookback_days`
    - 构建 `market_data` 时包含历史行（用 `trade_date` 列区分）
    - 截面 rank 操作只对当日数据生效
  - 文件: `packages/app/src/ditto_app/process/execution/backtest_process.py`

- [ ] Task 3.4: FactorBridge 历史窗口测试 `[M]`
  - 验收:
    - 用 `ts_mean(close, 3)` 表达式测试，验证 signal_value 非 null
    - 用 `delay(close, 5)` 测试，验证延迟信号正确
    - E2E smoke 测试增强：断言 ts_* 信号非空
  - 文件: `packages/app/tests/unit/process/execution/`, `packages/app/tests/integration/`

### Phase 4: 清理 + 文档

- [ ] Task 4.1: Prefect 骨架清理 `[S]`
  - 验收: `_submit_flow` 简化为单路径，无空 if 分支；保留 TODO 注释
  - 文件: `interfaces/src/ditto_interfaces/api/routes/backtest.py`

- [ ] Task 4.2: Trade API 路径文档同步 `[S]`
  - 验收: sprint plan 文档中的 API 路径与实际实现一致
  - 文件: `docs/plans/2026-04-10-v1-sprint-plan.md`

- [ ] Task 4.3: 未跟踪计划文档处理 `[S]`
  - 验收: 两个未跟踪 .md 文件已提交或删除
  - 文件: `docs/plans/2026-04-12-sprint-remaining-fixes.md`, `docs/plans/2026-04-12-v1-sprint-review-fixes.md`

- [ ] Task 4.4: 全量验证 `[S]`
  - 验收: `pixi run -e dev check` 通过（lint + fmt + type + test --fast + arch-check）

---

## 依赖关系

```
Phase 1 (阻塞 CI):
  1.1 → 1.3 → 1.5 → 1.7
  1.2 → 1.4 → 1.5 → 1.7
  1.6 → 1.7

Phase 2 (取消+进度):
  2.1 → 2.2 → 2.3 → 2.6 → 2.7
  2.4 → 2.5 → 2.6

Phase 3 (历史窗口):
  3.1 → 3.2 → 3.3 → 3.4

Phase 4 (清理):
  无依赖，可与 Phase 2/3 并行

Phase 2, 3, 4 可并行执行（跨模块无冲突）
```

## 复杂度汇总

| Phase | 任务数 | 总复杂度 |
|-------|--------|----------|
| Phase 1 | 7 | 4S + 2M + 1S = ~4M |
| Phase 2 | 7 | 3S + 3M + 1M = ~4M |
| Phase 3 | 4 | 1S + 3M = ~3.5M |
| Phase 4 | 4 | 4S = ~1S |
| **Total** | **22** | **~12.5M** |

## 风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| Phase 1 DTO 变更影响 BacktestQueryFacade 所有调用方 | 中 | grep 全部引用，确保类型一致 |
| Phase 2 取消可能在 mark_completed 和 mark_cancelled 之间竞争 | 低 | DB 终态 SQL guard 已有保护 |
| Phase 3 历史窗口改变 market_data schema，可能影响 Pipeline | 中 | 确保 rank 只在当日截面操作；增加 E2E 测试 |
| Phase 3 lookback_days 与编译表达式窗口不匹配 | 低 | V1 使用固定默认值 20；V2 可从编译结果推导 |
