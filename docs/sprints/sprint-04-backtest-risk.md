# Sprint 4: 回测与风控（基于官方设计文档）

**时间**: Week 13-16 (3-4 周)
**Phase**: 1.2 回测风控期
**目标**: 按照官方设计文档实现回测引擎和风控系统

**参考文档**：
- 《03_engine_design.md》 - 引擎设计文档（第5章回测引擎）
- 《08_risk_constitution.md》 - 风险宪法

## Sprint 目标

1. 实现FastBacktester（向量化回测）
2. 实现ProductionBacktester（事件驱动回测）
3. 实现RiskEngine（三级Kill Switch）
4. 实现对齐测试框架（误差<0.1%）
5. 实现Walk-Forward验证器

## 官方设计要点

### 1. 回测引擎架构（必须实现）

**双引擎模式**：
- **FastBacktester**：向量化计算，研究阶段使用
- **ProductionBacktester**：事件驱动，生产使用

**关键要求**（来自设计文档）：
- 涨跌停过滤：涨停不能买，跌停不能卖
- 成本模型：EnhancedCostModel（佣金、印花税、滑点、市场冲击）
- 对齐严格：Fast vs Prod误差≤0.1%

### 2. RiskEngine设计（严格按风险宪法）

**三级Kill Switch**（第4条）：
- **Level 1** (≥15%)：停止新开仓，回撤<8%自动恢复
- **Level 2** (≥18%)：强制减仓50%，需人工确认
- **Level 3** (≥20%)：强制清仓，需策略重构评审

**回撤速度触发**（第5条）：
- 3日回撤≥5%：提前触发Level 1
- 回撤加速度>1%/天²：暂停新开仓

**禁止行为**（第6条）：
- ❌ "再观察几天"
- ❌ 手动绕过
- ❌ Level 2/3不减仓

### 3. 对齐测试标准

**严格标准**（来自设计文档）：
```python
RETURN_TOLERANCE = 0.001      # 0.1%
DRAWDOWN_TOLERANCE = 0.005    # 0.5%
```

### 4. Walk-Forward验证（解决过拟合）

**核心思想**：
- 在训练期优化参数（可选）
- 在测试期验证
- 滚动前进，重复1-2
- 汇总所有测试期结果

## 任务分解

### P0 - 必须完成

#### 任务1: 实现FastBacktester
- **文件**：
  - `packages/core/src/ditto_core/backtest/fast_backtester.py`
  - `packages/core/src/ditto_core/backtest/models/backtest_result.py`
  - `packages/core/src/ditto_core/backtest/models/cost_model.py`
- **测试**：`packages/core/tests/unit/test_fast_backtester.py`
- **关键实现**：
  - 向量化计算（基于Polars）
  - 涨跌停过滤（严格按照设计）
  - EnhancedCostModel
  - 支持多种策略回测
- **状态**：❌

#### 任务2: 实现ProductionBacktester
- **文件**：
  - `packages/core/src/ditto_core/backtest/production_backtester.py`
  - `packages/core/src/ditto_core/backtest/event_engine.py`
  - `packages/core/src/ditto_core/backtest/portfolio.py`
  - `packages/core/src/ditto_core/backtest/order.py`
- **测试**：`packages/core/tests/unit/test_production_backtester.py`
- **关键实现**：
  - 事件驱动架构
  - 逐日交易模拟
  - 订单执行模拟
  - 更真实的成本模型
- **状态**：❌

#### 任务3: 实现RiskEngine
- **文件**：
  - `packages/core/src/ditto_core/risk/risk_engine.py`
  - `packages/core/src/ditto_core/risk/kill_switch.py`
  - `packages/core/src/ditto_core/risk/drawdown_monitor.py`
- **测试**：`packages/core/tests/unit/test_risk_engine.py`
- **关键实现**：
  - 三级Kill Switch（严格按风险宪法）
  - 回撤速度检测
  - 自动化触发机制
  - 审计日志
