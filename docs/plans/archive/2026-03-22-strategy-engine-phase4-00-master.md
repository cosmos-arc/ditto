# 策略引擎 Phase 4: 风控 + 统计完善

**Status:** In Progress (Part 01-04 Done)
**Design Doc:** `docs/plans/2026-03-21-strategy-engine-system-design-v3.md` §6.1, §7, §8, §10, §12
**Roadmap:** `docs/plans/2026-03-21-strategy-engine-phase2-5-roadmap.md`
**前置:** Phase 3 全部完成

---

## 概述

**Goal:** 三层风控 + 完整统计 + 审计日志 + 确定性回放

**里程碑:** 回测报告可直接用于策略决策

**交付物:**
- PreTradeRiskCheck 完整版（6 条内置规则）
- PostTradeRiskGuard（4 条内置规则 + RiskLock）
- RuleRefs 全量冻结 + RunManifest 序列化
- TradeStatistics 汇总 + AlphaStatistics
- risk_log / pre_trade_log 审计 artifact
- StrategyComparisonReport
- 确定性回放两层测试

---

## 关键设计决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | PreTrade 上下文 | 扩展为 v3 完整版（rules dict + buying_power_model + pending_tickets） | 6 条规则需要完整上下文 |
| 2 | PostTrade 集成位置 | `EngineLoop._step` 开头（调仓前扫描） | v3 §6.1 设计，紧急退出可在调仓前执行 |
| 3 | RuleRefs 收集 | EngineLoop.run() 遍历所有 step 后全量收集 | F3: 保留所有版本，不去重覆盖 |
| 4 | Manifest 序列化 | canonical JSON + 稳定排序 | P2: 同 manifest 二次生成字节级一致 |
| 5 | PostTrade V1 | Phase 4 实现基础扫描 + RiskLock，不实现主动订单生成 | 简化复杂度，主动订单留 Phase 5+ |

## v3 修订对应

| 修订 | Phase 4 落地 |
|------|-------------|
| R4 (PostTrade RiskLock) | PostTradeRiskGuard + RiskLockFilter, Part 02 |
| F3 (RuleRefs 全量冻结) | RunManifest.rule_refs 收集, Part 03 |
| R11 (RuleRefs 进 RunManifest) | RunManifest, Part 03 |
| R12 (risk_log) | ExecutionAuditCollector.record_risk_scan, Part 05 |
| S4 (确定性测试拆两层) | test_reproducible + test_version_change_diff, Part 07 |
| S5 (cooldown 预留) | RiskAction.cooldown_until 字段, Part 02 |
| A2 (pre_trade audit) | ExecutionAuditCollector.record_pre_trade_decisions, Part 05 |
| A3 (record_risk_scan 位置) | EngineLoop._step 中 PostTrade 后调用, Part 02 |
| R7 (RunMode 分离) | RunManifest.mode 使用 RunMode 枚举, Part 03 |
| S2 (rule_resolution_policy) | RunManifest.rule_resolution_policy, Part 03 |
| P1 (终态统一) | 确保所有终态使用 FILLED/CANCELED/REJECTED/INVALID, Part 07 |
| P2 (manifest 序列化) | canonical JSON + 稳定排序, Part 03 |
| P4 (order_log schema) | pre_trade_check_sequence 字段, Part 05 |

---

## 依赖关系

```
Part 01 (PreTrade 完整版)
Part 02 (PostTrade + RiskLock)
Part 03 (RuleRefs + RunManifest) ──→ Part 07 (确定性回放)
Part 04 (TradeStatistics + AlphaStats)
Part 05 (risk_log + pre_trade_log) ←── Part 01 + Part 02
Part 06 (StrategyComparisonReport) ←── Part 04
Part 07 (确定性回放测试) ←── Part 03
Part 08 (风控集成测试) ←── Part 01 + Part 02 + Part 05
```

