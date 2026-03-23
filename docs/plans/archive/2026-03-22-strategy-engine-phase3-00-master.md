# 策略引擎 Phase 3: Reality Model 完整化

**Status:** Done
**Design Doc:** `docs/plans/2026-03-21-strategy-engine-system-design-v3.md` §4.2, §5, §5.1
**Roadmap:** `docs/plans/2026-03-21-strategy-engine-phase2-5-roadmap.md`
**前置:** Phase 2 全部完成（2026-03-22）

---

## 概述

**Goal:** 回测引擎对 A 股 ETF/股票交易规则完整建模（含规则版本化）

**里程碑:** 涨跌停/T+1/100+1/ST 场景的回测结果可信

**交付物:**
- AShareFillModel / AShareFeeModel / AShareSettlementModel / VolumeShareSlippage
- ExecutionPlanner 完整版（T+1 / 涨跌停 / 停牌 / 100+1）
- InstrumentRuleProvider 接入 DataHub PIT 存储
- BacktestBrokerage 使用三层分离签名
- 升级后的快照测试 + 不变量测试

---

## 关键设计决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | Protocol 升级策略 | 直接升级签名，不保留旧签名 | Pre-release，无兼容负担 |
| 2 | Simple* 模型 | 更新为新签名，内部保持简单逻辑 | 作为 fallback + 测试用 |
| 3 | Brokerage 规则获取 | 注入 `InstrumentRuleProvider` | v3 §4.4 设计，解耦 DataHub |
| 4 | T+1 实现 | `ExecutionPlanner` 层通过 `available_quantity` 限制卖出 | `SettlementModel` 提供 `settle_date()`，Planner 层检查冻结 |
| 5 | 100+1 规则 | 买入 `max(100, qty)` 可 1 份递增；零股必须一次性卖出 | R1 政策溯源，2023-08-28 起 |
| 6 | RuleProvider 接口 | Core 层定义 Protocol + 内存实现，DataHub 层实现 PIT 版本 | 保持 Core 无 I/O |

## v3 修订对应

| 修订 | Phase 3 落地 |
|------|-------------|
| R1 (100+1 政策溯源) | 数量取整规则，Part 06 |
| R6 (三层分离签名) | 所有 Reality Model 方法签名，Part 01 |
| R8 (FillOutcome 集成) | AShareFillModel 返回 FillOutcome，Part 02 |
| F4 (显式 FillOutcome) | Phase 2 已完成，Phase 3 复用 |

---

## 依赖关系

```
Part 01 (Protocol 升级 + MarketSnapshot)
  ├→ Part 02 (AShareFillModel)
  ├→ Part 03 (AShareFeeModel)
  ├→ Part 04 (AShareSettlementModel + T+1)
  └→ Part 05 (VolumeShareSlippage)
       Part 02 + Part 04 ─→ Part 06 (ExecutionPlanner 完整化)
       Part 01–06 ─→ Part 07 (RuleProvider 接入)
       All ─→ Part 08 (快照测试升级 + InstrumentLifecycle)
```

**并行机会:** Part 02、03、04、05 可并行开发（仅依赖 Part 01）。

---

## 子计划清单

### Part 01: Protocol 升级 + MarketSnapshot `[L]`

升级四大 Reality Model Protocol 签名，引入 `MarketSnapshot`，更新 `BacktestBrokerage` 调用链。

**影响范围:** `execution/reality/`, `execution/brokerage.py`, `backtest/engine.py`, `backtest/data_feed.py`

- [x] Task 1.1: 新建 `MarketSnapshot` frozen dataclass `[S]` ✅
  - 字段: `trade_date`, `instrument_id`, `open`, `high`, `low`, `close`, `prev_close`, `volume`, `amount`, `is_suspended`, `limit_up`, `limit_down`, `avg_volume_20d`
  - 文件: `execution/reality/market.py` (新建)
  - 验收: frozen, 字段类型正确

- [x] Task 1.2: 扩展 `BarSnapshot` 添加市场状态字段 `[S]` ✅
  - ~~新增: `limit_up`, `limit_down`, `is_suspended`, `avg_volume_20d`~~
  - 实际: `Slice.bars` 直接使用 `MarketSnapshot`，无需独立 `BarSnapshot` 类
  - 文件: `backtest/data_feed.py`
  - 验收: `ParquetDataFeed` 构建 `MarketSnapshot` 时填充全部市场状态字段

