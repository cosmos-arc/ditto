# Phase 2 Part 04: CompositePreTradeCheck V1 + PreTradeContext

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现订单提交前的逐单校验（rolling context + resize recheck）

**Architecture:** PreTradeContext 是 frozen dataclass，每笔订单通过后通过 with_order_accepted() 返回新上下文。CompositePreTradeCheck 组合多条规则，resize 后重检（A1）。V1 仅包含 buying_power + lot_size 两条规则。

**Design Doc:** v3 §6.1 (PreTradeContext), §7.2 (PreTradeRiskCheck)

**Prerequisite:** Part 02 (Planner) + Part 03 (Brokerage) + Phase 0 accounting/

---

## V1 规则范围

| 规则 | V1 | Phase 4 扩展 |
|------|-----|-------------|
| buying_power | ✅ 检查现金 >= 预估成本 | 无变化 |
| lot_size | ✅ quantity >= 100 | 增加 concentration / turnover |
| no_short_sell | ❌ | ✅ |
| price_validity | ❌ | ✅ |
| concentration_pre | ❌ | ✅ |
| daily_turnover_pre | ❌ | ✅ |

## 任务清单

- [ ] Task 4.1: `OrderCheckResult` frozen dataclass `[S]`
  - 验收: decision("accept"/"reject"/"resize"), order_id, resized_quantity?, reason?, triggered_checks(tuple[str])
  - 文件: `packages/core/src/ditto_core/backtest/risk/pre_trade.py`

- [ ] Task 4.2: `PreTradeRiskCheck` Protocol `[S]`
  - 验收: check_order(order, context) → OrderCheckResult
  - 文件: `packages/core/src/ditto_core/backtest/risk/pre_trade.py`

- [ ] Task 4.3: `BuyingPowerCheck` 实现 `[M]`
  - 验收:
    - buying_power >= estimated_cost → accept
    - buying_power < estimated_cost → reject
    - 消费 BuyingPowerModel.available_buying_power() + FeeModel.estimate()
  - 文件: `packages/core/src/ditto_core/backtest/risk/pre_trade.py`

- [ ] Task 4.4: `LotSizeCheck` 实现 `[S]`
  - 验收:
    - quantity >= lot_size → pass (不拦截)
    - quantity < lot_size → resize to lot_size
  - 文件: `packages/core/src/ditto_core/backtest/risk/pre_trade.py`

- [ ] Task 4.5: `CompositePreTradeCheck` 实现 `[M]`
  - 验收:
    - resize 后重检（A1）: lot_size resize 400 → buying_power 仍检查
    - MAX_RESIZE_ITERATIONS = 3
    - 所有 check 通过 → accept（含 triggered_checks）
    - reject → 立即返回
    - resize 循环 → reject(reason="resize loop detected")
  - 文件: `packages/core/src/ditto_core/backtest/risk/pre_trade.py`

- [ ] Task 4.6: `PreTradeContext` frozen dataclass `[L]`
  - 验收:
    - with_order_accepted(buy) → reserved_cash 减少, frozen 增加, pending_buy_value 增加
    - with_order_accepted(sell) → available_quantity 递减 (B3)
    - _estimate_order_cost() → price × quantity + fee_estimate
    - _ticket_from_order() → OrderTicket(order=order)
  - 文件: `packages/core/src/ditto_core/backtest/engine.py`
  - 关键: F1 rolling context — 保持 frozen 语义，返回新实例

- [ ] Task 4.7: 包导出 `[S]`
  - 文件: `packages/core/src/ditto_core/backtest/__init__.py`, `backtest/risk/__init__.py`

- [ ] Task 4.8: 单元测试 `[M]`
  - 文件: `packages/core/tests/unit/backtest/test_pre_trade_unit.py`
  - 场景:
    - buying_power 充足 → accept
    - buying_power 不足 → reject
    - lot_size resize → resize(100)
    - lot_size resize 后 buying_power 不够 → reject (A1 重检)
    - MAX_RESIZE_ITERATIONS → reject("resize loop detected")
    - rolling context: 第二笔买单看到第一笔的 reserved_cash (F1)
    - rolling context: 卖出递减 available_quantity (B3)
    - triggered_checks 正确记录命中的 check id 链路 (R2)

---

## 文件清单

```
packages/core/src/ditto_core/backtest/
├── __init__.py                # [新增]
├── engine.py                  # [新增] PreTradeContext (EngineLoop 的其他部分 Part 05 补充)
└── risk/
    ├── __init__.py            # [新增]
    └── pre_trade.py           # [新增] PreTradeRiskCheck / CompositePreTradeCheck / BuyingPowerCheck / LotSizeCheck / OrderCheckResult

packages/core/tests/unit/backtest/
└── test_pre_trade_unit.py     # [新增]
```

## 质量门禁

```bash
pixi run -e dev check
```
