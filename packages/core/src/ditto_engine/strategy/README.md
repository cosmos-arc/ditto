# 策略模块 (strategy/)

**版本**: v3.1
**最后更新**: 2026-03-25
**状态**: 核心功能已完成，Port 控制面入口已接通

## 概要

策略决策层，基于 Pipeline + Stage 架构提供可组合的策略信号生成能力。
当前已由 Port 层 `StrategyRuntimeBuilder / StrategySliceBuilder / StrategyFacade`
接入 published catalog、单日 research/recommendation 和完整 backtest 编排链路。

## 架构

```
strategy/
├── pipeline.py          # StrategyPipeline — Stage 编排器
├── spec.py              # StrategySpec — 策略完整语义契约
├── context.py           # StrategyContext — 策略运行时上下文
├── models.py            # Signal / DecisionFrame / MarketState
├── protocols.py         # DecisionStage Protocol
├── validation.py        # validate_spec_params()
├── stages/              # 内置 Stages
│   ├── universe.py      # UniverseStage — 标的筛选
│   ├── signal.py        # SignalStage — 信号计算
│   ├── scoring.py       # ScoringStage — 得分排名
│   ├── filtering.py     # FilteringStage — 条件过滤
│   ├── selection.py     # SelectionStage — Top-N 选择
│   ├── risk_lock.py     # RiskLockFilterStage — 风控锁定
│   └── regime.py        # RegimeStage — 市场状态
└── templates/           # 策略模板
    └── etf_rotation.py  # ETF 轮动模板
```

## 核心概念

- **StrategySpec**: 策略的完整定义（ID、参数、Stages 配置）
- **StrategyPipeline**: 顺序编排 DecisionStage 列表
- **DecisionStage**: Protocol，每个 Stage 接收 DecisionFrame 输出 DecisionFrame
- **DecisionFrame**: 通过列名约定流转数据的 polars DataFrame（`instrument_id` 列类型为 `InstrumentId(int)`）

## Identity Model

策略层统一使用 `InstrumentId = NewType("InstrumentId", int)`（定义在 `ditto_kernel.identity`）：
- DecisionFrame 的 `instrument_id` 列为 int 类型
- TargetPortfolio.positions 的 key 为 `InstrumentId`
- SignalSnapshot.signals / RebalancePlan.target_weights 的 key 为 `InstrumentId`
- Core 层不持有任何展示信息（ticker/symbol），展示映射由 Port 层负责

## 依赖

- 上游: `ditto_datahub` (数据访问)
- 下游: 被 `ditto_core.portfolio`、`ditto_core.execution` 和 `ditto_port.services.strategy` 消费

## Port 侧入口

- `StrategyRuntimeBuilder`: 从 published `StrategySpecRecord` 恢复 `StrategySpec + StrategyPipeline`
- `StrategySliceBuilder`: 使用 market/metadata service 自动组装单日 `Slice`
- `StrategyFacade`: 提供 catalog-backed `research` / `recommend` / `backtest` 统一入口
- `ditto strategy ...`: CLI 入口，已支持 `research` / `recommend` / `backtest`

## 相关文档

- [v3 系统设计](../../../../docs/plans/2026-03-21-strategy-engine-system-design-v3.md)
- [治理收口计划](../../../../docs/plans/2026-03-24-strategy-engine-v3-governance-closeout-plan.md)
