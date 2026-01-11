# 投资组合管理模块

> 多策略协调、组合构建、持仓管理

## 概述

投资组合管理模块负责多策略协调、投资组合构建、持仓跟踪和风险控制，是连接策略执行和实际交易的核心环节。

## 目录结构

```
portfolio/
├── manager/          # 组合管理器
│   ├── portfolio_mgr.py # 多策略协调
│   ├── rebalance_mgr.py # 调仓管理
│   └── risk_mgr.py      # 风险控制
├── builder/          # 组合构建器
│   ├── weight_allocator.py # 权重分配
│   ├── position_sizer.py  # 仓位计算
│   └── trade_generator.py # 交易生成
└── position/         # 持仓管理
    ├── tracker.py    # 持仓跟踪
    ├── pnl_calc.py   # 盈亏计算
    └── analyzer.py   # 持仓分析
```

## 核心功能

### PortfolioManager - 组合管理器

**功能**: 多策略协调，统一管理多个策略的投资组合

**核心职责**:
- 管理多个策略的持仓
- 协调策略间的资金分配
- 执行调仓操作
- 风险控制

**使用示例**:

```python
from ditto_core.portfolio import PortfolioManager
from ditto_core.strategy import RotationStrategy, MomentumStrategy

# 初始化组合管理器
mgr = PortfolioManager(
    hub=hub,
    initial_capital=1_000_000,
    max_strategies=3
)

# 添加策略
rotation_strategy = RotationStrategy(top_n=3, rebalance_freq="monthly")
momentum_strategy = MomentumStrategy(top_n=5, rebalance_freq="weekly")

mgr.add_strategy(rotation_strategy, allocation=0.6)
mgr.add_strategy(momentum_strategy, allocation=0.4)

# 执行调仓
rebalance_result = mgr.rebalance(
    rebalance_date="2024-01-31",
    regime="bull"
)

# 查看结果
print(f"调仓交易数: {len(rebalance_result.trades)}")
print(f"预计交易成本: {rebalance_result.estimated_cost:.2f}")
```

### PortfolioBuilder - 组合构建器

**功能**: 根据策略信号构建投资组合

**权重分配方式**:

| 方式 | 说明 | 适用场景 |
|------|------|----------|
| **等权** | 所有标的权重相等 | 简单轮动 |
| **Score 加权** | 按因子得分加权 | 多因子策略 |
| **风险平价** | 按风险贡献加权 | 风险均衡 |
| **市值加权** | 按市值加权 | 指数跟踪 |

**使用示例**:

```python
from ditto_core.portfolio import PortfolioBuilder

builder = PortfolioBuilder(hub)

# 等权组合
portfolio = builder.build_equal_weighted(
    targets=["510300.SH", "510500.SH", "512000.SH"],
    total_capital=600_000,
    max_single_position=0.15  # 单票最大 15%
)

# Score 加权组合
portfolio = builder.build_score_weighted(
    targets={
        "510300.SH": 0.8,
        "510500.SH": 0.6,
        "512000.SH": 0.9
    },
    total_capital=600_000,
    min_weight=0.1,  # 最小权重 10%
    max_weight=0.4   # 最大权重 40%
)

# 风险平价组合
portfolio = builder.build_risk_parity(
    targets=["510300.SH", "510500.SH", "512000.SH"],
    total_capital=600_000,
    lookback_days=60
)
```

### PositionManager - 持仓管理器

**功能**: 跟踪持仓、计算盈亏、分析持仓

**使用示例**:

```python
from ditto_core.portfolio import PositionManager

pos_mgr = PositionManager(hub)

# 获取当前持仓
positions = pos_mgr.get_positions(asof_date="2024-01-31")

# 计算持仓盈亏
pnl = pos_mgr.calc_pnl(
    position=positions[0],
    start_date="2024-01-01",
    end_date="2024-01-31"
)

print(f"持仓收益: {pnl.total_pnl:.2f}")
print(f"已实现盈亏: {pnl.realized_pnl:.2f}")
print(f"浮动盈亏: {pnl.unrealized_pnl:.2f}")

# 持仓分析
analysis = pos_mgr.analyze_position(
    position=positions[0],
    asof_date="2024-01-31"
)

print(f"持仓天数: {analysis.holding_days}")
print(f"年化收益: {analysis.annual_return:.2%}")
print(f"夏普比率: {analysis.sharpe_ratio:.2f}")
```

