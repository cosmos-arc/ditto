# Phase 2 Part 05: EngineLoop 骨架 + 日历步进

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现回测引擎核心编排器 — 日历步进 + 调仓触发 + 状态编排

**Architecture:** EngineLoop 是回测引擎的主循环，持有所有组件引用。每个交易日执行 _step()：PostTrade(空) → Pipeline → Planner → PreTrade(rolling) → Brokerage.process_pending。V1 不含完整统计收集（Part 07 补充）。

**Design Doc:** v3 §6.1 (EngineLoop), §6.2 (DataFeed), §6.3 (RESEARCH/RECOMMENDATION 分离)

**Prerequisite:** Part 02 + Part 03 + Part 04 + Phase 1 strategy/pipeline

---

## V1 范围

| 功能 | V1 | 后续 Phase |
|------|-----|-----------|
| 日历步进 | ✅ | 无变化 |
| 调仓触发 | ✅ ExecutionSpec.trigger | 无变化 |
| Pipeline 调用 | ✅ | 无变化 |
| Planner 调用 | ✅ | 无变化 |
| PreTrade rolling | ✅ | Phase 4 扩展规则 |
| Brokerage 成交 | ✅ | Phase 3 替换 Reality Model |
| PostTrade 扫描 | ❌ 空（占位） | Phase 4 |
| 统计收集 | ❌ Part 07 补充 | Part 07 |
| RiskLock 管理 | ✅ 骨架（V1 无实际锁定） | Phase 4 |
| LIVE 模式 | ❌ | Phase 6 |

## 任务清单

- [ ] Task 5.1: `EngineConfig` frozen dataclass `[S]`
  - 验收: start_date, end_date, initial_cash, benchmark_id?, mode=BACKTEST, trade_matching=FIFO
  - 文件: `packages/core/src/ditto_core/backtest/engine.py`

- [ ] Task 5.2: `EngineMode` StrEnum `[S]`
  - 验收: BACKTEST / LIVE（V1 只实现 BACKTEST）
  - 文件: `packages/core/src/ditto_core/backtest/engine.py`

- [ ] Task 5.3: `EngineResult` dataclass `[S]`
  - 验收: run_id, period, final_nav, total_trades, orders, fills, account_view（最终状态）
  - 文件: `packages/core/src/ditto_core/backtest/engine.py`

- [ ] Task 5.4: `DataFeed` Protocol + `Slice` frozen dataclass `[S]`
  - 验收: DataFeed.trading_days() → list[str], get_slice(date) → Slice; Slice.trade_date, step_time(datetime, B4), bars(dict[str, MarketSnapshot]), benchmark_close?
  - 文件: `packages/core/src/ditto_core/backtest/data_feed.py`

- [ ] Task 5.5: `MarketSnapshot` frozen dataclass `[S]`
  - 验收: trade_date, instrument_id, open, high, low, close, prev_close, volume, amount, is_suspended, limit_up?, limit_down?, avg_volume_20d?
  - 文件: `packages/core/src/ditto_core/backtest/data_feed.py`

- [ ] Task 5.6: `EngineLoop.__init__()` 组装依赖 `[S]`
  - 验收: 注入 config, pipeline, planner, brokerage, pre_trade_check, data_feed, buying_power_model, fee_model; 初始化 StrategyContext + 空的 risk_locked_instruments
  - 文件: `packages/core/src/ditto_core/backtest/engine.py`

- [ ] Task 5.7: `EngineLoop._step()` 核心逻辑 `[XL]`
  - 验收:
    1. slice = data_feed.get_slice(date)
    2. PostTrade 扫描（V1: 空操作，占位接口）
    3. if is_rebalance_day: pipeline.run → planner.plan → pre_trade check (rolling) → place_order
    4. fills = brokerage.process_pending(slice)
    5. account_view 刷新（成交后快照, R3）
  - 文件: `packages/core/src/ditto_core/backtest/engine.py`
  - 关键:
    - F1: _build_pre_trade_context() 构建 rolling context
    - A1: PreTrade check 逐单执行，resize 后用 resized_quantity
    - B1: accept 路径统一处理 resized_quantity
    - S1: planner.plan() 传入 locked_instruments
    - R4: 每个 step 开始时 clear_locks()

- [ ] Task 5.8: `EngineLoop._build_pre_trade_context()` `[M]`
  - 验收: 构建 PreTradeContext(account_view, slice, rules, buying_power_model, fee_model, pending_tickets=())
  - 文件: `packages/core/src/ditto_core/backtest/engine.py`

- [ ] Task 5.9: `EngineLoop.run()` 日历推进 `[M]`
  - 验收: 遍历 trading_days → _step(date) → 构建 EngineResult
  - 文件: `packages/core/src/ditto_core/backtest/engine.py`

- [ ] Task 5.10: R4 RiskLock 管理 `[M]`
  - 验收:
    - _context.risk_locked_instruments: dict[str, str]
    - lock_instrument(id, reason) / is_locked(id) / clear_locks()
    - _execute_risk_actions(actions, slice): V1 遍历但无实际操作（PostTrade 为空）
    - clear_locks() 在每个 step 开始时调用
  - 文件: `packages/core/src/ditto_core/backtest/engine.py`

- [ ] Task 5.11: 包导出 `[S]`
  - 文件: `packages/core/src/ditto_core/backtest/__init__.py`

- [ ] Task 5.12: 单元测试 `[M]`
  - 文件: `packages/core/tests/unit/backtest/test_engine_loop_unit.py`
  - 场景:
    - 3 日步进 → EngineResult 包含正确的 final_nav
    - 空仓首次建仓 → Pipeline + Planner + Brokerage 正确串联
    - 非调仓日 → 跳过 Pipeline，只执行 process_pending
    - pending-aware → 有 pending sell 时不重复生成卖单
    - PreTrade rolling context → 第二笔买单看到第一笔的 reserved_cash
    - clear_locks → 每日清除
    - is_rebalance_day → 正确判断调仓日

---

## 文件清单

```
packages/core/src/ditto_core/backtest/
├── __init__.py                # 更新导出
├── engine.py                  # [新增] EngineLoop / EngineConfig / EngineMode / EngineResult
└── data_feed.py               # [新增] DataFeed Protocol / Slice / MarketSnapshot

packages/core/tests/unit/backtest/
└── test_engine_loop_unit.py   # [新增]
```

## 质量门禁

```bash
pixi run -e dev check
```
