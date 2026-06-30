"""Auto source selection coordinator for ingestion."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Protocol

from ditto_data.catalog import DataCatalogReader
from ditto_data.catalog.fallback_policy import CatalogSourceFallbackPolicyReader
from ditto_data.models import Dataset
from ditto_data.models.ingestion import IngestionResult
from ditto_kernel.instrument import InstrumentIngestParams

from ditto_application.catalog_freshness import select_ingestion_source
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.source_capability import (
    ensure_source_supported,
)
from ditto_application.source_fallback_policy_effect import (
    SourceFallbackPolicyEffect,
    ensure_source_fallback_policy_effect_executable,
    resolve_active_source_fallback_policy_effect,
    source_fallback_policy_details,
)

__all__ = [
    "AUTO_SOURCE_NAME",
    "AutoSourceIngestionCoordinator",
    "IngestionCoordinatorLike",
]

AUTO_SOURCE_NAME = "auto"
type DateRangeLister = Callable[[str, str, str], list[str]]


@dataclass(frozen=True, slots=True)
class _SourceSelectionDecision:
    source: str
    source_fallback_policy_effect: SourceFallbackPolicyEffect | None = None


class IngestionCoordinatorLike(Protocol):
    """Subset of ingestion coordinator behavior used by apps/process wrappers."""

    def ingest_date(
        self,
        dataset: str,
        trade_date: str,
        force: bool = False,
    ) -> IngestionResult:
        """Ingest one date."""
        ...

    def ingest_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        force: bool = False,
    ) -> list[IngestionResult]:
        """Ingest a date range."""
        ...

    def ingest_by_instrument(
        self,
        dataset: str,
        params: InstrumentIngestParams,
        force: bool = False,
    ) -> IngestionResult:
        """Ingest one instrument range."""
        ...

    def backfill_adj_factor(
        self,
        instrument_id: int,
        start: str,
        end: str,
    ) -> dict[str, object]:
        """Backfill adjustment factors."""
        ...


class AutoSourceIngestionCoordinator:
    """Choose a concrete source coordinator per date-level ingestion request."""

    def __init__(
        self,
        coordinators: Mapping[str, IngestionCoordinatorLike],
        *,
        catalog_reader: DataCatalogReader | None,
        source_fallback_policy_reader: CatalogSourceFallbackPolicyReader | None = None,
        date_range_lister: DateRangeLister | None = None,
        default_source: str = "tushare",
    ) -> None:
        if not coordinators:
            raise AppProcessError(
                "source=auto requires at least one concrete coordinator",
                field="coordinators",
                value=(),
            )
        self._coordinators = {
            source_name.lower(): coordinator
            for source_name, coordinator in coordinators.items()
        }
        self._catalog_reader = catalog_reader
        self._source_fallback_policy_reader = source_fallback_policy_reader
        self._date_range_lister = date_range_lister
        normalized_default_source = default_source.lower()
        self._default_source = (
            normalized_default_source
            if normalized_default_source in self._coordinators
            else next(iter(self._coordinators))
        )

    def ingest_date(
        self,
        dataset: str,
        trade_date: str,
        force: bool = False,
    ) -> IngestionResult:
        """Select source by dataset/date freshness, then delegate ingestion."""
        decision = self._source_decision_for_selection_date(
            dataset,
            trade_date,
        )
        _ensure_selected_source_supported(
            dataset,
            decision.source,
            operation="ingest_date",
            selection_date=trade_date,
            source_fallback_policy_effect=decision.source_fallback_policy_effect,
        )
        coordinator = self._coordinator_for_source(decision.source, decision)
        return coordinator.ingest_date(dataset, trade_date, force)

    def ingest_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        force: bool = False,
    ) -> list[IngestionResult]:
        """Select and delegate source per date when a date lister is available."""
        if self._date_range_lister is None:
            decision = _SourceSelectionDecision(source=self._default_source)
            _ensure_selected_source_supported(
                dataset,
                decision.source,
                operation="ingest_range",
                selection_date=None,
                start_date=start_date,
                end_date=end_date,
                source_fallback_policy_effect=decision.source_fallback_policy_effect,
            )
            coordinator = self._coordinator_for_source(decision.source, decision)
            return coordinator.ingest_range(
                dataset,
                start_date,
                end_date,
                force,
            )
        return [
            self.ingest_date(dataset, trade_date, force)
            for trade_date in self._date_range_lister(dataset, start_date, end_date)
        ]

    def ingest_by_instrument(
        self,
        dataset: str,
        params: InstrumentIngestParams,
        force: bool = False,
    ) -> IngestionResult:
        """Select source by instrument request freshness, then delegate ingestion."""
        trade_dates = self._instrument_trade_dates(dataset, params)
        if len(trade_dates) > 1:
            results = tuple(
                self._ingest_instrument_for_date(
                    dataset,
                    replace(params, start_date=trade_date, end_date=trade_date),
                    force,
                    selection_date=trade_date,
                )
                for trade_date in trade_dates
            )
            return _aggregate_instrument_results(dataset, params, results)

        selection_date = self._selection_date_for_instrument_request(params)
        return self._ingest_instrument_for_date(
            dataset,
            params,
            force,
            selection_date=selection_date,
        )

    def _ingest_instrument_for_date(
        self,
        dataset: str,
        params: InstrumentIngestParams,
        force: bool,
        *,
        selection_date: str | None,
    ) -> IngestionResult:
        decision = self._source_decision_for_selection_date(dataset, selection_date)
        _ensure_selected_source_supported(
            dataset,
            decision.source,
            operation="ingest_by_instrument",
            selection_date=selection_date,
            source_fallback_policy_effect=decision.source_fallback_policy_effect,
        )
        coordinator = self._coordinator_for_source(decision.source, decision)
        return coordinator.ingest_by_instrument(
            dataset,
            params,
            force,
        )

    def _instrument_trade_dates(
        self,
        dataset: str,
        params: InstrumentIngestParams,
    ) -> tuple[str, ...]:
        if self._date_range_lister is None:
            return ()
        if not params.start_date or not params.end_date:
            return ()
        if params.start_date == params.end_date:
            return ()
        return tuple(
            self._date_range_lister(dataset, params.start_date, params.end_date)
        )

    def backfill_adj_factor(
        self,
        instrument_id: int,
        start: str,
        end: str,
    ) -> dict[str, object]:
        """Delegate adj-factor backfill to the default source coordinator."""
        return self._coordinators[self._default_source].backfill_adj_factor(
            instrument_id,
            start,
            end,
        )

    def _source_decision_for_selection_date(
        self,
        dataset: str,
        trade_date: str | None,
    ) -> _SourceSelectionDecision:
        if trade_date is None:
            return _SourceSelectionDecision(source=self._default_source)
        catalog_source = select_ingestion_source(
            dataset=dataset,
            trade_date=trade_date,
            available_sources=tuple(self._coordinators),
            catalog_reader=self._catalog_reader,
        )
        policy_effect = resolve_active_source_fallback_policy_effect(
            self._source_fallback_policy_reader,
            dataset=dataset,
            trade_date=trade_date,
            catalog_selected_source=catalog_source,
        )
        if policy_effect is None:
            return _SourceSelectionDecision(source=catalog_source)
        return _SourceSelectionDecision(
            source=ensure_source_fallback_policy_effect_executable(policy_effect),
            source_fallback_policy_effect=policy_effect,
        )

    def _coordinator_for_source(
        self,
        source: str,
        decision: _SourceSelectionDecision,
    ) -> IngestionCoordinatorLike:
        coordinator = self._coordinators.get(source)
        if coordinator is not None:
            return coordinator
        details: dict[str, object] = {
            "field": "source_name",
            "value": source,
            "supported": sorted(self._coordinators),
        }
        details.update(
            source_fallback_policy_details(decision.source_fallback_policy_effect)
        )
        raise AppProcessError(
            f"Selected source is not configured: {source}",
            details=details,
        )

    @staticmethod
    def _selection_date_for_instrument_request(
        params: InstrumentIngestParams,
    ) -> str | None:
        if params.end_date:
            return params.end_date
        if params.start_date:
            return params.start_date
        return None


def _ensure_selected_source_supported(
    dataset: str,
    source: str,
    *,
    operation: str,
    selection_date: str | None,
    start_date: str | None = None,
    end_date: str | None = None,
    source_fallback_policy_effect: SourceFallbackPolicyEffect | None = None,
) -> None:
    try:
        dataset_enum = Dataset(dataset)
    except ValueError:
        return
    try:
        ensure_source_supported(dataset_enum, source)
    except AppProcessError as exc:
        details = dict(exc.details)
        details["operation"] = operation
        if selection_date is not None:
            details["selection_date"] = selection_date
        if start_date is not None:
            details["start_date"] = start_date
        if end_date is not None:
            details["end_date"] = end_date
        details.update(source_fallback_policy_details(source_fallback_policy_effect))
        raise AppProcessError(str(exc), details=details) from exc


def _aggregate_instrument_results(
    dataset: str,
    params: InstrumentIngestParams,
    results: tuple[IngestionResult, ...],
) -> IngestionResult:
    if not results:
        return IngestionResult(
            dataset=dataset,
            trade_date=params.start_date or params.end_date,
            status="skipped",
            message="instrument range auto-source completed: no dates selected",
        )

    success_count = sum(1 for result in results if result.status == "success")
    failed_count = sum(1 for result in results if result.status == "failed")
    skipped_count = sum(1 for result in results if result.status == "skipped")
    row_counts = tuple(
        result.row_count for result in results if result.row_count is not None
    )
    errors = tuple(result.error for result in results if result.error)
    if failed_count:
        status = "failed"
    elif success_count:
        status = "success"
    else:
        status = "skipped"

    return IngestionResult(
        dataset=dataset,
        trade_date=params.start_date or results[0].trade_date,
        status=status,
        row_count=sum(row_counts) if row_counts else None,
        message=(
            "instrument range auto-source completed: "
            f"success={success_count}, failed={failed_count}, skipped={skipped_count}"
        ),
        error="; ".join(errors) if errors else None,
    )
