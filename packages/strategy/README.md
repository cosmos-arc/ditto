# ditto-strategy

**版本**: v0.5.0 | **日期**: 2026-05-07 | **状态**: 稳定

## 概要

策略定义与信号生成能力包 — 基于 Pipeline + Stage 架构提供可组合的策略信号生成。

## 架构

Strategy 采用 Pipeline + Stage 架构，市场数据通过 StrategyInputBundle 注入，信号通过 SignalStore Protocol 持久化：

```
┌─────────────────────────────────────────────────┐
│           Application / Backtest 编排层           │
│       注入 StrategyInputBundle（市场数据）         │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│              Strategy Pipeline                   │
│  DecisionStage 列表顺序执行                       │
│  ┌─────────┬─────────┬─────────┬─────────┐      │
│  │Universe │ Signal  │ Scoring │Selection│ ...   │
│  └─────────┴─────────┴─────────┴─────────┘      │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│            SignalStore Protocol                  │
│         信号持久化（由外部注入实现）                │
└─────────────────────────────────────────────────┘
```

## 模块结构

```
ditto_strategy/
├── alpha/              # Alpha pipeline
│   ├── builtins/       # 内置 Stage（Universe/Signal/Scoring/Selection/Filtering/Regime）
│   ├── templates/      # 策略模板（ETF轮动/趋势摆动/选股/行业轮动）
│   ├── pipeline.py     # StrategyPipeline + StrategyInputBundle
│   ├── protocols.py    # DecisionStage Protocol
│   ├── context.py      # StrategyContext（风险锁/持仓/冷却）
│   ├── specs.py        # StrategySpec 定义
│   ├── models.py       # 策略运行模型
│   ├── frame.py        # FrameCol 常量 + validate_frame
│   ├── seeds.py        # 预定义 StrategySpec
│   └── validation.py   # 参数校验
├── signals/            # 信号契约
│   ├── store.py        # SignalStore Protocol
│   └── models.py       # 信号模型
├── storage/            # 策略持久化（SQLite）
│   └── sqlite/         # spec/run/artifact 存储 + 服务
├── runs/               # 策略运行模型
├── di/                 # 依赖注入
├── contracts.py        # 包级公共契约
├── errors.py           # StrategyError 异常层级
└── models.py           # 策略域模型
```

## 核心概念

### StrategySpec

策略的完整语义契约（frozen dataclass），包含 ID、参数、Stage 配置、成本模型、约束条件。

### StrategyPipeline + DecisionStage

Pipeline 顺序编排 DecisionStage 列表。每个 Stage 接收 `DecisionFrame`（polars DataFrame）并输出 DecisionFrame。

### DecisionFrame 列名约定

DecisionFrame 通过列名约定流转数据：
- `instrument_id`：标的 ID（InstrumentId(int) 类型）
- `signal`：信号值
- `score`：得分
- `weight`：权重

### SignalStore Protocol

信号持久化接口通过 Protocol 定义，由 application/backtest 注入具体实现，策略不持有存储依赖。

## 依赖规则

| 方向 | 规则 |
|------|------|
| strategy → kernel | ✅ 共享类型 |
| strategy → platform | ✅ SQLite / 日志 / 追踪 |
| strategy → data | ❌ 市场数据由外部注入 |
| strategy → features | ❌ |
| strategy → portfolio/risk/execution | ❌ |
| strategy → backtest | ❌ |
| strategy → application/apps | ❌ |

## 策略模板

| 模板 | 文件 | 说明 |
|------|------|------|
| ETF 轮动 | `templates/etf_rotation.py` | 动量+趋势ETF轮动 |
| ETF 趋势摆动 | `templates/etf_trend_swing.py` | 趋势+摆动ETF策略 |
| 股票行业轮动 | `templates/stock_sector_rotation.py` | 行业动量轮动 |
| 股票趋势选股 | `templates/stock_selection_trend.py` | 多因子趋势选股 |

## 快速开始

```python
from ditto_strategy.alpha.pipeline import StrategyPipeline, StrategyInputBundle
from ditto_strategy.alpha.specs import StrategySpec
from ditto_strategy.alpha.templates.etf_rotation import build_etf_rotation_pipeline

# 构建策略管线
pipeline = build_etf_rotation_pipeline()

# 执行策略（input_bundle 由编排层注入）
result = pipeline.execute(input_bundle)
```

## 测试

```bash
pixi run -e dev pytest packages/strategy/tests/unit -q        # 单元测试
pixi run -e dev pytest packages/strategy/tests/integration -q  # 集成测试
```

## 相关文档

- [Strategy 层规范](CLAUDE.md)
- [Alpha 模块详细说明](src/ditto_strategy/alpha/README.md)
- [架构边界标准](../../docs/architecture/boundaries-and-abstraction-standards.md)