**关键路径:** Part 01 + Part 02 → Part 05 → Part 08
**并行机会:** Part 03、Part 04、Part 06 可与 Part 01/02 并行。

---

## 子计划清单

### Part 01: PreTradeRiskCheck 完整版 + T+1 冻结逻辑 ✅

扩展 PreTrade 风控从 2 条规则到 6 条，升级 PreTradeContext 为 v3 完整版。
同时纳入 Phase 3 遗留的 T+1 冻结逻辑（Task 4.2）。

**V1 已有:** `BuyingPowerCheck` + `LotSizeCheck`
**新增:** `NoShortSellCheck` + `PriceValidityCheck` + `ConcentrationPreCheck` + `DailyTurnoverPreCheck`
**额外:** `BacktestBrokerage` T+1 冻结/解冻逻辑 + SELL 份额扣减

- [x] Task 0: T+1 冻结逻辑 (BacktestBrokerage) `[M]` — Phase 3 Task 4.2 纳入
  - `_frozen_quantities` / `_current_trade_date` 内部状态
  - `_register_frozen(iid, settle_date, qty)` — T+0 快速路径 vs T+N 延迟冻结
  - `_thaw_frozen(trade_date)` — process_pending 开头调用，恢复 available_quantity
  - BUY 时 available_quantity=0，解冻后恢复
  - SELL 守卫：leaves_quantity > available_quantity 时保持 SUBMITTED
  - 文件: `execution/brokerage.py`
  - 验收: T+1 买入次日可卖，T+0 立即可卖

- [x] Task 1.1: 升级 `PreTradeContext` 为 v3 完整版 `[L]`
  - 新增字段: `rules: dict[str, tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]]`
  - 新增字段: `market_snapshots: dict[str, MarketSnapshot]` (价格来源)
  - 新增字段: `buying_power_model: BuyingPowerModel`
  - 新增字段: `pending_tickets: tuple[OrderTicket, ...]`
  - 移除: `estimated_prices` / `lot_size` / `fee_schedule` → 改用 rules/market_snapshots
  - 辅助方法: `price_for()`, `lot_size_for()`, `fee_schedule_for()`, `estimate_order_cost()`
  - 文件: `backtest/risk/pre_trade.py`
  - 验收: frozen dataclass，字段类型正确

- [x] Task 1.2: 实现 `NoShortSellCheck` `[S]`
  - 检查卖出时 `position.available_quantity >= order.quantity`
  - 无持仓或数量不足 → reject
  - 文件: `backtest/risk/pre_trade.py`
  - 验收: 空仓卖出被拒，持仓不足被拒

- [x] Task 1.3: 实现 `PriceValidityCheck` `[S]`
  - LIMIT 单: 检查 `order.price` 在 `[limit_down, limit_up]` 范围内
  - 文件: `backtest/risk/pre_trade.py`
  - 验收: 超出涨跌停范围的 LIMIT 单被拒

- [x] Task 1.4: 实现 `ConcentrationPreCheck` `[M]`
  - 单标的持仓占比 <= 阈值（默认 20%）→ reject
  - 文件: `backtest/risk/pre_trade.py`
  - 验收: 超过集中度限制的订单被拒

- [x] Task 1.5: 实现 `DailyTurnoverPreCheck` `[M]`
  - 单日换手率 <= 阈值（默认 30%），累计 pending_tickets 金额
  - 超限 → reject
  - 文件: `backtest/risk/pre_trade.py`
  - 验收: 换手率超限的订单被拒

- [x] Task 1.6: 更新 `BuyingPowerCheck` + `LotSizeCheck` 使用 V3 context `[S]`
  - BuyingPowerCheck: `buying_power_model.available_buying_power()` 替代直接 cash
  - LotSizeCheck: `context.lot_size_for(iid)` 替代固定 lot_size
  - 文件: `backtest/risk/pre_trade.py`

