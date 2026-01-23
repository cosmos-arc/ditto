# 策略模块

**版本**: v0.2.0
**最后更新**: 2026-01-23
**状态**: 🔄 开发中

## 概要

策略抽象框架、信号生成、订单执行，提供统一的策略抽象框架，定义策略基类、信号生成接口和订单执行接口。

## 核心功能

策略模块提供统一的策略抽象框架，定义策略基类、信号生成接口和订单执行接口，支持多种量化策略的实现。

## 目录结构

```
strategy/
├── base/                 # 策略抽象基类
│   ├── strategy.py       # 策略基类
│   ├── context.py        # 策略上下文
│   └── state.py          # 策略状态管理
├── signal/               # 信号生成
│   ├── generator.py      # 信号生成器基类
│   ├── regime_signal.py  # Regime 信号
│   ├── factor_signal.py  # 因子信号
│   └── composite_signal.py # 组合信号
└── execution/            # 订单执行
    ├── executor.py       # 执行器基类
    ├── order.py          # 订单定义
    ├── fill.py           # 成交模拟
    └── cost.py           # 交易成本计算
```

## 核心功能

### Strategy - 策略基类

**功能**: 定义策略的统一接口和生命周期

**核心方法**:

```python
from abc import ABC, abstractmethod
from datetime import date
from ditto_datahub import DataHub

class Strategy(ABC):
    """策略抽象基类"""

    def __init__(self, hub: DataHub, name: str):
        self.hub = hub
        self.name = name
        self.state = StrategyState()

    @abstractmethod
    def initialize(self, start_date: date) -> None:
        """策略初始化"""
        pass

    @abstractmethod
    def generate_signals(self, trade_date: date) -> list[Signal]:
        """生成交易信号"""
        pass

    @abstractmethod
    def generate_orders(
        self,
        signals: list[Signal],
        trade_date: date
    ) -> list[Order]:
        """生成订单"""
        pass

    def on_data(self, trade_date: date) -> None:
        """数据更新回调"""
        # 1. 生成信号
        signals = self.generate_signals(trade_date)

        # 2. 生成订单
        orders = self.generate_orders(signals, trade_date)

        # 3. 返回订单
        return orders
```

**使用示例**:

```python
from ditto_core.strategy import Strategy

class RotationStrategy(Strategy):
    """行业轮动策略"""

    def __init__(
        self,
        hub: DataHub,
        top_n: int = 3,
        rebalance_freq: str = "monthly"
    ):
        super().__init__(hub, name="rotation")
        self.top_n = top_n
        self.rebalance_freq = rebalance_freq

    def initialize(self, start_date: date) -> None:
        """初始化策略"""
        logger.info(f"策略初始化: {self.name}")
        # 加载历史数据
        # 计算初始因子
        # 设置初始状态

    def generate_signals(self, trade_date: date) -> list[Signal]:
        """生成交易信号"""
        # 1. 检查是否需要调仓
        if not self._should_rebalance(trade_date):
            return []

        # 2. 计算 Regime
        regime = self.hub.regime.get_regime(trade_date)

        # 3. 计算因子
        factors = self.hub.factor.calc_factors(
            universe=self.universe,
            trade_date=trade_date
        )

        # 4. 选择 Top N
        selected = self._select_top_n(factors, self.top_n)

        # 5. 生成信号
        signals = [
            Signal(
                symbol=symbol,
                action="buy",
                weight=1.0 / self.top_n
            )
            for symbol in selected
        ]

        return signals

    def generate_orders(
        self,
        signals: list[Signal],
        trade_date: date
    ) -> list[Order]:
        """生成订单"""
        orders = []
        current_positions = self.state.get_positions()

        # 卖出不在目标列表中的持仓
        for symbol, position in current_positions.items():
            if symbol not in [s.symbol for s in signals]:
                orders.append(Order(
                    symbol=symbol,
                    action="sell",
                    quantity=position.quantity
                ))

        # 买入目标持仓
        for signal in signals:
            target_value = signal.weight * self.state.total_value
            target_quantity = int(target_value / self._get_price(signal.symbol, trade_date))

            orders.append(Order(
                symbol=signal.symbol,
                action="buy",
                quantity=target_quantity
            ))

        return orders
```

