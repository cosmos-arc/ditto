# Strategy 层架构规范

## 定位

Strategy 层是 **策略定义与信号生成** 能力包，负责 alpha pipeline、策略模板、信号契约和策略规格。

**核心原则**：
- 纯策略定义，不含交易执行逻辑
- 通过 Pipeline + Stage 模式组合策略行为
- 信号存储通过 Protocol 注入，不持有具体实现

## 依赖

```
ditto_strategy → ditto_kernel ✅
ditto_strategy → ditto_data ✅ (DataProvider Protocol)
ditto_strategy → ditto_features ✅
ditto_strategy → ditto_engine ✅ (临时：portfolio/execution 常量，Task 7-9 后移除)
ditto_strategy 禁止 → ditto_apps ❌
ditto_strategy 禁止 → ditto_application ❌
```

## 内部目录职责

```
ditto_strategy/
├── alpha/              # Alpha pipeline（从 engine 提取）
│   ├── builtins/       # 内置 Stage（Universe/Signal/Scoring/Selection/Filtering/Regime）
│   ├── templates/      # 策略模板（ETF轮动/趋势摆动/选股/行业轮动）
│   ├── pipeline.py     # StrategyPipeline + StrategyInputBundle
│   ├── protocols.py    # DecisionStage Protocol + DecisionFrame
│   ├── context.py      # StrategyContext（风险锁/持仓/冷却）
│   ├── models.py       # StrategyRun/Template/Version/SignalSnapshot/TargetPortfolio
│   ├── specs.py        # StrategySpec + CostModel/Execution/Constraint/Scorer/Selector
│   ├── frame.py        # FrameCol 常量 + validate_frame
│   ├── seeds.py        # 预定义 StrategySpec
│   └── validation.py   # validate_spec_params
├── signals/            # 信号契约（Protocol 定义）
│   ├── store.py        # SignalStore Protocol
│   └── models.py       # 信号模型（预留）
├── contracts.py        # 包级公共契约
└── errors.py           # StrategyError 异常层级
```

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
