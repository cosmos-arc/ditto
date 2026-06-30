# Alpha 决策模块 (alpha/)

**最后更新**: 2026-06-01
**状态**: 核心功能已完成，Port 控制面入口已接通

## 概要

Alpha 决策层，基于 Pipeline + Stage 架构提供可组合的策略信号生成能力。
当前已由 Port 层 `StrategyRuntimeBuilder / StrategySliceBuilder / StrategyFacade`
接入 published catalog、单日 research/recommendation 和完整 backtest 编排链路。

## 架构

```
alpha/
├── pipeline.py          # StrategyPipeline — Stage 编排器 + 边界校验
├── specs.py             # StrategySpec — 策略完整语义契约
├── context.py           # StrategyContext — 策略运行时上下文
├── models.py            # Signal / DecisionFrame / MarketState
├── protocols.py         # DecisionStage Protocol
├── validation.py        # validate_spec_params()
├── builtins/            # 内置 Stages
│   ├── universe.py      # UniverseStage — 标的筛选
│   ├── signal.py        # SignalStage — 信号计算
│   ├── scoring.py       # ScoringStage — 得分排名
│   ├── filtering.py     # FilteringStage — 条件过滤（含 RiskLockFilter）
│   ├── selection.py     # SelectionStage — Top-N 选择
│   └── regime.py        # RegimeStage — 市场状态
└── templates/           # 策略模板
    ├── etf_rotation.py          # ETF 轮动模板
    ├── etf_trend_swing.py       # ETF 趋势摆动模板
    ├── stock_sector_rotation.py # 股票行业轮动模板
    └── stock_selection_trend.py # 股票选择趋势模板
```

## 核心概念

- **StrategySpec**: 策略的完整定义（ID、参数、Stages 配置）
- **StrategyPipeline**: 顺序编排 DecisionStage 列表
- **DecisionStage**: Protocol，每个 Stage 接收 DecisionFrame 输出 DecisionFrame
- **DecisionFrame**: 通过列名约定流转数据的 polars DataFrame，`instrument_id` 为 identifier dtype（生产路径优先 `InstrumentId(int)`；实验模板仍保留字符串标识符兼容），由 `validate_frame()` 在 pipeline 边界校验必需列和已知语义列 dtype

## Identity Model

策略层统一使用 `InstrumentId = NewType("InstrumentId", int)`（定义在 `ditto_kernel.identity`）：
- 生产路径 DecisionFrame 的 `instrument_id` 列优先为 int 类型；实验模板测试仍允许字符串标识符，晋级前必须通过 `StrategyInputBundle.instrument_id_map` 在 `TargetPortfolio` 边界映射到 canonical `InstrumentId`，并启用 `require_canonical_target_ids=True` 证明未映射字符串会 fail closed
- TargetPortfolio.positions 的 key 为 `InstrumentId`
- SignalSnapshot.signals / RebalancePlan.target_weights 的 key 为 `InstrumentId`
- Engine 层不持有任何展示信息（ticker/symbol），展示映射由 Port 层负责

## 依赖

- 允许: `ditto_kernel`；SQLite 策略存储可通过 package 规范使用 `ditto_platform`
- 禁止: 直接依赖 `ditto_data` / `ditto_features` / `ditto_portfolio` / `ditto_risk` / `ditto_execution` / `ditto_backtest` / `ditto_application` / `ditto_apps`
- 市场数据由 application/backtest 通过 `StrategyInputBundle` 注入；组合、风控和执行由外层编排

## Port 侧入口

- `StrategyRuntimeBuilder`: 从 published `StrategySpecRecord` 恢复 `StrategySpec + StrategyPipeline`
- `StrategySliceBuilder`: 使用 market/metadata service 自动组装单日 `Slice`
- `StrategyFacade`: 提供 catalog-backed `research` / `recommend` / `backtest` 统一入口
- `ditto strategy ...`: CLI 入口，已支持 `research` / `recommend` / `backtest`

## 相关文档

- [v3 系统设计](../../../../docs/plans/2026-03-21-strategy-engine-system-design-v3.md)
- [治理收口计划](../../../../docs/plans/2026-03-24-strategy-engine-v3-governance-closeout-plan.md)
