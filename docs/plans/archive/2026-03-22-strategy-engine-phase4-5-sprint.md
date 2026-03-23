# 策略引擎 Phase 4-5 统一 Sprint 执行计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完成策略引擎剩余功能 — 三层风控 + 完整统计 + 审计日志 + 确定性回放 + 多策略模板 — **ALL DONE**

**Architecture:** Phase 4-5 覆盖 4 个 Wave，Wave 内并行、Wave 间串行。所有代码为纯计算，无 I/O。文件路径基于实际代码库状态（`backtest/statistics.py` 合并了设计中的 `backtest/audit/` 包）。

**Tech Stack:** Python 3.13, dataclass(frozen=True), Protocol, pytest

**Design Doc:** `docs/plans/2026-03-21-strategy-engine-system-design-v3.md` §7-8, §10, §12

**Existing Plans:**
- Phase 4 主计划: `docs/plans/2026-03-22-strategy-engine-phase4-00-master.md`
- Phase 5 主计划: `docs/plans/2026-03-22-strategy-engine-phase5-00-master.md`

---

## 已完成状态

| Phase | Part | 状态 | 关键交付物 |
|-------|------|------|-----------|
| Phase 0 | 01-05 | **Done** | accounting + execution rules + strategy specs + DataHub |
| Phase 1 | 01-04 | **Done** | Pipeline + builtins + portfolio construction + templates |
| Phase 2 | 01-08 | **Done** | EngineLoop + Planner + Brokerage + PreTrade V1 + AuditCollector |
| Phase 3 | 01-08 | **Done** | AShare Reality Model + Planner 完整化 + RuleProvider |
| Phase 4 | Part 01 | **Done** | PreTradeRiskCheck 6 条规则 + T+1 冻结 |
| Phase 5 | Part 01-02 | **Done** | etf_trend_swing 模板 + inverse_vol 分配器 |
| Phase 4 | Part 02 | **Done** | PostTradeRiskGuard 4 条规则 + CompositePostTradeGuard + EngineLoop RiskLock 集成 |
| Phase 4 | Part 03 | **Done** | RuleRefs + RunManifest + 序列化 + EngineLoop 集成 |
| Phase 4 | Part 04 | **Done** | AggregatedTradeStatistics + AlphaStatistics + BacktestReport |
| Phase 5 | Part 05 | **Done** | InstrumentDefinition 扩展 (ipo_date, delisting_date) + 新股涨跌停规则 |
| Phase 4 | Part 05 | **Done** | risk_log + pre_trade_log 审计日志 + EngineLoop 审计集成 |
| Phase 4 | Part 06 | **Done** | StrategyComparisonReport + compare_reports + MetricsDelta |
| Phase 5 | Part 03 | **Done** | stock_selection_trend 模板 + MultiFactorSignalStage + rebalance_freq |
| Phase 5 | Part 06 | **Done** | RiskLock 跨日 cooldown + cooldown_until_date |
| Phase 4 | Part 07 | **Done** | 确定性回放测试 (Layer1/2 + P5 证明型) |
| Phase 4 | Part 08 | **Done** | 风控集成测试 + 审计日志完整性 |
| Phase 5 | Part 04 | **Done** | stock_sector_rotation 两层 Pipeline + 行业内选股 |
| Phase 5 | Part 07 | **Done** | 4 个模板回测快照测试 + 通用不变量 |

---

## Wave 执行总览