- [x] Task 1.3: 升级 `FillModel` Protocol 签名 `[M]` ✅
  - 旧: `try_fill(order, slice_data: dict, slippage: float)`
  - 新: `try_fill(order, market: MarketSnapshot, definition: InstrumentDefinition, trading_rule: TradingRuleSet) -> FillOutcome`
  - 更新 `SimpleFillModel` 适配新签名（忽略额外参数，保持简单逻辑）
  - 文件: `execution/reality/fill.py`
  - 验收: Protocol 升级，SimpleFillModel 测试通过

- [x] Task 1.4: 升级 `SlippageModel` Protocol 签名 `[S]` ✅
  - 旧: `compute(close: float, direction: OrderDirection) -> float`
  - 新: `estimate(order: Order, market: MarketSnapshot, definition: InstrumentDefinition) -> float`
  - 更新 `FixedBpsSlippage` 适配
  - 文件: `execution/reality/slippage.py`
  - 验收: Protocol 升级，FixedBpsSlippage 测试通过

- [x] Task 1.5: 升级 `FeeModel` Protocol 签名 `[S]` ✅
  - 旧: `estimate(price, quantity, direction) -> float`
  - 新: `calculate(order: Order, fill: FillEvent, fee_schedule: FeeSchedule) -> float` + `estimate(order: Order, estimated_price: float, fee_schedule: FeeSchedule) -> float`
  - 更新 `SimpleFeeModel` 适配（内部忽略 FeeSchedule，保持 max(5, amount×0.03%) 逻辑）
  - 文件: `execution/reality/fee.py`
  - 验收: Protocol 升级，SimpleFeeModel 测试通过

- [x] Task 1.6: 升级 `SettlementModel` Protocol 签名 `[S]` ✅
  - 旧: `is_tradable(instrument_id, trade_date) -> bool`
  - 新: `is_tradable(instrument_id, trade_date, direction, position: Position | None, trading_rule: TradingRuleSet) -> bool` + `settle_date(trade_date: str, trading_rule: TradingRuleSet) -> str`
  - 更新 `SimpleSettlementModel` 适配（始终返回 True）
  - 文件: `execution/reality/settlement.py`
  - 验收: Protocol 升级，SimpleSettlementModel 测试通过

- [x] Task 1.7: `BacktestBrokerage` 接入规则获取 `[L]` ✅
  - 新增 `_get_rules(instrument_id, trade_date)` 内部方法
  - 通过构造参数接收 `rule_provider` 或 `rules_getter` callable
  - `process_pending` 使用新 Protocol 签名
  - `_apply_fill` 更新 `fee_model.calculate()` 调用
  - 文件: `execution/brokerage.py`
  - 验收: `process_pending` 使用三层规则调用四大模型

- [x] Task 1.8: 更新 `BrokerageModel` 初始化 `[S]` ✅
  - 确认接受新签名模型
  - 文件: `execution/reality/__init__.py`
  - 验收: `BrokerageModel(fill_model, slippage_model, fee_model, settlement_model)` 编译通过

- [x] Task 1.9: 更新 `EngineLoop` 适配新 `SliceData` `[M]` ✅
  - `_build_slice_data` 包含新 MarketSnapshot 字段
  - 传递 `rules_getter` 给 `BacktestBrokerage`
  - 文件: `backtest/engine.py`
  - 验收: 现有集成测试通过

- [x] Task 1.10: 更新 `ParquetDataFeed` 填充市场状态字段 `[M]` ✅
  - 读取 limit_up/limit_down/is_suspended/avg_volume_20d
  - 构建 `MarketSnapshot` 时填充
  - 文件: `backtest/data_feed.py`
  - 验收: 数据源字段映射正确

- [x] Task 1.11: 更新 `__init__.py` 导出 `[S]` ✅
  - 新增 `MarketSnapshot` 导出
  - 文件: `execution/reality/__init__.py`, `execution/__init__.py`

---

### Part 02: AShareFillModel `[L]`