- [x] Task 1.7: 更新 `EngineLoop` 使用完整 PreTradeContext `[M]`
  - `_build_pre_trade_context` 构造 V3 PreTradeContext
  - 注入 `rules` + `market_snapshots` + `buying_power_model` + `pending_tickets`
  - 文件: `backtest/engine.py`
  - 验收: EngineLoop 使用新 PreTradeContext

- [x] Task 1.8: PreTrade 完整版测试 `[L]`
  - 63 个单元测试: PreTradeContextHelpers(7) + F1 rolling(5) + NoShortSell(4) + PriceValidity(7) + LotSize(7) + BuyingPower(4) + Concentration(7) + DailyTurnover(7) + Composite(8)
  - 10 个 T+1 冻结测试: basic/thaw/partial_sell/multi_instrument/cycle0/sell_deduction 等
  - 6 个集成测试迁移: rolling context / resize recheck / no-oversell / lot-size rounding
  - 文件: `tests/unit/backtest/test_pre_trade_unit.py`, `tests/unit/execution/test_brokerage_unit.py`, `tests/integration/backtest/test_backtest_invariants.py`

---

### Part 02: PostTradeRiskGuard + RiskLock `[L]`

实现每日组合扫描 + RiskLock 防止 same-day re-entry。

- [ ] Task 2.1: 定义 `PostTradeRiskGuard` Protocol + `RiskAction` 模型 `[M]`
  - `PostTradeRiskGuard.scan(account_view, slice) -> list[RiskAction]`
  - `RiskAction`: action_type, instrument_id, target_quantity, reason, severity, rule_id, cooldown_until
  - `RiskActionType`: REDUCE_POSITION, LIQUIDATE, ALERT
  - `RiskSeverity`: WARNING, CRITICAL, EMERGENCY
  - 文件: `backtest/risk/post_trade.py` (新建)
  - 验收: Protocol 定义，类型检查通过

- [ ] Task 2.2: 实现 `MaxDrawdownRule` `[M]`
  - 组合回撤超阈值 → ALERT 或 LIQUIDATE
  - 需要历史 NAV 序列计算当前回撤
  - 通过 `StrategyContext` 或独立状态追踪峰值 NAV
  - 文件: `backtest/risk/post_trade.py`
  - 验收: 回撤超过 10% 触发 ALERT，超过 20% 触发 LIQUIDATE

- [ ] Task 2.3: 实现 `SingleLossLimitRule` `[M]`
  - 单标的亏损超阈值 → REDUCE_POSITION
  - `current_price < cost * (1 - threshold)` → 减仓
  - 文件: `backtest/risk/post_trade.py`
  - 验收: 单标的亏损超过阈值触发减仓

- [ ] Task 2.4: 实现 `ConcentrationLimitRule` `[M]`
  - 单标的持仓占比超限 → REDUCE_POSITION
  - `position_value / nav > max_weight` → 减仓至阈值
  - 文件: `backtest/risk/post_trade.py`
  - 验收: 持仓集中度超限触发减仓

- [ ] Task 2.5: 实现 `MarketAnomalyRule` `[S]`
  - 标的/市场异常波动 → ALERT
  - 日涨跌幅超过阈值（如 > 5%） → 告警
  - 文件: `backtest/risk/post_trade.py`
  - 验收: 异常波动触发告警

- [ ] Task 2.6: 实现 `CompositePostTradeGuard` `[S]`
  - 组合 4 条规则，顺序扫描
  - V1 只扫描并返回 RiskAction，不主动生成订单
  - 文件: `backtest/risk/post_trade.py`
  - 验收: 4 条规则组合扫描正确

- [ ] Task 2.7: 集成 `PostTrade` 到 `EngineLoop._step` `[L]`
  - 每个 step 开头执行 `post_trade_guard.scan(account_view, slice)`
  - `RiskAction` → `RiskActionType.ALERT` 只记录日志
  - `RiskAction` → `REDUCE_POSITION/LIQUIDATE` V1 只锁定标的（RiskLock），不生成订单
  - RiskLock: `_context.lock_instrument(instrument_id, reason)`
  - step 开头 `clear_locks()`（当日锁定，不跨日）
  - 文件: `backtest/engine.py`
  - 验收: PostTrade 扫描集成到主循环，RiskLock 生效

