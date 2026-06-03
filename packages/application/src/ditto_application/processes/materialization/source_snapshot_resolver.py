"""Source snapshot provenance resolution for derived materialization."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

import orjson
from ditto_data.catalog import DataCatalogReader
from ditto_data.catalog.metadata import default_dataset_metadata
from ditto_features.materialization.dependency_registry import (
    DependencyContract,
    dependency_contracts,
)

from ditto_application.processes.materialization.catalog_dependency_validation import (
    validate_dependency_catalog_compatibility,
)
from ditto_application.processes.materialization.types import InputContext

__all__ = [
    "CatalogCoverageDatesProvider",
    "CatalogSourceSnapshotResolver",
    "SourceSnapshotProvenance",
    "SourceSnapshotResolver",
    "UniverseSourceTickersProvider",
    "UniverseSourceTickersRequest",
]

type CatalogCoverageDatesProvider = Callable[[str, str], Iterable[str]]
type UniverseSourceTickersProvider = Callable[
    ["UniverseSourceTickersRequest"],
    Iterable[str],
]


@dataclass(frozen=True)
class UniverseSourceTickersRequest:
    """Request source-specific universe tickers for one dependency/date."""

    universe_id: str
    source: str
    asof: str | None
    dependency_ref: str
    catalog_dataset_id: str
    catalog_namespace: str


@dataclass(frozen=True)
class SourceSnapshotProvenance:
    """Resolved source snapshot aggregate plus exact selected source snapshots."""

    source_snapshot_id: str | None
    source_snapshot_ids: tuple[str, ...] = ()

    @classmethod
    def from_ids(cls, snapshot_ids: Iterable[str | None]) -> SourceSnapshotProvenance:
        """Build stable aggregate provenance from exact source snapshot IDs."""
        normalized = _normalize_snapshot_ids(snapshot_ids)
        return cls(
            source_snapshot_id=_aggregate_snapshot_id(normalized),
            source_snapshot_ids=normalized,
        )


class SourceSnapshotResolver(Protocol):
    """Resolve source snapshot provenance for one materialization input context."""

    def resolve(self, context: InputContext) -> SourceSnapshotProvenance:
        """Return the source snapshots selected for the materialization inputs."""
        ...


class CatalogSourceSnapshotResolver:
    """Resolve selected source snapshots from DataCatalog dependency assets."""

    def __init__(
        self,
        *,
        data_catalog_reader: DataCatalogReader,
        catalog_coverage_dates_provider: CatalogCoverageDatesProvider | None = None,
        universe_source_tickers_provider: UniverseSourceTickersProvider | None = None,
    ) -> None:
        self._data_catalog_reader = data_catalog_reader
        self._catalog_coverage_dates_provider = catalog_coverage_dates_provider
        self._universe_source_tickers_provider = universe_source_tickers_provider

    def resolve(self, context: InputContext) -> SourceSnapshotProvenance:
        """Return DataCatalog-proven source snapshot provenance for *context*."""
        plan = context.plan
        asof = str(plan.compute_start)
        required_dates = self._catalog_required_dates(
            start=asof,
            end=str(plan.compute_end),
        )
        contracts = dependency_contracts(context.dependencies)
        report = validate_dependency_catalog_compatibility(
            contracts=contracts,
            catalog_reader=self._data_catalog_reader,
            required_dates=required_dates,
            expected_source_snapshot_id=context.request.source_snapshot_id,
            required_source_tickers=(
                ()
                if required_dates
                else self._required_source_tickers(
                    context,
                    contracts=contracts,
                    asof=asof,
                )
            ),
            required_source_tickers_by_date_by_ref=(
                self._required_source_tickers_by_date_by_ref(
                    context,
                    contracts=contracts,
                    dates=required_dates,
                )
            ),
            required_source_tickers_by_date=None,
        )
        if report.source_snapshot_ids:
            return SourceSnapshotProvenance.from_ids(report.source_snapshot_ids)
        return SourceSnapshotProvenance.from_ids((context.request.source_snapshot_id,))

    def _catalog_required_dates(self, *, start: str, end: str) -> tuple[str, ...]:
        if self._catalog_coverage_dates_provider is None:
            return ()
        return tuple(self._catalog_coverage_dates_provider(start, end))

    def _required_source_tickers(
        self,
        context: InputContext,
        *,
        contracts: tuple[DependencyContract, ...],
        asof: str | None,
    ) -> tuple[str, ...]:
        if context.spec.universe_id is None:
            return ()
        provider = self._universe_source_tickers_provider
        if provider is None:
            return ()
        source_tickers: list[str] = []
        for contract in contracts:
            source = _contract_default_source(contract)
            if source is None:
                continue
            source_tickers.extend(
                provider(
                    UniverseSourceTickersRequest(
                        universe_id=context.spec.universe_id,
                        source=source,
                        asof=asof,
                        dependency_ref=contract.ref.ref,
                        catalog_dataset_id=contract.catalog_dataset_id,
                        catalog_namespace=contract.catalog_namespace,
                    )
                )
            )
        return tuple(dict.fromkeys(source_tickers))

    def _required_source_tickers_by_date_by_ref(
        self,
        context: InputContext,
        *,
        contracts: tuple[DependencyContract, ...],
        dates: tuple[str, ...],
    ) -> dict[str, dict[str, tuple[str, ...]]]:
        if context.spec.universe_id is None:
            return {}
        provider = self._universe_source_tickers_provider
        if provider is None:
            return {}
        source_tickers_by_ref: dict[str, dict[str, tuple[str, ...]]] = {}
        for contract in contracts:
            source = _contract_default_source(contract)
            if source is None:
                continue
            source_tickers_by_ref[contract.ref.ref] = {
                date: tuple(
                    dict.fromkeys(
                        provider(
                            UniverseSourceTickersRequest(
                                universe_id=context.spec.universe_id,
                                source=source,
                                asof=date,
                                dependency_ref=contract.ref.ref,
                                catalog_dataset_id=contract.catalog_dataset_id,
                                catalog_namespace=contract.catalog_namespace,
                            )
                        )
                    )
                )
                for date in dates
            }
        return source_tickers_by_ref


def _contract_default_source(contract: DependencyContract) -> str | None:
    metadata = default_dataset_metadata().get(contract.catalog_dataset_id)
    if metadata is None:
        return None
    return metadata.default_source


def _normalize_snapshot_ids(snapshot_ids: Iterable[str | None]) -> tuple[str, ...]:
    return tuple(sorted({snapshot_id for snapshot_id in snapshot_ids if snapshot_id}))


def _aggregate_snapshot_id(snapshot_ids: tuple[str, ...]) -> str | None:
    if len(snapshot_ids) == 0:
        return None
    if len(snapshot_ids) == 1:
        return snapshot_ids[0]
    digest = sha256(orjson.dumps(snapshot_ids)).hexdigest()
    return f"snapshot-set:sha256:{digest}"
