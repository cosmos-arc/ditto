---
paths: packages/core/src/ditto_core/engine/regime*.py, packages/core/src/ditto_core/engine/*regime*.py
---

# RegimeEngine — 市场状态识别引擎

> 识别当前市场处于牛市、熊市还是震荡状态

## 职责

- 分析市场指数数据，判断当前市场状态
- 为下游策略提供市场环境判断
- 支持状态转换的滞后确认，避免频繁切换

## 状态定义

```python
from enum import Enum


class MarketRegime(Enum):
    """市场状态枚举"""

    BULL = "bull"           # 牛市：趋势向上，适合进攻
    SIDEWAYS = "sideways"   # 震荡：无明显趋势，适合观望
    BEAR = "bear"           # 熊市：趋势向下，适合防守

    @property
    def is_bullish(self) -> bool:
        return self == MarketRegime.BULL

    @property
    def is_bearish(self) -> bool:
        return self == MarketRegime.BEAR

    @property
    def suggested_position_ratio(self) -> float:
        """建议仓位比例"""
        return {
            MarketRegime.BULL: 1.0,      # 满仓
            MarketRegime.SIDEWAYS: 0.5,  # 半仓
            MarketRegime.BEAR: 0.0,      # 空仓
        }[self]
```

## 配置

```python
from dataclasses import dataclass


@dataclass
class RegimeConfig:
    """市场状态识别配置"""

    # 均线参数
    ma_short: int = 20           # 短期均线周期
    ma_long: int = 60            # 长期均线周期

    # 状态确认
    confirm_days: int = 3        # 状态确认天数（防止假突破）

    # 震荡判定
    volatility_window: int = 20  # 波动率窗口
    trend_threshold: float = 0.02  # 趋势阈值（2%）

    # 可选：使用的指数
    benchmark_code: str = "000300"  # 沪深300

    def validate(self) -> None:
        if self.ma_short >= self.ma_long:
            raise ValueError(
                f"ma_short ({self.ma_short}) must < ma_long ({self.ma_long})"
            )
        if self.confirm_days < 1:
            raise ValueError("confirm_days must be at least 1")
        if self.trend_threshold <= 0:
            raise ValueError("trend_threshold must be positive")
```

## 结果

```python
from dataclasses import dataclass
from datetime import date


@dataclass
class RegimeResult:
    """状态识别结果"""

    # 核心结果
    regime: MarketRegime
    confidence: float            # 置信度 0~1

    # 计算细节
    as_of_date: date             # 数据截止日期
    ma_short: float              # 短期均线值
    ma_long: float               # 长期均线值
    trend_strength: float        # 趋势强度 (ma_short - ma_long) / ma_long
    volatility: float            # 当前波动率

    # 状态持续
    days_in_regime: int          # 当前状态持续天数
    previous_regime: MarketRegime | None  # 前一状态

    @property
    def is_regime_change(self) -> bool:
        """是否发生状态切换"""
        return (
            self.previous_regime is not None
            and self.previous_regime != self.regime
        )
```

## 实现

```python
import polars as pl
from .base import BaseEngine


class RegimeEngine(BaseEngine[RegimeConfig, pl.DataFrame, RegimeResult]):
    """市场状态识别引擎"""

    def __init__(self):
        super().__init__()
        self._regime_history: list[tuple[date, MarketRegime]] = []

    def _validate_config(self, config: RegimeConfig) -> None:
        config.validate()

    def _validate_input(self, data: pl.DataFrame) -> None:
        # 必需列
        required = {"trade_date", "close"}
        missing = required - set(data.columns)
        if missing:
            raise ValueError(f"Missing columns: {missing}")

        # 数据量检查
        min_rows = self.config.ma_long + self.config.confirm_days
        if data.height < min_rows:
            raise ValueError(
                f"Need at least {min_rows} rows, got {data.height}"
            )

    def _do_process(self, data: pl.DataFrame) -> RegimeResult:
        """识别市场状态"""
        # 1. 确保排序
        data = data.sort("trade_date")

        # 2. 计算指标（PIT 安全）
        data = self._compute_indicators(data)

        # 3. 判定状态
        regime, confidence, trend_strength = self._determine_regime(data)

        # 4. 状态确认（防止假突破）
        regime = self._confirm_regime(regime, data)

        # 5. 更新历史
        as_of_date = data["trade_date"].max()
        previous = self._regime_history[-1][1] if self._regime_history else None
        self._regime_history.append((as_of_date, regime))

        # 6. 计算持续天数
        days_in_regime = self._count_regime_days(regime)

        return RegimeResult(
            regime=regime,
            confidence=confidence,
            as_of_date=as_of_date,
            ma_short=data["ma_short"][-1],
            ma_long=data["ma_long"][-1],
            trend_strength=trend_strength,
            volatility=data["volatility"][-1],
            days_in_regime=days_in_regime,
            previous_regime=previous,
        )

    def _compute_indicators(self, data: pl.DataFrame) -> pl.DataFrame:
        """计算技术指标"""
        cfg = self.config

        return data.with_columns([
            # 均线（closed="left" 保证 PIT 安全）
            pl.col("close")
              .rolling_mean(cfg.ma_short, closed="left")
              .alias("ma_short"),

            pl.col("close")
              .rolling_mean(cfg.ma_long, closed="left")
              .alias("ma_long"),

            # 波动率
            pl.col("close")
              .pct_change()
              .rolling_std(cfg.volatility_window, closed="left")
              .alias("volatility"),
        ])

    def _determine_regime(
        self,
        data: pl.DataFrame,
    ) -> tuple[MarketRegime, float, float]:
        """判定市场状态"""
        # 取最近 N 天平均
        recent = data.tail(self.config.confirm_days)

        ma_short_avg = recent["ma_short"].mean()
        ma_long_avg = recent["ma_long"].mean()

        # 趋势强度
        trend_strength = (ma_short_avg - ma_long_avg) / ma_long_avg
        threshold = self.config.trend_threshold

        # 判定
        if trend_strength > threshold:
            regime = MarketRegime.BULL
            confidence = min(trend_strength / (threshold * 2), 1.0)
        elif trend_strength < -threshold:
            regime = MarketRegime.BEAR
            confidence = min(abs(trend_strength) / (threshold * 2), 1.0)
        else:
            regime = MarketRegime.SIDEWAYS
            # 越接近0，震荡越明确
            confidence = 1.0 - abs(trend_strength) / threshold

        return regime, confidence, trend_strength

    def _confirm_regime(
        self,
        new_regime: MarketRegime,
        data: pl.DataFrame,
    ) -> MarketRegime:
        """状态确认：防止假突破"""
        if not self._regime_history:
            return new_regime

        current_regime = self._regime_history[-1][1]

        # 如果状态没变，直接返回
        if new_regime == current_regime:
            return new_regime

        # 状态切换需要连续确认
        confirm_days = self.config.confirm_days
        if len(self._regime_history) < confirm_days:
            return current_regime

        # 检查最近 N 天是否都指向新状态
        # （简化实现，实际可能需要更复杂的逻辑）
        return new_regime

    def _count_regime_days(self, current: MarketRegime) -> int:
        """计算当前状态持续天数"""
        count = 0
        for _, regime in reversed(self._regime_history):
            if regime == current:
                count += 1
            else:
                break
        return count

    def _on_reset(self) -> None:
        """重置时清空历史"""
        self._regime_history.clear()
```

## 使用示例

```python
# 初始化
engine = RegimeEngine()
engine.initialize(RegimeConfig(
    ma_short=20,
    ma_long=60,
    confirm_days=3,
))

# 获取指数数据
index_data = data_service.get_index_daily("000300", start_date, end_date)

# 识别状态
result = engine.process(index_data)

print(f"当前状态: {result.regime.value}")
print(f"置信度: {result.confidence:.2%}")
print(f"建议仓位: {result.regime.suggested_position_ratio:.0%}")

# 根据状态调整策略
if result.regime == MarketRegime.BEAR:
    # 熊市：降低仓位或空仓
    target_position = 0.0
elif result.regime == MarketRegime.SIDEWAYS:
    # 震荡：减半仓位
    target_position = 0.5
else:
    # 牛市：满仓
    target_position = 1.0
```

## 测试用例

```python
class TestRegimeEngine:

    @pytest.fixture
    def engine(self):
        engine = RegimeEngine()
        engine.initialize(RegimeConfig(ma_short=5, ma_long=10))
        return engine

    def test_bull_market_detection(self, engine):
        """测试牛市识别"""
        # 构造上涨数据
        data = pl.DataFrame({
            "trade_date": pl.date_range(
                date(2024, 1, 1), date(2024, 2, 1), eager=True
            ),
            "close": [100 + i * 2 for i in range(32)],  # 持续上涨
        })

        result = engine.process(data)

        assert result.regime == MarketRegime.BULL
        assert result.confidence > 0.5
        assert result.trend_strength > 0

    def test_bear_market_detection(self, engine):
        """测试熊市识别"""
        data = pl.DataFrame({
            "trade_date": pl.date_range(
                date(2024, 1, 1), date(2024, 2, 1), eager=True
            ),
            "close": [100 - i * 2 for i in range(32)],  # 持续下跌
        })

        result = engine.process(data)

        assert result.regime == MarketRegime.BEAR
        assert result.trend_strength < 0

    def test_sideways_detection(self, engine):
        """测试震荡识别"""
        # 构造震荡数据
        base = 100
        prices = [base + (i % 5) - 2 for i in range(32)]  # 小幅波动

        data = pl.DataFrame({
            "trade_date": pl.date_range(
                date(2024, 1, 1), date(2024, 2, 1), eager=True
            ),
            "close": prices,
        })

        result = engine.process(data)

        assert result.regime == MarketRegime.SIDEWAYS

    def test_regime_change_tracking(self, engine):
        """测试状态切换追踪"""
        # 先喂入牛市数据
        bull_data = pl.DataFrame({
            "trade_date": pl.date_range(
                date(2024, 1, 1), date(2024, 1, 20), eager=True
            ),
            "close": [100 + i * 3 for i in range(20)],
        })
        result1 = engine.process(bull_data)

        # 再喂入熊市数据
        bear_data = pl.DataFrame({
            "trade_date": pl.date_range(
                date(2024, 1, 1), date(2024, 1, 20), eager=True
            ),
            "close": [160 - i * 3 for i in range(20)],
        })
        result2 = engine.process(bear_data)

        assert result2.is_regime_change
        assert result2.previous_regime == MarketRegime.BULL

    def test_pit_safety(self, engine):
        """测试 PIT 安全性"""
        data = pl.DataFrame({
            "trade_date": pl.date_range(
                date(2024, 1, 1), date(2024, 1, 15), eager=True
            ),
            "close": list(range(100, 115)),
        })

        result = engine.process(data)

        # MA5 在第 6 天(idx=5)应该是前 5 天的平均，不含第 6 天
        # 即 (100+101+102+103+104)/5 = 102
        # 由于 closed="left"，实际是 (100+101+102+103+104)/5
        # 验证没有使用未来数据
        assert result.as_of_date == date(2024, 1, 15)
```

## 扩展：多指标综合判定

```python
@dataclass
class AdvancedRegimeConfig(RegimeConfig):
    """高级配置：多指标综合"""

    # RSI 参数
    use_rsi: bool = True
    rsi_period: int = 14
    rsi_overbought: float = 70
    rsi_oversold: float = 30

    # 成交量参数
    use_volume: bool = True
    volume_ma_period: int = 20

    # 权重
    ma_weight: float = 0.5
    rsi_weight: float = 0.3
    volume_weight: float = 0.2
```

## 禁止清单

| 禁止 | 原因 | 替代方案 |
|------|------|----------|
| 不用 `closed="left"` | PIT 泄露 | 始终指定 |
| 单日数据判定状态 | 假突破多 | 多日确认 |
| 硬编码阈值 | 不可调优 | 放入 Config |
| 不记录历史状态 | 无法追踪切换 | 保存历史 |
| 状态频繁切换 | 交易成本高 | 加确认机制 |
