"""StrategySliceBuilder 单元测试。"""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

import polars as pl
from ditto_app.builders.strategy import (
    PublishedStrategyRuntime,
    StrategySliceBuilder,
)
from ditto_datahub.models.strategy import StrategySpecRecord
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_engine.strategy.pipeline import StrategyPipeline
from ditto_engine.strategy.specs import StrategySpec
from ditto_kernel.identity import InstrumentId as _InstrumentId

InstrumentId = _InstrumentId


def _make_strategy_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="momentum-etf",
        name="Momentum ETF",
        template="etf_rotation",
        universe="cn_etf",
        asset_class="etf",
        benchmark="000300.SH",
        params={"top_k": 3},
        tags=("momentum", "etf"),
    )


def _make_metadata_service() -> MagicMock:
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
    service.resolve_instrument_id.return_value = 3_000_001
    service.get_instrument.return_value = {"asset_class": "index"}
    service.list_calendar_range.return_value = pl.DataFrame(
        {
            "trade_date": ["2026-01-13"],
            "prev_trade_date": ["2026-01-10"],
        }
    )
    return service


def _make_market_service() -> MagicMock:
    service = MagicMock(spec=MarketService)
    service.list_bars.side_effect = [
        pl.DataFrame(
            {
                "instrument_id": [2_000_001, 2_000_001, 2_000_002, 2_000_002],
                "trade_date": [
                    "2026-01-10",
                    "2026-01-13",
                    "2026-01-10",
                    "2026-01-13",
                ],
                "open": [10.1, 10.6, 19.8, 19.6],
                "high": [10.6, 10.9, 20.0, 19.9],
                "low": [10.0, 10.4, 19.4, 19.5],
                "close": [10.5, 10.8, 19.5, 19.7],
                "volume": [1100, 1200, 2100, 2200],
                "amount": [11550, 12960, 40950, 43340],
            }
        ),
        pl.DataFrame(
            {
                "instrument_id": [3_000_001, 3_000_001],
                "trade_date": ["2026-01-10", "2026-01-13"],
                "open": [3010.0, 3020.0],
                "high": [3020.0, 3030.0],
                "low": [3000.0, 3010.0],
                "close": [3015.0, 3025.0],
                "volume": [1, 1],
                "amount": [3015.0, 3025.0],
            }
        ),
    ]
    return service


class TestStrategySliceBuilder:
    """catalog-backed 单日 Slice 组装测试。"""

    def test_build_published_slice_returns_single_day_slice(self) -> None:
        spec = _make_strategy_spec()
        runtime_builder = MagicMock()
        runtime_builder.build_published_runtime.return_value = PublishedStrategyRuntime(
            record=StrategySpecRecord(
                strategy_id=spec.strategy_id,
                name=spec.name,
                spec_json=asdict(spec),
                version=2,
                status="published",
                tags=spec.tags,
            ),
            spec=spec,
            pipeline=MagicMock(spec=StrategyPipeline),
        )
        builder = StrategySliceBuilder(
            strategy_runtime_builder=runtime_builder,
            metadata_service=_make_metadata_service(),
            market_service=_make_market_service(),
        )

        slice_ = builder.build_published_slice(
            "momentum-etf",
            trade_date="2026-01-13",
            version=2,
        )

        assert slice_.trade_date == "2026-01-13"
        assert set(slice_.bars) == {2_000_001, 2_000_002}
        assert slice_.bars[2_000_001].prev_close == 10.5
        assert slice_.benchmark_close == 3025.0
        runtime_builder.build_published_runtime.assert_called_once_with(
            "momentum-etf",
            2,
        )
