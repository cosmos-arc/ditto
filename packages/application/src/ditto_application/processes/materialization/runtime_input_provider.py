"""Runtime input provider for production derived materialization."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

import polars as pl
from ditto_data.catalog import DataCatalogReader
from ditto_data.services.market_service import MarketService
from ditto_features.materialization.dependency_registry import (
    DependencyContract,
    dependency_contracts,
)
from ditto_features.services import DerivedArtifactReader, DerivedCatalogService

from ditto_application.processes.materialization.catalog_dependency_validation import (
    validate_dependency_catalog_compatibility,
)
from ditto_application.processes.materialization.dependencies import (
    classify_dependencies,
    join_frames,
    prepare_derived_frame,
    prepare_market_frame,
    resolve_adj_type,
)
from ditto_application.processes.materialization.types import InputContext

__all__ = [
    "CatalogCoverageDatesProvider",
    "RuntimeDerivedInputProvider",
]

type CatalogCoverageDatesProvider = Callable[[str, str], Iterable[str]]


class RuntimeDerivedInputProvider:
    """Read runtime inputs from local market truth and upstream derived artifacts."""

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        market_service: MarketService,
        artifact_root: Path,
        data_catalog_reader: DataCatalogReader | None = None,
        catalog_coverage_dates_provider: CatalogCoverageDatesProvider | None = None,
    ) -> None:
        self._artifact_reader = DerivedArtifactReader(
            catalog_service=catalog_service,
            artifact_root=artifact_root,
        )
        self._market_service = market_service
        self._data_catalog_reader = data_catalog_reader
        self._catalog_coverage_dates_provider = catalog_coverage_dates_provider

    def load_input(self, context: InputContext) -> pl.DataFrame:
        """Load one runtime input frame for the requested dependency set."""
        spec = context.spec
        plan = context.plan
        join_keys = [*spec.entity_keys, *spec.effective_time_keys]

        market_deps, etf_deps, derived_deps = classify_dependencies(
            context.dependencies,
        )
        contracts_by_ref = {
            contract.ref.ref: contract
            for contract in dependency_contracts(context.dependencies)
        }
        start = str(plan.compute_start)
        end = str(plan.compute_end)
        if self._data_catalog_reader is not None:
            validate_dependency_catalog_compatibility(
                contracts=contracts_by_ref.values(),
                catalog_reader=self._data_catalog_reader,
                required_dates=self._catalog_required_dates(start=start, end=end),
                expected_source_snapshot_id=context.request.source_snapshot_id,
            )
        adj = resolve_adj_type(spec)

        frames = list(
            self._load_market_frames(
                market_deps,
                start,
                end,
                join_keys,
                contracts_by_ref,
            ),
        )
        frames.extend(
            self._load_etf_frames(
                etf_deps,
                start,
                end,
                join_keys,
                adj,
                contracts_by_ref,
            )
        )
        frames.extend(self._load_derived_frames(derived_deps, start, end, join_keys))

        if not frames:
            raise NotImplementedError(
                f"Phase 3 input backend not wired for derived_id={spec.id}"
            )
        return join_frames(frames, join_keys=join_keys)

    def _catalog_required_dates(self, *, start: str, end: str) -> tuple[str, ...]:
        if self._catalog_coverage_dates_provider is None:
            return ()
        return tuple(self._catalog_coverage_dates_provider(start, end))

    def _load_market_frames(
        self,
        deps: dict[str, set[str]],
        start: str,
        end: str,
        join_keys: list[str],
        contracts_by_ref: dict[str, DependencyContract],
    ) -> list[pl.DataFrame]:
        """Load stock market data frames for classified market dependencies."""
        frames: list[pl.DataFrame] = []
        for dataset_ref, value_columns in deps.items():
            raw = self._fetch_market_data(dataset_ref, start, end)
            if raw is None:
                continue
            frames.append(
                prepare_market_frame(
                    raw,
                    join_keys=join_keys,
                    value_columns=value_columns,
                    availability_column="trade_date",
                    contract=contracts_by_ref.get(dataset_ref),
                )
            )
        return frames

    def _fetch_market_data(
        self,
        dataset_ref: str,
        start: str,
        end: str,
    ) -> pl.DataFrame | None:
        """Fetch market data for a given dataset reference."""
        if dataset_ref == "market.stock_daily":
            return self._market_service.get_stock_bars(start=start, end=end)
        if dataset_ref == "market.adj_factor":
            return self._market_service.get_adj_factors(start=start, end=end)
        if dataset_ref == "market.stock_status":
            return self._market_service.get_stock_status(start=start, end=end)
        return None

    def _load_etf_frames(
        self,
        deps: dict[str, set[str]],
        start: str,
        end: str,
        join_keys: list[str],
        adj: str,
        contracts_by_ref: dict[str, DependencyContract],
    ) -> list[pl.DataFrame]:
        """Load ETF data frames for classified ETF dependencies."""
        frames: list[pl.DataFrame] = []
        if "etf.daily" in deps:
            raw = self._market_service.get_etf_bars(
                start=start,
                end=end,
                adj=adj,
            )
            frames.append(
                prepare_market_frame(
                    raw,
                    join_keys=join_keys,
                    value_columns=deps["etf.daily"],
                    availability_column="trade_date",
                    contract=contracts_by_ref.get("etf.daily"),
                )
            )
        return frames

    def _load_derived_frames(
        self,
        deps: list[str],
        start: str,
        end: str,
        join_keys: list[str],
    ) -> list[pl.DataFrame]:
        """Load upstream derived artifact frames."""
        frames: list[pl.DataFrame] = []
        for derived_id in deps:
            version = self._artifact_reader.resolve_offline_version(derived_id)
            upstream = self._artifact_reader.read_frame(
                derived_id=derived_id,
                version=version,
                start=start,
                end=end,
            )
            frames.append(
                prepare_derived_frame(
                    upstream,
                    join_keys=join_keys,
                    column_name=derived_id,
                )
            )
        return frames
