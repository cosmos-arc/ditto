# Strategy 层架构规范

## 定位

Strategy 层是 **策略定义与信号生成** 能力包，负责 alpha pipeline、策略模板、信号契约和策略规格。

**核心原则**：
- 纯策略定义，不含交易执行逻辑
- 通过 Pipeline + Stage 模式组合策略行为
- Pipeline 输入、signal join、每个 Stage 输出和最终组合边界必须通过 `validate_frame()` 校验 `DecisionFrame` 必需列与已知语义列 dtype
- 实验模板可临时使用字符串 `instrument_id`，但晋级前必须通过 `StrategyInputBundle.instrument_id_map` + `require_canonical_target_ids=True` 证明 `TargetPortfolio.positions` 已解析为 canonical `InstrumentId`，且未映射字符串会 fail closed
- `stock_sector_rotation` 的非空 stage 输入必须显式携带 `is_sector` / `sector_id` 等结构列；缺列应抛 `StrategySpecError`，不得泄漏 Polars 异常或静默放行
- 信号存储通过 Protocol 注入，不持有具体实现
- 运行控制面存储可持久化 `StrategyRunRecord` / `StrategyRunCheckpointRecord` 等通用记录，但不得导入 backtest 引擎 DTO；checkpoint 语义转换属于 application

## 允许依赖

```
ditto_strategy → ditto_kernel ✅
ditto_strategy → ditto_platform ✅ (storage/sqlite: SQLitePool, logger, traced)
```

外部依赖：polars, orjson

**注意**：strategy 不直接依赖 data、features、portfolio、risk、execution 或 backtest。市场数据由 application/backtest 通过 StrategyInputBundle 注入，信号存储通过 SignalStore Protocol 抽象。策略只产出信号和策略规格，组合构建、风控、执行由 application/backtest 编排。

## 禁止依赖

```
ditto_strategy → ditto_data ❌
ditto_strategy → ditto_features ❌
ditto_strategy → ditto_portfolio ❌
ditto_strategy → ditto_risk ❌
ditto_strategy → ditto_execution ❌
ditto_strategy → ditto_backtest ❌
ditto_strategy → ditto_analysis ❌
ditto_strategy → ditto_application ❌
ditto_strategy → ditto_apps ❌
```

## 内部目录职责

```
ditto_strategy/
├── alpha/              # Alpha pipeline（从 engine 提取）
│   ├── builtins/       # 内置 Stage（Universe/Signal/Scoring/Selection/Filtering/Regime）
│   │   ├── regime/     # Regime 子系统（regime_engine / regime_indicators / regime_types）
│   ├── templates/      # 策略模板（ETF轮动/趋势摆动/选股/行业轮动）
│   ├── pipeline.py     # StrategyPipeline + StrategyInputBundle + TargetPortfolio identity mapping
│   ├── protocols.py    # DecisionStage Protocol + DecisionFrame
│   ├── context.py      # StrategyContext（风险锁/持仓/冷却）
│   ├── models.py       # StrategyRun/Template/Version/SignalSnapshot/TargetPortfolio
│   ├── specs.py        # StrategySpec + CostModel/Execution/Constraint/Scorer/Selector
│   ├── frame.py        # FrameCol 常量 + DecisionFrame schema validate_frame
│   ├── seeds.py        # 预定义 StrategySpec
│   └── validation.py   # validate_spec_params
├── signals/            # 信号契约（Protocol 定义）
│   ├── store.py        # SignalStore Protocol
│   └── models.py       # 信号模型
├── storage/            # 策略持久化
│   └── sqlite/         # SQLite 存储
│       ├── strategy_spec_store.py
│       ├── strategy_run_store.py
│       ├── strategy_artifact_store.py
│       └── services/   # 策略目录/运行/工件服务
├── runs/               # 策略运行模型
│   └── models.py
├── observability/      # 可观测性
│   └── metrics.py      # 指标
├── audit/              # 审计追踪（待扩展）
├── di/                 # 依赖注入
│   └── storage.py
├── contracts.py        # 包级公共契约
├── _internal.py        # 内部共享工具（非公共 API）
├── errors.py           # StrategyError 异常层级
└── models.py           # 策略域模型
```

## 模板成熟度

| 模板 | 成熟度 | 说明 |
|------|--------|------|
| `etf_rotation` | initial-focus | ETF 轮动，有完整测试和 seed spec |
| `etf_trend_swing` | initial-focus | ETF 趋势摆动，含 TrailingStopStage |
| `stock_selection_trend` | experimental | 多因子选股，有单元测试 |
| `stock_sector_rotation` | experimental | 行业轮动，自定义 stage 有结构列 fail-closed 契约和快照集成测试 |

成熟度定义见 `docs/architecture/capability-maturity.md`。stock/sector 模板在通过独立测试审查、canonical identity 映射证据、模板结构列 fail-closed 证据和 golden snapshot 输出签名前不得标注为 initial-focus。

## 测试位置

```
packages/strategy/tests/
├── unit/
│   ├── alpha/          # Alpha pipeline 单元测试（417 tests）
│   └── signals/        # 信号契约测试
└── integration/
    └── alpha/          # Alpha 端到端集成测试
```

## 典型导入示例

```python
from ditto_strategy.alpha.pipeline import StrategyPipeline, StrategyInputBundle
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.specs import StrategySpec
from ditto_strategy.alpha.templates.etf_rotation import build_etf_rotation_pipeline
from ditto_strategy.signals.store import SignalStore
```

## 常用验证命令

```bash
pixi run -e dev pytest packages/strategy/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```
