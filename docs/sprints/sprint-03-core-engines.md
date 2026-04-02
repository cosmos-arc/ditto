# Sprint 3: 核心引擎实现（基于官方设计文档）

**时间**: Week 9-12 (3-4 周)
**Phase**: 1.1 核心引擎期
**目标**: 按照官方设计文档实现核心引擎和策略框架

**参考文档**：
- 《03_engine_design.md》 - 引擎设计文档（v2.0 Final）
- 《08_risk_constitution.md》 - 风险宪法

## Sprint 目标

1. 实现RegimeEngine（市场状态识别）
2. 实现FactorEngine（4个核心因子）
3. 实现RotationEngine（多因子打分）
4. 实现策略框架（Strategy基类及实现）
5. 实现PortfolioManager（组合管理）

## 官方设计要点

### 1. RegimeEngine设计（严格遵循）

**关键特性**：
- 自适应阈值（基于历史分位数）
- 确认期机制（连续N天才确认）
- 极端行情检测（CRASH/CRISIS/VOL_SPIKE）

**核心参数**：
```python
# 官方设计中的固定参数
LOOKBACK_DAYS = 500
BULL_QUANTILE = 0.7
BEAR_QUANTILE = 0.3
CONFIRM_DAYS = 3

# 维度权重
TREND_WEIGHT = 0.4
MOMENTUM_WEIGHT = 0.3
VOLATILITY_WEIGHT = 0.2
WIDTH_WEIGHT = 0.1
```

### 2. 因子引擎设计

**核心因子**：
1. **RSFactor（相对强弱）**
   - 计算：ETF收益 - 基准收益
   - 周期：20日

2. **VolatilityFactor（波动率）**
   - 计算：年化波动率，低波动高得分
   - 处理：取倒数后标准化

3. **ValueFactor（估值）**
   - 计算：历史分位数
   - 数据：ETF估值数据

4. **CrowdingFactor（拥挤度）**
   - 计算：成交额放大倍数倒数

**健康度监控**（严格按官方标准）：
- 6M IC > 3%：健康
- 6M IC 2-3%：观察
- 6M IC 1-2%：警告（权重降低50%）
- 6M IC < 1%：下线

### 3. 策略框架设计

**核心抽象**（必须按官方实现）：
```python
class Strategy(ABC):
    @abstractmethod
    def generate_signals(self, ctx: StrategyContext) -> SignalSet:
        pass

    @abstractmethod
    def validate_prerequisites(self, ctx: StrategyContext) -> bool:
        pass
```

**策略类型**：
1. **RegimeAwareStrategy** - 感知Regime
2. **FactorBasedStrategy** - 基于因子
3. **具体实现**：
   - ETFRotationStrategy（行业轮动）
   - DefensiveStrategy（防御策略）
   - MomentumStrategy（动量策略）

### 4. PortfolioManager设计

**职责**（官方定义）：
1. 管理多个策略实例
2. 资金分配（风险预算）
3. 信号聚合与冲突处理
4. 风险预算控制

## 任务分解

### P0 - 必须完成

#### 任务1: 实现RegimeEngine
- **文件**：
  - `packages/core/src/ditto_engine/engine/regime_engine.py`
  - `packages/core/src/ditto_engine/engine/extreme_market_detector.py`
- **测试**：`packages/core/tests/unit/test_regime_engine.py`
- **关键实现**：
  - 完全按照官方文档的算法实现
  - 包含自适应阈值计算
  - 包含确认期机制
  - 包含极端行情检测
- **状态**：❌

#### 任务2: 实现因子系统
- **文件**：
  - `packages/core/src/ditto_engine/factors/base.py` - Factor基类
  - `packages/core/src/ditto_engine/factors/rs_factor.py`
  - `packages/core/src/ditto_engine/factors/volatility_factor.py`
  - `packages/core/src/ditto_engine/factors/value_factor.py`
  - `packages/core/src/ditto_engine/factors/crowding_factor.py`
  - `packages/core/src/ditto_engine/factors/analyzer.py` - FactorAnalyzer
- **测试**：`packages/core/tests/unit/test_factors/`
- **状态**：❌

