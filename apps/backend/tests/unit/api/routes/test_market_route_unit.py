"""Unit tests for market route handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import cast
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.processes.experiments.regime_diagnostics_reader import (
    RegimeDiagnosticsReader,
    RegimeDiagnosticsView,
    RegimeIndicatorValue,
    RegimeObservation,
)
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.market_context import (
    MarketContextDriverView,
    MarketContextFacade,
    MarketContextImpact,
    MarketContextMetric,
    MarketContextView,
)
from ditto_apps.api.errors import UnprocessableEntityError
from ditto_apps.api.routes.market import (
    get_market_context,
    get_regime_diagnostics,
    post_bars,
)
from ditto_apps.models.common import APIResponse
from ditto_apps.models.market import (
    Bar,
    BarsQuery,
    MarketContextResponse,
    RegimeDiagnosticsResponse,
)
from ditto_strategy.alpha.builtins.regime.regime_types import RegimeLabel


async def _inline_to_thread(function: Callable[..., object], /, *args, **kwargs):
    return function(*args, **kwargs)


class TestPostBarsHandler:
    """POST /market/bars handler behavior without TestClient/Dishka wiring."""

    def test_passes_maturity_opt_in_to_application_facade(self) -> None:
        """Market bars API forwards maturity opt-in, leaving policy to application."""
        facade = MagicMock(spec=MarketQueryFacade)
        facade.find_bars.return_value = pl.DataFrame()
        query = BarsQuery(
            instrument_ids=[1],
            asset_class="stock",
            allow_experimental_data=True,
        )
        handler = cast(
            Callable[..., Awaitable[APIResponse[list[Bar]]]],
            post_bars.__dict__["__dishka_orig_func__"],
        )

        with patch(
            "ditto_apps.api.routes.market.asyncio.to_thread",
            side_effect=_inline_to_thread,
        ):
            response = asyncio.run(handler(query=query, facade=facade))

        assert response.data == []
        call_kwargs = facade.find_bars.call_args.kwargs
        assert call_kwargs["asset_class"] == "stock"
        assert call_kwargs["allow_experimental_data"] is True


class TestGetRegimeDiagnosticsHandler:
    """GET /market/regime handler preserves exact PIT and artifact identity."""

    def test_preserves_scope_and_evidence(self) -> None:
        reader = MagicMock(spec=RegimeDiagnosticsReader)
        reader.read.return_value = RegimeDiagnosticsView(
            snapshot_id="snapshot-regime-1",
            snapshot_manifest_hash="a" * 64,
            dataset_id="research-index-daily",
            source_snapshot_ids=("provider-bars-v1",),
            builder_version="research-snapshot-builder-v1",
            known_at_policy="sample_time",
            benchmark_instrument_id=300_001,
            start_date=date(2026, 1, 21),
            end_date=date(2026, 1, 25),
            knowledge_cutoff=date(2026, 1, 26),
            model_id="momentum-20d-v1",
            lookback_observations=20,
            bear_threshold=35.0,
            bull_threshold=65.0,
            bars_input_id="bars-regime-1",
            bars_content_hash="b" * 64,
            bars_schema_hash="c" * 64,
            observations=(
                RegimeObservation(
                    observed_at=date(2026, 1, 25),
                    score=100.0,
                    label=RegimeLabel.BULL,
                    position_ratio=1.0,
                    indicators=(RegimeIndicatorValue("momentum", 1.0),),
                ),
            ),
            transitions=(),
        )
        handler = cast(
            Callable[..., Awaitable[APIResponse[RegimeDiagnosticsResponse]]],
            get_regime_diagnostics.__dict__["__dishka_orig_func__"],
        )

        with patch(
            "ditto_apps.api.routes.market.asyncio.to_thread",
            side_effect=_inline_to_thread,
        ):
            response = asyncio.run(
                handler(
                    reader=reader,
                    snapshot_id="snapshot-regime-1",
                    snapshot_manifest_hash="a" * 64,
                    benchmark_instrument_id=300_001,
                    start_date=date(2026, 1, 21),
                    end_date=date(2026, 1, 25),
                    knowledge_cutoff=date(2026, 1, 26),
                )
            )

        scope = reader.read.call_args.args[0]
        assert scope.knowledge_cutoff == date(2026, 1, 26)
        assert scope.snapshot_manifest_hash == "a" * 64
        assert response.data.current.observed_at == date(2026, 1, 25)
        assert response.data.current.label == "bull"
        assert response.data.bear_threshold == 35.0
        assert response.data.bull_threshold == 65.0
        assert response.data.bars_content_hash == "b" * 64


class TestGetMarketContextHandler:
    """GET /market/context exposes exact PIT identity and evidence."""

    def test_passes_exact_snapshot_request_and_maps_evidence(self) -> None:
        as_of = datetime(2026, 8, 31, 9, tzinfo=UTC)
        knowledge_cutoff = datetime(2026, 8, 31, 8, tzinfo=UTC)
        publication_cutoff = datetime(2026, 8, 31, 7, 30, tzinfo=UTC)
        snapshot_ids = ("snapshot-stock", "snapshot-macro")
        snapshot_set_id = aggregate_source_snapshot_ids(snapshot_ids)
        assert snapshot_set_id is not None
        facade = MagicMock(spec=MarketContextFacade)
        facade.get_context.return_value = MarketContextView(
            as_of=as_of,
            knowledge_cutoff=knowledge_cutoff,
            publication_cutoff=publication_cutoff,
            source_snapshot_ids=snapshot_ids,
            source_snapshot_set_id=snapshot_set_id,
            status="ready",
            feature_set_id="market-regime:sha256:abc",
            feature_version="market-regime.v1",
            regime_label="risk_on",
            regime_score=0.4,
            drivers=(
                MarketContextDriverView(
                    name="breadth",
                    category="a_share",
                    contribution=0.2,
                    direction="supportive",
                ),
            ),
            metrics=(
                MarketContextMetric(
                    name="csi300_return_20d",
                    category="a_share",
                    value=0.05,
                    unit="ratio",
                    trend="rising",
                    freshness="fresh",
                    evidence_ref="dataset://stock_daily/csi300@2026-08-31",
                ),
            ),
            impacts=(
                MarketContextImpact(
                    target_domain="risk",
                    target="volatility_budget",
                    direction="supportive",
                    rationale_driver="volatility",
                ),
            ),
            missing_inputs=(),
            data_conflicts=(),
            uncertainties=(),
            evidence_refs=("dataset://stock_daily/csi300@2026-08-31",),
        )
        handler = cast(
            Callable[..., Awaitable[APIResponse[MarketContextResponse]]],
            get_market_context.__dict__["__dishka_orig_func__"],
        )

        with patch(
            "ditto_apps.api.routes.market.asyncio.to_thread",
            side_effect=_inline_to_thread,
        ):
            response = asyncio.run(
                handler(
                    facade=facade,
                    as_of=as_of,
                    knowledge_cutoff=knowledge_cutoff,
                    publication_cutoff=publication_cutoff,
                    source_snapshot_id=["snapshot-stock", "snapshot-macro"],
                )
            )

        request = facade.get_context.call_args.args[0]
        assert request.source_snapshot_ids == ("snapshot-stock", "snapshot-macro")
        assert request.publication_cutoff == publication_cutoff
        assert response.data.status == "ready"
        assert response.data.source_snapshot_set_id == snapshot_set_id
        assert response.data.drivers[0].name == "breadth"
        assert response.data.impacts[0].target_domain == "risk"
        assert response.data.metrics[0].evidence_ref.startswith("dataset://")

    def test_maps_invalid_pit_request_to_stable_422_error(self) -> None:
        facade = MagicMock(spec=MarketContextFacade)
        facade.get_context.side_effect = ValueError("timezone-aware required")
        handler = cast(
            Callable[..., Awaitable[APIResponse[MarketContextResponse]]],
            get_market_context.__dict__["__dishka_orig_func__"],
        )

        with (
            patch(
                "ditto_apps.api.routes.market.asyncio.to_thread",
                side_effect=_inline_to_thread,
            ),
            pytest.raises(UnprocessableEntityError) as caught,
        ):
            asyncio.run(
                handler(
                    facade=facade,
                    as_of=datetime(2026, 8, 31, 9),
                    knowledge_cutoff=datetime(2026, 8, 31, 8),
                    publication_cutoff=datetime(2026, 8, 31, 7, 30),
                    source_snapshot_id=["snapshot-stock"],
                )
            )

        assert caught.value.error_code == "MARKET_CONTEXT_INVALID"