```
Wave 1: Foundation (4 parallel tracks)
  Track A: PostTradeRiskGuard + RiskLock          [Phase 4 Part 02] L ✅ Done
  Track B: RuleRefs + RunManifest                 [Phase 4 Part 03] L ✅ Done
  Track C: AggregatedTradeStatistics + AlphaStats  [Phase 4 Part 04] L ✅ Done
  Track D: InstrumentDefinition 扩展               [Phase 5 Part 05] M ✅ Done
    ↓
Wave 2: Audit + Templates (4 parallel tracks)
  Track A: risk_log + pre_trade_log                [Phase 4 Part 05] M  ← depends Wave 1A  ✅ Done
  Track B: StrategyComparisonReport                [Phase 4 Part 06] M  ← depends Wave 1C  ✅ Done
  Track C: stock_selection_trend 模板              [Phase 5 Part 03] XL ← no Phase 4 dep  ✅ Done
  Track D: RiskLock 跨日 cooldown                  [Phase 5 Part 06] S  ← depends Wave 1A  ✅ Done
    ↓
Wave 3: Proof + Extension (3 parallel tracks)
  Track A: 确定性回放测试 (S4)                     [Phase 4 Part 07] L  ← depends Wave 1B  ✅ Done
  Track B: 风控集成测试                             [Phase 4 Part 08] M  ← depends Wave 2A  ✅ Done
  Track C: stock_sector_rotation 模板              [Phase 5 Part 04] XL ← depends Wave 2C  ✅ Done
    ↓
Wave 4: 收尾
  Track A: 每个模板回测快照测试                     [Phase 5 Part 07] L  ← depends Wave 3C  ✅ Done
```

## 文件路径映射（设计 → 实际）

| 设计路径 | 实际路径 | 说明 |
|---------|---------|------|
| `backtest/audit/collector.py` | `backtest/statistics.py` | 合并为单一文件 |
| `backtest/audit/models.py` | `backtest/statistics.py` (新增模型) | 同上 |
| `backtest/audit/portfolio.py` | `backtest/statistics.py` | 已有 PortfolioStatistics |
| `backtest/audit/trade.py` | `backtest/statistics.py` | 已有 TradeStatistics |
| `backtest/risk/post_trade.py` | `backtest/risk/post_trade.py` (新建) | — |
| `backtest/manifest.py` | `backtest/manifest.py` (新建) | — |
| `portfolio/comparison.py` | `portfolio/comparison.py` (新建) | — |

---

## Wave 1: Foundation

### Wave 1 — Track A: PostTradeRiskGuard + RiskLock [L]

**对应:** Phase 4 Part 02

**新文件:**
- `packages/core/src/ditto_core/backtest/risk/post_trade.py`
- `packages/core/tests/unit/backtest/test_post_trade_unit.py`

**修改文件:**
- `packages/core/src/ditto_core/backtest/risk/__init__.py`
- `packages/core/src/ditto_core/backtest/__init__.py`
- `packages/core/src/ditto_core/backtest/engine.py`
- `packages/core/src/ditto_core/strategy/context.py`

**Task 1A.1: 定义 PostTrade 风控模型 `[S]`**

- [x] 在 `backtest/risk/post_trade.py` 定义 `RiskActionType` (REDUCE_POSITION / LIQUIDATE / ALERT)、`RiskSeverity` (WARNING / CRITICAL / EMERGENCY)、`RiskAction` (frozen)、`PostTradeRiskGuard` Protocol
- [x] 验收: frozen dataclass, Protocol 类型检查通过
- 文件: `backtest/risk/post_trade.py`

**Task 1A.2: 实现 MaxDrawdownRule `[M]`**

- [x] 实现 `MaxDrawdownRule(PostTradeRiskGuard)` — 组合回撤超阈值触发
  - 需要 `peak_nav` 跨 step 追踪 → 作为 Rule 内部状态
  - `warning_threshold: float` (默认 10%) → ALERT
  - `emergency_threshold: float` (默认 20%) → LIQUIDATE
- [x] 验收: 回撤 10% 触发 ALERT, 20% 触发 LIQUIDATE
- 文件: `backtest/risk/post_trade.py`

**Task 1A.3: 实现 SingleLossLimitRule `[M]`**

- [x] 实现 `SingleLossLimitRule(PostTradeRiskGuard)` — 单标的亏损超阈值
  - `current_price < position.average_cost * (1 - threshold)` → REDUCE_POSITION
  - `threshold: float` (默认 15%), `instrument_id` 标记
- [x] 验收: 亏损超限触发减仓
- 文件: `backtest/risk/post_trade.py`

**Task 1A.4: 实现 ConcentrationLimitRule `[M]`**

- [x] 实现 `ConcentrationLimitRule(PostTradeRiskGuard)` — 单标的持仓超限
  - `position.market_value / account_view.nav > max_weight` → REDUCE_POSITION
  - `max_weight: float` (默认 0.2)