### Signal - 信号生成

**功能**: 定义交易信号的数据结构

**信号类型**:

| 信号类型 | 说明 | 示例 |
|---------|------|------|
| **BUY** | 买入信号 | 因子得分高 |
| **SELL** | 卖出信号 | 因子得分低 |
| **HOLD** | 持有信号 | 因子得分中性 |
| **REBALANCE** | 调仓信号 | 定期调仓 |

**信号定义**:

```python
from dataclasses import dataclass
from datetime import date
from enum import Enum

class SignalAction(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    REBALANCE = "rebalance"

@dataclass
class Signal:
    """交易信号"""
    symbol: str              # 标的代码
    action: SignalAction     # 信号类型
    weight: float | None = None  # 目标权重（可选）
    price: float | None = None    # 目标价格（可选）
    reason: str | None = None     # 信号原因（可选）
    confidence: float = 1.0   # 信号置信度（0-1）
    trade_date: date | None = None  # 交易日期
```

**信号生成器**:

```python
from ditto_core.strategy import SignalGenerator

class RegimeSignalGenerator(SignalGenerator):
    """Regime 信号生成器"""

    def generate(self, trade_date: date) -> Signal:
        """生成 Regime 信号"""
        regime = self.hub.regime.get_regime(trade_date)

        # 根据 Regime 生成信号
        if regime == "bull":
            action = SignalAction.BUY
            weight = 0.8
        elif regime == "osc":
            action = SignalAction.HOLD
            weight = 0.5
        else:  # bear
            action = SignalAction.SELL
            weight = 0.2

        return Signal(
            symbol="PORTFOLIO",
            action=action,
            weight=weight,
            reason=f"Regime: {regime}",
            trade_date=trade_date
        )

class FactorSignalGenerator(SignalGenerator):
    """因子信号生成器"""

    def generate(self, trade_date: date) -> list[Signal]:
        """生成因子信号"""
        # 1. 计算因子
        factors = self.hub.factor.calc_factors(
            universe=self.universe,
            trade_date=trade_date
        )

        # 2. 归一化因子得分
        scores = self._normalize_factors(factors)

        # 3. 生成信号
        signals = []
        for symbol, score in scores.items():
            if score > 0.7:
                action = SignalAction.BUY
            elif score < 0.3:
                action = SignalAction.SELL
            else:
                action = SignalAction.HOLD

            signals.append(Signal(
                symbol=symbol,
                action=action,
                weight=score,
                reason=f"Factor score: {score:.2f}",
                trade_date=trade_date
            ))

        return signals
```

### Order - 订单执行

**功能**: 定义订单数据结构和执行逻辑

**订单定义**:

```python
from dataclasses import dataclass
from enum import Enum

class OrderAction(Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(Enum):
    MARKET = "market"       # 市价单
    LIMIT = "limit"         # 限价单
    STOP = "stop"           # 止损单

@dataclass
class Order:
    """订单"""
    symbol: str              # 标的代码
    action: OrderAction      # 买卖方向
    quantity: int            # 数量（股）
    order_type: OrderType = OrderType.MARKET  # 订单类型
    price: float | None = None    # 限价单价格
    stop_price: float | None = None  # 止损价格
    trade_date: date | None = None  # 交易日期
    status: str = "pending"  # 订单状态
```

**订单执行器**:

