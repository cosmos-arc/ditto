# Backtest 层架构规范

## 定位

Backtest 是**回测引擎平面**，负责：
- 回测主循环（Engine Loop）
- Step chain 编排（策略、风控、执行、审计）
- 数据回放（Data Feed、Replay）
- 绩效统计（Statistics）
- 报告渲染（Report Renderer）
- 清单与审计收集（Manifest、Audit Collector）

**核心原则**：
- 回测是最高层模拟 runtime，可以依赖所有能力包
- 不导入真实券商网关（只使用模拟执行）
- Step chain 模式保证每步职责单一、可测试
- 统计指标计算独立于主循环，方便扩展

## 允许依赖

```
ditto_backtest → ditto_kernel ✅
ditto_backtest → ditto_data ✅
ditto_backtest → ditto_strategy ✅
ditto_backtest → ditto_portfolio ✅
ditto_backtest → ditto_risk ✅
ditto_backtest → ditto_execution ✅
```

外部依赖：polars, numpy, orjson

## 禁止依赖

```
ditto_backtest → ditto_features ❌
ditto_backtest → ditto_analysis ❌
ditto_backtest → ditto_application ❌
ditto_backtest → ditto_apps ❌
ditto_backtest → ditto_platform ❌
```

**特殊约束**：
- 禁止导入 `ditto_execution.broker.gateways` 中的真实券商实现

## 内部目录职责

```
ditto_backtest/
├── engine.py             # 回测主循环（EngineLoop）
├── steps/                # Step chain
│   ├── data_fetch.py     # 数据获取 step
│   ├── strategy.py       # 策略计算 step
│   ├── risk_scan.py      # 风控扫描 step
│   ├── pre_trade.py      # 盘前检查 step
│   ├── execution.py      # 执行模拟 step
│   ├── audit.py          # 审计收集 step
│   ├── planning.py       # 计划编排 step
│   ├── input_bundle.py   # 输入数据包
│   └── types.py          # Step 类型定义
├── audit/                # 审计子系统
│   ├── collector.py      # 审计收集器
│   └── records.py        # 审计记录
├── simulation/           # 模拟模型子包
│   ├── brokerage.py      # 券商模拟（BrokerageModel）
│   ├── fill.py           # 成交模拟（FillModel / AShareFillModel / SimpleFillModel / ClosingAuctionFillModel）
│   ├── settlement.py     # 交收规则（SettlementModel / AShareSettlementModel / SimpleSettlementModel）
│   └── slippage.py       # 滑点模型（SlippageModel / FixedBpsSlippage / VolumeShareSlippage）
├── data_feed.py          # 数据回放接口
├── synchronizer.py       # 回测时间同步器（BacktestSynchronizer — 桥接 DataFeed 到 Synchronizer Protocol）
├── replay.py             # 回放控制器
├── statistics.py         # 绩效统计计算
├── _statistics_types.py  # 统计类型定义
├── report_renderer.py    # 报告渲染器
├── manifest.py           # 回测清单（RunManifest）
├── result.py             # 引擎运行结果（EngineResult）
├── brokerage.py          # 回测层 brokerage 入口
├── errors.py             # 回测领域错误（BacktestError / EngineConfigError / ReplayError / SimulationError）
├── config.py             # 回测配置
└── contracts.py          # 回测契约（TradingLoop Protocol）
```

## 测试位置

```
packages/backtest/tests/
├── unit/
│   ├── conftest.py
│   ├── _helpers.py
│   ├── test_engine_loop_unit.py
│   ├── test_engine_events_unit.py
│   ├── test_replay_unit.py
│   ├── test_statistics_helpers_unit.py
│   ├── test_report_renderer_unit.py
│   ├── test_manifest_unit.py
│   ├── test_provider_data_feed_unit.py
│   ├── test_data_feed_history_unit.py
│   ├── test_backtest_synchronizer_unit.py
│   ├── test_trading_loop_protocol_unit.py
│   ├── test_step_types_unit.py
│   ├── test_data_fetch_step.py
│   ├── test_strategy_step.py
│   ├── test_risk_scan_step.py
│   ├── test_pre_trade_step.py
│   ├── test_pre_trade_unit.py
│   ├── test_execution_step.py
│   ├── test_planning_step.py
│   ├── test_audit_step.py
│   ├── test_audit_collector_unit.py
│   └── test_post_trade_unit.py
├── integration/
│   ├── conftest.py
│   ├── test_e2e_smoke.py
│   ├── test_golden_baseline.py
│   ├── test_reproducibility.py
│   ├── test_backtest_invariants.py
│   ├── test_risk_integration.py
│   └── test_backtest_snapshot.py
└── benchmarks/
    └── test_derived_benchmarks.py
```

## 典型导入示例

```python
# 回测引擎
from ditto_backtest.engine import EngineLoop
from ditto_backtest.config import BacktestConfig

# Step chain
from ditto_backtest.steps.strategy import StrategyStep
from ditto_backtest.steps.execution import ExecutionStep

# 数据回放
from ditto_backtest.data_feed import DataFeed
from ditto_backtest.synchronizer import BacktestSynchronizer
from ditto_backtest.replay import ReplayController

# 统计与报告
from ditto_backtest.statistics import calculate_statistics
from ditto_backtest.report_renderer import ReportRenderer
```

## 常用验证命令

```bash
pixi run -e dev pytest packages/backtest/tests/unit -q
pixi run -e dev pytest packages/backtest/tests/integration -q
pixi run -e dev type packages/backtest/src
pixi run -e dev arch-check
```
