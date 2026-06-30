"""Unit tests for RuntimeDerivedInputProvider MarketService integration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.processes.materialization.catalog_dependency_validation import (
    DependencyCatalogCompatibilityError,
)
from ditto_application.processes.materialization.runtime_input_provider import (
    RuntimeDerivedInputProvider,
)
from ditto_application.processes.materialization.types import (
    InputContext,
    MissingDependencyError,
)
from ditto_data.catalog import InMemoryDataCatalog
from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
)
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.materialization.contracts import (
    DerivedExecutionPlan,
    DerivedRunMode,
)
from ditto_features.materialization.dependency_registry import (
    resolve_etf_dependency,
    resolve_market_dependency,
)
from ditto_kernel.strategy import ExecutionPolicy


def _make_spec(**overrides: object) -> DerivedSpec:
    defaults: dict[str, object] = {
        "id": "test.factor",
        "version": 1,
        "role": DerivedRole.FEATURE,
        "materialization_profile": MaterializationProfile.SERIES,
        "expression": "close",
    }
    defaults.update(overrides)
    return DerivedSpec(**defaults)  # type: ignore[arg-type]


def _make_plan(**overrides: object) -> DerivedExecutionPlan:
    defaults: dict[str, object] = {
        "derived_id": "test.factor",
        "version": 1,
        "profile": MaterializationProfile.SERIES,
        "mode": DerivedRunMode.FULL,
        "request_start": "2024-01-01",
        "request_end": "2024-01-10",
        "compute_start": "2024-01-01",
        "compute_end": "2024-01-10",
        "partitions": ("2024-01-01",),
        "lookback": 0,
        "requires_full_day": False,
    }
    defaults.update(overrides)
    return DerivedExecutionPlan(**defaults)  # type: ignore[arg-type]


def _make_input_context(
    *,
    dependencies: tuple[str, ...] = ("market.close",),
    execution_policy: ExecutionPolicy | None = None,
    source_snapshot_id: str | None = None,
) -> InputContext:
    spec_kwargs: dict[str, object] = {}
    if execution_policy is not None:
        spec_kwargs["execution_policy"] = execution_policy
    spec = _make_spec(**spec_kwargs)
    plan = _make_plan()
    request = MagicMock()
    request.request_start = "2024-01-01"
    request.request_end = "2024-01-10"
    request.source_snapshot_id = source_snapshot_id
    return InputContext(
        spec=spec,
        request=request,
        plan=plan,
        dependencies=dependencies,
    )


_STOCK_DAILY_DF = pl.DataFrame(
    {
        "instrument_id": [1, 2],
        "trade_date": ["2024-01-01", "2024-01-01"],
        "close": [10.0, 20.0],
        "open": [9.5, 19.5],
        "high": [10.5, 20.5],
        "low": [9.0, 19.0],
        "pre_close": [9.0, 19.0],
        "volume": [1000, 2000],
        "amount": [10000.0, 40000.0],
    }
)

_ETF_DAILY_DF = pl.DataFrame(
    {
        "instrument_id": [10, 20],
        "trade_date": ["2024-01-01", "2024-01-01"],
        "close": [5.0, 10.0],
        "open": [4.8, 9.8],
        "high": [5.2, 10.2],
        "low": [4.5, 9.5],
        "pre_close": [4.5, 9.5],
        "volume": [500, 1000],
        "amount": [2500.0, 10000.0],
        "pct_change": [1.0, 2.0],
    }
)


def _catalog_entry(
    *,
    dataset_id: str = "stock_daily",
    namespace: str = "market",
    source: str = "tushare",
    schema_version: str = "market.stock_daily.v1",
    trade_date: str = "2024-01-10",
    source_snapshot_id: str | None = "snapshot:tushare:stock_daily:2024-01-10:abc",
    columns: tuple[str, ...] = (
        "instrument_id",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
    ),
) -> DataCatalogEntry:
    timestamp = datetime(2024, 1, 10, 16, 0, tzinfo=UTC)
    return DataCatalogEntry(
        asset=DataAssetRef(
            dataset_id=dataset_id,
            namespace=namespace,
            partition_keys=(f"trade_date={trade_date}",),
        ),
        storage_uri=f"lake://{namespace}/{dataset_id}/{trade_date}.parquet",
        schema=DataSchemaFingerprint(
            schema_hash=f"schema:{dataset_id}",
            row_count=2,
            created_at=timestamp,
            schema_version=schema_version,
            columns=columns,
        ),
        source=source,
        freshness_at=timestamp,
        source_snapshot_id=source_snapshot_id,
    )


class TestResolveMarketDependency:
    """Tests for _resolve_market_dependency helper."""

    @pytest.mark.parametrize(
        ("dep", "expected"),
        [
            ("market.close", ("market.stock_daily", "close")),
            ("market.open", ("market.stock_daily", "open")),
            ("market.volume", ("market.stock_daily", "volume")),
            ("market.adj_factor", ("market.adj_factor", "adj_factor")),
            ("market.is_suspended", ("market.stock_status", "is_suspended")),
            ("market.is_st", ("market.stock_status", "is_st")),
        ],
    )
    def test_resolves_known_dependencies(
        self,
        dep: str,
        expected: tuple[str, str],
    ) -> None:
        assert resolve_market_dependency(dep) == expected

    def test_raises_for_unknown_dependency(self) -> None:
        with pytest.raises(
            NotImplementedError,
            match=r"market\.unknown_col",
        ):
            resolve_market_dependency("market.unknown_col")


class TestResolveEtfDependency:
    """Tests for _resolve_etf_dependency helper."""

    @pytest.mark.parametrize(
        ("dep", "expected"),
        [
            ("etf.close", ("etf.daily", "close")),
            ("etf.open", ("etf.daily", "open")),
            ("etf.volume", ("etf.daily", "volume")),
            ("etf.pct_change", ("etf.daily", "pct_change")),
        ],
    )
    def test_resolves_known_etf_dependencies(
        self,
        dep: str,
        expected: tuple[str, str],
    ) -> None:
        assert resolve_etf_dependency(dep) == expected

    def test_raises_for_unknown_etf_dependency(self) -> None:
        with pytest.raises(
            NotImplementedError,
            match=r"etf\.unknown_col",
        ):
            resolve_etf_dependency("etf.unknown_col")


class TestRuntimeDerivedInputProvider:
    """Tests for RuntimeDerivedInputProvider with MarketService."""

    def _make_provider(
        self,
        *,
        mock_market_service: MagicMock | None = None,
        data_catalog: InMemoryDataCatalog | None = None,
        catalog_coverage_dates: tuple[str, ...] | None = None,
    ) -> RuntimeDerivedInputProvider:
        catalog_service = MagicMock()
        catalog_service.resolve_offline_version.return_value = 1
        catalog_service.read_frame.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-01"],
                "value": [1.0],
            }
        )
        market = mock_market_service or MagicMock()
        return RuntimeDerivedInputProvider(
            catalog_service=catalog_service,
            market_service=market,
            artifact_root=Path("/tmp/artifacts"),
            data_catalog_reader=data_catalog,
            catalog_coverage_dates_provider=(
                (lambda _start, _end: catalog_coverage_dates)
                if catalog_coverage_dates is not None
                else None
            ),
        )

    def test_load_input_delegates_to_market_service_get_stock_bars(self) -> None:
        """Provider should call market_service.get_stock_bars for stock_daily deps."""
        mock_market = MagicMock()
        mock_market.get_stock_bars.return_value = _STOCK_DAILY_DF
        provider = self._make_provider(mock_market_service=mock_market)
        ctx = _make_input_context(dependencies=("market.close", "market.volume"))

        result = provider.load_input(ctx)

        mock_market.get_stock_bars.assert_called_once_with(
            start="2024-01-01",
            end="2024-01-10",
        )
        assert "close" in result.columns
        assert "volume" in result.columns

    def test_load_input_delegates_to_market_service_get_adj_factors(self) -> None:
        """Provider should call market_service.get_adj_factors for adj_factor deps."""
        adj_df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-01"],
                "adj_factor": [1.0],
            }
        )
        mock_market = MagicMock()
        mock_market.get_adj_factors.return_value = adj_df
        provider = self._make_provider(mock_market_service=mock_market)
        ctx = _make_input_context(dependencies=("market.adj_factor",))

        result = provider.load_input(ctx)

        mock_market.get_adj_factors.assert_called_once_with(
            start="2024-01-01",
            end="2024-01-10",
        )
        assert "adj_factor" in result.columns

    def test_load_input_delegates_to_market_service_get_stock_status(self) -> None:
        """Provider should call market_service.get_stock_status for status deps."""
        status_df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-01"],
                "is_suspended": [0],
            }
        )
        mock_market = MagicMock()
        mock_market.get_stock_status.return_value = status_df
        provider = self._make_provider(mock_market_service=mock_market)
        ctx = _make_input_context(dependencies=("market.is_suspended",))

        result = provider.load_input(ctx)

        mock_market.get_stock_status.assert_called_once_with(
            start="2024-01-01",
            end="2024-01-10",
        )
        assert "is_suspended" in result.columns

    def test_load_input_joins_multiple_market_sources(self) -> None:
        """Provider should join multiple market data sources on entity/time keys."""
        bars_df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-01"],
                "close": [10.0],
                "open": [9.5],
                "high": [10.5],
                "low": [9.0],
                "pre_close": [9.0],
                "volume": [1000],
                "amount": [10000.0],
            }
        )
        adj_df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-01"],
                "adj_factor": [1.0],
            }
        )
        mock_market = MagicMock()
        mock_market.get_stock_bars.return_value = bars_df
        mock_market.get_adj_factors.return_value = adj_df
        provider = self._make_provider(mock_market_service=mock_market)
        ctx = _make_input_context(dependencies=("market.close", "market.adj_factor"))

        result = provider.load_input(ctx)

        assert "close" in result.columns
        assert "adj_factor" in result.columns
        assert "availability_time" in result.columns
        assert len(result) == 1

    def test_load_input_raises_for_unsupported_dependency(self) -> None:
        """Provider should raise NotImplementedError for unsupported deps."""
        provider = self._make_provider()
        ctx = _make_input_context(dependencies=("market.unknown_col",))

        with pytest.raises(NotImplementedError, match=r"market\.unknown_col"):
            provider.load_input(ctx)

    def test_load_input_fails_closed_when_market_frame_misses_requested_column(
        self,
    ) -> None:
        """Provider should reject source frames that miss requested value columns."""
        stock_df = _STOCK_DAILY_DF.drop("volume")
        mock_market = MagicMock()
        mock_market.get_stock_bars.return_value = stock_df
        provider = self._make_provider(mock_market_service=mock_market)
        ctx = _make_input_context(dependencies=("market.close", "market.volume"))

        with pytest.raises(MissingDependencyError) as exc_info:
            provider.load_input(ctx)

        assert exc_info.value.missing == ["volume"]
        assert "volume" not in exc_info.value.available

    def test_load_input_fails_closed_when_market_frame_misses_time_key(self) -> None:
        """Provider should reject source frames that miss contract time columns."""
        stock_df = _STOCK_DAILY_DF.drop("trade_date")
        mock_market = MagicMock()
        mock_market.get_stock_bars.return_value = stock_df
        provider = self._make_provider(mock_market_service=mock_market)
        ctx = _make_input_context(dependencies=("market.close",))

        with pytest.raises(MissingDependencyError) as exc_info:
            provider.load_input(ctx)

        assert exc_info.value.missing == ["trade_date"]
        assert "trade_date" not in exc_info.value.available

    def test_load_input_fails_before_market_read_when_catalog_schema_misses_column(
        self,
    ) -> None:
        """Provider should reject catalog-incompatible source assets before IO."""
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            _catalog_entry(
                columns=(
                    "instrument_id",
                    "trade_date",
                    "close",
                )
            )
        )
        mock_market = MagicMock()
        provider = self._make_provider(
            mock_market_service=mock_market,
            data_catalog=catalog,
        )
        ctx = _make_input_context(dependencies=("market.close", "market.volume"))

        with pytest.raises(DependencyCatalogCompatibilityError) as exc_info:
            provider.load_input(ctx)

        assert exc_info.value.dataset_ref == "market.stock_daily"
        assert exc_info.value.missing_columns == ("volume",)
        mock_market.get_stock_bars.assert_not_called()

    def test_load_input_fails_before_market_read_when_catalog_coverage_misses_date(
        self,
    ) -> None:
        """Provider should reject catalog assets that do not cover request dates."""
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(_catalog_entry(trade_date="2024-01-01"))
        mock_market = MagicMock()
        provider = self._make_provider(
            mock_market_service=mock_market,
            data_catalog=catalog,
            catalog_coverage_dates=("2024-01-01", "2024-01-02"),
        )
        ctx = _make_input_context(dependencies=("market.close",))

        with pytest.raises(DependencyCatalogCompatibilityError) as exc_info:
            provider.load_input(ctx)

        assert exc_info.value.dataset_ref == "market.stock_daily"
        assert exc_info.value.reason == "missing_catalog_coverage"
        assert exc_info.value.missing_dates == ("2024-01-02",)
        mock_market.get_stock_bars.assert_not_called()

    def test_load_input_rejects_catalog_snapshot_mismatch_before_market_read(
        self,
    ) -> None:
        """Provider should pin source reads to the requested catalog snapshot."""
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            _catalog_entry(source_snapshot_id="snapshot:tushare:stock_daily:v1")
        )
        mock_market = MagicMock()
        provider = self._make_provider(
            mock_market_service=mock_market,
            data_catalog=catalog,
        )
        ctx = _make_input_context(
            dependencies=("market.close",),
            source_snapshot_id="snapshot:tushare:stock_daily:v2",
        )

        with pytest.raises(DependencyCatalogCompatibilityError) as exc_info:
            provider.load_input(ctx)

        assert exc_info.value.dataset_ref == "market.stock_daily"
        assert exc_info.value.reason == "source_snapshot_mismatch"
        assert (
            exc_info.value.expected_source_snapshot_id
            == "snapshot:tushare:stock_daily:v2"
        )
        assert (
            exc_info.value.actual_source_snapshot_id
            == "snapshot:tushare:stock_daily:v1"
        )
        mock_market.get_stock_bars.assert_not_called()

    def test_load_input_delegates_to_get_etf_bars_for_etf_deps(self) -> None:
        """Provider should call market_service.get_etf_bars for etf.* deps."""
        mock_market = MagicMock()
        mock_market.get_etf_bars.return_value = _ETF_DAILY_DF
        provider = self._make_provider(mock_market_service=mock_market)
        ctx = _make_input_context(
            dependencies=("etf.close", "etf.volume"),
        )

        result = provider.load_input(ctx)

        mock_market.get_etf_bars.assert_called_once_with(
            start="2024-01-01",
            end="2024-01-10",
            adj="none",
        )
        assert "close" in result.columns
        assert "volume" in result.columns

    def test_load_input_passes_adj_type_to_get_etf_bars(self) -> None:
        """Provider should pass execution_policy.adj_type to get_etf_bars."""
        mock_market = MagicMock()
        mock_market.get_etf_bars.return_value = _ETF_DAILY_DF
        provider = self._make_provider(mock_market_service=mock_market)
        ctx = _make_input_context(
            dependencies=("etf.close",),
            execution_policy=ExecutionPolicy(adj_type="qfq"),
        )

        result = provider.load_input(ctx)

        mock_market.get_etf_bars.assert_called_once_with(
            start="2024-01-01",
            end="2024-01-10",
            adj="qfq",
        )
        assert "close" in result.columns

    def test_load_input_joins_etf_and_market_sources(self) -> None:
        """Provider should join ETF and stock market data on entity/time keys."""
        stock_df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-01"],
                "close": [10.0],
                "open": [9.5],
                "high": [10.5],
                "low": [9.0],
                "pre_close": [9.0],
                "volume": [1000],
                "amount": [10000.0],
            }
        )
        etf_df = pl.DataFrame(
            {
                "instrument_id": [10],
                "trade_date": ["2024-01-01"],
                "close": [5.0],
                "open": [4.8],
                "high": [5.2],
                "low": [4.5],
                "pre_close": [4.5],
                "volume": [500],
                "amount": [2500.0],
                "pct_change": [1.0],
            }
        )
        mock_market = MagicMock()
        mock_market.get_stock_bars.return_value = stock_df
        mock_market.get_etf_bars.return_value = etf_df
        provider = self._make_provider(mock_market_service=mock_market)
        ctx = _make_input_context(
            dependencies=("market.close", "etf.close"),
        )

        result = provider.load_input(ctx)

        mock_market.get_stock_bars.assert_called_once()
        mock_market.get_etf_bars.assert_called_once()
        assert "close" in result.columns
        assert "availability_time" in result.columns