- [x] 验收: 集中度超限触发减仓
- 文件: `backtest/risk/post_trade.py`

**Task 1A.5: 实现 MarketAnomalyRule `[S]`**

- [x] 实现 `MarketAnomalyRule(PostTradeRiskGuard)` — 日涨跌幅超限
  - `abs(daily_return) > threshold` (默认 5%) → ALERT
  - 从 `account_view` 或 `market_snapshot` 计算日涨跌幅
- [x] 验收: 异常波动触发告警
- 文件: `backtest/risk/post_trade.py`

**Task 1A.6: 实现 CompositePostTradeGuard `[S]`**

- [x] 实现 `CompositePostTradeGuard` — 组合 4 条规则顺序扫描
  - V1 只扫描并返回 `list[RiskAction]`, 不主动生成订单
  - ALERT 只记录, REDUCE_POSITION/LIQUIDATE V1 只锁定
- [x] 验收: 4 条规则组合扫描正确
- 文件: `backtest/risk/post_trade.py`

**Task 1A.7: 集成 PostTrade 到 EngineLoop._step `[L]`**

- [x] `EngineLoop.__init__` 新增 `post_trade_guard: PostTradeRiskGuard | None` 参数
- [x] `_step` 开头执行 `post_trade_guard.scan(account_view, slice_)`
  - ALERT → 记录日志 (Phase 4 Part 05 实现)
  - REDUCE_POSITION/LIQUIDATE → `_context.lock_instrument(iid, reason)`
  - step 开头 `_context.clear_locks()` (当日锁定)
- [x] 更新 `__init__.py` 导出
- [x] 验收: PostTrade 扫描集成到主循环, RiskLock 生效
- 文件: `backtest/engine.py`, `backtest/risk/__init__.py`, `backtest/__init__.py`

**Task 1A.8: PostTrade 单元测试 `[L]`**

- [x] 4 条规则独立测试 + CompositePostTradeGuard 组合测试
- [x] RiskLock 生命周期: 当日锁定、次日清除
- [x] RiskLock 防重入: 锁定标的不被 Pipeline 选入
- [x] 验收: 全部测试通过, `pixi run -e dev check`
- 文件: `tests/unit/backtest/test_post_trade_unit.py`

---

### Wave 1 — Track B: RuleRefs + RunManifest [L] ✅ Done

**对应:** Phase 4 Part 03

**新文件:**
- `packages/core/src/ditto_core/backtest/manifest.py`
- `packages/core/tests/unit/backtest/test_manifest_unit.py`

**修改文件:**
- `packages/core/src/ditto_core/backtest/__init__.py`
- `packages/core/src/ditto_core/backtest/engine.py`

**Task 1B.1: 定义 RuleRef + RunManifest 模型 `[M]`**

- [x] `RunMode(StrEnum)`: RESEARCH / RECOMMENDATION / BACKTEST / LIVE (R7)
- [x] `RuleRef(frozen)`: instrument_id, definition_version, trading_rule_as_of, fee_schedule_as_of, trading_rule_effective_to, fee_schedule_effective_to
- [x] `RunManifest(frozen)`: run_id, strategy_id, strategy_version, mode(RunMode), input_refs, parameter_overrides, rule_refs, artifacts, config_hash, engine_version, rule_resolution_policy(S2), created_at(RFC3339)
- [x] 验收: frozen, 类型检查通过
- 文件: `backtest/manifest.py`

**Task 1B.2: 实现 RuleRefCollector `[M]`**

- [x] `RuleRefCollector` 在 `EngineLoop.run()` 遍历所有 step 后全量收集
- [x] key = `(instrument_id, definition_version, trading_rule_as_of, fee_schedule_as_of)`
- [x] 保留首次出现, 不去重覆盖 (F3)
- [x] `definition_version` = 简单 hash(InstrumentDefinition 字段)
- [x] 验收: 跨规则变更日版本不被覆盖
- 文件: `backtest/manifest.py`

**Task 1B.3: 实现 Manifest 序列化 `[M]`**

- [x] `serialize_manifest(manifest: RunManifest) -> str`: canonical JSON
  - key 排序, 无多余空白
  - `rule_refs` 按 `(instrument_id, definition_version, trading_rule_as_of, fee_schedule_as_of)` 稳定排序
  - 时间字段 RFC3339 UTC (P3)
  - 使用 `orjson.dumps(..., option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)` + canonical 化