- **状态**：❌

#### 任务4: 实现对齐测试框架
- **文件**：
  - `packages/core/src/ditto_core/backtest/alignment_tester.py`
  - `packages/core/tests/integration/test_backtest_alignment.py`
- **验收**：
  - 误差<0.1%（RETURN_TOLERANCE）
  - 持仓完全匹配
  - 交易次数一致
- **状态**：❌

### P1 - 应该完成

#### 任务5: 实现Walk-Forward验证器
- **文件**：
  - `packages/core/src/ditto_core/backtest/walk_forward.py`
- **功能**：
  - 滚动窗口验证
  - 避免过拟合
  - 参数优化
  - 结果汇总
- **状态**：❌

#### 任务6: 实现BacktestOrchestrator
- **文件**：
  - `packages/core/src/ditto_core/backtest/orchestrator.py`
- **功能**：
  - 协调各类回测任务
  - 统一结果格式
  - 批量回测管理
- **状态**：❌

#### 任务7: API集成
- **文件**：
  - `apps/port/src/ditto_port/api/v1/backtest.py`
  - `apps/port/src/ditto_port/services/backtest_svc.py`
- **功能**：
  - RESTful API
  - 回测任务管理
  - 结果查询
- **状态**：❌

## 关键实现细节

### 1. 涨跌停过滤（必须实现）

```python
def _filter_limit_locked(self, symbols, limit_status, direction):
    """过滤涨跌停（按官方设计）"""
    filtered = []
    for symbol in symbols:
        status = limit_status.get(symbol, "NORMAL")

        if direction == "BUY":
            # 涨停/停牌无法买入
            if status not in ("LIMIT_UP", "SUSPENDED"):
                filtered.append(symbol)
        else:  # SELL
            # 跌停/停牌无法卖出
            if status not in ("LIMIT_DOWN", "SUSPENDED"):
                filtered.append(symbol)

    return filtered
```

### 2. 增强成本模型

```python
class EnhancedCostModel:
    """官方设计的成本模型"""
    def __init__(self, commission_rate=0.0005, stamp_tax_rate=0.001):
        self.commission_rate = commission_rate
        self.stamp_tax_rate = stamp_tax_rate
        self.min_commission = 5.0
        self.flow_fee = 0.0
        self.base_slippage = 0.001
        self.market_impact_coef = 0.1

    def calc_total_cost(self, order_amount, direction, daily_volume,
                       volatility, spread):
        """计算总成本"""
        # 佣金
        commission = max(order_amount * self.commission_rate,
                        self.min_commission)

        # 印花税（仅卖出）
        stamp_tax = order_amount * self.stamp_tax_rate if direction == "SELL" else 0

        # 滑点（包含市场冲击）
        participation_rate = order_amount / (daily_volume + 1e-10)
        market_impact = self.market_impact_coef * volatility * (participation_rate ** 0.5)
        slippage_cost = order_amount * (self.base_slippage + spread/2 + market_impact)

        return commission + stamp_tax + self.flow_fee + slippage_cost
```

### 3. Kill Switch实现

```python
class KillSwitch:
    """三级Kill Switch（严格按风险宪法第4条）"""

    THRESHOLDS = {
        "level1": 0.15,  # 15%
        "level2": 0.18,  # 18%
        "level3": 0.20,  # 20%
    }

    SPEED_TRIGGERS = {
        "three_day": 0.05,      # 3日回撤≥5%
        "acceleration": 0.01    # >1%/天²
    }

    def check(self, current_drawdown, drawdown_speed, history):
        """检查触发条件"""
        # Level检查
        if current_drawdown >= self.THRESHOLDS["level3"]:
            return "LEVEL3", "强制清仓"
        elif current_drawdown >= self.THRESHOLDS["level2"]:
            return "LEVEL2", "强制减仓50%"
        elif current_drawdown >= self.THRESHOLDS["level1"]:
            return "LEVEL1", "停止新开仓"

        # 速度检查
        if drawdown_speed >= self.SPEED_TRIGGERS["three_day"]:
            return "LEVEL1_SPEED", "3日回撤过大"
        if drawdown_speed >= self.SPEED_TRIGGERS["acceleration"]:
            return "PAUSE", "回撤加速度过大"

        return "OK", None
```