#### 任务3: 实现策略框架
- **文件**：
  - `packages/core/src/ditto_engine/strategy/base.py`
  - `packages/core/src/ditto_engine/strategy/rotation_strategy.py`
  - `packages/core/src/ditto_engine/strategy/defensive_strategy.py`
  - `packages/core/src/ditto_engine/strategy/momentum_strategy.py`
- **测试**：`packages/core/tests/unit/test_strategies/`
- **状态**：❌

#### 任务4: 实现PortfolioManager
- **文件**：
  - `packages/core/src/ditto_engine/portfolio/portfolio_manager.py`
  - `packages/core/src/ditto_engine/portfolio/strategy_allocation.py`
- **测试**：`packages/core/tests/unit/test_portfolio_manager.py`
- **状态**：❌

### P1 - 应该完成

#### 任务5: 技术指标库
- **文件**：
  - `packages/core/src/ditto_engine/indicators/technical.py`
- **功能**：
  - Polars原生实现
  - 比Pandas-TA快18倍
  - 支持SMA、EMA、RSI、MACD、布林带、ATR
- **状态**：❌

## 验收标准

- [ ] RegimeEngine历史回溯符合：
  - 2015股灾：bear状态
  - 2020新冠：osc→bear→bull
  - 2021结构牛：bull状态
- [ ] 所有因子IC值验证（6M IC > 2%）
- [ ] 策略信号可解释（reason字段）
- [ ] PortfolioManager支持多策略协调
- [ ] 所有代码通过pre-commit检查

## 关键文件清单

```
packages/core/src/ditto_engine/
├── engine/
│   ├── __init__.py
│   ├── base_engine.py
│   ├── regime_engine.py          # 完全按官方实现
│   ├── extreme_market_detector.py # 极端行情检测
│   └── models/
│       └── regime_result.py
├── factors/
│   ├── __init__.py
│   ├── base.py                   # Factor抽象基类
│   ├── rs_factor.py             # 相对强弱
│   ├── volatility_factor.py     # 波动率
│   ├── value_factor.py          # 估值
│   ├── crowding_factor.py       # 拥挤度
│   ├── analyzer.py              # FactorAnalyzer
│   └── health_monitor.py        # 健康度监控
├── strategy/
│   ├── __init__.py
│   ├── base.py                  # Strategy基类（按官方）
│   ├── rotation_strategy.py     # 行业轮动
│   ├── defensive_strategy.py    # 防御策略
│   └── momentum_strategy.py     # 动量策略
├── portfolio/
│   ├── __init__.py
│   ├── portfolio_manager.py     # 组合管理器
│   └── strategy_allocation.py   # 策略分配
└── indicators/
    └── technical.py             # 技术指标库
```

## 与官方设计的对应关系

| 官方设计 | Sprint实现 |
|---------|------------|
| RegimeEngine + ExtremeMarketDetector | 任务1 |
| Factor Engine + TechnicalIndicators | 任务2 |
| Strategy Layer (Portfolio/Strategy/Signal) | 任务3 |
| Portfolio Manager | 任务4 |
| 配置驱动 | 通过YAML文件实现 |

## 注意事项

1. **严格遵循官方文档**：所有算法必须与设计文档一致
2. **使用DataHub**：所有数据访问通过DataHub，确保PIT安全
3. **Polars优先**：性能关键部分使用Polars向量化
4. **完整测试**：每个组件都需要单元测试和集成测试
5. **基于数据层成果**：Sprint 2 已完成数据层完善，可充分利用 DataHub 的完整功能

## 下一步

Sprint 3完成后，将进入Sprint 4回测与风控阶段，使用已实现的引擎构建完整的回测系统。

---

## 调整说明

**原 Sprint 2 核心引擎任务**已延后到当前 Sprint 3，原因是 Sprint 2 专注于数据层完善：
- DQ 三层架构（L1/L2/L3）
- DataHub 完整实现（Universe/Index/Freeze/元数据）
- 数据摄取增强（增量/监控/告警/AkShare）
- 黄金数据集验证（最终验收）

这为引擎开发提供了坚实的数据基础。

---

## 状态图例

- ❌ 未开始
- 🔄 进行中
- ✅ 已完成
- 🚧 阻塞中
- 📝 规划中
