"""_resolution 共享模块单元测试."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_application.builders._resolution import (
    resolve_benchmark,
    resolve_instrument_display,
)
from ditto_kernel.identity import InstrumentId


class TestResolveInstrumentDisplay:
    """resolve_instrument_display 测试."""

    def test_normal_case(self) -> None:
        metadata = MagicMock()
        metadata.get_instrument.side_effect = [
            {"ticker": "510300", "exchange": "SH"},
            {"ticker": "159919", "exchange": "SZ"},
        ]
        result = resolve_instrument_display([1, 2], metadata)
        assert result.tickers == ("510300.SH", "159919.SZ")
        assert result.id_map == {
            "510300.SH": InstrumentId(1),
            "159919.SZ": InstrumentId(2),
        }
        assert result.display_map == {
            InstrumentId(1): "510300.SH",
            InstrumentId(2): "159919.SZ",
        }

    def test_empty_list(self) -> None:
        metadata = MagicMock()
        result = resolve_instrument_display([], metadata)
        assert result.tickers == ()
        assert result.id_map == {}
        assert result.display_map == {}

    def test_no_instrument(self) -> None:
        metadata = MagicMock()
        metadata.get_instrument.return_value = None
        result = resolve_instrument_display([42], metadata)
        assert result.tickers == ("42",)
        assert result.id_map == {"42": InstrumentId(42)}
        assert result.display_map == {InstrumentId(42): "42"}

    def test_no_exchange(self) -> None:
        metadata = MagicMock()
        metadata.get_instrument.return_value = {"ticker": "510300", "exchange": ""}
        result = resolve_instrument_display([1], metadata)
        assert result.tickers == ("1",)
        assert result.id_map == {"1": InstrumentId(1)}
        assert result.display_map == {InstrumentId(1): "1"}


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