实现完整的 A 股成交模拟，覆盖 v3 §5.3 规则矩阵全部场景。

- [x] Task 2.1: 实现 `AShareFillModel` 规则矩阵 `[L]` ✅
  - 场景: 停牌 / 涨停+买入 / 跌停+卖出 / 涨停+卖出 / 跌停+买入 / MarketOnClose / LIMIT / 正常
  - 涨跌停通过 `TradingRuleSet.price_limit_pct` + `MarketSnapshot.limit_up/limit_down` 判断
  - 停牌通过 `MarketSnapshot.is_suspended` 判断
  - 文件: `execution/reality/fill.py`
  - 验收: 8 种场景全部正确返回 `Filled` 或 `NoFill`，`can_retry` 语义正确

- [x] Task 2.2: 实现 `ClosingAuctionFillModel` `[M]` ✅
  - 用于 `MARKET_ON_CLOSE` 订单
  - 成交比例 = f(order.quantity, market.avg_volume_20d)
  - 不成交返回 `NoFill("insufficient_auction", can_retry=False)`
  - 文件: `execution/reality/fill.py`
  - 验收: 大单部分成交，极小单零成交

- [x] Task 2.3: `AShareFillModel` 场景矩阵测试 `[M]` ✅
  - 参数化: 涨跌停 × 买卖 × Market/Limit/MarketOnClose
  - 不变量: 停牌 → `NoFill(can_retry=True)`, 无 `FillEvent`
  - 不变量: `insufficient_auction` → `NoFill(can_retry=False)` → `INVALID` 终态
  - 文件: `tests/unit/execution/test_fill_model_unit.py`
  - 验收: 所有场景矩阵测试通过

---

### Part 03: AShareFeeModel `[M]`

实现完整 A 股费用计算。

- [x] Task 3.1: 实现 `AShareFeeModel` `[M]` ✅
  - 佣金: `max(fee_schedule.min_commission, amount × fee_schedule.commission_rate)`
  - 印花税: `fee_schedule.stamp_duty_rate`（仅卖出，ETF=0）
  - 过户费: `fee_schedule.transfer_fee_rate`（ETF=0）
  - `calculate()`: 实际成交费用
  - `estimate()`: 预估费用（同 calculate 逻辑）
  - 文件: `execution/reality/fee.py`
  - 验收: 佣金 < 5 元 → 5 元；ETF 无印花税+过户费；股票卖出有全部三项

- [x] Task 3.2: `AShareFeeModel` 边界值测试 `[S]` ✅
  - 场景: 佣金 < 5 元、ETF 买卖、股票买卖、大额交易
  - 文件: `tests/unit/execution/test_fee_model_unit.py`
  - 验收: 边界值测试通过

---

### Part 04: AShareSettlementModel + T+1 账户更新 `[L]`

实现 T+0/T+1 交收规则，更新 `BacktestBrokerage` 持仓冻结逻辑。

- [x] Task 4.1: 实现 `AShareSettlementModel` `[M]` ✅
  - `is_tradable()`: 根据 `settlement_cycle` 判断是否可卖
  - `settle_date()`: 计算 `trade_date + settlement_cycle` 个交易日
  - ETF 股票型 T+1, ETF 跨境型 T+0, ETF 债券型 T+0, ETF 商品型 T+0
  - 买入不需要检查（始终可买）
  - 文件: `execution/reality/settlement.py`
  - 验收: ETF T+1 买入后不可卖，次日可卖；跨境 T+0 当日可卖

- [x] Task 4.2: T+1 卖出限制（由 `ExecutionPlanner` 层实现）`[L]` ✅
  - ~~Brokerage 层 `_frozen_quantities` 方案~~
  - 实际: `ExecutionPlanner` 通过 `position.available_quantity` 限制卖出数量
  - 不可卖部分生成 `BlockedOrder(reason="t_plus1_not_sellable", severity="defer")`
  - 文件: `execution/planner.py`
  - 验收: T+1 冻结份额不生成卖单，测试覆盖 T+0/T+1 切换

- [x] Task 4.3: SettlementModel 测试 `[M]` ✅
  - T+0 即卖, T+1 次日可卖
  - `settle_date` 正确计算（跳过非交易日）
  - 文件: `tests/unit/execution/test_settlement_unit.py` (新建)
  - 验收: 全部交收规则测试通过

