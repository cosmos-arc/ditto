---
paths: packages/core/src/ditto_core/strategy/**/*.py, packages/core/src/ditto_core/strategies/**/*.py
---

# 策略编写规范

> ETF 轮动策略的设计与实现标准

## 策略架构

```
┌─────────────────────────────────────────────────────────┐
│                    Strategy Layer                        │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────┐   │
│  │              BaseStrategy (抽象基类)             │   │
│  │  • initialize()  初始化                         │   │
│  │  • generate_signals()  生成信号                 │   │
│  │  • on_data()  数据回调                          │   │
│  └─────────────────────────────────────────────────┘   │
│                         ▲                               │
│           ┌─────────────┼─────────────┐                │
│           │             │             │                │
│  ┌────────┴───┐  ┌──────┴─────┐  ┌───┴────────┐      │
│  │ ETFRotation│  │ MomentumETF │  │ ValueETF   │      │
│  │ Strategy   │  │ Strategy    │  │ Strategy   │      │
│  └────────────┘  └────────────┘  └────────────┘      │
│                                                        │
└─────────────────────────────────────────────────────────┘
```

## 策略基类

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any
import polars as pl


@dataclass
class Signal:
    """交易信号"""

    code: str                               # 标的代码
    direction: str                          # "buy" | "sell" | "hold"
    weight: float                           # 目标权重 (0~1)

    # 可选信息
    reason: str | None = None               # 信号原因
    confidence: float = 1.0                 # 置信度
    priority: int = 0                       # 优先级

    # 执行约束
    limit_price: float | None = None        # 限价
    stop_loss: float | None = None          # 止损价
    take_profit: float | None = None        # 止盈价

    def __post_init__(self):
        if self.direction not in ("buy", "sell", "hold"):
            raise ValueError(f"Invalid direction: {self.direction}")
        if not 0 <= self.weight <= 1:
            raise ValueError(f"Weight must be in [0, 1], got {self.weight}")


@dataclass
class StrategyContext:
    """策略上下文：传递给策略的环境信息"""

    current_date: date                      # 当前日期
    positions: dict[str, float]             # 当前持仓 code -> weight
    cash_ratio: float                       # 现金比例
    portfolio_value: float                  # 组合总值

    # 市场状态
    market_regime: str | None = None        # 市场状态

    # 历史数据
    price_history: pl.DataFrame | None = None
    factor_data: pl.DataFrame | None = None


@dataclass
class StrategyConfig:
    """策略配置基类"""

    name: str                               # 策略名称
    version: str = "1.0.0"                  # 版本号

    # 标的池
    universe: list[str] = field(default_factory=list)

    # 调仓
    rebalance_freq: str = "weekly"          # daily | weekly | monthly

    # 仓位
    max_positions: int = 5                  # 最大持仓数
    max_single_weight: float = 0.3          # 单标的最大权重
    min_cash_ratio: float = 0.05            # 最小现金比例

    # 风控
    stop_loss: float | None = None          # 策略级止损
    take_profit: float | None = None        # 策略级止盈

    def validate(self) -> None:
        if not self.universe:
            raise ValueError("universe cannot be empty")
        if self.max_positions < 1:
            raise ValueError("max_positions must be at least 1")


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(self):
        self._config: StrategyConfig | None = None
        self._initialized: bool = False
        self._name: str = self.__class__.__name__

    @property
    def config(self) -> StrategyConfig:
        if self._config is None:
            raise RuntimeError("Strategy not initialized")
        return self._config

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ========== 公开接口 ==========

    def initialize(self, config: StrategyConfig) -> None:
        """初始化策略"""
        config.validate()
        self._config = config
        self._on_initialize()
        self._initialized = True

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """生成交易信号（主入口）"""
        if not self._initialized:
            raise RuntimeError("Strategy not initialized")

        # 检查是否需要调仓
        if not self._should_rebalance(context):
            return []

        # 生成原始信号
        signals = self._generate_signals(context)

        # 信号后处理
        signals = self._post_process_signals(signals, context)

        # 风控过滤
        signals = self._apply_risk_filters(signals, context)

        return signals

    # ========== 子类必须实现 ==========

    @abstractmethod
    def _generate_signals(self, context: StrategyContext) -> list[Signal]:
        """生成交易信号（子类实现核心逻辑）"""
        ...

    # ========== 子类可选覆盖 ==========

    def _on_initialize(self) -> None:
        """初始化后钩子"""
        pass

    def _should_rebalance(self, context: StrategyContext) -> bool:
        """判断是否需要调仓"""
        # 默认实现：根据配置的频率
        return self._check_rebalance_date(context.current_date)

    def _post_process_signals(
        self,
        signals: list[Signal],
        context: StrategyContext,
    ) -> list[Signal]:
        """信号后处理"""
        # 默认：按权重排序，截取 top N
        signals = sorted(signals, key=lambda s: s.weight, reverse=True)
        return signals[:self.config.max_positions]

    def _apply_risk_filters(
        self,
        signals: list[Signal],
        context: StrategyContext,
    ) -> list[Signal]:
        """应用风控过滤"""
        # 默认：检查单标的权重上限
        filtered = []
        for signal in signals:
            if signal.weight > self.config.max_single_weight:
                signal.weight = self.config.max_single_weight
            filtered.append(signal)
        return filtered

    # ========== 工具方法 ==========

    def _check_rebalance_date(self, current_date: date) -> bool:
        """检查是否为调仓日"""
        freq = self.config.rebalance_freq

        if freq == "daily":
            return True
        elif freq == "weekly":
            return current_date.weekday() == 0  # 周一
        elif freq == "monthly":
            return current_date.day == 1  # 每月1号
        else:
            return True