## 调仓管理

### 调仓触发条件

| 触发类型 | 说明 | 示例 |
|---------|------|------|
| **定期调仓** | 按固定周期调仓 | 每月第一个交易日 |
| **触发调仓** | 满足条件时调仓 | Regime 切换 |
| **阈值调仓** | 偏离目标超过阈值 | 权重偏离 > 5% |

### 调仓流程

```
1. 生成调仓计划
   ├─ 计算目标权重
   ├─ 对比当前持仓
   └─ 生成交易列表

2. 风险检查
   ├─ 仓位限制检查
   ├─ Kill Switch 检查
   └─ 流动性检查

3. 交易优化
   ├─ 减少交易数量
   ├─ 合并买卖方向
   └─ 分批大额交易

4. 执行交易
   ├─ 生成订单
   ├─ 模拟成交
   └─ 更新持仓
```

**使用示例**:

```python
from ditto_core.portfolio import RebalanceManager

rebalance_mgr = RebalanceManager(hub)

# 生成调仓计划
plan = rebalance_mgr.generate_plan(
    current_portfolio=current_portfolio,
    target_weights={
        "510300.SH": 0.4,
        "510500.SH": 0.3,
        "512000.SH": 0.3
    },
    rebalance_date="2024-01-31"
)

# 风险检查
risk_check = rebalance_mgr.check_risk(
    plan=plan,
    regime="bull",
    max_total_position=0.9
)

if not risk_check.is_safe:
    logger.warning(f"风险检查失败: {risk_check.violations}")
    # 调整计划或中止调仓

# 执行调仓
execution_result = rebalance_mgr.execute(
    plan=plan,
    slippage_rate=0.001,  # 0.1% 滑点
    commission_rate=0.0003  # 万三佣金
)

print(f"执行交易数: {len(execution_result.trades)}")
print(f"实际交易成本: {execution_result.actual_cost:.2f}")
```

## 风险控制

### 仓位限制

根据 Regime 状态动态调整仓位：

| Regime | 总仓位 | 单票上限 | 现金下限 |
|--------|--------|----------|----------|
| Bull   | 70-90% | 15% | 10% |
| Osc    | 50-70% | 12% | 30% |
| Bear   | 10-40% | 10% | 60% |

**使用示例**:

```python
from ditto_core.portfolio import RiskManager

risk_mgr = RiskManager(hub)

# 获取仓位限制
limits = risk_mgr.get_position_limits(regime="bull")

# 验证仓位合规
compliance = risk_mgr.check_position_limits(
    portfolio=portfolio,
    regime="bull"
)

if not compliance.is_compliant:
    logger.error(f"仓位违规: {compliance.violations}")
    # 强制平仓或调整仓位
```

### 风险监控

**实时监控指标**:

| 指标 | 说明 | 阈值 |
|------|------|------|
| 组合回撤 | 相对高点的回撤 | ≥10% 触发 Level 1 |
| 单票仓位 | 单个标的权重 | ≤15% (Bull) |
| 集中度 | 前 5 大持仓占比 | ≤60% |
| 换手率 | 调仓换手率 | ≤50% |

## 依赖关系

- **上游**: `ditto-datahub` (数据访问)、`ditto-core.engine` (引擎)、`ditto-core.strategy` (策略)
- **下游**: `ditto-core.engine.risk` (风险引擎)

## 核心设计原则

### 1. 多策略协调

支持同时运行多个策略，自动分配资金：

```python
# 添加策略
mgr.add_strategy(rotation_strategy, allocation=0.6)
mgr.add_strategy(momentum_strategy, allocation=0.4)

# 自动协调资金分配
```

### 2. 风险优先

所有调仓操作必须通过风险检查：

```python
# 风险检查
if not risk_check.is_safe:
    # 拒绝调仓
    return
```

### 3. 交易成本优化

自动优化交易，减少不必要的调仓：

```python
# 自动过滤小额调仓
plan = rebalance_mgr.optimize(
    plan=plan,
    min_trade_amount=10_000,  # 最小交易额 1万
    min_weight_diff=0.05      # 最小权重差异 5%
)
```

## 相关文档

- [引擎设计文档](../../../../docs/design/03_engine_design.md)
- [风险宪法](../../../../docs/design/08_risk_constitution.md)
- [系统设计总览](../../../../docs/design/01_system_design.md)
