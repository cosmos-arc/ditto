# PR #62 + 6 维度并行审查修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 PR #62 Code Review 发现的 7 个问题 + 6 维度并行审查发现的 24 个警告，共 31 项。

**Architecture:** 分 6 个 Phase 按优先级递减执行。Phase 1-3 对应 PR #62 原始问题（P0-P2），Phase 4-6 对应 6 维度审查新增警告。

**Tech Stack:** Python 3.12+, polars, loguru, FastAPI, basedpyright, ruff

---

## 概述

- Sprint: V1 Sprint | Phase: Review Fixes
- 创建: 2026-04-13
- 来源:
  - [PR #62 Code Review](https://github.com/cosmos-arc/ditto/pull/62#issuecomment-4237652187) — 7 个问题
  - `/ditto-review` 6 维度并行审查 — 24 个警告

## 问题总览

| Phase | 来源 | 问题数 | 优先级 |
|-------|------|--------|--------|
| Phase 1 | PR #62 P0 | 4 | TYPE_CHECKING 硬性违规 |
| Phase 2 | PR #62 P1 | 3 | 代码质量缺陷 |
| Phase 3 | PR #62 P2 | 4 | 架构治理优化 |
| Phase 4 | 6 维度 - 质量 | 5 | 日志统一 + Protocol + 嵌套 |
| Phase 5 | 6 维度 - 可维护 | 5 | 长函数拆分 + TODO |
| Phase 6 | 6 维度 - 文档 | 5 | API docstring + CLAUDE.md |

---

## 技术方案

### Phase 1: TYPE_CHECKING 消除（PR #62 P0）

**根因分析**：4 个文件的 TYPE_CHECKING guard 均无实际运行时循环依赖。

| 文件 | 导入目标 | 循环? | 原因 |
|------|---------|-------|------|
| `process/ingestion/coordinator_factory.py` | `ports.QualityCheckerProtocol` | 否 | 同模块，ports.py 不导入 factory |
| `process/ingestion/config.py` | `ports.QualityCheckerProtocol` | 否 | 同模块，ports.py 不导入 config |
| `process/ingestion/range_process.py` | `ports.IngestDateHandlerProtocol`, `backfill_manager.BackfillManager` | 否 | backfill_manager 导入 coordinator 而非 range_process |
| `command/ingestion.py` | `process/ingestion.coordinator.IngestionCoordinator` | 否 | coordinator.py 不导入 command/（R8 允许 command→process） |

**方案**：所有文件已有 `from __future__ import annotations`，注解为惰性字符串，直接移除 TYPE_CHECKING guard，将 import 提升为常规导入。

### Phase 3: Barrel 治理（PR #62 P2）

**关键发现**：`query/__init__.py`（30 符号）和 `alpha/__init__.py`（31 符号）均无任何代码消费 barrel 路径（grep 确认零消费者）。所有代码直接从叶模块导入。

**方案**：精简 barrel 至核心公共 API 入口。

- `alpha/__init__.py`：保留 StrategyPipeline, StrategySpec, StrategyRun, TargetPortfolio, StrategyContext, StrategyInputBundle, DecisionStage, RegimeStage, StrategyTemplate（9 个核心类型），其余消费者直接从叶模块导入
- `query/__init__.py`：保留 4 个核心 Facade: BacktestQueryFacade, StrategyQueryFacade, TradeQueryFacade, ComparisonQueryFacade

### Phase 4: 日志统一

**根因**：4 个文件混用 stdlib `logging` 而非 `loguru`，影响结构化日志一致性。

**方案**：
```python
# 替换前
import logging
logger = logging.getLogger(__name__)

# 替换后
from loguru import logger
```

### Phase 5: 长函数拆分

**方案**：提取辅助方法，降低单函数行数到 ≤50 行。

- `_build_actual_navs` (95 行) → `_build_actual_navs_simple` + `_build_actual_navs_full`
- `_compute_single_instrument` (80 行) → `_apply_buy_fill` + `_apply_sell_fill`
- `RecordFillHandler.handle` (77 行) → `_validate_intent_match` + `_build_fill_dto`

---

## 任务清单

### Phase 1: P0 — CLAUDE.md 硬性违规修复

- [ ] Task 1.1: 移除 `coordinator_factory.py` 的 TYPE_CHECKING guard `[S]`
  - 验收: `from ditto_app.process.ingestion.ports import QualityCheckerProtocol` 为常规导入；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/process/ingestion/coordinator_factory.py`
  - 测试: 无需新增（类型检查器覆盖）

- [ ] Task 1.2: 移除 `config.py` 的 TYPE_CHECKING guard `[S]`
  - 验收: `from ditto_app.process.ingestion.ports import QualityCheckerProtocol` 为常规导入；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/process/ingestion/config.py`
  - 测试: 无需新增

- [ ] Task 1.3: 移除 `range_process.py` 的 TYPE_CHECKING guard `[S]`
  - 验收: `BackfillManager` 和 `IngestDateHandlerProtocol` 为常规导入；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/process/ingestion/range_process.py`
  - 测试: 无需新增

- [ ] Task 1.4: 移除 `command/ingestion.py` 的 TYPE_CHECKING guard `[S]`
  - 验收: `from ditto_app.process.ingestion.coordinator import IngestionCoordinator` 为常规导入；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/command/ingestion.py`
  - 测试: 无需新增

### Phase 2: P1 — 代码质量缺陷修复

- [ ] Task 2.1: 移除 `comparison.py` 死代码（重复 return） `[S]`
  - 验收: 第 340 行的 `return nav_series` 被删除；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/query/comparison.py` (L340)
  - 测试: 无需新增（现有测试覆盖 `_build_actual_navs` 返回值）

- [ ] Task 2.2: 提取重复常量 `_REGIME_DEFAULT_LOOKBACK` `[S]`
  - 验收: 常量仅在一处定义（`ditto_app.contracts`）；两处使用均引用同一来源；`pixi run -e dev check` 通过
  - 文件:
    - `packages/app/src/ditto_app/process/execution/backtest_process.py` (L68)
    - `packages/app/src/ditto_app/builders/service_factory.py` (L63)
  - 方案: 在 `ditto_app.contracts` 中定义 `REGIME_DEFAULT_LOOKBACK = 60`，两处改为从 contracts 导入
  - 测试: 无需新增

- [ ] Task 2.3: `retry_run` 端点增加 None record 防御 `[S]`
  - 验收: `facade.get_run(new_run_id)` 返回 None 时返回 500 错误而非静默提交空参数；`pixi run -e dev check` 通过
  - 文件: `interfaces/src/ditto_interfaces/api/routes/backtest.py` (L310-319)
  - 方案: 在 `record = await asyncio.to_thread(facade.get_run, new_run_id)` 之后增加 `if record is None: raise HTTPException(status_code=500, detail=...)`
  - 测试: 更新现有 `test_retry_failed_succeeds` 测试，增加 `record is None` 分支覆盖

### Phase 3: P2 — 架构治理优化

- [ ] Task 3.1: 精简 `alpha/__init__.py` barrel（31→≤15） `[M]`
  - 验收: `__all__` 符号数 ≤ 15；现有消费者不受影响（已确认无代码使用 barrel 路径）；`pixi run -e dev check` 通过
  - 文件: `packages/engine/src/ditto_engine/alpha/__init__.py`
  - 方案: 仅保留 9 个核心公共 API: StrategyPipeline, StrategySpec, StrategyRun, TargetPortfolio, StrategyContext, StrategyInputBundle, DecisionStage, RegimeStage, StrategyTemplate
  - 测试: `pixi run -e dev check`（类型检查确认无 barrel 消费者）

- [ ] Task 3.2: 精简 `query/__init__.py` barrel（30→≤15） `[M]`
  - 验收: `__all__` 符号数 ≤ 15；现有消费者不受影响；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/query/__init__.py`
  - 方案: 仅保留 4 个核心 Facade: BacktestQueryFacade, StrategyQueryFacade, TradeQueryFacade, ComparisonQueryFacade
  - 测试: `pixi run -e dev check`

- [ ] Task 3.3: `strategy_run_process.py` 添加 get_or_create 语义 `[S]`
  - 验收: 与 `backtest_process.py` 保持一致的 get_or_create 模式；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/process/execution/strategy_run_process.py` (L169-177)
  - 方案: 参照 `backtest_process.py` L201-212，在 `create_run` 前增加 `get_run` 检查
  - 测试: 无需新增（当前无 pre-creation 使用场景，防御性改进）

- [ ] Task 3.4: `data_feed.py` get_history() 增加 PIT 边界注释 `[S]`
  - 验收: filter 行有 inline comment 说明 strict `<` 的 PIT 理由；`pixi run -e dev check` 通过
  - 文件: `packages/engine/src/ditto_engine/backtest/data_feed.py` (L262-263)
  - 方案: 在 `pl.col("trade_date") < as_of_date` 行添加 `# PIT: strict < 排除当日数据，防止未来数据泄露到因子回看窗口`
  - 测试: 无需新增（已有 `test_as_of_date_excluded` 和 `test_zero_lookback` 覆盖）

### Phase 4: 质量维度 — 日志统一 + Protocol + 嵌套 + 重复

- [ ] Task 4.1: `backtest.py` 路由日志 stdlib→loguru `[S]`
  - 验收: `import logging` 和 `logging.getLogger` 被替换为 `from loguru import logger`；所有 `logger.xxx(...)` 调用签名兼容；`pixi run -e dev check` 通过
  - 文件: `interfaces/src/ditto_interfaces/api/routes/backtest.py` (L7, L49)
  - 方案:
    ```python
    # 删除
    import logging
    # 删除
    logger = logging.getLogger(__name__)
    # 新增
    from loguru import logger
    ```
  - 测试: 无需新增（现有路由测试覆盖日志路径）

- [ ] Task 4.2: `trade.py` 路由日志 stdlib→loguru `[S]`
  - 验收: 同 Task 4.1
  - 文件: `interfaces/src/ditto_interfaces/api/routes/trade.py` (L6, L41)
  - 测试: 无需新增

- [ ] Task 4.3: `delivery.py` 日志 stdlib→loguru `[S]`
  - 验收: 同 Task 4.1
  - 文件: `packages/app/src/ditto_app/process/execution/delivery.py` (L12, L17)
  - 测试: 无需新增

- [ ] Task 4.4: `comparison.py` 日志 stdlib→loguru `[S]`
  - 验收: 同 Task 4.1
  - 文件: `packages/app/src/ditto_app/query/comparison.py` (L10, L24)
  - 测试: 无需新增

- [ ] Task 4.5: `NotificationPort` 改为 typing.Protocol `[S]`
  - 验收: `NotificationPort` 继承 `typing.Protocol`；`send` 方法体改为 `...`；现有适配器实现兼容（结构子类型）；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/process/execution/delivery.py` (L22-32)
  - 方案:
    ```python
    from typing import Protocol

    class NotificationPort(Protocol):
        """通知发送协议 — App 层定义，Interfaces 层注入适配器."""

        def send(
            self,
            template: str,
            context: dict[str, Any],
            level: str,
        ) -> dict[str, bool]:
            """发送通知，返回各通道成功/失败映射."""
            ...
    ```
  - 测试: 无需新增（现有 `test_delivery_unit.py` 覆盖适配器）

- [ ] Task 4.6: 提取 `coordinator.py` 重复的 except 块 `[M]`
  - 验收: `_process_fetched_data` (L414-443) 和 `_process_fetched_data_by_instrument` (L634-667) 的双层 except 块被提取为 `_write_data_safe` 方法；行为不变；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/process/ingestion/coordinator.py`
  - 方案: 提取公共方法：
    ```python
    def _write_data_safe(
        self,
        dataset: str,
        df: pl.DataFrame,
        trade_date: date,
        on_duplicate: OnDuplicate,
        *,
        source_ticker: str | None = None,
        event_suffix: str = "",
    ) -> WriteResult | IngestionResult:
        """安全写入数据，失败时返回 IngestionResult."""
        try:
            return self._data_writer.write_data(dataset, df, trade_date, on_duplicate)
        except (
            pl.exceptions.ComputeError, pl.exceptions.SchemaError,
            ValueError, KeyError, TypeError, OSError,
        ) as e:
            logger.warning(
                f"write_data_failed{event_suffix}",
                event="write_data_error",
                dataset=dataset,
                trade_date=trade_date,
                source_ticker=source_ticker,
                error_type=type(e).__name__,
                error=str(e),
            )
            return self._result_handler.handle_unknown_error(dataset, trade_date, e)
        except Exception as e:
            logger.exception(
                f"write_data_failed{event_suffix}_unexpected",
                event="write_data_error",
                dataset=dataset,
                trade_date=trade_date,
                source_ticker=source_ticker,
                error_type=type(e).__name__,
            )
            return self._result_handler.handle_unknown_error(dataset, trade_date, e)
    ```
  - 测试: 无需新增（现有 coordinator 测试覆盖写入成功/失败路径）

- [ ] Task 4.7: 消除 `manual_tracker.py` 嵌套深度 4 `[S]`
  - 验收: `_compute_single_instrument` 最大嵌套 ≤ 3；行为不变；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/process/execution/manual_tracker.py` (L153-160)
  - 方案: 将 sell 方向校验提取为提前 return 模式，将整个 `elif fill.direction == "sell"` 分支提取为 `_apply_sell_fill` 私有方法（与 Phase 5 Task 5.2 合并执行）
  - 测试: 无需新增（现有 `test_manual_tracker_unit.py` 覆盖）

- [ ] Task 4.8: 消除 `replay.py` 嵌套深度 4 `[S]`
  - 验收: `_compare_input_ref_details` 最大嵌套 ≤ 3；行为不变；`pixi run -e dev check` 通过
  - 文件: `packages/engine/src/ditto_engine/backtest/replay.py` (L303-319)
  - 方案: 将 `elif a_ref.data_hash != b_ref.data_hash` 的嵌套逻辑扁平化为提前 continue 模式：
    ```python
    all_ids = sorted(set(a_map) | set(b_map))
    for iid in all_ids:
        a_ref = a_map.get(iid)
        b_ref = b_map.get(iid)
        if a_ref is None:
            diffs.append(f"input_ref_details: {iid} only in replay")
            continue
        if b_ref is None:
            diffs.append(f"input_ref_details: {iid} only in original")
            continue
        if a_ref.data_hash != b_ref.data_hash:
            diffs.append(
                f"data_hash mismatch for {iid}: "
                f"{a_ref.data_hash} vs {b_ref.data_hash}",
            )
    ```
  - 测试: 无需新增（现有 `test_replay_unit.py` 覆盖）

### Phase 5: 可维护维度 — 长函数拆分 + TODO

- [ ] Task 5.1: 拆分 `_build_actual_navs` (95 行) `[M]`
  - 验收: `_build_actual_navs` ≤ 30 行（仅做分支调度）；提取 `_build_actual_navs_simple` 和 `_build_actual_navs_full`；行为不变；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/query/comparison.py` (L246-340)
  - 方案:
    ```python
    def _build_actual_navs(
        fills: list[ManualExecutionFill],
        initial_cash: float,
        price_query: MarketQueryFacade | None = None,
    ) -> list[tuple[str, float]]:
        """从成交记录构建实际 NAV 序列."""
        if not fills:
            return []
        if price_query is None:
            return _build_actual_navs_simple(fills, initial_cash)
        return _build_actual_navs_full(fills, initial_cash, price_query)

    def _build_actual_navs_simple(
        fills: list[ManualExecutionFill],
        initial_cash: float,
    ) -> list[tuple[str, float]]:
        """回退: 无行情数据源时使用简化逻辑（仅扣除费用）."""
        ...

    def _build_actual_navs_full(
        fills: list[ManualExecutionFill],
        initial_cash: float,
        price_query: MarketQueryFacade,
    ) -> list[tuple[str, float]]:
        """完整 NAV 重建 — 逐日重建现金/持仓台账并按收盘价计算 NAV."""
        ...
    ```
  - 测试: 无需新增（现有 `test_build_actual_navs_unit.py` 通过 `_build_actual_navs` 覆盖所有分支）

- [ ] Task 5.2: 拆分 `_compute_single_instrument` (80 行) `[M]`
  - 验收: `_compute_single_instrument` ≤ 35 行；提取 `_apply_buy_fill` 和 `_apply_sell_fill`；行为不变；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/process/execution/manual_tracker.py` (L120-199)
  - 方案: 将 buy/sell 分支各提取为返回 `(new_qty, new_avg_cost, new_total_fees, new_realized_pnl, new_unsettled_buy_quantity)` 的纯函数：
    ```python
    def _apply_buy_fill(
        quantity: int,
        avg_cost: float,
        fill: ManualExecutionFill,
        compute_settlement: Callable[[str, int], str],
        snapshot_date: str,
    ) -> tuple[int, float, float, int]:
        """处理买入成交，返回 (quantity, avg_cost, fee_increment, unsettled_buy_increment)."""
        ...

    def _apply_sell_fill(
        quantity: int,
        avg_cost: float,
        fill: ManualExecutionFill,
    ) -> tuple[int, float, float]:
        """处理卖出成交，返回 (remaining_quantity, fee_increment, realized_pnl_increment)."""
        ...
    ```
  - 测试: 无需新增（现有 `test_manual_tracker_unit.py` 覆盖聚合逻辑）
  - 注意: 与 Task 4.7 合并执行（同时解决嵌套深度问题）

- [ ] Task 5.3: 拆分 `RecordFillHandler.handle` (77 行) `[M]`
  - 验收: `handle` ≤ 35 行；提取 `_validate_intent_match` 和 `_build_fill_dto`；行为不变；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/command/trade.py` (L78-155)
  - 方案:
    ```python
    @staticmethod
    def _validate_intent_match(
        intent_record: TradeIntentRecord,
        command: RecordFillCommand,
    ) -> None:
        """验证 intent 存在且字段一致，不一致时 raise ValueError."""
        ...

    @staticmethod
    def _build_fill_dto(
        command: RecordFillCommand,
        tracker: ManualTracker,
    ) -> ManualExecutionFill:
        """构建 ManualExecutionFill DTO（含交收日期）."""
        ...
    ```
  - 测试: 无需新增（现有 `test_trade_unit.py` 覆盖 handle 完整流程）

- [ ] Task 5.4: 清理 `backtest.py` TODO 注释 `[S]`
  - 验收: `# TODO(R3): Prefect Worker 异步提交` 被替换为正式的规划注释或移除；`pixi run -e dev check` 通过
  - 文件: `interfaces/src/ditto_interfaces/api/routes/backtest.py` (L133-134)
  - 方案: 将 TODO 替换为 docstring 说明当前实现状态：
    ```python
    # V1 使用进程内同步执行，远程 Worker 异步提交待后续迭代实现。
    ```
  - 测试: 无需新增

- [ ] Task 5.5: 清理 `patrol.py` PIT TODO 注释 `[S]`
  - 验收: TODO 被解决或转换为 issue 跟踪；`pixi run -e dev check` 通过
  - 文件: `packages/app/src/ditto_app/process/quality/patrol.py` (L206)
  - 方案: 读取上下文，评估是否应直接修复（`end=trade_date` 前一天）或保留为已知限制。如果是简单修复则直接修复，否则添加 `@deprecated` 风格注释说明原因。
  - 测试: 无需新增

### Phase 6: 文档维度 — API docstring + CLAUDE.md

- [ ] Task 6.1: 补充 `backtest.py` 模块 docstring `[S]`
  - 验收: 模块 docstring 列出所有 12 个端点的路由概览；`pixi run -e dev check` 通过
  - 文件: `interfaces/src/ditto_interfaces/api/routes/backtest.py` (L1)
  - 方案:
    ```python
    """回测 API 路由.

    端点:
    - POST   /backtests/runs                    触发回测
    - POST   /backtests/runs/{id}/cancel         取消回测
    - POST   /backtests/runs/{id}/retry          重试回测
    - GET    /backtests/runs                     列出运行记录
    - GET    /backtests/runs/{id}                获取运行详情
    - GET    /backtests/runs/{id}/trades         成交明细
    - GET    /backtests/runs/{id}/audit          审计记录
    - GET    /backtests/runs/{id}/report         回测报告
    - GET    /backtests/runs/{id}/lineage        运行血统
    - POST   /backtests/runs/{id}/replay         重放验证
    - GET    /backtests/runs/{id}/nav            NAV 序列
    - GET    /backtests/runs/{id}/benchmark      基准 NAV
    """
    ```
  - 测试: 无需新增

- [ ] Task 6.2: 补充 `trade.py` 模块 docstring `[S]`
  - 验收: 模块 docstring 列出所有 9 个端点；`pixi run -e dev check` 通过
  - 文件: `interfaces/src/ditto_interfaces/api/routes/trade.py` (L1)
  - 方案:
    ```python
    """交易闭环 API 路由.

    端点:
    - GET    /trade/intents                       列出交易意图
    - PUT    /trade/intents/{id}/status           更新意图状态
    - POST   /trade/fills                          录入成交
    - GET    /trade/fills                          列出成交记录
    - GET    /trade/positions                      查询持仓快照
    - GET    /trade/pnl                            盈亏汇总
    - GET    /trade/signals/latest                 最新信号
    - GET    /trade/signals/{strategy_id}/intents  信号意图明细
    - GET    /trade/comparison                     回测 vs 实际对比
    """
    ```
  - 测试: 无需新增

- [ ] Task 6.3: 补充 `strategy.py` 模块 docstring `[S]`
  - 验收: 模块 docstring 列出所有 5 个端点；`pixi run -e dev check` 通过
  - 文件: `interfaces/src/ditto_interfaces/api/routes/strategy.py` (L1)
  - 方案:
    ```python
    """策略 API 路由.

    端点:
    - POST   /strategies                          创建策略
    - GET    /strategies                          列出策略
    - GET    /strategies/{id}                     获取策略详情
    - PUT    /strategies/{id}                     更新策略
    - POST   /strategies/{id}/publish             发布策略
    """
    ```
  - 测试: 无需新增

- [ ] Task 6.4: 补充 `universe.py` 模块 docstring `[S]`
  - 验收: 模块 docstring 列出所有 6 个端点；`pixi run -e dev check` 通过
  - 文件: `interfaces/src/ditto_interfaces/api/routes/universe.py` (L1)
  - 方案:
    ```python
    """Universe API 路由.

    端点:
    - GET    /universes                           列出 Universe
    - GET    /universes/{id}                      获取 Universe 详情
    - GET    /universes/{id}/members              查询成分列表
    - POST   /universes                           创建自定义 Universe
    - PUT    /universes/{id}                      更新 Universe
    - DELETE /universes/{id}                      删除 Universe
    """
    ```
  - 测试: 无需新增

- [ ] Task 6.5: 更新 `interfaces/CLAUDE.md` FastAPI 路由分组 `[S]`
  - 验收: CLAUDE.md 包含 4 个 API 路由分组的 prefix/tag 说明；`pixi run -e dev check` 通过
  - 文件: `interfaces/CLAUDE.md` (FastAPI 规范区域)
  - 方案: 在 FastAPI 规范表格后增加路由分组说明：
    ```markdown
    ### API 路由分组

    | Prefix | Tag | 模块 | 说明 |
    |--------|-----|------|------|
    | `/backtests` | backtests | `api/routes/backtest.py` | 回测运行/报告/重放 |
    | `/trade` | trade | `api/routes/trade.py` | 交易闭环（意图/成交/持仓/盈亏/对比） |
    | `/strategies` | strategies | `api/routes/strategy.py` | 策略 CRUD + 发布 |
    | `/universes` | universes | `api/routes/universe.py` | Universe 管理 |
    ```
  - 测试: 无需新增

---

## 执行顺序

```
Phase 1 (P0): 1.1 → 1.2 → 1.3 → 1.4     （可并行，无依赖）
Phase 2 (P1): 2.1 → 2.2 → 2.3            （可并行）
Phase 3 (P2): 3.1 → 3.2 → 3.3 → 3.4      （可并行）
Phase 4 (质量): 4.1-4.4 可并行 → 4.5 → 4.6 → 4.7+5.2 → 4.8
Phase 5 (可维护): 5.1 → 5.3 → 5.4 → 5.5  （5.2 与 4.7 合并）
Phase 6 (文档): 6.1 → 6.2 → 6.3 → 6.4 → 6.5  （可并行）
```

Phase 间串行（前一个 Phase 完成后再启动下一个），Phase 内标注可并行的任务可同时执行。

### 依赖关系

```
Phase 1 ──→ Phase 2 ──→ Phase 3
                           │
                           ▼
Phase 4 (4.1-4.4 并行) ──→ 4.5 ──→ 4.6 ──→ 4.7+5.2 ──→ 4.8
                                                    │
Phase 5 (5.1, 5.3, 5.4, 5.5 可并行) ←─────────────┘
                           │
                           ▼
Phase 6 (6.1-6.5 可并行)
```

## 风险评估

| 任务 | 风险 | 缓解措施 |
|------|------|---------|
| 1.1-1.4 TYPE_CHECKING | 运行时 ImportError | 已验证无循环依赖；`from __future__ import annotations` 保证注解惰性 |
| 2.2 常量提取 | 遗漏引用 | `grep _REGIME_DEFAULT_LOOKBACK` 确认仅 2 处 |
| 2.3 None 防御 | 改变 API 行为 | 仅在异常路径（record=None）改变行为，正常路径不受影响 |
| 3.1-3.2 Barrel 精简 | 外部消费者中断 | 已确认零消费者使用 barrel 路径 |
| 3.3 get_or_create | 不必要的防御 | 保留 create_run 语义，仅在已有记录时跳过创建 |
| 4.1-4.4 日志替换 | logger.xxx 签名不兼容 | loguru logger 兼容 stdlib logging 的 info/warning/error/exception 方法 |
| 4.5 Protocol 改造 | 适配器不兼容 | loguru 使用结构子类型，现有适配器实现自动兼容 |
| 4.6 except 提取 | 日志 event key 变化 | 保持原有 event key 不变，仅 suffix 不同 |
| 5.1-5.3 函数拆分 | 行为回归 | 纯提取重构，不改变任何逻辑；现有测试全覆盖 |
| 6.1-6.4 docstring | 端点列表过时 | 列表从路由装饰器 grep 生成，保证与代码一致 |