```

## ETF 轮动策略示例

```python
from dataclasses import dataclass, field


@dataclass
class ETFRotationConfig(StrategyConfig):
    """ETF 轮动策略配置"""

    # 因子权重
    factor_weights: dict[str, float] = field(default_factory=lambda: {
        "momentum_20": 0.4,
        "volatility_20": -0.3,
        "volume_ratio": 0.3,
    })

    # 选择数量
    top_n: int = 5

    # 市场状态适应
    regime_aware: bool = True
    bear_market_weight: float = 0.3     # 熊市减仓到30%


class ETFRotationStrategy(BaseStrategy):
    """ETF 轮动策略"""

    def __init__(
        self,
        factor_engine: "FactorEngine",
        rotation_engine: "RotationEngine",
        regime_engine: "RegimeEngine" = None,
    ):
        super().__init__()
        self._factor_engine = factor_engine
        self._rotation_engine = rotation_engine
        self._regime_engine = regime_engine

    def _on_initialize(self) -> None:
        """初始化引擎"""
        config: ETFRotationConfig = self.config

        # 初始化因子引擎
        self._factor_engine.initialize(FactorConfig(
            factor_names=list(config.factor_weights.keys()),
        ))

        # 初始化轮动引擎
        self._rotation_engine.initialize(RotationConfig(
            top_n=config.top_n,
            factor_weights=config.factor_weights,
        ))

    def _generate_signals(self, context: StrategyContext) -> list[Signal]:
        """生成轮动信号"""
        config: ETFRotationConfig = self.config

        # 1. 获取市场状态
        position_ratio = 1.0
        if config.regime_aware and self._regime_engine:
            regime_result = self._regime_engine.process(context.price_history)

            if regime_result.regime.is_bearish:
                position_ratio = config.bear_market_weight

        # 2. 计算因子
        factor_result = self._factor_engine.process(context.price_history)

        # 3. 轮动选择
        rotation_result = self._rotation_engine.process(factor_result)

        # 4. 生成信号
        signals = []

        # 卖出不在选择列表中的
        for code in context.positions:
            if code not in rotation_result.selected_codes:
                signals.append(Signal(
                    code=code,
                    direction="sell",
                    weight=0.0,
                    reason="Not in top selection",
                ))

        # 买入新选择的
        for rotation_signal in rotation_result.signals:
            target_weight = rotation_signal.target_weight * position_ratio

            signals.append(Signal(
                code=rotation_signal.code,
                direction="buy" if target_weight > 0 else "hold",
                weight=target_weight,
                reason=f"Rank #{rotation_signal.rank}, Score={rotation_signal.score:.2f}",
                confidence=rotation_signal.score,
            ))

        return signals


# 使用示例
strategy = ETFRotationStrategy(
    factor_engine=FactorEngine(),
    rotation_engine=RotationEngine(),
    regime_engine=RegimeEngine(),
)

strategy.initialize(ETFRotationConfig(
    name="ETF_Rotation_V1",
    universe=["510300", "510500", "510050", "159915", "159919"],
    rebalance_freq="weekly",
    top_n=3,
    factor_weights={
        "momentum_20": 0.5,
        "volatility_20": -0.3,
        "rs_20": 0.2,
    },
))
```

## 策略生命周期

```
┌───────────────┐
│   Created     │  strategy = ETFRotationStrategy()
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  Initialize   │  strategy.initialize(config)
│               │  - 验证配置
│               │  - 初始化引擎
└───────┬───────┘
        │
        ▼
┌───────────────┐
│   Running     │  signals = strategy.generate_signals(context)
│               │  - 每个调仓日调用
│   (循环)      │  - 返回交易信号
└───────┬───────┘
        │
        ▼
┌───────────────┐
│   Stopped     │  可选：strategy.stop()
└───────────────┘
```

## 信号生成流程

```
generate_signals(context)
        │
        ▼
┌───────────────────┐
│ _should_rebalance │ → 不调仓 → 返回空列表
└────────┬──────────┘
         │ 需要调仓
         ▼
