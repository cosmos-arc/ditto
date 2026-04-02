"""MarketServiceDataFeed 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
from ditto_app.process.strategy import (
    MarketServiceDataFeed,
    MarketServiceDataFeedConfig,
)
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_kernel.identity import InstrumentId as _InstrumentId

InstrumentId = _InstrumentId


def _make_metadata_service() -> MagicMock:
    """构造 MetadataService mock。"""
    service = MagicMock(spec=MetadataService)
    service.get_universe.return_value = [2_000_001, 2_000_002]
    ticker_map = {
        2_000_001: "510300.SH",
        2_000_002: "159919.SZ",
        3_000_001: "000300.SH",
    }
    service.get_source_ticker.side_effect = lambda instrument_id, *_args, **_kwargs: (
        ticker_map[instrument_id]
    )
    service.resolve_instrument_id.return_value = 3_000_001  # 仅用于 universe 查询
    service.get_instrument.return_value = {"asset_class": "index"}
    service.list_calendar_range.return_value = pl.DataFrame(
        {
            "trade_date": ["2026-01-10", "2026-01-13"],
            "prev_trade_date": ["2026-01-09", "2026-01-10"],
        }
    )
    return service


def _make_market_service() -> MagicMock:
    """构造 MarketService mock。"""
    service = MagicMock(spec=MarketService)
    service.list_bars.side_effect = [
        pl.DataFrame(
            {
                "instrument_id": [
                    2_000_001,
                    2_000_001,
                    2_000_001,
                    2_000_002,
                    2_000_002,
                    2_000_002,
                ],
                "trade_date": [
                    "2026-01-09",
                    "2026-01-10",
                    "2026-01-13",
                    "2026-01-09",
                    "2026-01-10",
                    "2026-01-13",
                ],
                "open": [10.0, 10.1, 10.6, 20.0, 19.8, 19.6],
                "high": [10.2, 10.6, 10.9, 20.1, 20.0, 19.9],
                "low": [9.9, 10.0, 10.4, 19.7, 19.4, 19.5],
                "close": [10.0, 10.5, 10.8, 20.0, 19.5, 19.7],
                "volume": [1000, 1100, 1200, 2000, 2100, 2200],
                "amount": [10000, 11550, 12960, 40000, 40950, 43340],
            }
        ),
        pl.DataFrame(
            {
                "instrument_id": [3_000_001, 3_000_001, 3_000_001],
                "trade_date": ["2026-01-09", "2026-01-10", "2026-01-13"],
                "open": [3000.0, 3010.0, 3020.0],
                "high": [3010.0, 3020.0, 3030.0],
                "low": [2990.0, 3000.0, 3010.0],
                "close": [3005.0, 3015.0, 3025.0],
                "volume": [1, 1, 1],
                "amount": [3005.0, 3015.0, 3025.0],
            }
        ),
    ]
    return service


class TestMarketServiceDataFeed:
    """市场服务 DataFeed 适配器测试。"""

    def test_trading_days_and_slice_use_prev_close_and_benchmark(self) -> None:
        """adapter 应使用交易日历、回填 prev_close，并单独提供 benchmark_close。"""
        metadata_service = _make_metadata_service()
        market_service = _make_market_service()
        data_feed = MarketServiceDataFeed(
            metadata_service=metadata_service,
            market_service=market_service,
            config=MarketServiceDataFeedConfig(
                universe_id="cn_etf",
                asset_class="etf",
                start_date="2026-01-10",
                end_date="2026-01-13",
                benchmark_id=InstrumentId(3_000_001),
            ),
        )

        trading_days = data_feed.trading_days()
        slice_ = data_feed.get_slice("2026-01-13")

        assert trading_days == ["2026-01-10", "2026-01-13"]
        assert set(slice_.bars) == {2_000_001, 2_000_002}
        assert slice_.bars[2_000_001].prev_close == 10.5
        assert slice_.bars[2_000_002].prev_close == 19.5
        assert slice_.benchmark_close == 3025.0
        assert 3_000_001 not in slice_.bars
        assert market_service.list_bars.call_count == 2

    def test_canonical_benchmark_id_skips_resolve(self) -> None:
        """canonical InstrumentId benchmark 不再调用 resolve_instrument_id。"""
        metadata_service = _make_metadata_service()
        market_service = _make_market_service()
        data_feed = MarketServiceDataFeed(
            metadata_service=metadata_service,
            market_service=market_service,
            config=MarketServiceDataFeedConfig(
                universe_id="cn_etf",
                asset_class="etf",
                start_date="2026-01-10",
                end_date="2026-01-13",
                benchmark_id=InstrumentId(3_000_001),
            ),
        )

        slice_ = data_feed.get_slice("2026-01-13")
        assert slice_.benchmark_close == 3025.0

        # resolve_instrument_id 仅用于 universe 查询，不被 benchmark 路径调用
        metadata_service.resolve_instrument_id.assert_not_called()