- [ ] Task 2.8: `RiskLockFilter` Pipeline 集成 `[S]`
  - 确保 Pipeline Filter 阶段自动注入 RiskLockFilter
  - 已在 Phase 1 实现，确认 Phase 4 配合正确
  - 文件: `strategy/builtins/filtering.py`
  - 验收: 锁定标的不被 Pipeline 选入

- [ ] Task 2.9: PostTrade 测试 `[L]`
  - 4 条规则独立测试 + 组合测试
  - RiskLock 生命周期: 当日锁定、次日清除
  - RiskLock 防重入: 清仓标的不被 Pipeline 选入 (S1)
  - 文件: `tests/unit/backtest/test_post_trade_unit.py` (新建)
  - 验收: 全部 PostTrade 测试通过

---

### Part 03: RuleRefs + RunManifest `[L]`

实现全量 RuleRefs 冻结 + RunManifest 序列化，支撑确定性回放。

- [ ] Task 3.1: 定义 `RuleRef` + `RunManifest` 模型 `[M]`
  - `RuleRef`: instrument_id, definition_version, trading_rule_as_of, fee_schedule_as_of, effective_to 字段
  - `RunManifest`: run_id, strategy_id, strategy_version, mode (RunMode), input_refs, parameter_overrides, rule_refs, artifacts, config_hash, engine_version, rule_resolution_policy, created_at
  - `RunMode`: RESEARCH / RECOMMENDATION / BACKTEST / LIVE
  - 文件: `backtest/manifest.py` (新建)
  - 验收: frozen dataclass，类型检查通过

- [ ] Task 3.2: 实现 `RunManifestCollector` `[M]`
  - 在 `EngineLoop.run()` 中收集全量 RuleRefs
  - key = `(instrument_id, definition_version, trading_rule_as_of, fee_schedule_as_of)`
  - 保留首次出现，不去重覆盖（F3）
  - `definition_version` = hash(InstrumentDefinition)
  - 文件: `backtest/manifest.py`
  - 验收: 跨规则变更日的版本不被覆盖

- [ ] Task 3.3: 实现 Manifest 序列化 `[M]`
  - canonical JSON（key 排序、无多余空白）
  - rule_refs 按稳定 key 排序
  - 同 manifest 二次生成字节级一致（P2）
  - 时间字段 RFC3339 UTC（P3）
  - 文件: `backtest/manifest.py`
  - 验收: 序列化稳定性测试通过

- [ ] Task 3.4: `EngineLoop` 集成 `RunManifest` `[M]`
  - `run()` 结束时构建 RunManifest
  - `EngineResult` 新增 `manifest` 字段
  - 文件: `backtest/engine.py`
  - 验收: EngineResult 包含完整 manifest

- [ ] Task 3.5: Manifest 测试 `[M]`
  - 全量冻结测试：跨规则变更日的版本不被覆盖
  - 序列化稳定性测试：同 manifest 二次生成字节级一致
  - rule_refs 排序稳定性
  - 文件: `tests/unit/backtest/test_manifest_unit.py` (新建)
  - 验收: 全部 Manifest 测试通过

---

### Part 04: TradeStatistics 汇总 + AlphaStatistics `[L]`

实现汇总级别统计和 Alpha 分析。

- [ ] Task 4.1: 实现 `AggregatedTradeStatistics` `[L]`
  - 从 `TradeRecord` 序列汇总:
  - total_trades, long_trades, short_trades
  - win_trades, loss_trades, win_rate
  - profit_factor, avg_win, avg_loss, avg_win_loss_ratio
  - max_consecutive_wins, max_consecutive_losses
  - avg_holding_days, median_holding_days
  - best_trade, worst_trade, avg_trade_return_pct
  - 文件: `backtest/statistics.py`
  - 验收: 汇总计算正确，edge case（无交易、全胜、全败）

