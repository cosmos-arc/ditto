# Code Review 全量修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 PR #62 code review 中全部 20+ 分问题（7 项），确保代码质量达标

**Architecture:** 纯修复计划，无架构变更。按置信度降序排列：2 项 working tree 已有修复（需验证提交），5 项新增修复

**Tech Stack:** Python 3.12, polars, pytest

---

## 问题总览

| # | 问题 | 评分 | 状态 | 复杂度 |
|---|------|------|------|--------|
| 1 | NAV fallback 非累积 bug | 100 | working tree 已修复 | S |
| 2 | `_KNOWN_DATASETS` 遗漏 `index_weight` | 100 | working tree 已修复 | S |
| 3 | `execution_delay` 尾部信号丢失 | 75 | 需改逻辑 + 文档 | M |
| 4 | "Port 层" 术语过时（4 文件） | 75 | 文档替换 | S |
| 5 | `hasattr` 冗余守卫 | 75 | 删除死代码 | S |
| 6 | docstring 缺 `execution_delay` + `parent_run_id` | 50 | 补文档 | S |
| 7 | Protocol 重复 `...` | 75 | 删除多余行 | S |

---

## Task 1: 验证并提交 NAV fallback + _KNOWN_DATASETS 修复

**Files:**
- Modify: `packages/app/src/ditto_app/query/comparison.py:160-167`
- Modify: `packages/app/tests/unit/query/test_build_actual_navs_unit.py`
- Modify: `interfaces/src/ditto_interfaces/api/routes/ingestion.py:26-48`

**说明**: Working tree 已有修复，验证正确性后提交。

**Step 1: 验证 NAV fallback 修复**

修复内容：`setdefault(trade_date, initial_cash)` → 运行 `cash` 变量累积扣费。

Run: `pixi run -e dev pytest packages/app/tests/unit/query/test_build_actual_navs_unit.py -v`
Expected: PASS

**Step 2: 验证 _KNOWN_DATASETS 修复**

修复内容：在 `index_daily` 后添加 `index_weight`。

Run: `pixi run -e dev pytest interfaces/tests/ -k "ingestion" -v --timeout=30 2>/dev/null || echo "no matching tests"`
Expected: 无失败

**Step 3: 提交修复**

```bash
git add packages/app/src/ditto_app/query/comparison.py packages/app/tests/unit/query/test_build_actual_navs_unit.py interfaces/src/ditto_interfaces/api/routes/ingestion.py
git commit -m "fix: NAV fallback 累积计算 + _KNOWN_DATASETS 补充 index_weight"
```

---

## Task 2: execution_delay 尾部信号 flush

**Files:**
- Modify: `packages/engine/src/ditto_engine/backtest/engine.py:336-354`
- Modify: `packages/engine/src/ditto_engine/backtest/config.py:34-47`
- Modify: `packages/engine/tests/unit/backtest/test_engine_loop_unit.py:1072-1097`

**说明**: 在 `run()` 主循环结束后，对 `_signal_queue` 中剩余信号执行 flush——对每个剩余信号执行 PlanningStep + PreTradeStep + ExecutionStep 链。同时在 `EngineConfig.execution_delay` docstring 中说明尾部 flush 行为。

**Step 1: 写失败测试 — 验证尾部信号被 flush**

在 `test_engine_loop_unit.py` 的 `TestExecutionDelay` 类中添加测试：

```python
def test_delay_1_trailing_signal_flushed(self) -> None:
    """execution_delay=1: 回测结束后尾部信号被 flush 执行。"""
    loop, pipeline, planner, brokerage = self._make_delay_loop(
        execution_delay=1,
    )
    loop.run()

    # 3 天每天生成信号，Day 0 信号 Day 1 执行，Day 1 信号 Day 2 执行，
    # Day 2 信号在 run() 结束时 flush → place_order 3 次
    assert pipeline.run.call_count == 3
    assert brokerage.place_order.call_count == 3
    assert planner.plan.call_count == 3
```

Run: `pixi run -e dev pytest packages/engine/tests/unit/backtest/test_engine_loop_unit.py::TestExecutionDelay::test_delay_1_trailing_signal_flushed -v`
Expected: FAIL — `brokerage.place_order.call_count` 为 2 而非 3

**Step 2: 更新已有测试期望**

将 `test_delay_1_first_day_no_execution` 的期望从 2 改为 3：

```python
def test_delay_1_first_day_no_execution(self) -> None:
    """execution_delay=1: 首日信号入队延迟，但尾部信号在 run() 结束时 flush → 3 天 3 次执行。"""
    loop, pipeline, _planner, brokerage = self._make_delay_loop(
        execution_delay=1,
    )
    loop.run()

    assert pipeline.run.call_count == 3
    # 首日信号入队，Day 1 执行；Day 1 信号 Day 2 执行；Day 2 信号 flush → 3 次
    assert brokerage.place_order.call_count == 3
```

