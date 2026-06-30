"""BacktestSynchronizer 单元测试."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from ditto_backtest.data_feed import Slice
from ditto_backtest.synchronizer import BacktestSynchronizer
from ditto_kernel.clock import SimulatedClock
from ditto_kernel.identity import InstrumentId
from ditto_kernel.synchronizer import Synchronizer, TimeSlice
from ditto_kernel.trading import MarketSnapshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

IID_1 = InstrumentId(1)
IID_2 = InstrumentId(2)


def _make_snapshot(
    iid: InstrumentId = IID_1,
    close: float = 10.0,
    trade_date: str = "2026-03-01",
) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date=trade_date,
        instrument_id=iid,
        open=close,
        high=close + 0.5,
        low=close - 0.5,
        close=close,
        prev_close=close,
        volume=1_000_000.0,
        amount=10_000_000.0,
    )


def _step_time(day: str) -> datetime:
    """构造某日 15:00 UTC 的 step_time."""
    d = datetime.strptime(day, "%Y-%m-%d")
    return d.replace(hour=15, minute=0, second=0, tzinfo=UTC)


def _make_slice(
    day: str,
    bars: dict[InstrumentId, MarketSnapshot] | None = None,
    benchmark_close: float | None = None,
    source_snapshot_ids: dict[InstrumentId, str] | None = None,
) -> Slice:
    bars = bars or {IID_1: _make_snapshot(IID_1, trade_date=day)}
    return Slice(
        trade_date=day,
        step_time=_step_time(day),
        bars=bars,
        benchmark_close=benchmark_close,
        source_snapshot_ids=source_snapshot_ids or {},
    )


def _make_feed(
    trading_days: list[str],
    slices: dict[str, Slice] | None = None,
) -> MagicMock:
    """构造满足 DataFeed Protocol 的 mock."""
    slices = slices or {d: _make_slice(d) for d in trading_days}
    feed = MagicMock(spec=["trading_days", "get_slice", "get_history"])
    feed.trading_days.return_value = trading_days
    feed.get_slice.side_effect = lambda d: slices[d]
    return feed


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStreamProducesTimeSlices:
    """stream() 产出 TimeSlice 序列."""

    def test_count_matches_filtered_days(self):
        """产出数量等于 start_date 过滤后的交易日数."""
        days = ["2026-03-01", "2026-03-02", "2026-03-03", "2026-03-04"]
        feed = _make_feed(days)
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-02",
        )
        result = list(sync.stream())

        assert len(result) == 3  # 03-02, 03-03, 03-04

    def test_all_items_are_time_slice(self):
        """所有产出都是 TimeSlice 实例."""
        days = ["2026-03-01", "2026-03-02"]
        feed = _make_feed(days)
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-01",
        )
        for item in sync.stream():
            assert isinstance(item, TimeSlice)

    def test_time_context_fields(self):
        """TimeSlice.time_context 的各字段正确映射."""
        day = "2026-03-05"
        bars = {IID_1: _make_snapshot(IID_1, trade_date=day)}
        feed = _make_feed([day], {day: _make_slice(day, bars)})
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-01",
        )
        ts = next(sync.stream())

        assert ts.time_context.trade_date == "2026-03-05"
        assert ts.time_context.decision_time == _step_time("2026-03-05")
        assert IID_1 in ts.bars

    def test_bars_preserved(self):
        """bars 字典完整传递到 TimeSlice."""
        bars = {
            IID_1: _make_snapshot(IID_1, close=10.0, trade_date="2026-03-01"),
            IID_2: _make_snapshot(IID_2, close=20.0, trade_date="2026-03-01"),
        }
        slices = {"2026-03-01": _make_slice("2026-03-01", bars)}
        feed = _make_feed(["2026-03-01"], slices)
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-01",
        )
        ts = next(sync.stream())

        assert len(ts.bars) == 2
        assert ts.bars[IID_1].close == 10.0
        assert ts.bars[IID_2].close == 20.0

    def test_benchmark_close_preserved(self):
        """benchmark_close 与 bars 使用同一个 Slice PIT 边界."""
        slices = {
            "2026-03-01": _make_slice(
                "2026-03-01",
                benchmark_close=3025.0,
            ),
        }
        feed = _make_feed(["2026-03-01"], slices)
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-01",
        )
        ts = next(sync.stream())

        assert ts.benchmark_close == 3025.0

    def test_source_snapshot_ids_preserved(self):
        """source_snapshot_ids 与 bars 使用同一个 Slice PIT 边界."""
        source_snapshot_ids = {
            IID_1: "snapshot:tushare:stock_daily:2026-03-01:abc",
        }
        slices = {
            "2026-03-01": _make_slice(
                "2026-03-01",
                source_snapshot_ids=source_snapshot_ids,
            ),
        }
        feed = _make_feed(["2026-03-01"], slices)
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-01",
        )
        ts = next(sync.stream())

        assert ts.source_snapshot_ids == source_snapshot_ids


class TestKnowledgeDate:
    """knowledge_date 计算: decision_time.date() - knowledge_lag_days."""

    def test_default_lag_one_day(self):
        """默认 knowledge_lag_days=1 → knowledge_date = 前一自然日."""
        day = "2026-03-05"
        feed = _make_feed([day])
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-01",
        )
        ts = next(sync.stream())

        expected_knowledge = date(2026, 3, 4)
        assert ts.time_context.knowledge_date == expected_knowledge

    def test_custom_lag(self):
        """自定义 knowledge_lag_days=2 → knowledge_date = 前 2 自然日."""
        day = "2026-03-05"
        feed = _make_feed([day])
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-01",
            knowledge_lag_days=2,
        )
        ts = next(sync.stream())

        expected_knowledge = date(2026, 3, 3)
        assert ts.time_context.knowledge_date == expected_knowledge

    def test_lag_zero(self):
        """knowledge_lag_days=0 → knowledge_date = decision_time.date() 本身."""
        day = "2026-03-05"
        feed = _make_feed([day])
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-01",
            knowledge_lag_days=0,
        )
        ts = next(sync.stream())

        assert ts.time_context.knowledge_date == date(2026, 3, 5)


class TestStartDateFiltering:
    """start_date 过滤: 早于 start_date 的交易日被跳过."""

    def test_filters_days_before_start(self):
        """start_date='2026-03-03' 时, 03-01 和 03-02 被过滤."""
        days = ["2026-03-01", "2026-03-02", "2026-03-03", "2026-03-04"]
        feed = _make_feed(days)
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-03",
        )
        result = list(sync.stream())

        assert len(result) == 2
        assert result[0].time_context.trade_date == "2026-03-03"
        assert result[1].time_context.trade_date == "2026-03-04"

    def test_start_date_exact_match_included(self):
        """start_date 恰好匹配某交易日时, 该日包含在产出中."""
        days = ["2026-03-01", "2026-03-02"]
        feed = _make_feed(days)
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-01",
        )
        result = list(sync.stream())

        assert len(result) == 2
        assert result[0].time_context.trade_date == "2026-03-01"

    def test_start_date_after_all_trading_days(self):
        """start_date 晚于所有交易日 → stream() 产出空序列."""
        days = ["2026-03-01", "2026-03-02"]
        feed = _make_feed(days)
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-04-01",
        )
        result = list(sync.stream())

        assert result == []


class TestEmptyTradingDays:
    """空交易日边界情况."""

    def test_empty_trading_days_yields_nothing(self):
        """trading_days() 返回空列表 → stream() 不产出任何 TimeSlice."""
        feed = _make_feed([])
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-01",
        )
        result = list(sync.stream())

        assert result == []


class TestClockReturnsSimulatedClock:
    """clock() 返回注入的 SimulatedClock."""

    def test_returns_injected_clock(self):
        """clock() 返回构造时注入的 SimulatedClock 实例."""
        feed = _make_feed([])
        initial = datetime(2026, 1, 1, tzinfo=UTC)
        clock = SimulatedClock(initial)

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-01",
        )

        returned = sync.clock()
        assert returned is clock
        assert returned.now() == initial


class TestProtocolSatisfaction:
    """BacktestSynchronizer 满足 Synchronizer Protocol（结构化子类型）."""

    def test_satisfies_synchronizer_protocol(self):
        """BacktestSynchronizer 实例可作为 Synchronizer 使用."""
        feed = _make_feed([])
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))

        sync = BacktestSynchronizer(
            data_feed=feed,
            clock=clock,
            start_date="2026-03-01",
        )

        def consume(s: Synchronizer) -> None:
            """仅用于类型检查 — 运行时验证可调用."""
            list(s.stream())
            s.clock()

        consume(sync)  # 不抛异常即通过

    def test_has_required_methods(self):
        """BacktestSynchronizer 具有 stream() 和 clock() 方法签名."""
        assert hasattr(BacktestSynchronizer, "stream")
        assert hasattr(BacktestSynchronizer, "clock")