---

### Part 05: VolumeShareSlippage `[M]`

实现按成交额占比线性递增的滑点模型。

- [x] Task 5.1: 实现 `VolumeShareSlippage` `[M]` ✅
  - 公式: `slippage = base_bps + impact_factor × (trade_amount / avg_daily_amount)`
  - 参数: `base_bps: float`, `impact_factor: float`
  - `avg_daily_amount` 从 `MarketSnapshot.avg_volume_20d × close` 估算
  - 文件: `execution/reality/slippage.py`
  - 验收: 小单接近 base_bps，大单按比例递增

- [x] Task 5.2: `VolumeShareSlippage` 测试 `[S]` ✅
  - 场景: 小单/中单/大单/无日均量
  - 文件: `tests/unit/execution/test_slippage_unit.py`
  - 验收: 滑点随成交额占比递增

---

### Part 06: ExecutionPlanner 完整化 `[L]`

将 `SimpleExecutionPlanner` 升级为完整版，支持 A 股全量规则。

- [x] Task 6.1: 升级 `rules` 参数为三层规则 dict `[M]` ✅
  - 旧: `rules: dict[str, object]`
  - 新: `rules: dict[str, tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]]`
  - `ExecutionPlanner` Protocol 签名同步更新
  - 文件: `execution/planner.py`
  - 验收: Protocol 签名变更，EngineLoop 调用适配

- [x] Task 6.2: 实现 T+1 卖出检查 `[M]` ✅
  - 卖出数量上限 = `position.available_quantity`
  - 使用 `TradingRuleSet.settlement_cycle` 判断冻结状态
  - 不可卖部分生成 `BlockedOrder(reason="t_plus1_not_sellable", severity="defer")`
  - 文件: `execution/planner.py`
  - 验收: T+1 冻结份额不生成卖单

- [x] Task 6.3: 实现涨跌停预检 `[M]` ✅
  - 买入 + 涨停板 → `BlockedOrder(reason="limit_up_no_buy", severity="defer")`
  - 卖出 + 跌停板 → `BlockedOrder(reason="limit_down_no_sell", severity="defer")`
  - 使用 `MarketSnapshot.limit_up / limit_down` 判断
  - 文件: `execution/planner.py`
  - 验收: 涨跌停场景正确阻止订单

- [x] Task 6.4: 实现停牌过滤 `[S]` ✅
  - `MarketSnapshot.is_suspended` → `BlockedOrder(reason="suspended", severity="block")`
  - 文件: `execution/planner.py`
  - 验收: 停牌标的不生成订单

- [x] Task 6.5: 实现 100+1 数量取整 `[M]` ✅
  - `round_buy_quantity`: `max(lot_size, raw_quantity)`（100+1 规则）
  - `round_sell_quantity`: 分整手 + 零股，以 `available_quantity` 为上界
  - 零股必须一次性卖出（不拆分）
  - 文件: `execution/planner.py`
  - 验收: 买入 50→100, 买入 350→350; 卖出 350→整手 300 + 零股 50（单笔）

- [x] Task 6.6: 传入 `MarketSnapshot` 给 Planner `[S]` ✅
  - `ExecutionPlanner.plan()` 新增 `slice` 参数（或从 rules 关联）
  - 文件: `execution/planner.py`, `backtest/engine.py`
  - 验收: Planner 可获取市场快照做预检

- [x] Task 6.7: Planner 完整化单元测试 `[L]` ✅
  - pending-aware + T+1 + 涨跌停 + 停牌 + 100+1 联合场景
  - 100+1 边界: 买入 50→100, 买入 350→350, 卖出 350→(300+50)
  - 不变量: 卖出不超过 available_quantity
  - 文件: `tests/unit/execution/test_planner_unit.py`
  - 验收: 全部 Planner 测试通过

---

### Part 07: InstrumentRuleProvider 接入 `[L]`

定义 `InstrumentRuleProvider` Protocol，实现内存版 + DataHub PIT 版。

