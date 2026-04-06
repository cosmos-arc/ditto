"""_resolution 共享模块单元测试."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_app.builders._resolution import (
    resolve_benchmark,
    resolve_display_map,
    resolve_tickers,
)
from ditto_kernel.identity import InstrumentId


class TestResolveTickers:
    """resolve_tickers 测试."""

    def test_normal_case(self) -> None:
        metadata = MagicMock()
        metadata.get_instrument.side_effect = [
            {"ticker": "510300", "exchange": "SH"},
            {"ticker": "159919", "exchange": "SZ"},
        ]
        result_tickers, result_map = resolve_tickers([1, 2], metadata)
        assert result_tickers == ("510300.SH", "159919.SZ")
        assert result_map == {
            "510300.SH": InstrumentId(1),
            "159919.SZ": InstrumentId(2),
        }

    def test_empty_list(self) -> None:
        metadata = MagicMock()
        tickers, id_map = resolve_tickers([], metadata)
        assert tickers == ()
        assert id_map == {}

    def test_no_instrument(self) -> None:
        metadata = MagicMock()
        metadata.get_instrument.return_value = None
        tickers, id_map = resolve_tickers([42], metadata)
        assert tickers == ("42",)
        assert id_map == {"42": InstrumentId(42)}

    def test_no_exchange(self) -> None:
        metadata = MagicMock()
        metadata.get_instrument.return_value = {"ticker": "510300", "exchange": ""}
        tickers, id_map = resolve_tickers([1], metadata)
        assert tickers == ("1",)
        assert id_map == {"1": InstrumentId(1)}


class TestResolveDisplayMap:
    """resolve_display_map 测试."""

    def test_normal_case(self) -> None:
        metadata = MagicMock()
        metadata.get_instrument.side_effect = [
            {"ticker": "510300", "exchange": "SH"},
            {"ticker": "159919", "exchange": "SZ"},
        ]
        result = resolve_display_map([1, 2], metadata)
        assert result == {
            InstrumentId(1): "510300.SH",
            InstrumentId(2): "159919.SZ",
        }

    def test_empty_list(self) -> None:
        metadata = MagicMock()
        result = resolve_display_map([], metadata)
        assert result == {}

    def test_no_instrument(self) -> None:
        metadata = MagicMock()
        metadata.get_instrument.return_value = None
        result = resolve_display_map([42], metadata)
        assert result == {InstrumentId(42): "42"}


class TestResolveBenchmark:
    """resolve_benchmark 测试."""

    def test_config_benchmark_takes_priority(self) -> None:
        metadata = MagicMock()
        result = resolve_benchmark(
            spec_benchmark="000300",
            metadata_service=metadata,
            source="tushare",
            as_of="2024-01-01",
            config_benchmark=InstrumentId(999),
        )
        assert result == InstrumentId(999)
        metadata.resolve_instrument_id.assert_not_called()

    def test_spec_benchmark_resolved(self) -> None:
        metadata = MagicMock()
        metadata.resolve_instrument_id.return_value = 100
        result = resolve_benchmark(
            spec_benchmark="000300",
            metadata_service=metadata,
            source="tushare",
            as_of="2024-01-01",
        )
        assert result == InstrumentId(100)

    def test_spec_benchmark_not_found(self) -> None:
        metadata = MagicMock()
        metadata.resolve_instrument_id.return_value = None
        result = resolve_benchmark(
            spec_benchmark="000300",
            metadata_service=metadata,
            source="tushare",
            as_of="2024-01-01",
        )
        assert result is None

    def test_no_benchmark(self) -> None:
        metadata = MagicMock()
        result = resolve_benchmark(
            spec_benchmark=None,
            metadata_service=metadata,
            source="tushare",
            as_of="2024-01-01",
        )
        assert result is None
        metadata.resolve_instrument_id.assert_not_called()
