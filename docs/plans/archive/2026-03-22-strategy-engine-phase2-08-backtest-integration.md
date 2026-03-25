# Phase 2 Part 08: 回测集成测试

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 端到端验证回测闭环 — etf_rotation 策略 3-5 日快照测试 + 不变量测试

**Architecture:** 使用真实组件（非 mock）组装完整回测引擎，用固定 parquet 数据验证输出确定性。集成测试确保所有模块正确协作。

**Design Doc:** v3 §10 (测试策略), §10.3 (各模块测试重点), §10.6 (完整不变量清单)

**Prerequisite:** Part 01-07 全部完成

---

## 任务清单

- [x] Task 8.1: 测试 fixture — 3 日快照数据 `[M]`
  - 验收: 准备 3 个交易日的 parquet 数据 + etf_rotation 策略配置 + EngineConfig
  - 文件: `packages/core/tests/integration/backtest/conftest.py`
  - 数据: 3 个 ETF 标的 × 3 个交易日 × OHLCV
  - 策略: etf_rotation（Phase 1 模板），V1 每日调仓

- [x] Task 8.2: etf_rotation 回测快照测试 `[M]`
  - 验收: 固定输入 → 期望 NAV 序列 + fill_log + trade_log
  - 文件: `packages/core/tests/integration/backtest/test_backtest_snapshot.py`
  - 场景:
    - 3 日回测 → 期望 final_nav 在合理范围
    - 调仓日 → 期望正确数量的 orders + fills
    - 首日买入所有 ETF（空仓 → 等权配置）

- [x] Task 8.3: 不变量测试 `[M]`
  - 验收: 回测过程中不变量始终成立（16 个测试，覆盖 12 不变量）
  - 文件: `packages/core/tests/integration/backtest/test_backtest_invariants.py`
  - 不变量清单:
    - ✅ cash_conservation (buy/sell)
    - ✅ no_oversell (brokerage + pre_trade_context)
    - ✅ terminal_state_irreversible (FILLED + INVALID)
    - ✅ cash_book_immutability (frozen)
    - ✅ order_ticket_immutability (frozen)
    - ✅ stats_use_post_fill_snapshot (R3)
    - ✅ no_fill_event_on_no_fill (R8)
    - ✅ risk_lock_clears_next_day (R4)
    - ✅ rolling_pre_trade_context (F1)
    - ✅ pending_aware_planner (F2)
    - ✅ planner_lock (S1)
    - ✅ resize_triggers_recheck (A1)

- [x] Task 8.4: 5 日扩展快照测试 `[M]`
  - 验收: 5 个交易日 + 多次调仓 → NAV 曲线连续 + 交易明细完整
  - 文件: `packages/core/tests/integration/backtest/test_backtest_snapshot.py`
  - 场景:
    - 5 日回测，V1 每日调仓
    - NAV 在合理范围，成交价格在 OHLC 范围内

---

## 文件清单

```
packages/core/tests/integration/backtest/
├── __init__.py                # [新增]
├── conftest.py                # [新增] 共享 fixture
├── test_backtest_snapshot.py  # [新增] 快照测试
└── test_backtest_invariants.py # [新增] 不变量测试
```

## 质量门禁

```bash
pixi run -e dev check          # 子计划完成后
pixi run -e dev ci             # Phase 2 全部完成后
```

## Phase 2 完成标志

所有集成测试通过后，Phase 2 达成里程碑：
- ETF 轮动策略 BACKTEST 闭环
- 基础统计报告（NAV 曲线 + 交易明细 + PortfolioStatistics）
- 快照测试 + 不变量测试全部通过