- [x] 验收: 同 manifest 二次生成字节级一致 (P2)
- 文件: `backtest/manifest.py`

**Task 1B.4: EngineLoop 集成 RunManifest `[M]`**

- [x] `EngineLoop.__init__` 新增 `rule_ref_collector: RuleRefCollector | None`
- [x] `run()` 中每个 step 后调用 `collector.observe(date, rules)`
- [x] `run()` 结束时构建 `RunManifest`, `EngineResult` 新增 `manifest` 字段
- [x] 更新 `__init__.py` 导出
- [x] 验收: EngineResult 包含完整 manifest
- 文件: `backtest/engine.py`, `backtest/__init__.py`

**Task 1B.5: Manifest 测试 `[M]`**

- [x] 全量冻结测试: 跨规则变更日的版本不被覆盖
- [x] 序列化稳定性: 同 manifest 二次生成字节级一致
- [x] rule_refs 排序稳定性
- [x] 验收: 全部测试通过
- 文件: `tests/unit/backtest/test_manifest_unit.py`

---

### Wave 1 — Track C: AggregatedTradeStatistics + AlphaStatistics [L] ✅ Done

**对应:** Phase 4 Part 04

**修改文件:**
- `packages/core/src/ditto_core/backtest/statistics.py`
- `packages/core/tests/unit/backtest/test_audit_collector_unit.py`

**Task 1C.1: 实现 AggregatedTradeStatistics `[L]`**

- [x] 从 `TradeRecord` 序列汇总:
  - total_trades, long_trades, short_trades
  - win_trades, loss_trades, win_rate, profit_factor
  - avg_win, avg_loss, avg_win_loss_ratio
  - max_consecutive_wins, max_consecutive_losses
  - avg_holding_days, median_holding_days
  - best_trade, worst_trade, avg_trade_return_pct
- [x] `ExecutionAuditCollector.compute_aggregated_trade_statistics() -> AggregatedTradeStatistics`
- [x] 边界: 无交易 → 所有数值为 0; 全胜/全败
- [x] 验收: 汇总计算正确
- 文件: `backtest/statistics.py`

**Task 1C.2: 实现 AlphaStatistics `[L]`**

- [x] 从 NAV 序列 + benchmark NAV 序列计算:
  - annualized_return, annualized_volatility, sharpe_ratio, sortino_ratio
  - max_drawdown, max_drawdown_duration_days, calmar_ratio
  - information_ratio, tracking_error, beta, alpha_annualized
  - total_turnover, avg_turnover_per_rebalance
  - total_fees, net_return_after_cost, cost_drag
- [x] 无基准时: IR/tracking_error/beta/alpha = None
- [x] `ExecutionAuditCollector.compute_alpha_statistics() -> AlphaStatistics`
- [x] 复用 `engine/evaluation/metrics/_math.py` (可直接 import 的纯数学工具)
- [x] 验收: 有/无基准场景正确
- 文件: `backtest/statistics.py`

**Task 1C.3: 实现 BacktestReport 构建 `[M]`**

- [x] `BacktestReport(frozen)`: run_id, period, initial_cash, final_nav, trade_stats, portfolio_stats, alpha_stats, nav_series, trade_log, fill_log
- [x] `ExecutionAuditCollector.build_report() -> BacktestReport`
  - 聚合 PortfolioStatistics + TradeStatistics + AlphaStatistics
- [x] 验收: BacktestReport 包含所有维度
- 文件: `backtest/statistics.py`

**Task 1C.4: 统计计算测试 `[M]`**

- [x] AggregatedTradeStatistics: win_rate, profit_factor, consecutive wins/losses, edge cases
- [x] AlphaStatistics: 有/无基准
- [x] BacktestReport: 完整性
- [x] 验收: 全部测试通过
- 文件: `tests/unit/backtest/test_audit_collector_unit.py`

---

### Wave 1 — Track D: InstrumentDefinition 扩展 [M] ✅ Done

**对应:** Phase 5 Part 05

