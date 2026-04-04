"""StrategyInputAssembler 单元测试 — 6 个场景覆盖 bundle 组装逻辑。"""

from __future__ import annotations

from datetime import datetime

import pytest
from ditto_app.process.strategy import StrategyInputAssembler
from ditto_engine.backtest.data_feed import MarketSnapshot, Slice

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snapshot(
    iid: int = 1,
    close: float = 10.0,
    prev_close: float = 9.8,
    volume: float = 1_000_000.0,
) -> MarketSnapshot:
    """创建 MarketSnapshot 测试辅助函数。"""
    return MarketSnapshot(
        trade_date="2026-03-01",
        instrument_id=iid,
        open=prev_close,
        high=max(close, prev_close) + 0.2,
        low=min(close, prev_close) - 0.2,
        close=close,
        prev_close=prev_close,
        volume=volume,
        amount=close * volume,
    )


def _make_slice(
    bars: dict[int, MarketSnapshot] | None = None,
    benchmark_close: float | None = None,
) -> Slice:
    """创建 Slice 测试辅助函数。"""
    if bars is None:
        bars = {1: _make_snapshot()}
    return Slice(
        trade_date="2026-03-01",
        step_time=datetime(2026, 3, 1, 15, 0),
        bars=bars,
        benchmark_close=benchmark_close,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStrategyInputAssemblerInit:
    """测试 StrategyInputAssembler 初始化。"""

    def test_default_values(self) -> None:
        assembler = StrategyInputAssembler()
        assert assembler.strategy_id == "default"
        assert assembler.run_id == ""
        assert assembler.parameters == {}

    def test_custom_values(self) -> None:
        assembler = StrategyInputAssembler(
            strategy_id="momentum-etf",
            run_id="run-2026-03-24",
            parameters={"lookback": 20, "threshold": 0.05},
        )
        assert assembler.strategy_id == "momentum-etf"
        assert assembler.run_id == "run-2026-03-24"
        assert assembler.parameters == {"lookback": 20, "threshold": 0.05}

    def test_parameters_is_copy(self) -> None:
        """parameters 属性返回副本，不暴露内部状态。"""
        params = {"key": "value"}
        assembler = StrategyInputAssembler(parameters=params)
        assert assembler.parameters is not assembler._parameters
        assert assembler.parameters == params


class TestBasicAssembly:
    """测试基本 bundle 组装。"""

    def test_single_instrument(self) -> None:
        """单标的 bundle 组装。"""
        assembler = StrategyInputAssembler(
            strategy_id="test",
            run_id="run-001",
        )
        bars = {1: _make_snapshot()}
        slice_ = _make_slice(bars)
        bundle = assembler.assemble("2026-03-01", slice_)

        assert bundle.trade_date == "2026-03-01"
        assert bundle.strategy_id == "test"
        assert bundle.run_id == "run-001"
        assert bundle.instruments.height == 1
        assert bundle.market_data.height == 1
        assert bundle.signal_values is not None
        assert bundle.signal_values.height == 1

    def test_multiple_instruments(self) -> None:
        """多标的 bundle 组装。"""
        assembler = StrategyInputAssembler()
        bars = {
            1: _make_snapshot(1, close=10.0, prev_close=9.8),
            2: _make_snapshot(2, close=20.0, prev_close=19.5),
            3: _make_snapshot(3, close=15.0, prev_close=15.0),
        }
        slice_ = _make_slice(bars)
        bundle = assembler.assemble("2026-03-01", slice_)

        assert bundle.instruments.height == 3
        assert bundle.market_data.height == 3
        assert bundle.signal_values is not None
        assert bundle.signal_values.height == 3

        # 验证 instrument_id 列包含所有标的
        ids = bundle.instruments["instrument_id"].to_list()
        assert set(ids) == {1, 2, 3}


class TestMarketData:
    """测试 market_data DataFrame 内容。"""

    def test_market_data_columns(self) -> None:
        """market_data 包含 OHLCV 列。"""
        assembler = StrategyInputAssembler()
        bars = {1: _make_snapshot()}
        slice_ = _make_slice(bars)
        bundle = assembler.assemble("2026-03-01", slice_)

        cols = bundle.market_data.columns
        assert "instrument_id" in cols
        assert "open" in cols
        assert "high" in cols
        assert "low" in cols
        assert "close" in cols
        assert "volume" in cols

    def test_market_data_values(self) -> None:
        """market_data 中的 OHLCV 值正确。"""
        assembler = StrategyInputAssembler()
        bar = _make_snapshot(1, close=10.5, prev_close=10.0, volume=500_000.0)
        slice_ = _make_slice({1: bar})
        bundle = assembler.assemble("2026-03-01", slice_)

        row = bundle.market_data.row(0, named=True)
        assert row["instrument_id"] == 1
        assert row["close"] == 10.5
        assert row["open"] == 10.0
        assert row["volume"] == 500_000.0


class TestSignalComputation:
    """测试动量信号计算 (close / prev_close - 1)。"""

    def test_positive_momentum(self) -> None:
        """价格上涨，信号值为正。"""
        assembler = StrategyInputAssembler()
        bar = _make_snapshot(1, close=11.0, prev_close=10.0)
        slice_ = _make_slice({1: bar})
        bundle = assembler.assemble("2026-03-01", slice_)

        assert bundle.signal_values is not None
        row = bundle.signal_values.row(0, named=True)
        assert row["signal_value"] == pytest.approx(0.1)

    def test_negative_momentum(self) -> None:
        """价格下跌，信号值为负。"""
        assembler = StrategyInputAssembler()
        bar = _make_snapshot(1, close=9.0, prev_close=10.0)
        slice_ = _make_slice({1: bar})
        bundle = assembler.assemble("2026-03-01", slice_)

        assert bundle.signal_values is not None
        row = bundle.signal_values.row(0, named=True)
        assert row["signal_value"] == pytest.approx(-0.1)

    def test_zero_momentum(self) -> None:
        """价格不变，信号值为 0。"""
        assembler = StrategyInputAssembler()
        bar = _make_snapshot(1, close=10.0, prev_close=10.0)
        slice_ = _make_slice({1: bar})
        bundle = assembler.assemble("2026-03-01", slice_)

        assert bundle.signal_values is not None
        row = bundle.signal_values.row(0, named=True)
        assert row["signal_value"] == pytest.approx(0.0)

    def test_zero_prev_close_signal_is_zero(self) -> None:
        """prev_close 为 0 时，信号值为 0.0（避免除零错误）。"""
        assembler = StrategyInputAssembler()
        bar = _make_snapshot(1, close=10.0, prev_close=0.0)
        slice_ = _make_slice({1: bar})
        bundle = assembler.assemble("2026-03-01", slice_)

        assert bundle.signal_values is not None
        row = bundle.signal_values.row(0, named=True)
        assert row["signal_value"] == 0.0

    def test_signal_values_columns(self) -> None:
        """signal_values 包含 instrument_id 和 signal_value 列。"""
        assembler = StrategyInputAssembler()
        slice_ = _make_slice()
        bundle = assembler.assemble("2026-03-01", slice_)

        assert bundle.signal_values is not None
        cols = bundle.signal_values.columns
        assert "instrument_id" in cols
        assert "signal_value" in cols


class TestBenchmarkClose:
    """测试 benchmark_close 传递。"""

    def test_with_benchmark(self) -> None:
        """benchmark_close 正确传递到 bundle。"""
        assembler = StrategyInputAssembler()
        slice_ = _make_slice(benchmark_close=3000.5)
        bundle = assembler.assemble("2026-03-01", slice_)

        assert bundle.benchmark_close == 3000.5

    def test_without_benchmark(self) -> None:
        """无 benchmark 时，bundle 中为 None。"""
        assembler = StrategyInputAssembler()
        slice_ = _make_slice(benchmark_close=None)
        bundle = assembler.assemble("2026-03-01", slice_)

        assert bundle.benchmark_close is None


class TestCustomParameters:
    """测试自定义参数传递。"""

    def test_parameters_passed_to_bundle(self) -> None:
        """parameters 正确传递到 bundle。"""
        params = {"lookback": 20, "threshold": 0.05, "universe": [1]}
        assembler = StrategyInputAssembler(parameters=params)
        slice_ = _make_slice()
        bundle = assembler.assemble("2026-03-01", slice_)

        assert bundle.parameters == params

    def test_default_empty_parameters(self) -> None:
        """默认参数为空字典。"""
        assembler = StrategyInputAssembler()
        slice_ = _make_slice()
        bundle = assembler.assemble("2026-03-01", slice_)

        assert bundle.parameters == {}


class TestEmptyBars:
    """测试空 bars 场景。"""

    def test_empty_bars(self) -> None:
        """空 bars 时，bundle 中 DataFrames 为空但仍有效。"""
        assembler = StrategyInputAssembler()
        slice_ = _make_slice(bars={})
        bundle = assembler.assemble("2026-03-01", slice_)

        assert bundle.instruments.height == 0
        assert bundle.market_data.height == 0
        assert bundle.signal_values is not None
        assert bundle.signal_values.height == 0
        assert bundle.trade_date == "2026-03-01"
        assert bundle.strategy_id == "default"


class TestValidUntil:
    """测试信号过期检查 (valid_until < trade_date 时信号为空)。"""

    def test_expired_signals_produce_none(self) -> None:
        """valid_until < trade_date 时，signal_values 应为 None。"""
        assembler = StrategyInputAssembler()
        slice_ = _make_slice()
        bundle = assembler.assemble(
            "2026-03-06",
            slice_,
            valid_until="2026-03-05",
        )

        # 信号已过期，signal_values 应为 None
        assert bundle.signal_values is None
        # market_data 不受影响
        assert bundle.market_data.height == 1
        assert bundle.instruments.height == 1

    def test_valid_signals_produced_normally(self) -> None:
        """valid_until >= trade_date 时，signal_values 正常生成。"""
        assembler = StrategyInputAssembler()
        slice_ = _make_slice()
        bundle = assembler.assemble(
            "2026-03-05",
            slice_,
            valid_until="2026-03-05",
        )

        # 信号未过期，正常生成
        assert bundle.signal_values is not None
        assert bundle.signal_values.height == 1

    def test_no_valid_until_produces_signals(self) -> None:
        """不传 valid_until 时，信号正常生成（向后兼容）。"""
        assembler = StrategyInputAssembler()
        slice_ = _make_slice()
        bundle = assembler.assemble("2026-03-01", slice_)

        assert bundle.signal_values is not None
        assert bundle.signal_values.height == 1

    def test_valid_until_after_trade_date(self) -> None:
        """valid_until > trade_date 时，信号正常生成。"""
        assembler = StrategyInputAssembler()
        slice_ = _make_slice()
        bundle = assembler.assemble(
            "2026-03-01",
            slice_,
            valid_until="2026-03-10",
        )

        assert bundle.signal_values is not None
        assert bundle.signal_values.height == 1


class TestReusability:
    """测试跨多次调用复用。"""

    def test_reuse_across_dates(self) -> None:
        """同一个 assembler 可用于不同日期的 slice。"""
        assembler = StrategyInputAssembler(
            strategy_id="momentum",
            run_id="run-001",
            parameters={"lookback": 20},
        )
        bars_day1 = {1: _make_snapshot(1, close=10.0, prev_close=9.5)}
        bars_day2 = {1: _make_snapshot(1, close=10.5, prev_close=10.0)}

        slice1 = Slice(
            trade_date="2026-03-01",
            step_time=datetime(2026, 3, 1, 15, 0),
            bars=bars_day1,
        )
        slice2 = Slice(
            trade_date="2026-03-02",
            step_time=datetime(2026, 3, 2, 15, 0),
            bars=bars_day2,
        )

        bundle1 = assembler.assemble("2026-03-01", slice1)
        bundle2 = assembler.assemble("2026-03-02", slice2)

        assert bundle1.trade_date == "2026-03-01"
        assert bundle2.trade_date == "2026-03-02"
        assert bundle1.strategy_id == bundle2.strategy_id == "momentum"
        assert bundle1.run_id == bundle2.run_id == "run-001"

        # 信号值应不同（不同日期的动量不同）
        sig1 = bundle1.signal_values.row(0, named=True)["signal_value"]
        sig2 = bundle2.signal_values.row(0, named=True)["signal_value"]
        assert sig1 != sig2
