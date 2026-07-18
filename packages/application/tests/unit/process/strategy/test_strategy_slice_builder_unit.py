"""StrategySliceBuilder 单元测试。"""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.builders import (
    PublishedStrategyRuntime,
    StrategySliceBuilder,
)
from ditto_application.exceptions import AppBuilderError
from ditto_data.catalog.promotion import DatasetMaturityPromotion
from ditto_data.provider import DataProvider
from ditto_data.services.metadata_service import MetadataService
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.specs import StrategySpec
from ditto_strategy.models import StrategySpecRecord


def _make_strategy_spec(
    *,
    strategy_id: str = "momentum-etf",
    name: str = "Momentum ETF",
    template: str = "etf_rotation",
    universe: str = "cn_etf",
    asset_class: str = "etf",
) -> StrategySpec:
    return StrategySpec(
        strategy_id=strategy_id,
        name=name,
        template=template,
        universe=universe,
        asset_class=asset_class,
        benchmark="000300.SH",
        params={"top_k": 3},
        tags=("momentum", asset_class),
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
    service.instrument.get_instrument.side_effect = _instrument_map.get
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


class _MaturityPromotionReader:
    def __init__(self, promoted_dataset_ids: set[str]) -> None:
        self._promoted_dataset_ids = promoted_dataset_ids

    def get_dataset_maturity_promotion(
        self,
        dataset_id: str,
    ) -> DatasetMaturityPromotion | None:
        if dataset_id not in self._promoted_dataset_ids:
            return None
        return DatasetMaturityPromotion(
            dataset_id=dataset_id,
            previous_maturity="experimental",
            promoted_maturity="initial-focus",
            promoted_by="architecture-review",
        )


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
            spec_hash="b" * 64,
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

    def test_rejects_experimental_stock_data_by_default(self) -> None:
        """单日 strategy slice 默认不得静默使用 experimental 股票数据集。"""
        spec = _make_strategy_spec(
            strategy_id="stock-alpha",
            name="Stock Alpha",
            template="stock_selection",
            universe="cn_stock",
            asset_class="stock",
        )
        runtime_builder = MagicMock()
        runtime_builder.build_published_runtime.return_value = PublishedStrategyRuntime(
            record=StrategySpecRecord(
                strategy_id=spec.strategy_id,
                name=spec.name,
                spec_json=asdict(spec),
                version=1,
                status="published",
                tags=spec.tags,
            ),
            spec=spec,
            pipeline=MagicMock(spec=StrategyPipeline),
            spec_hash="b" * 64,
        )
        data_provider = _make_data_provider()
        builder = StrategySliceBuilder(
            strategy_runtime_builder=runtime_builder,
            metadata_service=_make_metadata_service(),
            data_provider=data_provider,
        )

        with pytest.raises(AppBuilderError, match="experimental dataset"):
            builder.build_published_slice(
                "stock-alpha",
                trade_date="2026-01-13",
                version=1,
            )

        data_provider.get_bars.assert_not_called()

    def test_allows_experimental_stock_data_when_explicit(self) -> None:
        """研究场景可显式 opt in 构造股票数据 slice。"""
        spec = _make_strategy_spec(
            strategy_id="stock-alpha",
            name="Stock Alpha",
            template="stock_selection",
            universe="cn_stock",
            asset_class="stock",
        )
        runtime_builder = MagicMock()
        runtime_builder.build_published_runtime.return_value = PublishedStrategyRuntime(
            record=StrategySpecRecord(
                strategy_id=spec.strategy_id,
                name=spec.name,
                spec_json=asdict(spec),
                version=1,
                status="published",
                tags=spec.tags,
            ),
            spec=spec,
            pipeline=MagicMock(spec=StrategyPipeline),
            spec_hash="b" * 64,
        )
        builder = StrategySliceBuilder(
            strategy_runtime_builder=runtime_builder,
            metadata_service=_make_metadata_service(),
            data_provider=_make_data_provider(),
        )

        slice_ = builder.build_published_slice(
            "stock-alpha",
            trade_date="2026-01-13",
            version=1,
            allow_experimental_data=True,
        )

        assert slice_.trade_date == "2026-01-13"

    def test_allows_promoted_stock_data_without_research_opt_in(self) -> None:
        """已完成 metadata promotion 的股票数据可进入默认运行时。"""
        spec = _make_strategy_spec(
            strategy_id="stock-alpha",
            name="Stock Alpha",
            template="stock_selection",
            universe="cn_stock",
            asset_class="stock",
        )
        runtime_builder = MagicMock()
        runtime_builder.build_published_runtime.return_value = PublishedStrategyRuntime(
            record=StrategySpecRecord(
                strategy_id=spec.strategy_id,
                name=spec.name,
                spec_json=asdict(spec),
                version=1,
                status="published",
                tags=spec.tags,
            ),
            spec=spec,
            pipeline=MagicMock(spec=StrategyPipeline),
            spec_hash="b" * 64,
        )
        builder = StrategySliceBuilder(
            strategy_runtime_builder=runtime_builder,
            metadata_service=_make_metadata_service(),
            data_provider=_make_data_provider(),
            maturity_promotion_reader=_MaturityPromotionReader(
                {"stock_daily", "stock_basic"}
            ),
        )

        slice_ = builder.build_published_slice(
            "stock-alpha",
            trade_date="2026-01-13",
            version=1,
        )

        assert slice_.trade_date == "2026-01-13"