**修改文件:**
- `packages/core/src/ditto_core/execution/rules.py`
- `packages/core/tests/unit/execution/test_rules_unit.py`

**Task 1D.1: InstrumentDefinition 新增字段 `[S]`**

- [x] 新增 `ipo_date: str | None` (上市日期)
- [x] 新增 `delisting_date: str | None` (退市日期)
- [x] backward compatible: 新字段默认 None
- [x] 验收: 新字段定义, 类型检查通过
- 文件: `execution/rules.py`

**Task 1D.2: 新股涨跌停规则 + 扩展测试 `[M]`**

- [x] `TradingRuleSet` 中 `price_limit_pct=None` 表示无涨跌停 (新股前 5 日)
- [x] 新股规则通过 TradingRuleSet 版本化体现 (上市日期 → 规则变更日期)
- [x] 退市整理期: `lifecycle_state="delisting"` 时 10% 涨跌幅
- [x] 测试: 新股首日无涨跌停, N+1 日恢复, 退市整理期 10%
- [x] 验收: 扩展规则测试通过
- 文件: `execution/rules.py`, `tests/unit/execution/test_rules_unit.py`

---

## Wave 2: Audit + Templates

### Wave 2 — Track A: risk_log + pre_trade_log 审计 [M]

**对应:** Phase 4 Part 05

**修改文件:**
- `packages/core/src/ditto_core/backtest/statistics.py`
- `packages/core/src/ditto_core/backtest/engine.py`
- `packages/core/tests/unit/backtest/test_audit_collector_unit.py`

**Task 2A.1: 定义 RiskScanRecord + PreTradeDecisionRecord 模型 `[S]`**

- [x] `RiskScanRecord(frozen)`: trade_date, rule_id, instrument_id, severity, action_taken, detail, current_value, threshold
- [x] `PreTradeDecisionRecord(frozen)`: trade_date, order_id, instrument_id, direction, original_quantity, final_quantity, decision("accepted"/"rejected"/"resized"), reason, check_sequence
- [x] 验收: frozen, 加入 `__all__`
- 文件: `backtest/statistics.py`

**Task 2A.2: ExecutionAuditCollector 新增审计 API `[M]`**

- [x] `record_risk_scan(date, results: tuple[RiskScanRecord])` (R12)
- [x] `record_pre_trade_decisions(date, decisions: tuple[PreTradeDecisionRecord])` (A2+F1)
- [x] `get_risk_log() -> tuple[RiskScanRecord]`
- [x] `get_pre_trade_log() -> tuple[PreTradeDecisionRecord]`
- [x] 验收: 审计记录正确存储和检索
- 文件: `backtest/statistics.py`

**Task 2A.3: EngineLoop 集成审计日志记录 `[M]`**

- [x] PostTrade 后调用 `audit_collector.record_risk_scan(date, records)` (A3)
- [x] PreTrade 后收集 decisions, 调用 `audit_collector.record_pre_trade_decisions(date, decisions)` (A2)
- [x] `pre_trade_decisions` 记录完整 `check_sequence` (R2 触发链路)
- [x] `EngineLoop.__init__` 新增 `audit_collector: ExecutionAuditCollector | None`
- [x] 验收: 主循环正确记录审计日志
- 文件: `backtest/engine.py`

**Task 2A.4: 审计日志测试 `[M]`**

- [x] risk_log: PostTrade 触发 → 记录 RiskScanRecord
- [x] pre_trade_log: accept/reject/resize → 记录 PreTradeDecisionRecord
- [x] check_sequence: resize 链路完整记录
- [x] 验收: 全部审计日志测试通过
- 文件: `tests/unit/backtest/test_audit_collector_unit.py`

---

### Wave 2 — Track B: StrategyComparisonReport [M] ✅ Done

**对应:** Phase 4 Part 06

**新文件:**
- `packages/core/src/ditto_core/portfolio/comparison.py`
- `packages/core/tests/unit/portfolio/test_comparison_unit.py`

**修改文件:**
- `packages/core/src/ditto_core/portfolio/__init__.py`

**Task 2B.1: 定义 StrategyComparisonReport + compare_reports `[M]`**

