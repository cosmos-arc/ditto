# B1 · 成交量约束 fill（回测真实性）实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** 回测大单按成交量 participation rate 截断、支持部分成交，消除"系统性乐观"，使回测收益/成本可信。

**Architecture:** fill 合约层**本就支持部分成交**（`_make_filled` 的 `filled_quantity`/`leaves_quantity`，`ClosingAuctionFillModel` 已用 participation rate）。两处真实改动：① `AShareFillModel` 连续竞价路径（`_fill_market_or_limit`）加 participation rate 截断；② 回测层 `BacktestBrokerage._build_fill_event` 移除 all-or-nothing 强制，改用 fill model 返回的实际 `filled_quantity`，部分成交余量经 FSM `PARTIALLY_FILLED` 流通。

**Tech Stack:** Python / pytest / inline-snapshot；无新依赖。

**战略索引:** [wave1 主计划](2026-06-24-wave1-implementation-plan.md) §1.3（golden 策略）/§4；[战略定位](2026-06-24-strategic-positioning-and-functional-gap-analysis.md) §6.4。

> **⚠️ 分支基线注意：** 同 A1。
> **⚠️ golden 大面积变更：** B1 会改变所有回测的 fill 量 → golden 全红，属预期。逐策略核对后重录，禁止掰回旧值（主计划 §1.3）。

---

## 现状实证

- [fill.py](../../packages/backtest/src/ditto_backtest/simulation/fill.py)：
  - `FillModel` Protocol `try_fill(order, market, definition, trading_rule) -> FillOutcome`（L31）。
  - `AShareFillModel._evaluate`（L160）：处理停牌/MARKET_ON_CLOSE/涨跌停/MARKET/LIMIT，**连续竞价路径不读 volume**。
  - `_fill_market_or_limit`（L201）：MARKET→`_make_filled(order, market.close)`（全量）；LIMIT→限价成交（全量）。
  - `_make_filled`（L218）：**已支持** `filled_qty` 参数 + `leaves_quantity = order.quantity - qty`。
  - `ClosingAuctionFillModel`（L81）：已有 `participation_rate_threshold × avg_volume_20d` 部分成交逻辑。
- [brokerage.py](../../packages/backtest/src/ditto_backtest/brokerage.py) `_build_fill_event`（L318）：
  - L330 `fill_qty = ticket.leaves_quantity`；L335-344 `model_qty = filled.fill_event.filled_quantity; if model_qty != fill_qty: raise FillProcessingError(...)` —— **all-or-nothing 强制在此**，注释明示"如 V2 引入部分成交需重构 fill model contract"。
  - L383 FSM `transition(...)` **已支持** `PARTIALLY_FILLED`（注释："FSM 单一状态来源: transition() 决定 FILLED / PARTIALLY_FILLED"）。
- `_process_single_ticket`（L237）：`NoFill(can_retry=True)` 保持 SUBMITTED 下 step 再试（L312）——部分成交余量可复用此机制。

**Files:**
- Modify: `packages/backtest/src/ditto_backtest/simulation/fill.py`（AShareFillModel + `_fill_market_or_limit` + participation rate）
- Modify: `packages/backtest/src/ditto_backtest/brokerage.py`（`_build_fill_event` 去 all-or-nothing）
- Modify: 回测配置（`BacktestServiceConfig` 加 `participation_rate` / `fill_mode`）+ `jobs/flows/backtest.py` build 工厂
- Test: `packages/backtest/tests/unit/`（fill + brokerage）、`packages/backtest/tests/integration/test_golden_baseline.py`

---

## Task B1.0：前置确认（强制）

**Step 1：** `Grep "class MarketSnapshot" packages/kernel/src/ditto_kernel`，确认 `MarketSnapshot` 是否有**当日 `volume`** 字段（已知有 `avg_volume_20d`/`close`/`low`/`high`/`limit_up`/`limit_down`/`is_suspended`）。
- 若有 `volume` → 连续竞价 participation rate 用 `market.volume`；
- 若无 → 用 `market.avg_volume_20d`（与集合竞价一致），或在 kernel 加 `volume` 字段（影响面更大，B1 内优先用 avg_volume_20d）。
**Step 2：** Read `BacktestServiceConfig`（回测配置）+ `jobs/flows/backtest.py` 的 `build_fee_model`/`build_slippage_model` 工厂，确认 fill model 如何构造注入（B1 需把 participation_rate 注入 AShareFillModel）。
**Step 3：** Read 现有 `test_fill_model_unit.py` / `test_brokerage_unit.py`，镜像 fixture。

---

## Task B1.1：RED — fill 合约允许部分成交（brokerage 去 all-or-nothing）

**Step 1（RED）：** 测试 `BacktestBrokerage._build_fill_event`：fill model 返回 `filled_quantity=300`、`leaves=700` → 构建 FillEvent 用 **300**（不 raise），`cumulative`/`leaves` 正确：

```python
def test_partial_fill_does_not_raise(brokerage_with_partial_fill_model):
    fill = brokerage_with_partial_fill_model._build_fill_event(ticket, filled_partial, slippage=0.0, ...)
    assert fill.filled_quantity == 300          # 用 model_qty，非 leaves
    assert fill.leaves_quantity == order_qty - (prev_filled + 300)
```