```python
from ditto_core.strategy import OrderExecutor

class SimpleOrderExecutor(OrderExecutor):
    """简单订单执行器"""

    def execute(
        self,
        orders: list[Order],
        trade_date: date
    ) -> list[Fill]:
        """执行订单"""
        fills = []

        for order in orders:
            # 1. 获取价格
            price = self._get_execution_price(order, trade_date)

            # 2. 检查涨跌停
            if self._is_limit_price(order.symbol, price, trade_date):
                logger.warning(f"涨跌停无法成交: {order.symbol}")
                continue

            # 3. 模拟成交
            fill = Fill(
                symbol=order.symbol,
                action=order.action,
                quantity=order.quantity,
                price=price,
                trade_date=trade_date
            )

            # 4. 计算交易成本
            fill.commission = self._calc_commission(fill)
            fill.slippage = self._calc_slippage(fill)

            fills.append(fill)

        return fills

    def _get_execution_price(
        self,
        order: Order,
        trade_date: date
    ) -> float:
        """获取成交价格"""
        bar = self.hub.bars.get_bar(order.symbol, trade_date)

        if order.order_type == OrderType.MARKET:
            # 市价单：使用收盘价
            return bar.close
        elif order.order_type == OrderType.LIMIT:
            # 限价单：使用限价或收盘价
            return min(order.price, bar.close) if order.action == OrderAction.BUY else max(order.price, bar.close)
        else:
            return bar.close

    def _is_limit_price(
        self,
        symbol: str,
        price: float,
        trade_date: date
    ) -> bool:
        """检查是否涨跌停"""
        bar = self.hub.bars.get_bar(symbol, trade_date)
        return price == bar.high or price == bar.low

    def _calc_commission(self, fill: Fill) -> float:
        """计算佣金"""
        # 万三佣金率
        commission_rate = 0.0003
        return fill.quantity * fill.price * commission_rate

    def _calc_slippage(self, fill: Fill) -> float:
        """计算滑点"""
        # 0.1% 滑点
        slippage_rate = 0.001
        return fill.quantity * fill.price * slippage_rate
```

### 策略上下文

**功能**: 提供策略运行时的上下文信息

```python
from dataclasses import dataclass

@dataclass
class StrategyContext:
    """策略上下文"""
    hub: DataHub                    # 数据访问
    trade_date: date                # 当前交易日
    regime: str                     # 市场状态
    portfolio_value: float          # 组合价值
    available_cash: float           # 可用资金
    positions: dict[str, int]       # 当前持仓

    def get_position(self, symbol: str) -> int:
        """获取持仓数量"""
        return self.positions.get(symbol, 0)

    def get_weight(self, symbol: str) -> float:
        """获取持仓权重"""
        quantity = self.get_position(symbol)
        price = self.hub.bars.get_close(symbol, self.trade_date)
        position_value = quantity * price
        return position_value / self.portfolio_value
```

## 依赖关系

- **上游**: `ditto-datahub` (数据访问)、`ditto-core.engine` (引擎)
- **下游**: `ditto-core.portfolio` (组合管理)

## 核心设计原则

### 1. 策略与执行分离

策略只负责生成信号，不负责执行细节：

```python
# 策略生成信号
signals = strategy.generate_signals(trade_date)

# 执行器生成订单
orders = executor.generate_orders(signals)

# 订单执行
fills = order_executor.execute(orders, trade_date)
```

### 2. 状态管理

策略需要维护自己的状态：

```python
class StrategyState:
    """策略状态"""

    def __init__(self):
        self.positions: dict[str, int] = {}
        self.cash: float = 0
        self.last_rebalance: date | None = None

    def update_position(self, symbol: str, quantity: int):
        """更新持仓"""
        self.positions[symbol] = quantity

    def get_position(self, symbol: str) -> int:
        """获取持仓"""
        return self.positions.get(symbol, 0)
```

### 3. 可测试性

策略设计应易于测试：

```python
def test_rotation_strategy():
    # Arrange
    hub = MockDataHub()
    strategy = RotationStrategy(hub, top_n=3)

    # Act
    signals = strategy.generate_signals(date(2024, 1, 31))

    # Assert
    assert len(signals) == 3
    assert all(s.action == SignalAction.BUY for s in signals)
```

## 相关文档

- [引擎设计文档](../../../../docs/design/03_engine_design.md)
- [系统设计总览](../../../../docs/design/01_system_design.md)
- [Polars 使用指南](../../../../.claude/skills/polars-guide/SKILL.md)