- [x] `StrategyComparisonReport(frozen)`: baseline_run_id, compare_run_id, metrics_delta(sharpe/sortino/max_dd/turnover/cost_drag 等), improvement_directions
- [x] `compare_reports(baseline: BacktestReport, compare: BacktestReport) -> StrategyComparisonReport`
- [x] 相同策略 → 零差异; 不同策略 → 正确差异
- [x] 验收: 对比计算正确
- 文件: `portfolio/comparison.py`

**Task 2B.2: 对比报告测试 `[S]`**

- [x] 相同策略 → 零差异
- [x] 不同策略 → 正确差异方向
- [x] 验收: 测试通过
- 文件: `tests/unit/portfolio/test_comparison_unit.py`

---

### Wave 2 — Track C: stock_selection_trend 模板 [XL] ✅ Done

**对应:** Phase 5 Part 03

**新文件:**
- `packages/core/src/ditto_core/strategy/templates/stock_selection_trend.py`
- `packages/core/tests/unit/strategy/test_stock_selection_trend_unit.py`

**修改文件:**
- `packages/core/src/ditto_core/strategy/templates/__init__.py`

**Task 2C.1: 定义 StockSelectionTrendSpec + 参数约束 `[S]`**

- [x] frozen dataclass, 含 universe_filter/signal_factors/signal_weights/top_k/max_weight/rebalance_freq
- [x] `ParamConstraint` 验证
- [x] 验收: Spec 定义, 参数约束验证
- 文件: `strategy/templates/stock_selection_trend.py`

**Task 2C.2: 实现多因子信号 Stage `[L]`**

- [x] `MultiFactorSignalStage(DecisionStage)` — 多因子加权信号
- [x] 从 `input_bundle.signal_values` 读取因子列
- [x] `score = Σ(w_i × factor_i_normalized)` (rank-based 标准化)
- [x] 验收: 多因子信号计算正确
- 文件: `strategy/templates/stock_selection_trend.py`

**Task 2C.3: 实现 Pipeline 组装 `[M]`**

- [x] `build_stock_selection_trend_pipeline(config)`:
  - Universe → MultiFactorSignal → Scoring → TrendFilter → Select(top_k) → Allocate(equal/inverse_vol)
  - MaxWeight constraint (max_weight 参数)
- [x] 验收: Pipeline 端到端运行
- 文件: `strategy/templates/stock_selection_trend.py`

**Task 2C.4: 实现 rebalance_freq 调仓频率支持 `[M]`**

- [x] `EngineLoop._is_rebalance_day` 支持 monthly/weekly/daily
- [x] `monthly`: 每月第一个交易日; `weekly`: 每周一; `daily`: 每日
- [x] `EngineConfig` 新增 `rebalance_freq: str` 字段
- [x] 验收: 调仓频率正确
- 文件: `backtest/engine.py`

**Task 2C.5: stock_selection_trend 单元测试 `[L]`**

- [x] Spec 参数验证
- [x] 多因子信号计算
- [x] Pipeline 端到端
- [x] 调仓频率
- [x] 验收: 全部测试通过
- 文件: `tests/unit/strategy/test_stock_selection_trend_unit.py`

---

### Wave 2 — Track D: RiskLock 跨日 cooldown [S] ✅ Done

**对应:** Phase 5 Part 06

**修改文件:**
- `packages/core/src/ditto_core/backtest/risk/post_trade.py`
- `packages/core/src/ditto_core/strategy/context.py`
- `packages/core/src/ditto_core/backtest/engine.py`

**Task 2D.1: 实现 cooldown_until_date `[S]`**

- [x] `RiskAction.cooldown_until_date: str | None` 字段 (S5)
- [x] `StrategyContext.lock_instrument(instrument_id, reason, cooldown_until=None)`
- [x] `clear_locks()` 只清除 `cooldown_until <= today` 的锁定
- [x] `_execute_risk_actions` 中设置跨日锁定
- [x] 验收: cooldown 锁定跨日生效, 到期自动清除
- 文件: `backtest/risk/post_trade.py`, `strategy/context.py`, `backtest/engine.py`

**Task 2D.2: cooldown 测试 `[S]`**

- [x] 设置 cooldown → 次日仍锁定 → 到期日清除
- [x] 与当日锁定共存
- [x] 验收: cooldown 生命周期测试通过
- 文件: `tests/unit/backtest/test_post_trade_unit.py`