更新 `test_delay_1_signal_executed_next_day`：

```python
def test_delay_1_signal_executed_next_day(self) -> None:
    """execution_delay=1: Day 0 的信号在 Day 1 执行（planner 收到延迟信号）。"""
    targets = [_make_target(d) for d in DAYS]
    loop, _pipeline, planner, _brokerage = self._make_delay_loop(
        execution_delay=1,
        targets=targets,
    )
    loop.run()

    # Day 1 执行 Day 0 信号, Day 2 执行 Day 1 信号, flush 执行 Day 2 信号 → 3 次
    assert planner.plan.call_count == 3
    first_call_target = planner.plan.call_args_list[0][1]["target"]
    assert first_call_target is targets[0]
```

**Step 3: 实现 `_flush_delayed_signals`**

在 `engine.py` 的 `run()` 方法中，主循环结束后、获取 `account_view` 之前，添加 flush 逻辑：

```python
        # flush 延迟信号 -- 回测结束时执行队列中剩余的延迟信号
        while self._execution_delay > 0 and self._signal_queue:
            signal = self._signal_queue.popleft()
            logger.info(
                "Flushing delayed signal after last trading day",
            )
            self._execute_delayed_signal(signal)
```

添加私有方法 `_execute_delayed_signal`（放在 `_dequeue_delayed_signal` 之后）：

```python
    def _execute_delayed_signal(self, signal: TargetPortfolioLike) -> None:
        """对延迟信号执行 Planning → PreTrade → Execution 链（用于尾部 flush）。"""
        # 复用最后交易日的数据切片
        last_date = self._trading_days[-1] if self._trading_days else ""
        ctx = StepContext(date=last_date, is_rebalance_day=True)
        ctx.target_portfolio = signal

        for step in self._steps:
            if isinstance(step, PlanningStep):
                ctx.target_portfolio = signal
                ctx.is_rebalance_day = True
                result = step.execute(ctx)
                if not result.success:
                    step_name = type(step).__name__
                    logger.warning(
                        "Flush PlanningStep failed: {}",
                        step_name,
                    )
                    return
                # PlanningStep 后清除信号，避免 StrategyStep 再次入队
                ctx.target_portfolio = None
            elif isinstance(step, (PreTradeStep, type(self._steps[4]) if len(self._steps) > 4 else object)):
                result = step.execute(ctx)
                if not result.success:
                    return
            elif isinstance(step, ExecutionStep):
                result = step.execute(ctx)
                if not result.success:
                    return
                # 累积成交
                self._fills.extend(ctx.step_fills)
                self._orders.extend(ctx.step_orders)
                return

        # 累积成交和订单
        self._fills.extend(ctx.step_fills)
        self._orders.extend(ctx.step_orders)
```

**注意**: 上述实现需要更精确地引用 Step 类型。更简洁的方案是直接从 `_steps` 中提取 PlanningStep / PreTradeStep / ExecutionStep 子链执行：

```python
    def _execute_delayed_signal(self, signal: TargetPortfolioLike) -> None:
        """对延迟信号执行 Planning → PreTrade → Execution 子链（尾部 flush）。"""
        from ditto_engine.backtest.steps.planning import PlanningStep
        from ditto_engine.backtest.steps.pre_trade import PreTradeStep
        from ditto_engine.backtest.steps.execution import ExecutionStep

        last_date = self._trading_days[-1] if self._trading_days else ""
        ctx = StepContext(date=last_date, is_rebalance_day=True)
        ctx.target_portfolio = signal

        for step in self._steps:
            if isinstance(step, PlanningStep):
                ctx.target_portfolio = signal
                ctx.is_rebalance_day = True
            elif isinstance(step, StrategyStep):
                # 跳过 StrategyStep（不生成新信号）
                continue
            elif isinstance(step, (PreTradeStep, ExecutionStep)):
                pass  # 正常执行
            else:
                continue  # 跳过 DataFetchStep / RiskScanStep / AuditStep

            result = step.execute(ctx)
            if not result.success:
                step_name = type(step).__name__
                logger.warning("Flush step {} failed", step_name)
                return

        self._fills.extend(ctx.step_fills)
        self._orders.extend(ctx.step_orders)
```

需要额外导入 `StrategyStep`：

```python
from ditto_engine.backtest.steps.strategy import StrategyStep
```

**Step 4: 运行测试验证**

Run: `pixi run -e dev pytest packages/engine/tests/unit/backtest/test_engine_loop_unit.py::TestExecutionDelay -v`
Expected: ALL PASS

**Step 5: 补充 EngineConfig docstring**

在 `config.py` 的 `EngineConfig` Attributes 中添加：

```
        execution_delay: 信号延迟执行天数 (T+N)。尾部未执行的信号在 run() 结束时自动 flush。
```

**Step 6: 提交**

