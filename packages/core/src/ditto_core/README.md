# ditto-core

> 核心业务逻辑层 - 量化引擎、组合管理、策略框架

## 一、核心功能

提供量化交易系统的核心业务逻辑，包括回测引擎、投资组合管理、策略框架等。

## 二、架构定位

```
┌─────────────────────────────────────┐
│         apps/server                 │
│     (FastAPI 服务层)                  │
├─────────────────────────────────────┤
│      ditto-core (当前层)             │
│  ┌──────────┐  ┌──────────┐         │
│  │ Engine   │  │Strategy  │         │
│  └──────────┘  └──────────┘         │
│  ┌──────────┐                       │
│  │Portfolio │                       │
│  └──────────┘                       │
├─────────────────────────────────────┤
│        ditto-datahub                │
│     (数据访问层)                      │
├─────────────────────────────────────┤
│      ditto-foundation               │
│     (基础设施层)                      │
└─────────────────────────────────────┘
```

**依赖方向**: 仅依赖 `ditto-datahub` 和 `ditto-foundation`

## 三、目录结构

```
src/ditto_core/
├── engine/            # 引擎模块
│   ├── regime/        # Regime 识别（牛/震荡/熊）
│   ├── factor/        # 因子计算（RS/Value/Vol/Crowding）
│   ├── rotation/      # 轮动策略引擎
│   ├── backtest/      # 回测引擎（Fast + Production）
│   └── risk/          # 风险管理引擎
├── portfolio/         # 组合管理模块
│   ├── manager/       # 组合管理器
│   ├── builder/       # 组合构建器
│   └── position/      # 持仓管理
├── strategy/          # 策略模块
│   ├── base/          # 策略抽象基类
│   ├── signal/        # 信号生成接口
│   └── execution/     # 订单执行接口
└── types.py           # 类型定义
```

## 四、关键模块说明

### engine/ - 引擎层

| 模块 | 说明 |
|------|------|
| `RegimeEngine` | 市场状态识别引擎，支持自适应阈值 + 确认期机制 |
| `FactorEngine` | 多因子计算引擎（RS/Value/Vol/Crowding） |
| `RotationEngine` | 行业轮动策略引擎，TopN 选择 |
| `FastBacktester` | 向量化回测引擎，用于研究阶段 |
| `ProductionBacktester` | 事件驱动回测引擎，模拟实盘 |
| `RiskEngine` | 风险管理引擎，三层 Kill Switch |

### portfolio/ - 组合管理层

| 模块 | 说明 |
|------|------|
| `PortfolioManager` | 多策略协调，持仓管理 |
| `PortfolioBuilder` | 组合构建，权重分配 |
| `PositionManager` | 持仓跟踪，盈亏计算 |

### strategy/ - 策略层

| 模块 | 说明 |
|------|------|
| `Strategy` | 策略抽象基类 |
| `SignalGenerator` | 信号生成接口 |
| `OrderExecutor` | 订单执行接口 |

## 五、注意事项

1. **PIT 安全**: 所有计算必须使用 `knowledge_date <= trade_date` 的数据
2. **涨跌停感知**: 回测引擎必须过滤涨跌停无法成交的情况
3. **向量化优先**: 研究阶段使用 Polars 向量化计算
4. **双引擎对齐**: Fast 与 Production 引擎误差 ≤ 0.1%
5. **风险控制**: 严格遵守三层 Kill Switch 规则
6. **TDD 开发**: 遵循 RED → GREEN → REFACTOR 流程
7. **统一日志**: 使用 loguru 记录结构化日志

## 六、日志使用说明

所有模块使用 `loguru` 记录结构化日志：

### 日志级别
- **DEBUG**: 函数入参、中间结果
- **INFO**: 正常业务流程（策略开始/完成、调仓执行）
- **WARNING**: 可恢复异常（因子计算失败、数据缺失）
- **ERROR**: 错误但系统可继续（回测失败、订单拒绝）

### 示例
```python
from loguru import logger

logger.info(
    "backtest_complete",
    event="backtest",
    strategy="etf_rotation",
    total_return=0.15,
    max_drawdown=0.08,
    duration_ms=2500,
)
```

## 七、使用示例

```python
from ditto_core.engine import RegimeEngine, FactorEngine
from ditto_core.portfolio import PortfolioManager
from ditto_datahub import DataHub

# 初始化
hub = DataHub()

# Regime 识别
regime_engine = RegimeEngine(hub)
result = regime_engine.calc_regime_for_range(
    start_date="2024-01-01",
    end_date="2024-01-31"
)

# 因子计算
factor_engine = FactorEngine(hub)
factors = factor_engine.calc_factors(
    universe=["510300.SH", "510500.SH"],
    start_date="2024-01-01",
    end_date="2024-01-31"
)

# 组合管理
portfolio_mgr = PortfolioManager(hub)
portfolio = portfolio_mgr.build_portfolio(
    strategy_name="etf_rotation",
    rebalance_date="2024-01-31"
)
```

## 八、相关文档

- [引擎设计文档](../../../../docs/design/03_engine_design.md)
- [风险宪法](../../../../docs/design/08_risk_constitution.md)
- [PIT 安全指南](../../../../.claude/skills/pit-guide/SKILL.md)