┌───────────────────┐
│ _generate_signals │ ← 子类实现核心逻辑
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│ _post_process     │ 排序、截取 TopN
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│ _apply_risk_filter│ 权重限制、风控过滤
└────────┬──────────┘
         │
         ▼
     返回 signals
```

## 策略设计原则

### 1. 单一职责

```python
# Good: 策略只负责信号生成
class MyStrategy(BaseStrategy):
    def _generate_signals(self, context):
        # 只生成信号，不执行交易
        return [Signal(...)]


# Bad: 策略内执行交易
class BadStrategy(BaseStrategy):
    def _generate_signals(self, context):
        signals = [Signal(...)]
        self.broker.execute(signals)  # 错！不应该在这里
        return signals
```

### 2. 配置与逻辑分离

```python
# Good: 所有参数通过配置传入
@dataclass
class MyConfig(StrategyConfig):
    momentum_window: int = 20
    volatility_threshold: float = 0.02

class MyStrategy(BaseStrategy):
    def _generate_signals(self, context):
        window = self.config.momentum_window  # 从配置读取


# Bad: 硬编码参数
class BadStrategy(BaseStrategy):
    def _generate_signals(self, context):
        window = 20  # 硬编码！
```

### 3. PIT 安全

```python
# Good: 只使用当日之前的数据
def _generate_signals(self, context):
    # context.price_history 已经是 PIT 安全的
    factors = self._compute_factors(context.price_history)
    return self._select_by_factors(factors)


# Bad: 使用未来数据
def _generate_signals(self, context):
    # 错！使用了当日收盘价生成当日信号
    today_close = self._get_today_close()
    return self._select_by_price(today_close)
```

### 4. 可测试性

```python
# Good: 依赖注入，便于 mock
class MyStrategy(BaseStrategy):
    def __init__(self, factor_engine: FactorEngine):
        self._factor_engine = factor_engine


# 测试时可以 mock
def test_strategy():
    mock_factor_engine = MockFactorEngine()
    strategy = MyStrategy(factor_engine=mock_factor_engine)
```

## 策略测试规范

```python
class TestETFRotationStrategy:

    @pytest.fixture
    def strategy(self):
        strategy = ETFRotationStrategy(
            factor_engine=MockFactorEngine(),
            rotation_engine=MockRotationEngine(),
        )
        strategy.initialize(ETFRotationConfig(
            name="test",
            universe=["A", "B", "C"],
            top_n=2,
        ))
        return strategy

    @pytest.fixture
    def context(self):
        return StrategyContext(
            current_date=date(2024, 1, 8),  # 周一
            positions={"A": 0.5},
            cash_ratio=0.5,
            portfolio_value=1_000_000,
        )

    def test_generate_signals_on_rebalance_day(self, strategy, context):
        """测试调仓日信号生成"""
        signals = strategy.generate_signals(context)

        assert len(signals) > 0
        assert all(isinstance(s, Signal) for s in signals)

    def test_no_signals_on_non_rebalance_day(self, strategy, context):
        """测试非调仓日"""
        context.current_date = date(2024, 1, 9)  # 周二
        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_sell_signal_for_dropped_positions(self, strategy, context):
        """测试落选标的生成卖出信号"""
        context.positions = {"X": 0.5}  # X 不在选择列表中
        signals = strategy.generate_signals(context)

        sell_signals = [s for s in signals if s.direction == "sell"]
        assert any(s.code == "X" for s in sell_signals)

    def test_weight_limit_applied(self, strategy, context):
        """测试权重限制"""
        signals = strategy.generate_signals(context)

        for signal in signals:
            assert signal.weight <= strategy.config.max_single_weight

    def test_max_positions_respected(self, strategy, context):
        """测试最大持仓数"""
        signals = strategy.generate_signals(context)
        buy_signals = [s for s in signals if s.direction == "buy"]

        assert len(buy_signals) <= strategy.config.max_positions
```

## 策略版本管理

```python
@dataclass
class StrategyVersion:
    """策略版本"""

    version: str              # 语义化版本 "1.2.3"
    description: str          # 版本说明
    changes: list[str]        # 变更列表
    created_at: datetime

    # 参数变更
    config_changes: dict[str, Any] = field(default_factory=dict)


# 策略配置中包含版本
@dataclass
class MyStrategyConfig(StrategyConfig):
    name: str = "ETF_Rotation"
    version: str = "1.2.0"
```

## 禁止清单

| 禁止 | 原因 | 替代方案 |
|------|------|----------|
| 策略内执行交易 | 职责混乱 | 只返回信号 |
| 硬编码参数 | 不可调优 | 放入 Config |
| 使用未来数据 | PIT 泄露 | 严格使用历史数据 |
| 直接访问外部状态 | 难以测试 | 通过 Context 传入 |
| 忽略市场状态 | 熊市亏损大 | 加入 Regime 判断 |
| 不限制权重 | 集中度过高 | 设置权重上限 |
| 不设止损 | 风险失控 | 策略级或信号级止损 |