- [x] Task 7.1: 定义 `InstrumentRuleProvider` Protocol `[S]` ✅
  - `get_definition(instrument_id) -> InstrumentDefinition`
  - `get_trading_rule(instrument_id, as_of_date) -> TradingRuleSet`
  - `get_fee_schedule(instrument_id, as_of_date) -> FeeSchedule`
  - `get_rules(as_of_date, instrument_ids) -> dict[str, tuple[...]]`
  - 文件: `execution/rules.py`
  - 验收: Protocol 定义，类型检查通过

- [x] Task 7.2: 实现 `InMemoryRuleProvider` `[M]` ✅
  - 构造时传入 `definitions / trading_rules / fee_schedules` dict
  - `get_rules` 按 `as_of_date` 查找最新生效版本
  - 用于单元测试和集成测试
  - 文件: `execution/rules.py`
  - 验收: 简单 dict 查询正确

- [x] Task 7.3: 实现 `DataHubInstrumentRuleProvider` `[M]` ✅
  - 连接 `TradingRuleReader` + `FeeScheduleReader` PIT 查询
  - `InstrumentDefinition` 从 `InstrumentRegistration` + `Extension` 组装
  - 文件: `packages/datahub/src/ditto_datahub/services/strategy/instrument_rule_provider.py`
  - 验收: PIT 查询正确返回对应版本规则

- [x] Task 7.4: `EngineLoop` 注入 `InstrumentRuleProvider` `[M]` ✅
  - `EngineLoop.__init__` 新增 `rule_provider` 参数
  - `_step` 中通过 `rule_provider.get_rules(date, ids)` 获取规则
  - 传递给 `ExecutionPlanner.plan()` 和 `BacktestBrokerage`
  - 文件: `backtest/engine.py`
  - 验收: EngineLoop 使用 RuleProvider 获取规则

- [x] Task 7.5: RuleProvider 测试 `[M]` ✅
  - InMemory 版: 多版本规则查询正确
  - PIT 边界: `effective_to` 不包含
  - 文件: `tests/unit/execution/test_rules_unit.py`
  - 文件: `packages/datahub/tests/unit/services/strategy/` (新建)
  - 验收: 规则查询测试通过

---

### Part 08: InstrumentLifecycle + 快照测试升级 `[M]`

实现 ST/*ST 生命周期影响涨跌停限制，升级回测快照测试。

- [x] Task 8.1: `InstrumentLifecycle` 基础实现 `[M]` ✅
  - `ST` → `price_limit_pct=5%`
  - `*ST` → `price_limit_pct=5%`
  - 正常 → `price_limit_pct=10%`（主板）/ 20%（创业板/科创板）
  - `lifecycle_state` 变更通过 `TradingRuleSet` 版本化体现
  - 文件: `execution/rules.py`
  - 验收: 不同 lifecycle_state 的涨跌停限制正确

- [x] Task 8.2: 升级回测快照测试 `[L]` ✅
  - 新增涨跌停场景 3 日快照测试（涨停买入失败、跌停卖出失败）
  - 新增 T+1 场景 3 日快照测试（买入次日才可卖）
  - 新增 ST 场景 3 日快照测试（ST 涨跌停 5%）
  - 文件: `tests/integration/backtest/test_backtest_snapshot.py`
  - 验收: 新快照测试通过，NAV 序列确定性

- [x] Task 8.3: 升级不变量测试 `[M]` ✅
  - T+1 冻结: 买入当日 `available_quantity` 不变
  - 涨跌停: 涨停买入不成交、跌停卖出不成交
  - 零股: 必须一次性卖出，不得拆分
  - 不超卖: 卖出 <= `effective_position`
  - 文件: `tests/integration/backtest/test_backtest_invariants.py`
  - 验收: 全部不变量测试通过

---

## 风险点

| 风险 | 影响 | 缓解 |
|------|------|------|
| Protocol 升级破坏现有测试 | Phase 2 集成测试失败 | Part 01 同步更新所有调用方 + Simple* 适配器 |
| T+1 冻结逻辑复杂 | 跨日解冻状态管理 | 由 `ExecutionPlanner` 通过 `available_quantity` 控制，无需 Brokerage 层冻结 |
| 三层规则数据不全 | DataHub 无真实 PIT 数据 | `InMemoryRuleProvider` 兜底，测试用硬编码数据 |