- [ ] Task 4.2: 实现 `AlphaStatistics` `[L]`
  - 从信号/成交数据计算:
  - n_signals, signal_accuracy, avg_signal_return
  - avg_magnitude_realized, signal_decay_days
  - top_quintile_return, bottom_quintile_return, long_short_spread
  - rebalance_effectiveness
  - 文件: `backtest/statistics.py`
  - 验收: 有基准时计算 alpha/IR/beta，无基准时字段为 None

- [ ] Task 4.3: 实现 `BacktestReport` 构建 `[M]`
  - 聚合 PortfolioStatistics + TradeStatistics + AlphaStatistics
  - 包含 nav_series + trade_log + fill_log
  - 文件: `backtest/statistics.py`
  - 验收: BacktestReport 包含所有统计维度

- [ ] Task 4.4: `ExecutionAuditCollector` 扩展 `[M]`
  - 新增 `compute_aggregated_trade_statistics()` 方法
  - 新增 `compute_alpha_statistics()` 方法
  - 新增 `build_report()` 方法
  - 文件: `backtest/statistics.py`
  - 验收: 收集器可产出完整报告

- [ ] Task 4.5: 统计计算测试 `[M]`
  - AggregatedTradeStatistics: win_rate, profit_factor, consecutive wins/losses
  - AlphaStatistics: 有/无基准场景
  - BacktestReport: 完整性
  - 文件: `tests/unit/backtest/test_audit_collector_unit.py`
  - 验收: 全部统计测试通过

---

### Part 05: risk_log + pre_trade_log 审计 artifact `[M]`

实现审计日志收集 + artifact 持久化接口。

- [ ] Task 5.1: 定义 `RiskScanRecord` + `PreTradeDecisionRecord` 模型 `[S]`
  - `RiskScanRecord`: trade_date, rule_id, instrument_id, severity, action_taken, detail, current_value, threshold
  - `PreTradeDecisionRecord`: trade_date, order_id, instrument_id, direction, original_quantity, final_quantity, decision, reason, check_sequence
  - 文件: `backtest/statistics.py`
  - 验收: frozen dataclass

- [ ] Task 5.2: `ExecutionAuditCollector` 新增审计 API `[M]`
  - `record_risk_scan(date, results: tuple[RiskScanRecord])` (R12)
  - `record_pre_trade_decisions(date, decisions: tuple[PreTradeDecisionRecord])` (A2 + F1)
  - `get_risk_log() -> tuple[RiskScanRecord]`
  - `get_pre_trade_log() -> tuple[PreTradeDecisionRecord]`
  - 文件: `backtest/statistics.py`
  - 验收: 审计记录正确存储和检索

- [ ] Task 5.3: `EngineLoop` 集成审计日志记录 `[M]`
  - PostTrade 后调用 `audit_collector.record_risk_scan(date, records)` (A3)
  - PreTrade 后调用 `audit_collector.record_pre_trade_decisions(date, decisions)` (A2)
  - `pre_trade_decisions` 记录完整 `check_sequence`（R2 触发链路）
  - 文件: `backtest/engine.py`
  - 验收: 主循环正确记录审计日志

- [ ] Task 5.4: 审计日志测试 `[M]`
  - risk_log: PostTrade 触发 → 记录 RiskScanRecord
  - pre_trade_log: accept/reject/resize → 记录 PreTradeDecisionRecord
  - check_sequence: resize 链路完整记录
  - 文件: `tests/unit/backtest/test_audit_collector_unit.py`
  - 验收: 审计日志测试通过

---

### Part 06: StrategyComparisonReport `[M]`

实现策略对比报告。

