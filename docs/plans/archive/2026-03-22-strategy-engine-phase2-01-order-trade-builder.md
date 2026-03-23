# Phase 2 Part 01: Order 模型 + TradeBuilder

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 定义执行层的 Order / OrderEvent 模型，实现 FIFO trade matching

**Architecture:** Order 和 OrderEvent 是 frozen dataclass，OrderTicket（Phase 0 accounting）关联 Order。TradeBuilder 消费 FillEvent，按 FIFO 协议匹配 entry/exit，产出 TradeRecord。

**Design Doc:** v3 §4.1 (Order), §8.2 (TradeBuilder)

**Prerequisite:** Phase 0 accounting/ 已提交

---

## 任务清单

- [ ] Task 1.1: `OrderType` / `OrderDirection` 枚举 `[S]`
  - 验收: MARKET / LIMIT / STOP_MARKET / MARKET_ON_CLOSE; BUY / SELL
  - 文件: `packages/core/src/ditto_core/execution/orders.py`

- [ ] Task 1.2: `Order` frozen dataclass `[S]`
  - 验收: order_id, instrument_id, order_type, direction, quantity, price?, stop_price?, created_at, strategy_run_id, with_quantity() → new Order
  - 文件: `packages/core/src/ditto_core/execution/orders.py`

- [ ] Task 1.3: `OrderEvent` frozen dataclass `[S]`
  - 验收: order_id, status(OrderStatus), fill_price?, fill_quantity, fee, message?, timestamp
  - 文件: `packages/core/src/ditto_core/execution/orders.py`

- [ ] Task 1.4: `TradeRecord` frozen dataclass `[S]`
  - 验收: trade_id, instrument_id, direction, entry_date, exit_date?, entry_price, exit_price?, quantity, gross_pnl?, fees, net_pnl?, holding_days?, return_pct?, entry_order_ids, exit_order_ids
  - 文件: `packages/core/src/ditto_core/execution/trade_builder.py`

- [ ] Task 1.5: `TradeMatchingMethod` 枚举 + `TradeBuilder` Protocol `[S]`
  - 验收: FIFO / FLAT_TO_FLAT; on_fill(fill, account_view), get_open_trades(), get_closed_trades(), flush()
  - 文件: `packages/core/src/ditto_core/execution/trade_builder.py`

- [ ] Task 1.6: `FifoTradeBuilder` 实现 `[M]`
  - 验收: FIFO 匹配逻辑 — 买入创建 open trade，卖出按 FIFO 关闭最早 open trade
  - 文件: `packages/core/src/ditto_core/execution/trade_builder.py`
  - 测试:
    - 单笔开仓 + 平仓 → 一笔 closed trade
    - 多笔开仓（同标的）+ 一笔卖出 → FIFO 关闭最早
    - 部分平仓 → 关闭 + 剩余 open
    - flush() → 返回所有未关闭的 open trades 并清空
    - 卖出数量超过 open trades 总量 → 忽略超额部分（不应发生，防御性处理）

- [ ] Task 1.7: 包导出更新 `[S]`
  - 验收: `execution/__init__.py` 导出 Order, OrderType, OrderDirection, OrderEvent, TradeRecord, TradeBuilder, FifoTradeBuilder, TradeMatchingMethod
  - 文件: `packages/core/src/ditto_core/execution/__init__.py`

- [ ] Task 1.8: 单元测试 `[M]`
  - 文件:
    - `packages/core/tests/unit/execution/test_orders_unit.py`
    - `packages/core/tests/unit/execution/test_trade_builder_unit.py`

---

## 文件清单

```
packages/core/src/ditto_core/execution/
├── __init__.py           # 更新导出
├── orders.py             # [新增] Order / OrderType / OrderDirection / OrderEvent
└── trade_builder.py      # [新增] TradeBuilder / FifoTradeBuilder / TradeRecord / TradeMatchingMethod

packages/core/tests/unit/execution/
├── test_orders_unit.py           # [新增]
└── test_trade_builder_unit.py    # [新增]
```

## 质量门禁

```bash
pixi run -e dev check
```
