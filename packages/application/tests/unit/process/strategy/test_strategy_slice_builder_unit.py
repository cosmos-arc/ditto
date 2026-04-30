"""StrategySliceBuilder 单元测试。"""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

import polars as pl
from ditto_application.builders import (
    PublishedStrategyRuntime,
    StrategySliceBuilder,
)
from ditto_data.models.strategy import StrategySpecRecord
from ditto_data.provider import DataProvider
from ditto_data.services.metadata_service import MetadataService
from ditto_engine.alpha.pipeline import StrategyPipeline
from ditto_engine.alpha.specs import StrategySpec
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
    service.resolve_instrument_id.return_value = 3_000_001
    _instrument_map = {
        2_000_001: {"ticker": "510300", "exchange": "XSHG", "asset_class": "etf"},
        2_000_002: {"ticker": "159919", "exchange": "XSHE", "asset_class": "etf"},
        3_000_001: {"ticker": "000300", "exchange": "XSHG", "asset_class": "index"},
    }
    service.get_instrument.side_effect = _instrument_map.get
    return service


def _make_data_provider() -> MagicMock:
    """构造 DataProvider mock，返回行情和交易日历。"""
    provider = MagicMock(spec=DataProvider)
    provider.get_bars.return_value = pl.DataFrame(
        {
            "instrument_id": [
                2_000_001,
                2_000_001,
                2_000_002,
                2_000_002,
                3_000_001,
                3_000_001,
            ],
            "trade_date": [
                "2026-01-10",
                "2026-01-13",
                "2026-01-10",
                "2026-01-13",
                "2026-01-10",
                "2026-01-13",
            ],
            "open": [10.1, 10.6, 19.8, 19.6, 3010.0, 3020.0],
            "high": [10.6, 10.9, 20.0, 19.9, 3020.0, 3030.0],
            "low": [10.0, 10.4, 19.4, 19.5, 3000.0, 3010.0],
            "close": [10.5, 10.8, 19.5, 19.7, 3015.0, 3025.0],
            "volume": [1100, 1200, 2100, 2200, 1, 1],
            "amount": [11550.0, 12960.0, 40950.0, 43340.0, 3015.0, 3025.0],
        }
    )
    provider.get_schedule.return_value = pl.DataFrame(
        {
            "trade_date": ["2026-01-10", "2026-01-13"],
        }
    )
    return provider


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
            data_provider=_make_data_provider(),
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
