# ditto_engine

量化交易核心引擎 -- 策略决策、回测、执行、组合构建、账户契约。

## 架构定位

```
interfaces → app → engine → kernel
                        → data (errors + provider Protocol only)
```

## 模块说明

### alpha/
Alpha 决策层。StrategySpec 策略语义契约、StrategyPipeline 流水线编排、DecisionStage Protocol。
内置 7 个 Stages（Universe / Signal / Scoring / Filtering / Selection / RiskLock / Trend / Regime）和
4 个策略模板（etf_rotation / etf_trend_swing / stock_sector_rotation / stock_selection_trend）。
DecisionFrame 通过 Polars DataFrame 列名约定流转。

### execution/
执行层。ExecutionPlanner 订单规划、BacktestBrokerage 回测经纪商（T+1 冻结 + 批内滚动更新）、
TradeBuilder 成交匹配（FIFO / FlatToFlat）、Reality Model（佣金/滑点/成交/结算）。

### backtest/
回测引擎。EngineLoop 日历步进主循环、PreTrade 6 规则 + PostTrade 4 Guard 风控体系、
BacktestReport（NAV/Sharpe/Calmar/CVaR）、RunManifest 运行清单、
ExecutionAuditCollector 审计、BacktestReportSerializer SQLite 存储。

### portfolio/
组合构建。WeightAllocator Protocol 及三种实现（EqualWeight / ScoreWeight / InverseVol）、
ConstraintChecker 按 priority 排序（MaxWeight / MinWeight / MaxPositions）、
AllocationStage / ConstraintStage 适配 DecisionStage、compare_reports() 报告对比。

### accounting/
共享账户契约层。Account（唯一可变对象）/ CashBook / OrderBook / Position 均为 frozen dataclass，
AccountView 只读快照供上层安全消费，BuyingPowerModel Protocol。

### risk/
风险管理。风险模型计算（回撤检测、风险度量），告警编排在 App 层。

### events.py
域事件定义。OrderSubmitted / OrderFilled / RiskGuardTriggered 等。
