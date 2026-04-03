# ditto-core

**版本**: v0.2.0
**最后更新**: 2026-01-23
**状态**: 🔄 开发中

## 概要

核心业务逻辑层 - 量化引擎、组合管理、策略框架，提供量化交易系统的核心业务逻辑。

## 核心功能

提供量化交易系统的核心业务逻辑，包括回测引擎、投资组合管理、策略框架等。

## 二、架构定位

```
┌─────────────────────────────────────┐
│         apps/port                 │
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
│        ditto-infra                  │
│     (基础设施层)                      │
└─────────────────────────────────────┘
```

**依赖方向**: 仅依赖 `ditto-datahub` 和 `ditto-infra`

## 三、目录结构

```
src/ditto_engine/
├── quality/           # 数据质量模块（Domain Layer）
│   ├── checkers/      # DQ 检查器
│   │   ├── technical.py      # L1 技术检查
│   │   ├── business.py       # L2 业务检查
│   │   └── statistical.py    # L3 统计检查
│   ├── spec.py        # 规则配置模型
│   ├── config.py      # DQ 配置（pydantic-settings）
│   ├── engine.py      # QualityEngine
│   └── report.py      # 报告生成器
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

### quality/ - 数据质量模块

| 模块 | 说明 |
|------|------|
| `QualityEngine` | DQ 检查引擎，协调 L1/L2/L3 检查 |
| `TechnicalChecker` | L1 技术检查（非空、唯一、外键、类型） |
| `BusinessChecker` | L2 业务检查（正数、范围、 completeness） |
| `StatisticalChecker` | L3 统计检查（Z-score 异常、波动检测） |
| `DQSettings` | DQ 配置（pydantic-settings，支持环境变量） |
| `DQReportGenerator` | DQ 报告生成器（Markdown/HTML） |

**架构特点**：
- 纯函数式业务逻辑，零依赖 DataHub
- 所有数据通过参数注入（由 Application Layer 提供）
- 支持多级 DQ 检查（L1 阻断、L2 警告、L3 告警）

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
from pathlib import Path
from ditto_engine.quality import QualityEngine
from ditto_engine.engine import RegimeEngine, FactorEngine
from ditto_engine.portfolio import PortfolioManager
from ditto_data import DataHub
from ditto_data.storage.market import MarketBarsQuery
import polars as pl

# 初始化
hub: DataHub = container.get(DataHub)

# === 数据质量检查 ===
# L1/L2 检查（写入时）
dq_engine = QualityEngine(data_root=Path("data"))
result = dq_engine.check(df, dataset="stock_daily")
if result.has_errors:
    print(f"DQ 检查失败: {result.error_count} 个错误")

# L3 统计检查（批量监控）
historical = hub.market.query(
    MarketBarsQuery(
        market_wide=True,
        asset_class="stock",
        start="2024-01-01",
        end="2024-01-31",
    )
)
current = hub.market.query(
    MarketBarsQuery(
        market_wide=True,
        asset_class="stock",
        start="2024-02-01",
        end="2024-02-01",
    )
)
result = dq_engine.check_statistical(
    dataset="stock_daily",
    current=current,      # 注入当前数据
    historical=historical, # 注入历史数据
)

# === Regime 识别 ===
regime_engine = RegimeEngine(hub)
result = regime_engine.calc_regime_for_range(
    start_date="2024-01-01",
    end_date="2024-01-31"
)

# === 因子计算 ===
factor_engine = FactorEngine(hub)
factors = factor_engine.calc_factors(
    universe=[InstrumentId(2_000_001), InstrumentId(2_000_002)],
    start_date="2024-01-01",
    end_date="2024-01-31"
)

# === 组合管理 ===
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