---

## Wave 3: Proof + Extension

### Wave 3 — Track A: 确定性回放测试 [L] ✅ Done

**对应:** Phase 4 Part 07

**新文件:**
- `packages/core/tests/integration/backtest/test_reproducibility.py`

**Task 3A.1: Layer 1 — 同 manifest 结果一致 `[M]`**

- [x] `test_reproducible_with_same_manifest`: 同 config + 同代码 → manifest.rule_refs 相同, final_nav/fill_log/nav_series 完全一致
- [x] 验收: 两次运行结果字节级一致
- 文件: `tests/integration/backtest/test_reproducibility.py`

**Task 3A.2: Layer 2 — 版本变更 diff report `[L]`**

- [x] `test_version_change_diff_report`: 模拟不同 FillModel 策略, diff report 精确指出受影响的 instrument_id + date
- [x] 验收: diff report 可定位差异
- 文件: `tests/integration/backtest/test_reproducibility.py`

**Task 3A.3: 3 个证明型测试 (P5) `[M]`**

- [x] `test_manifest_canonical_json_stable`: 同输入二次生成 manifest.json 字节级一致
- [x] `test_rule_refs_sorted_and_diffable`: rule_refs 稳定排序, diff 可定位变更
- [x] `test_order_log_resize_check_chain`: pre_trade_decision.check_sequence 还原 resize 链路
- [x] 验收: 3 个证明型测试通过
- 文件: `tests/integration/backtest/test_reproducibility.py`

---

### Wave 3 — Track B: 风控集成测试 [M] ✅ Done

**对应:** Phase 4 Part 08

**新文件:**
- `packages/core/tests/integration/backtest/test_risk_integration.py`

**Task 3B.1: PostTrade 触发 + RiskLock 集成测试 `[M]`**

- [x] 场景: 回撤超限 → RiskLock → Pipeline 不选入 → Planner 不生成买单
- [x] 验证完整链路: PostTrade.scan → lock → RiskLockFilter → Planner S1
- [x] 验收: 风控链路集成测试通过
- 文件: `tests/integration/backtest/test_risk_integration.py`

**Task 3B.2: 审计日志完整性测试 `[M]`**

- [x] 场景: 完整回测 → 检查 risk_log + pre_trade_log + fill_log 一致性
- [x] 每个 fill 有对应 pre_trade_decision
- [x] 每个 RiskAction 有对应 risk_log 记录
- [x] 验收: 审计日志完整性验证通过
- 文件: `tests/integration/backtest/test_risk_integration.py`

---

### Wave 3 — Track C: stock_sector_rotation 模板 [XL] ✅ Done

**对应:** Phase 5 Part 04

**新文件:**
- `packages/core/src/ditto_core/strategy/templates/stock_sector_rotation.py`
- `packages/core/tests/unit/strategy/test_stock_sector_rotation_unit.py`

**修改文件:**
- `packages/core/src/ditto_core/strategy/templates/__init__.py`

**Task 3C.1: 定义 StockSectorRotationSpec + 行业信号 Stage `[L]`**

- [x] frozen dataclass: sector_signal, top_sectors, stocks_per_sector, sector_weight_method, stock_weight_method, rebalance_freq
- [x] `SectorSignalStage(DecisionStage)` — 行业动量信号
- [x] 验收: 行业信号计算正确
- 文件: `strategy/templates/stock_sector_rotation.py`

**Task 3C.2: 实现行业选择 + 权重分配 Stage `[L]`**

- [x] 选择 Top K 行业
- [x] 分配行业权重 (equal/score_weight/inverse_vol)
- [x] 验收: 行业选择和权重分配正确
- 文件: `strategy/templates/stock_sector_rotation.py`

**Task 3C.3: 实现行业内选股 Stage `[L]`**

- [x] 每个选中行业内按因子评分选 Top K 股票
- [x] 行业内 equal_weight 分配
- [x] 验收: 行业内选股正确
- 文件: `strategy/templates/stock_sector_rotation.py`

**Task 3C.4: 组装两层 Pipeline `[M]`**