```bash
git add packages/engine/src/ditto_engine/backtest/engine.py packages/engine/src/ditto_engine/backtest/config.py packages/engine/tests/unit/backtest/test_engine_loop_unit.py
git commit -m "fix: execution_delay 尾部信号 flush — 回测结束时不丢失延迟信号"
```

---

## Task 3: 清理 "Port 层" 过时术语

**Files:**
- Modify: `packages/data/src/ditto_data/models/common.py:234`
- Modify: `packages/app/tests/unit/process/strategy/test_backtest_service_unit.py:1`
- Modify: `packages/app/tests/unit/process/strategy/test_port_strategy_run_service_unit.py:1`
- Modify: `packages/app/tests/unit/process/strategy/test_artifact_writer_unit.py:1`

**Step 1: 替换术语**

| 文件 | 原文 | 替换为 |
|------|------|--------|
| `common.py:234` | `Port 层 IngestionCoordinator 路由` | `App 层 IngestionCoordinator 路由` |
| `test_backtest_service_unit.py:1` | `Port 层回测编排服务` | `回测编排服务` |
| `test_port_strategy_run_service_unit.py:1` | `Port 层策略运行编排服务` | `策略运行编排服务` |
| `test_artifact_writer_unit.py:1` | `Port 层产物序列化` | `产物序列化` |

**Step 2: 验证无回归**

Run: `pixi run -e dev pytest packages/app/tests/unit/process/strategy/ -v --timeout=30`
Expected: ALL PASS

**Step 3: 提交**

```bash
git add packages/data/src/ditto_data/models/common.py packages/app/tests/unit/process/strategy/test_backtest_service_unit.py packages/app/tests/unit/process/strategy/test_port_strategy_run_service_unit.py packages/app/tests/unit/process/strategy/test_artifact_writer_unit.py
git commit -m "fix: 清理过时 'Port 层' 术语 → App 层"
```

---

## Task 4: 删除 hasattr 冗余守卫

**Files:**
- Modify: `packages/app/src/ditto_app/process/execution/backtest_process.py:439-441`

**Step 1: 删除 hasattr 检查**

将：
```python
        if hasattr(data_feed, "get_history"):
            history_df = data_feed.get_history(instrument_ids, ctx.date, lookback_days)
```

改为：
```python
        history_df = data_feed.get_history(instrument_ids, ctx.date, lookback_days)
```

并调整缩进（去掉一级 if 嵌套，保持 `if not history_df.is_empty():` 的缩进不变）。

**Step 2: 验证**

Run: `pixi run -e dev pytest packages/app/tests/unit/process/execution/ -v --timeout=30`
Expected: ALL PASS

**Step 3: 提交**

```bash
git add packages/app/src/ditto_app/process/execution/backtest_process.py
git commit -m "refactor: 删除 hasattr(data_feed, 'get_history') 冗余守卫 — Protocol 保证方法存在"
```

---

## Task 5: 补全 docstring 缺失字段

**Files:**
- Modify: `packages/engine/src/ditto_engine/backtest/config.py:34-47`
- Modify: `packages/app/src/ditto_app/process/execution/backtest_process.py:81-92`

**Step 1: EngineConfig 补充 execution_delay**

在 `config.py` Attributes 列表中 `engine_version` 之后添加：

```
        execution_delay: 信号延迟执行天数 (T+N)，尾部信号自动 flush
```

**Step 2: BacktestServiceConfig 补充 parent_run_id + execution_delay**

在 `backtest_process.py` Attributes 列表中 `engine_version` 之后添加：

```
        parent_run_id: 父运行 ID（用于重试/衍生场景）
        execution_delay: 信号延迟执行天数
```

**Step 3: 提交**

```bash
git add packages/engine/src/ditto_engine/backtest/config.py packages/app/src/ditto_app/process/execution/backtest_process.py
git commit -m "docs: 补全 EngineConfig / BacktestServiceConfig docstring 缺失字段"
```

---

## Task 6: 删除 Protocol 重复省略号

**Files:**
- Modify: `packages/engine/src/ditto_engine/risk/post_trade.py:131-132`

**Step 1: 删除多余的 `...`**

将：
```python
    def reset(self) -> None:
        """重置内部状态，确保跨回测隔离。"""
        ...
        ...
```

改为：
```python
    def reset(self) -> None:
        """重置内部状态，确保跨回测隔离。"""
        ...
```

**Step 2: 验证**

Run: `pixi run -e dev pytest packages/engine/tests/unit/risk/ -v --timeout=30`
Expected: ALL PASS

**Step 3: 提交**

```bash
git add packages/engine/src/ditto_engine/risk/post_trade.py
git commit -m "fix: 删除 PostTradeRiskGuard.reset() 重复省略号"
```

---

## Task 7: 全量验证

**Step 1: 运行完整检查**

Run: `pixi run -e dev check`
Expected: ALL PASS（lint + fmt + type + test --fast）

**Step 2: 确认所有修改已提交**

Run: `git status`
Expected: clean（或仅有 docs/plans/ 未提交的计划文件）