**Step 2：** `pixi run -e dev pytest packages/backtest/tests/unit -k "build_fill_event or partial" -q` → FAIL（当前 raise）。
**Step 3（GREEN）：** 改 `brokerage.py:330-344`：
- 删除 `if model_qty != fill_qty: raise FillProcessingError(...)`。
- `fill_qty = filled.fill_event.filled_quantity`（用 fill model 实际成交量）。
- `cumulative = ticket.filled_quantity + fill_qty`；`leaves = order.quantity - cumulative`（保持原逻辑，现基于部分量）。
- `fill_qty == 0` 时按 NoFill 处理（返回 None / 不产生空 FillEvent）。
**Step 4：** PASS。**Step 5：** Commit `refactor(backtest): allow partial fills in brokerage fill event`。

---

## Task B1.2：RED — AShareFillModel 连续竞价 participation rate 截断

**Step 1（RED）：** 测试 `_fill_market_or_limit`（经 AShareFillModel）：
- bar volume=10000、order=2000、participation=0.05 → `filled_quantity=500`；
- order=300、participation=0.05 → `filled_quantity=300`（不超 order）；
- volume=0 → `filled_quantity=0`（保守不成交，NoFill can_retry 或 Filled qty=0）。
（volume 来源按 B1.0 结论：优先 `market.volume`，否则 `avg_volume_20d`。）

**Step 2：** FAIL。
**Step 3（GREEN）：** `AShareFillModel.__init__` 加 `participation_rate: float = 0.0`（0 = 不限流，向后兼容）；`_fill_market_or_limit` 改为方法或传入 participation，计算 `fillable = order.quantity if participation_rate<=0 else min(order.quantity, int(participation_rate × volume))`，`_make_filled(order, price, filled_qty=fillable)`。`fillable==0` → `NoFill(reason="volume_constraint", can_retry=True)`。
**Step 4：** PASS。**Step 5：** Commit `feat(backtest): participation-rate volume constraint in AShareFillModel`。

---

## Task B1.3：RED — 边界（volume 缺失 / 涨跌停 / 集合竞价不受影响）

**Step 1（RED）：** 测试：
- `volume`/`avg_volume_20d` 缺失 → 退化策略明确（保守：fillable=0 不成交，或全量 fallback——**B1 选保守不成交**并测试）；
- 涨停买入 → 仍 NoFill（不受 volume 影响）；
- MARKET_ON_CLOSE → 仍走 `ClosingAuctionFillModel`（其自有 participation），不受新连续竞价逻辑影响。
**Step 2：** FAIL → **Step 3：** 实现/确认分支 → **Step 4：** PASS。
**Step 5：** Commit `test(backtest): volume-constraint edge cases (missing vol / limit / auction)`。

---

## Task B1.4：配置开关 + DI 接线

**Step 1：** `BacktestServiceConfig` 加 `participation_rate: float = 0.05`（默认开启限流）、`fill_mode: Literal["partial","all_or_nothing"] = "partial"`（兼容旧行为）。
**Step 2（RED）：** 测试 `jobs/flows/backtest.py` build 工厂按 config 构造 `AShareFillModel(participation_rate=...)`；`fill_mode="all_or_nothing"` 时 participation_rate=0（等价旧行为）。
**Step 3（GREEN）：** 工厂接线。
**Step 4：** `pixi run -e dev check` + `arch-check`。
**Step 5：** Commit `feat(backtest): participation_rate + fill_mode config wiring`。

---

## Task B1.5：golden 重录 + 证据（关键）

**Step 1：** `pixi run -e dev pytest packages/backtest/tests/integration/test_golden_baseline.py packages/backtest/tests/integration/test_reproducibility.py -q` → 预期**大面积红**（fill 量变 → 收益/成本变）。
**Step 2：** **逐策略核对**新数值方向合理（流动性差标的收益下降 = 正确；高流动性影响小）。
**Step 3：** `pixi run -e dev test --snapshot` 重录。
**Step 4：** Commit：`test: re-record golden after volume-constrained fills (<key metric deltas, e.g. Sharpe X→Y on low-liquidity template>)`。
> **绝对禁止**把 participation_rate 调到 1.0 或关截断让数值回到旧值。

---

## DoD

- [ ] 连续竞价 MARKET/LIMIT 受 participation rate 截断；fill 合约支持部分成交（无 all-or-nothing raise）。
- [ ] 部分成交余量经 FSM `PARTIALLY_FILLED` 正确流通（下 step 重试或按 fill_mode 取消）。
- [ ] `fill_mode` 开关保留旧行为可回归；volume 缺失/涨跌停/集合竞价边界正确。
- [ ] golden 重录带证据；`check` + `arch-check` 全绿；确定性（reproducibility）保持。

## 风险

| 风险 | 缓解 |
|---|---|
| 部分成交余量跨日携带改变回测语义 | 明确 `fill_mode` 默认 partial；余量 SUBMITTED 下 step 再试（与现有 can_retry 一致）；文档化"未成交部分顺延"行为 |
| `MarketSnapshot` 无 `volume` 字段 | B1.0 先确认；无则用 `avg_volume_20d`，并在 fill/注释标明（当日 volume 为 P1 改进项） |
| golden 重录误把真回归当改进 | 逐策略人工核对数值方向；差异写进 commit；保留 `all_or_nothing` 模式可对照 |
| fill_qty=0 产生空 FillEvent 污染审计 | `_build_fill_event` 前置 `fill_qty==0` → 视同 NoFill（不产事件） |