- [x] `build_stock_sector_rotation_pipeline(config)`:
  - 第一层: Universe(sector ETFs) → Signal → Score → Select(top_sectors) → Allocate
  - 第二层: 对每个选中行业 → Universe(stocks) → Score → Select(top_k) → Allocate
- [x] 合并两层结果为统一 TargetPortfolio
- [x] 验收: 两层 Pipeline 端到端运行
- 文件: `strategy/templates/stock_sector_rotation.py`

**Task 3C.5: stock_sector_rotation 单元测试 `[L]`**

- [x] 行业信号 + 选择 + 权重
- [x] 行业内选股
- [x] 两层 Pipeline 端到端
- [x] 验收: 全部测试通过
- 文件: `tests/unit/strategy/test_stock_sector_rotation_unit.py`

---

## Wave 4: 收尾

### Wave 4 — Track A: 每个模板回测快照测试 [L] ✅ Done

**对应:** Phase 5 Part 07

**新文件:**
- `packages/core/tests/integration/strategy/test_etf_trend_swing_snapshot.py`
- `packages/core/tests/integration/strategy/test_stock_selection_trend_snapshot.py`
- `packages/core/tests/integration/strategy/test_stock_sector_rotation_snapshot.py`
- `packages/core/tests/integration/strategy/conftest.py`

**Task 4A.1: etf_trend_swing 快照测试 `[M]`**

- [x] 5 日快照, 含追踪止损触发场景
- [x] NAV 序列确定性
- [x] 验收: 快照测试通过
- 文件: `tests/integration/strategy/test_etf_trend_swing_snapshot.py`

**Task 4A.2: stock_selection_trend 快照测试 `[M]`**

- [x] 10 日快照, 含多因子评分 + 调仓频率验证
- [x] NAV 序列确定性
- [x] 验收: 快照测试通过
- 文件: `tests/integration/strategy/test_stock_selection_trend_snapshot.py`

**Task 4A.3: stock_sector_rotation 快照测试 `[M]`**

- [x] 10 日快照, 含两层 Pipeline + 行业切换
- [x] NAV 序列确定性
- [x] 验收: 快照测试通过
- 文件: `tests/integration/strategy/test_stock_sector_rotation_snapshot.py`

**Task 4A.4: 模板通用不变量测试 `[S]`**

- [x] 所有模板: 不超卖, 现金守恒, 权重和 <= 1.0
- [x] 追踪止损: 触发后权重为 0
- [x] 调仓频率: 非调仓日无新订单
- [x] 共享 fixtures 在 `conftest.py`
- [x] 验收: 不变量测试通过
- 文件: `tests/integration/strategy/conftest.py`

---

## 质量门禁

每个 Task 完成后执行:

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
```

每个 Wave 完成后执行:

```bash
pixi run -e dev ci             # CI 完整检查
```

## 里程碑

| Wave | 里程碑 |
|------|--------|
| Wave 1 | PostTrade 风控 + RunManifest + 统计体系 + InstrumentDefinition 扩展 |
| Wave 2 | 审计日志 + 策略对比 + 选股模板 + cooldown |
| Wave 3 | 确定性回放 + 风控集成 + 行业轮动模板 |
| Wave 4 | 4 个模板全部可用, 回测报告可直接用于策略决策 |

## v3 修订追踪

| 修订 | 落地位置 |
|------|---------|
| R4 (PostTrade RiskLock) | Wave 1 Track A |
| R7 (RunMode 分离) | Wave 1 Track B |
| F3 (RuleRefs 全量冻结) | Wave 1 Track B |
| R11 (RuleRefs 进 RunManifest) | Wave 1 Track B |
| R12 (risk_log) | Wave 2 Track A |
| S4 (确定性测试拆两层) | Wave 3 Track A |
| S5 (cooldown 预留) | Wave 2 Track D |
| A2 (pre_trade audit) | Wave 2 Track A |
| A3 (record_risk_scan 位置) | Wave 2 Track A |
| S2 (rule_resolution_policy) | Wave 1 Track B |
| P2 (manifest 序列化) | Wave 1 Track B |
| P4 (order_log schema) | Wave 2 Track A |
| P5 (3 个证明型测试) | Wave 3 Track A |
