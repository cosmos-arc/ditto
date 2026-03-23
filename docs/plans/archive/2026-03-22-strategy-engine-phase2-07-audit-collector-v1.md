# Phase 2 Part 07: ExecutionAuditCollector V1

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现执行审计收集器 — NAV 曲线 + PortfolioStatistics + order_log + fill_log

**Architecture:** ExecutionAuditCollector 统一管理统计收集和审计日志（S3）。V1 包含 NAV 曲线收集、PortfolioStatistics 计算、TradeStatistics 计算、BacktestReport 组装。risk_log 和 pre_trade_log 占位（Phase 4 完整实现）。

**Design Doc:** v3 §8.3 (三层统计), §8.4 (ExecutionAuditCollector), §8.5 (Artifact)

**Prerequisite:** Part 05 (EngineLoop) + Part 01 (TradeBuilder) + Phase 0 execution/fills

---

## V1 统计范围

| 统计项 | V1 | Phase 4 扩展 |
|--------|-----|-------------|
| NAV 曲线 | ✅ | 无变化 |
| PortfolioStatistics | ✅ 部分 | AlphaStats |
| TradeStatistics | ✅ | 无变化 |
| order_log / fill_log | ✅ | 补 pre_trade_check_sequence (P4) |
| risk_log | 占位（record_risk_scan 空实现） | R12 完整 |
| pre_trade_log | 占位（record_pre_trade_decisions 空实现） | A2 完整 |

## 任务清单

- [ ] Task 7.1: `RiskScanRecord` frozen dataclass `[S]`
  - 验收: trade_date, rule_id, instrument_id?, severity, action_taken?, detail, current_value?, threshold?
  - 文件: `packages/core/src/ditto_core/backtest/audit/models.py`

- [ ] Task 7.2: `PreTradeDecisionRecord` frozen dataclass `[S]`
  - 验收: trade_date, order_id, instrument_id, direction, original_quantity, final_quantity?, decision, reason?, check_sequence
  - 文件: `packages/core/src/ditto_core/backtest/audit/models.py`

- [ ] Task 7.3: `ExecutionAuditCollector.__init__()` `[S]`
  - 验收: 接收 TradeBuilder; 初始化 _nav_series, _risk_log, _pre_trade_log
  - 文件: `packages/core/src/ditto_core/backtest/audit/collector.py`

- [ ] Task 7.4: `ExecutionAuditCollector.record()` `[M]`
  - 验收:
    - 遍历 fills → trade_builder.on_fill()
    - 追加 nav_series (date, account_view.nav)
  - 文件: `packages/core/src/ditto_core/backtest/audit/collector.py`
  - 关键: account_view 必须是成交后的快照 (R3)

- [ ] Task 7.5: `ExecutionAuditCollector.record_risk_scan()` + `record_pre_trade_decisions()` `[S]`
  - 验收: V1 占位实现，追加到内部列表（Phase 4 才真正使用）
  - 文件: `packages/core/src/ditto_core/backtest/audit/collector.py`

- [ ] Task 7.6: `PortfolioStatistics` 计算 `[L]`
  - 验收: 从 nav_series + initial_cash + benchmark? 计算:
    - total_return, annualized_return
    - annualized_volatility, sharpe_ratio, sortino_ratio
    - max_drawdown, max_drawdown_duration_days, calmar_ratio
    - information_ratio, tracking_error, beta, alpha_annualized
    - total_turnover, avg_turnover_per_rebalance
    - total_fees, net_return_after_cost, cost_drag
  - 文件: `packages/core/src/ditto_core/backtest/audit/portfolio.py`
  - 复用: engine/evaluation/metrics/_math.py 中的纯数学公式

- [ ] Task 7.7: `TradeStatistics` 计算 `[M]`
  - 验收: 从 trade_builder.get_closed_trades() 计算:
    - total_trades, long_trades, short_trades
    - win_trades, loss_trades, win_rate, profit_factor
    - avg_win, avg_loss, avg_win_loss_ratio
    - max_consecutive_wins/losses
    - avg/median holding_days
    - best/worst trade, avg_trade_return_pct
  - 文件: `packages/core/src/ditto_core/backtest/audit/trade.py`

- [ ] Task 7.8: `BacktestReport` frozen dataclass `[S]`
  - 验收: run_id, period, initial_cash, final_nav, trade_stats, portfolio_stats, alpha_stats?, trade_log, nav_series, fill_log, risk_log, pre_trade_log
  - 文件: `packages/core/src/ditto_core/backtest/audit/collector.py`

- [ ] Task 7.9: `build_report()` 方法 `[M]`
  - 验收: 收集 trade_builder.flush() + nav_series + 统计计算 → BacktestReport
  - 文件: `packages/core/src/ditto_core/backtest/audit/collector.py`

- [ ] Task 7.10: 包导出 `[S]`
  - 文件: `packages/core/src/ditto_core/backtest/audit/__init__.py`, `backtest/__init__.py`

- [ ] Task 7.11: 单元测试 `[M]`
  - 文件:
    - `packages/core/tests/unit/backtest/test_audit_collector_unit.py`
    - `packages/core/tests/unit/backtest/test_portfolio_stats_unit.py`
  - 场景:
    - record() 追加 NAV + fills
    - 已知 fill 序列 → 期望 TradeStatistics
    - 已知 nav_series → 期望 PortfolioStatistics
    - 属性测试: NAV > 0, max_dd <= 0, sharpe 合理范围
    - build_report() → BacktestReport 字段完整

---

## 文件清单

```
packages/core/src/ditto_core/backtest/
└── audit/
    ├── __init__.py            # [新增]
    ├── collector.py           # [新增] ExecutionAuditCollector / BacktestReport
    ├── models.py              # [新增] RiskScanRecord / PreTradeDecisionRecord
    ├── portfolio.py           # [新增] PortfolioStatistics
    └── trade.py               # [新增] TradeStatistics

packages/core/tests/unit/backtest/
├── test_audit_collector_unit.py    # [新增]
└── test_portfolio_stats_unit.py    # [新增]
```

## 质量门禁

```bash
pixi run -e dev check
```