- [ ] Task 6.1: 定义 `StrategyComparisonReport` 模型 `[S]`
  - baseline_run_id, compare_run_id
  - metrics_delta: 关键指标差异（return, sharpe, max_dd, turnover, cost_drag）
  - statistical_significance: Sharpe 差异显著性检验
  - improvement_directions: 改进建议
  - 文件: `portfolio/comparison.py` (新建或扩展)
  - 验收: frozen dataclass

- [ ] Task 6.2: 实现 `compare_reports()` 函数 `[M]`
  - 输入两个 BacktestReport，输出 StrategyComparisonReport
  - 使用 `_math.py` 复用 sharpe/sortino/dd 计算
  - 文件: `portfolio/comparison.py`
  - 验收: 对比计算正确

- [ ] Task 6.3: 对比报告测试 `[S]`
  - 相同策略 → 零差异
  - 不同策略 → 正确差异
  - 文件: `tests/unit/portfolio/test_comparison_unit.py` (新建)
  - 验收: 对比报告测试通过

---

### Part 07: 确定性回放测试 `[L]`

实现 S4 两层确定性回放测试。

- [ ] Task 7.1: Layer 1 — 同 manifest 结果一致 `[M]`
  - `test_reproducible_with_same_manifest`:
  - 同 config + 同代码 → `manifest.rule_refs` 相同
  - `final_nav` / `fill_log` / `nav_series` 完全一致
  - 文件: `tests/integration/backtest/test_reproducibility.py` (新建)
  - 验收: 两次运行结果字节级一致

- [ ] Task 7.2: Layer 2 — 版本变更 diff report `[L]`
  - `test_version_change_diff_report`:
  - 模拟代码版本变更（不同 FillModel 策略）
  - diff report 精确指出受影响的 instrument_id + date
  - 文件: `tests/integration/backtest/test_reproducibility.py`
  - 验收: diff report 可定位差异

- [ ] Task 7.3: 3 个 10 分钟证明型测试 (P5) `[M]`
  - `test_manifest_canonical_json_stable`: 同输入二次生成 manifest.json 字节级一致
  - `test_rule_refs_sorted_and_diffable`: rule_refs 稳定排序，diff 可定位变更
  - `test_order_log_resize_check_chain`: order_log.check_sequence 还原 resize 链路
  - 文件: `tests/integration/backtest/test_reproducibility.py`
  - 验收: 3 个证明型测试通过

---

### Part 08: 风控集成测试 `[M]`

端到端风控测试，验证三层风控协同工作。

- [ ] Task 8.1: PostTrade 触发 + RiskLock 集成测试 `[M]`
  - 场景: 回撤超限 → RiskLock → Pipeline 不选入 → Planner 不生成买单
  - 验证完整链路: PostTrade.scan → lock → RiskLockFilter → Planner S1
  - 文件: `tests/integration/backtest/test_risk_integration.py` (新建)
  - 验收: 风控链路集成测试通过

- [ ] Task 8.2: 审计日志完整性测试 `[M]`
  - 场景: 完整回测 → 检查 risk_log + pre_trade_log + fill_log 一致性
  - 验证: 每个 fill 都有对应的 pre_trade_decision
  - 验证: 每个 RiskAction 都有对应的 risk_log 记录
  - 文件: `tests/integration/backtest/test_risk_integration.py`
  - 验收: 审计日志完整性验证通过

---

## 风险点

| 风险 | 影响 | 缓解 |
|------|------|------|
| PreTradeContext 升级破坏现有测试 | V1 测试使用旧 context | 同步更新测试 fixtures |
| PostTrade 状态追踪复杂 | 历史峰值 NAV 需要跨 step 维护 | 独立 `_peak_nav` 字段，step 内更新 |
| Manifest 收集内存开销 | 长回测 rule_refs 数量多 | key 去重，仅保留首次出现 |
| 确定性回放敏感 | 任何随机性打破确定性 | 所有模型纯函数，时间源 slice.step_time |
