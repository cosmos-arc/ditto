---
paths: packages/core/src/ditto_core/engine/backtest*.py, packages/core/src/ditto_core/engine/*backtest*.py
---

# BacktestEngine — 回测引擎

> 策略历史验证，支持向量化和事件驱动两种模式

## 职责

- 基于历史数据验证策略表现
- 计算收益、风险、交易等各类指标
- 支持 T+1、涨跌停等 A 股特殊规则
- 提供向量化（快速）和事件驱动（精确）两种模式

## 双引擎架构

```
┌─────────────────────────────────────────────────────────┐
│                    BacktestEngine                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌───────────────────┐    ┌───────────────────┐        │
│  │   VectorBacktest  │    │   EventBacktest   │        │
│  │   (研究模式)       │    │   (生产模式)       │        │
│  ├───────────────────┤    ├───────────────────┤        │
│  │ • 快速迭代        │    │ • 精确模拟         │        │
│  │ • 粗略估计        │    │ • 完整订单簿       │        │
│  │ • 适合策略研发    │    │ • 适合最终验证     │        │
│  └───────────────────┘    └───────────────────┘        │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │         结果必须对齐（误差 < 0.5%）              │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## 配置

```python
from dataclasses import dataclass, field
from datetime import date
from typing import Literal


@dataclass
class BacktestConfig:
    """回测配置"""

    # 时间范围
    start_date: date
    end_date: date

    # 资金
    initial_capital: float = 1_000_000

    # 成本
    commission_rate: float = 0.0003      # 万三佣金
    stamp_duty: float = 0.001            # 千一印花税（卖出）
    slippage: float = 0.001              # 千一滑点

    # 基准
    benchmark_code: str = "510300"       # 沪深300ETF

    # A股约束
    t_plus_1: bool = True                # T+1 交易
    price_limit: float = 0.10            # 涨跌停限制（10%）
    handle_suspended: Literal["skip", "hold", "error"] = "hold"

    # 执行假设
    fill_price: Literal["open", "close", "vwap"] = "open"  # 成交价
    partial_fill: bool = False           # 是否允许部分成交

    # 模式
    mode: Literal["vector", "event"] = "vector"

    def validate(self) -> None:
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if self.commission_rate < 0:
            raise ValueError("commission_rate cannot be negative")
```

## 结果

```python
from dataclasses import dataclass, field
from datetime import date, datetime
import polars as pl


@dataclass
class BacktestMetrics:
    """回测指标"""

    # 收益指标
    total_return: float              # 总收益率
    annual_return: float             # 年化收益率
    benchmark_return: float          # 基准收益率
    alpha: float                     # 超额收益

    # 风险指标
    volatility: float                # 年化波动率
    max_drawdown: float              # 最大回撤
    max_drawdown_duration: int       # 最大回撤持续天数

    # 风险调整收益
    sharpe_ratio: float              # 夏普比率
    sortino_ratio: float             # 索提诺比率
    calmar_ratio: float              # 卡玛比率
    information_ratio: float         # 信息比率

    # 交易统计
    total_trades: int                # 总交易次数
    win_rate: float                  # 胜率
    profit_factor: float             # 盈亏比
    avg_win: float                   # 平均盈利
    avg_loss: float                  # 平均亏损

    # 换手统计
    avg_turnover: float              # 平均换手率
    total_commission: float          # 总佣金


@dataclass
class DailyResult:
    """每日结果"""

    date: date
    portfolio_value: float           # 组合净值
    cash: float                      # 现金
    positions_value: float           # 持仓市值

    daily_return: float              # 日收益率
    cumulative_return: float         # 累计收益率
    drawdown: float                  # 当前回撤

    benchmark_return: float          # 基准日收益
    excess_return: float             # 超额收益

    positions: dict[str, float]      # 持仓明细 code -> weight


@dataclass
class TradeRecord:
    """交易记录"""

    date: date
    code: str
    direction: Literal["buy", "sell"]
    quantity: int
    price: float
    amount: float
    commission: float

    # 成交状态
    status: Literal["filled", "partial", "rejected"]
    reject_reason: str | None = None


@dataclass
class BacktestResult:
    """回测结果"""

    # 汇总指标
    metrics: BacktestMetrics

    # 时间序列
    equity_curve: pl.DataFrame       # 净值曲线
    daily_results: list[DailyResult]

    # 交易记录
    trade_log: list[TradeRecord]

    # 元数据
    config: BacktestConfig
    created_at: datetime = field(default_factory=datetime.now)
```

## 实现框架

```python
import polars as pl
from abc import abstractmethod
from .base import BaseEngine


class BacktestEngine(BaseEngine[BacktestConfig, "BacktestInput", BacktestResult]):
    """回测引擎"""

    def _validate_config(self, config: BacktestConfig) -> None:
        config.validate()

    def _do_process(self, input: "BacktestInput") -> BacktestResult:
        """执行回测"""
        if self.config.mode == "vector":
            return self._run_vector(input)
        else:
            return self._run_event(input)

    def _run_vector(self, input: "BacktestInput") -> BacktestResult:
        """向量化回测"""
        raise NotImplementedError("Vector backtest")

    def _run_event(self, input: "BacktestInput") -> BacktestResult:
        """事件驱动回测"""
        raise NotImplementedError("Event backtest")


class VectorBacktestEngine:
    """向量化回测实现"""

    def run(
        self,
        signals: pl.DataFrame,       # 信号：date, code, weight
        prices: pl.DataFrame,        # 价格：date, code, open, close
        config: BacktestConfig,
    ) -> BacktestResult:
        """向量化回测"""

        # 1. 准备数据
        data = self._prepare_data(signals, prices)

        # 2. 计算持仓收益
        data = self._compute_returns(data, config)

        # 3. 计算组合净值
        equity = self._compute_equity(data, config)

        # 4. 计算指标
        metrics = self._compute_metrics(equity, config)

        return BacktestResult(
            metrics=metrics,
            equity_curve=equity,
            daily_results=self._to_daily_results(equity),
            trade_log=[],  # 向量化模式无详细交易记录
            config=config,
        )

    def _prepare_data(
        self,
        signals: pl.DataFrame,
        prices: pl.DataFrame,
    ) -> pl.DataFrame:
        """准备数据"""
        return (
            signals
            .join(prices, on=["trade_date", "code"], how="left")
            .sort(["trade_date", "code"])
        )

    def _compute_returns(
        self,
        data: pl.DataFrame,
        config: BacktestConfig,
    ) -> pl.DataFrame:
        """计算收益"""
        # 使用 fill_price 确定成交价
        price_col = "open" if config.fill_price == "open" else "close"

        return data.with_columns([
            # 持仓收益（开盘买入，收盘计算）
            (pl.col("close") / pl.col(price_col) - 1).alias("position_return"),

            # 扣除交易成本
            (pl.col("weight").diff().abs() *
             (config.commission_rate + config.slippage)).alias("trade_cost"),
        ])

    def _compute_equity(
        self,
        data: pl.DataFrame,
        config: BacktestConfig,
    ) -> pl.DataFrame:
        """计算净值曲线"""
        # 按日聚合
        daily = (
            data
            .group_by("trade_date")
            .agg([
                # 加权收益
                (pl.col("weight") * pl.col("position_return")).sum().alias("portfolio_return"),
                # 交易成本
                pl.col("trade_cost").sum().alias("daily_cost"),
            ])
            .sort("trade_date")
        )

        # 计算净收益
        daily = daily.with_columns([
            (pl.col("portfolio_return") - pl.col("daily_cost")).alias("net_return")
        ])

        # 计算累计净值
        daily = daily.with_columns([
            (1 + pl.col("net_return")).cum_prod().alias("nav"),
            pl.col("net_return").cum_sum().alias("cumulative_return"),
        ])

        # 计算回撤
        daily = daily.with_columns([
            (pl.col("nav") / pl.col("nav").cum_max() - 1).alias("drawdown")
        ])

        return daily


class EventBacktestEngine:
    """事件驱动回测实现"""

    def __init__(self):
        self._current_date: date | None = None
        self._cash: float = 0
        self._positions: dict[str, Position] = {}
        self._trades: list[TradeRecord] = []
        self._daily_results: list[DailyResult] = []

    def run(
        self,
        strategy: "Strategy",
        data_feed: "DataFeed",
        config: BacktestConfig,
    ) -> BacktestResult:
        """事件驱动回测"""

        # 初始化
        self._cash = config.initial_capital
        self._positions = {}
        self._trades = []

        # 获取交易日历
        trading_days = data_feed.get_trading_days(
            config.start_date, config.end_date
        )

        # 逐日模拟
        for date in trading_days:
            self._current_date = date

            # 1. 更新行情（PIT 安全）
            market_data = data_feed.get_data(date)

            # 2. 处理停牌
            self._handle_suspended(market_data, config)

            # 3. 生成信号
            signals = strategy.generate_signals(
                date=date,
                market_data=market_data,
                positions=self._positions,
            )

            # 4. T+1 检查
            if config.t_plus_1:
                signals = self._apply_t1_constraint(signals, date)

            # 5. 执行交易
            self._execute_orders(signals, market_data, config)

            # 6. 更新持仓市值
            self._update_positions(market_data)

            # 7. 记录每日结果
            self._record_daily(date, market_data)

        # 计算指标
        metrics = self._compute_final_metrics(config)

        return BacktestResult(
            metrics=metrics,
            equity_curve=self._to_equity_df(),
            daily_results=self._daily_results,
            trade_log=self._trades,
            config=config,
        )

    def _apply_t1_constraint(
        self,
        signals: list["Signal"],
        current_date: date,
    ) -> list["Signal"]:
        """应用 T+1 约束"""
        valid_signals = []

        for signal in signals:
            if signal.direction == "sell":
                # 卖出：检查是否今日买入
                position = self._positions.get(signal.code)
                if position and position.buy_date >= current_date:
                    continue  # T+1，不能卖

            valid_signals.append(signal)

        return valid_signals

    def _execute_orders(
        self,
        signals: list["Signal"],
        market_data: "MarketData",
        config: BacktestConfig,
    ) -> None:
        """执行订单"""
        for signal in signals:
            price_data = market_data.get(signal.code)

            if price_data is None:
                self._trades.append(TradeRecord(
                    date=self._current_date,
                    code=signal.code,
                    direction=signal.direction,
                    quantity=0,
                    price=0,
                    amount=0,
                    commission=0,
                    status="rejected",
                    reject_reason="No price data",
                ))
                continue

            # 检查涨跌停
            if self._is_limit(price_data, signal.direction, config):
                self._trades.append(TradeRecord(
                    date=self._current_date,
                    code=signal.code,
                    direction=signal.direction,
                    quantity=0,
                    price=0,
                    amount=0,
                    commission=0,
                    status="rejected",
                    reject_reason="Price limit",
                ))
                continue

            # 确定成交价
            fill_price = self._get_fill_price(price_data, config)
            fill_price *= (1 + config.slippage) if signal.direction == "buy" else (1 - config.slippage)

            # 执行
            self._fill_order(signal, fill_price, config)

    def _is_limit(
        self,
        price_data: "PriceData",
        direction: str,
        config: BacktestConfig,
    ) -> bool:
        """检查是否涨跌停"""
        if price_data.prev_close is None:
            return False

        change = (price_data.close - price_data.prev_close) / price_data.prev_close

        if direction == "buy" and change >= config.price_limit:
            return True  # 涨停买不进
        if direction == "sell" and change <= -config.price_limit:
            return True  # 跌停卖不出

        return False
```

## 指标计算

```python
def compute_metrics(
    equity_curve: pl.DataFrame,
    benchmark: pl.DataFrame,
    config: BacktestConfig,
) -> BacktestMetrics:
    """计算回测指标"""

    returns = equity_curve["net_return"]
    nav = equity_curve["nav"]

    # 收益指标
    total_return = nav[-1] / nav[0] - 1
    trading_days = len(returns)
    annual_return = (1 + total_return) ** (252 / trading_days) - 1

    # 基准收益
    bench_return = benchmark["close"][-1] / benchmark["close"][0] - 1
    alpha = annual_return - bench_return * (252 / trading_days)

    # 风险指标
    volatility = returns.std() * (252 ** 0.5)

    drawdown = equity_curve["drawdown"]
    max_drawdown = drawdown.min()  # 负值

    # 夏普比率
    risk_free_rate = 0.03  # 假设无风险利率 3%
    excess_return = annual_return - risk_free_rate
    sharpe_ratio = excess_return / volatility if volatility > 0 else 0

    # 索提诺比率
    downside_returns = returns.filter(returns < 0)
    downside_std = downside_returns.std() * (252 ** 0.5)
    sortino_ratio = excess_return / downside_std if downside_std > 0 else 0

    # 卡玛比率
    calmar_ratio = annual_return / abs(max_drawdown) if max_drawdown < 0 else 0

    return BacktestMetrics(
        total_return=total_return,
        annual_return=annual_return,
        benchmark_return=bench_return,
        alpha=alpha,
        volatility=volatility,
        max_drawdown=max_drawdown,
        max_drawdown_duration=0,  # 需要额外计算
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        information_ratio=0,  # 需要额外计算
        total_trades=0,
        win_rate=0,
        profit_factor=0,
        avg_win=0,
        avg_loss=0,
        avg_turnover=0,
        total_commission=0,
    )
```

## 测试用例

```python
class TestBacktestEngine:

    def test_vector_vs_event_alignment(self):
        """验证两种模式结果对齐"""
        # 相同输入
        config = BacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=1_000_000,
        )

        # 向量化模式
        config.mode = "vector"
        result_vector = backtest_engine.process(input)

        # 事件模式
        config.mode = "event"
        result_event = backtest_engine.process(input)

        # 验证结果接近
        assert abs(
            result_vector.metrics.total_return -
            result_event.metrics.total_return
        ) < 0.005  # 误差 < 0.5%

    def test_t_plus_1_constraint(self):
        """测试 T+1 约束"""
        # 准备数据：今日买入，今日尝试卖出
        # 验证卖出被拒绝
        ...

    def test_price_limit_handling(self):
        """测试涨跌停处理"""
        # 准备数据：标的涨停
        # 验证买入被拒绝
        ...

    def test_pit_safety(self):
        """测试回测 PIT 安全性"""
        # 验证每日决策只使用该日之前的数据
        ...
```

## 禁止清单

| 禁止 | 原因 | 替代方案 |
|------|------|----------|
| 使用未来数据 | PIT 泄露 | 严格按日期过滤 |
| 忽略 T+1 | A股必须 | 配置开启 |
| 忽略涨跌停 | 无法成交 | 检查并拒绝 |
| 不计交易成本 | 收益虚高 | 包含佣金滑点 |
| 两种模式不对齐 | 结果不可信 | 误差 < 0.5% |
| 硬编码成本参数 | 不可调整 | 放入 Config |
