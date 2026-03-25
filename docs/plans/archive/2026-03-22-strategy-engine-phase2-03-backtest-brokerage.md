# Phase 2 Part 03: BacktestBrokerage 简化版

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现回测 Brokerage — 订单提交 + 成交模拟 + Account 状态更新

**Architecture:** BacktestBrokerage 是 state owner，持有 Account 实例。process_pending 遍历 pending orders → FillModel.try_fill → Account.apply_fill → OrderTicket 更新。简化版 Reality Model 用简单规则替代 A 股完整规则。

**Design Doc:** v3 §4.4 (Brokerage), §5 (Reality Model), §5.3 (四大模型)

**Prerequisite:** Part 01 (Order + FillOutcome) + Phase 0 accounting/

---

## 简化 Reality Model

| 模型 | Phase 2 简化版 | Phase 3 完整版 |
|------|---------------|---------------|
| FillModel | MARKET → close±slippage; LIMIT → 价格范围检查 | AShareFillModel (涨跌停/停牌/集合竞价) |
| FeeModel | max(5, amount × 0.03%) | AShareFeeModel (印花税/过户费/最低5元) |
| SlippageModel | 固定 2bp | VolumeShareSlippage |
| SettlementModel | is_tradable() 永远 True | AShareSettlementModel (T+0/T+1) |

## 任务清单

- [ ] Task 3.1: `Brokerage` Protocol `[S]`
  - 验收: connect(), get_account() → AccountView, place_order(order) → OrderTicket, cancel_order(id) → bool, process_pending(slice) → tuple[FillEvent]
  - 文件: `packages/core/src/ditto_core/execution/brokerage.py`

- [ ] Task 3.2: `SimpleFillModel` `[S]`
  - 验收:
    - MARKET 单 → Filled(fill_price = close + slippage)
    - LIMIT 单 + 价格在范围内 → Filled
    - LIMIT 单 + 价格超出范围 → NoFill("price_out_of_range", can_retry=False)
  - 文件: `packages/core/src/ditto_core/execution/reality/fill.py`

- [ ] Task 3.3: `SimpleFeeModel` `[S]`
  - 验收: fee = max(5.0, trade_amount × 0.0003)
  - 文件: `packages/core/src/ditto_core/execution/reality/fee.py`

- [ ] Task 3.4: `FixedBpsSlippage` `[S]`
  - 验收: slippage = price × bps / 10000 (默认 2bp)
  - 文件: `packages/core/src/ditto_core/execution/reality/slippage.py`

- [ ] Task 3.5: `SimpleSettlementModel` `[S]`
  - 验收: is_tradable() → True（所有资产随时可交易）
  - 文件: `packages/core/src/ditto_core/execution/reality/settlement.py`

- [ ] Task 3.6: `BacktestBrokerage` 实现 `[L]`
  - 验收:
    - place_order → OrderBook.submit → 返回 OrderTicket
    - process_pending → 遍历 pending → try_fill → apply_fill → update ticket
    - Filled → OrderTicket.with_fill() + Account.apply_fill()
    - NoFill(can_retry=True) → 保留 pending 状态
    - NoFill(can_retry=False) → OrderTicket.with_invalid() (B2)
    - get_account → AccountView (frozen snapshot)
    - cancel_order → OrderBook.cancel()
  - 文件: `packages/core/src/ditto_core/execution/brokerage.py`
  - 关键: B4 时间源必须使用 slice.step_time，禁止 datetime.now()

- [ ] Task 3.7: `BrokerageModel` 组合 `[S]`
  - 验收: 打包 fill_model + slippage_model + fee_model + settlement_model
  - 文件: `packages/core/src/ditto_core/execution/reality/__init__.py`

- [ ] Task 3.8: 包导出更新 `[S]`
  - 验收: execution/__init__.py 导出 Brokerage, BacktestBrokerage, SimpleFillModel, SimpleFeeModel, FixedBpsSlippage, SimpleSettlementModel, BrokerageModel
  - 文件: `packages/core/src/ditto_core/execution/__init__.py`

- [ ] Task 3.9: 单元测试 `[M]`
  - 文件:
    - `packages/core/tests/unit/execution/test_brokerage_unit.py`
    - `packages/core/tests/unit/execution/test_fill_model_unit.py`
    - `packages/core/tests/unit/execution/test_fee_model_unit.py`
    - `packages/core/tests/unit/execution/test_slippage_unit.py`
  - 场景:
    - place_order + process_pending → Account 状态正确更新
    - FIFO ticket 状态更新 (NEW → SUBMITTED → FILLED)
    - NoFill can_retry=False → INVALID 终态 (B2)
    - NoFill can_retry=True → 保持 SUBMITTED
    - 部分成交 → PARTIALLY_FILLED
    - cancel_order → CANCELED
    - 终态不可逆: FILLED → cancel → StateTransitionError
    - FillOutcome 正确: MARKET 成交 / LIMIT 超价拒绝

---

## 文件清单

```
packages/core/src/ditto_core/execution/
├── __init__.py                # 更新导出
├── brokerage.py               # [新增] Brokerage / BacktestBrokerage
└── reality/                   # [新增目录]
    ├── __init__.py            # BrokerageModel
    ├── fill.py                # SimpleFillModel
    ├── fee.py                 # SimpleFeeModel
    ├── slippage.py            # FixedBpsSlippage
    └── settlement.py          # SimpleSettlementModel

packages/core/tests/unit/execution/
├── test_brokerage_unit.py     # [新增]
├── test_fill_model_unit.py    # [新增]
├── test_fee_model_unit.py     # [新增]
└── test_slippage_unit.py      # [新增]
```

## 质量门禁

```bash
pixi run -e dev check
```