## 验收标准

- [ ] 对齐测试100%通过（误差<0.1%）
- [ ] 历史关键时点验证：
  - 2015股灾：回撤<25%，Kill Switch正确触发
  - 2020新冠：回撤<15%，符合预期
  - 2022熊市：回撤<20%
- [ ] Kill Switch严格按风险宪法实现
- [ ] 涨跌停过滤正确工作
- [ ] Walk-Forward验证器可用
- [ ] API接口完整

## 关键文件清单

```
packages/core/src/ditto_core/
├── backtest/
│   ├── __init__.py
│   ├── fast_backtester.py        # 向量化引擎
│   ├── production_backtester.py  # 事件驱动引擎
│   ├── alignment_tester.py       # 对齐测试
│   ├── walk_forward.py           # Walk-Forward验证
│   ├── orchestrator.py           # 回测编排器
│   ├── event_engine.py           # 事件引擎
│   ├── portfolio.py              # 投资组合
│   └── models/
│       ├── backtest_result.py    # 回测结果
│       ├── cost_model.py         # 成本模型
│       └── order.py              # 订单模型
├── risk/
│   ├── __init__.py
│   ├── risk_engine.py            # 风控引擎
│   ├── kill_switch.py            # 熔断机制
│   └── drawdown_monitor.py       # 回撤监控

apps/port/src/ditto_port/
├── api/v1/
│   └── backtest.py               # 回测API
└── services/
    └── backtest_svc.py           # 回测服务
```

## 与官方设计的对应关系

| 官方设计 | Sprint实现 |
|---------|------------|
| FastBacktester + ProductionBacktester | 任务1、2 |
| 对齐测试（误差<0.1%） | 任务4 |
| 三级Kill Switch | 任务3 |
| Walk-Forward验证 | 任务5 |
| 涨跌停过滤 | 在任务1、2中实现 |
| EnhancedCostModel | 在任务1、2中实现 |

## 交付物

1. 完整回测框架（Fast + Production）
2. 严格的风险控制（Kill Switch）
3. 对齐测试保证（误差<0.1%）
4. Walk-Forward验证器
5. RESTful API接口

## 注意事项

1. **严格遵循风险宪法**：所有风控规则必须按文档实现
2. **涨跌停过滤**：必须实现，否则回测结果不可信
3. **对齐测试**：误差必须<0.1%，这是硬性要求
4. **审计日志**：所有风控动作必须记录
5. **成本模型**：必须包含市场冲击等现实因素
6. **基于数据层和引擎成果**：充分利用 Sprint 2（数据层）和 Sprint 3（引擎）的成果

---

**Phase 1成功标准达成**：
- ✅ 数据基础坚实（Sprint 1）
- ✅ 数据层完善（Sprint 2）
- ✅ 核心引擎完备（Sprint 3）
- ✅ 回测验证通过（Sprint 4）
- ✅ 风控体系健全（Sprint 4）

---

## 调整说明

**原 Sprint 3 回测与风控任务**已延后到当前 Sprint 4，原因是：
- Sprint 2 专注于数据层完善（DQ/DataHub/摄取/验证）
- Sprint 3 专注于核心引擎实现（RegimeEngine/FactorEngine/Strategy）
- Sprint 4 专注于回测与风控系统

这样的调整确保了每个阶段都有充分的时间完成，并建立了清晰的依赖关系。

---

## 状态图例

- ❌ 未开始
- 🔄 进行中
- ✅ 已完成
- 🚧 阻塞中
- 📝 规划中
