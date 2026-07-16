"""Recover sparse PIT history through full DQ-gated component replay."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from ditto_data.catalog import DataCatalogReader
from ditto_data.models.ingestion import IngestionQualityEvidence, IngestionResult
from ditto_platform.foundation import logger

from ditto_application.catalog_freshness import (
    PersistedIngestionEvidenceVerifier,
    catalog_asof_snapshot,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.sparse_pit import is_sparse_pit_dataset
from ditto_application.processes.ingestion.sparse_recovery_models import (
    SparsePITComponentRecoveryResult,
    SparsePITReattestationRequest,
    SparsePITReattestationResult,
)

__all__ = ["SparsePITIngestionPort", "SparsePITReattestationProcess"]


class SparsePITIngestionPort(Protocol):
    """Date-level ingestion capability consumed by sparse recovery."""

    def ingest_date(
        self,
        dataset: str,
        trade_date: str,
        force: bool = False,
    ) -> IngestionResult:
        """Ingest one dataset component through the normal write path."""
        ...


class SparsePITReattestationProcess:
    """Replay every persisted sparse component and verify durable evidence."""

    def __init__(
        self,
        *,
        ingestion: SparsePITIngestionPort,
        catalog: DataCatalogReader,
        verifier: PersistedIngestionEvidenceVerifier,
    ) -> None:
        self._ingestion = ingestion
        self._catalog = catalog
        self._verifier = verifier

    def run(
        self,
        request: SparsePITReattestationRequest,
    ) -> SparsePITReattestationResult:
        """Force-reingest all components at or before the requested cutoff."""
        request_error = self._request_error(request)
        if request_error is not None:
            return self._failed(request, error=request_error)

        try:
            component_dates = self._component_dates(request)
        except Exception as error:
            logger.exception(
                "Sparse PIT component discovery raised",
                event="sparse_pit_reattest_discovery_error",
                dataset=request.dataset,
                error_type=type(error).__name__,
            )
            return self._failed(
                request,
                error="SPARSE_REATTEST_COMPONENT_DISCOVERY_FAILED",
            )
        if not component_dates:
            return self._failed(request, error="SPARSE_REATTEST_COMPONENTS_MISSING")

        components = tuple(
            self._recover_component(request, trade_date)
            for trade_date in component_dates
        )
        if any(not component.passed for component in components):
            return self._failed(
                request,
                component_dates=component_dates,
                components=components,
                error="SPARSE_REATTEST_COMPONENT_FAILED",
            )

        try:
            snapshot = catalog_asof_snapshot(
                reader=self._catalog,
                dataset=request.dataset,
                source=request.source,
                signal_date=request.signal_date,
            )
            snapshot_verified = snapshot is not None and (
                self._verifier.verify_asof_snapshot(
                    dataset=request.dataset,
                    source=request.source,
                    signal_date=request.signal_date,
                    expected_snapshot_ids=snapshot.source_snapshot_ids,
                    expected_row_count=snapshot.row_count,
                )
            )
        except Exception as error:
            logger.exception(
                "Sparse PIT cumulative evidence verification raised",
                event="sparse_pit_reattest_snapshot_error",
                dataset=request.dataset,
                error_type=type(error).__name__,
            )
            snapshot = None
            snapshot_verified = False
        if snapshot is None or not snapshot_verified:
            return self._failed(
                request,
                component_dates=component_dates,
                components=components,
                error="SPARSE_REATTEST_SNAPSHOT_EVIDENCE_INVALID",
            )

        return SparsePITReattestationResult(
            dataset=request.dataset,
            source=request.source,
            signal_date=request.signal_date,
            passed=True,
            component_dates=component_dates,
            components=components,
            source_snapshot_id=snapshot.source_snapshot_id,
            source_snapshot_ids=snapshot.source_snapshot_ids,
            row_count=snapshot.row_count,
        )

    def _recover_component(
        self,
        request: SparsePITReattestationRequest,
        trade_date: str,
    ) -> SparsePITComponentRecoveryResult:
        try:
            result = self._ingestion.ingest_date(
                request.dataset,
                trade_date,
                force=True,
            )
        except Exception as error:
            logger.exception(
                "Sparse PIT component re-ingestion raised",
                event="sparse_pit_reattest_component_error",
                dataset=request.dataset,
                trade_date=trade_date,
                error_type=type(error).__name__,
            )
            return SparsePITComponentRecoveryResult(
                trade_date=trade_date,
                passed=False,
                error="SPARSE_REATTEST_COMPONENT_EXCEPTION",
            )

        evidence = result.quality_evidence
        evidence_error = self._component_evidence_error(
            result,
            evidence,
            request=request,
            trade_date=trade_date,
        )
        if evidence_error is not None:
            return SparsePITComponentRecoveryResult(
                trade_date=trade_date,
                passed=False,
                error=evidence_error,
            )
        if evidence is None or not isinstance(evidence.checksum, str):
            return SparsePITComponentRecoveryResult(
                trade_date=trade_date,
                passed=False,
                error="SPARSE_REATTEST_COMPONENT_QUALITY_EVIDENCE_INVALID",
            )
        return SparsePITComponentRecoveryResult(
            trade_date=trade_date,
            passed=True,
            checksum=evidence.checksum,
            row_count=evidence.row_count,
        )

    def _component_evidence_error(
        self,
        result: IngestionResult,
        evidence: IngestionQualityEvidence | None,
        *,
        request: SparsePITReattestationRequest,
        trade_date: str,
    ) -> str | None:
        if result.status != "success":
            return result.error or "SPARSE_REATTEST_COMPONENT_INGESTION_FAILED"
        if not (
            evidence is not None
            and evidence.kind == "write_time_l1_l2"
            and evidence.status == "passed"
            and evidence.source == request.source
            and evidence.trade_date == trade_date
            and evidence.levels == ("l1", "l2")
            and isinstance(evidence.checksum, str)
            and bool(evidence.checksum)
            and not isinstance(evidence.row_count, bool)
            and evidence.row_count >= 0
        ):
            return "SPARSE_REATTEST_COMPONENT_QUALITY_EVIDENCE_INVALID"
        try:
            durable = self._verifier.verify_exact_date(
                dataset=request.dataset,
                source=request.source,
                trade_date=trade_date,
                checksum=evidence.checksum,
                row_count=evidence.row_count,
            )
        except Exception as error:
            logger.exception(
                "Sparse PIT component evidence verification raised",
                event="sparse_pit_reattest_component_verification_error",
                dataset=request.dataset,
                trade_date=trade_date,
                error_type=type(error).__name__,
            )
            durable = False
        if not durable:
            return "SPARSE_REATTEST_COMPONENT_DURABLE_EVIDENCE_INVALID"
        return None

    def _component_dates(
        self,
        request: SparsePITReattestationRequest,
    ) -> tuple[str, ...]:
        cutoff = date.fromisoformat(request.signal_date)
        dates: set[date] = set()
        for entry in self._catalog.list_assets():
            if (
                entry.asset.dataset_id != request.dataset
                or entry.source != request.source
            ):
                continue
            if len(entry.asset.partition_keys) != 1:
                msg = "Sparse PIT component must have exactly one partition key"
                raise AppProcessError(msg)
            key = entry.asset.partition_keys[0]
            if not key.startswith("trade_date="):
                msg = "Sparse PIT component partition must be trade_date"
                raise AppProcessError(msg)
            try:
                component_date = date.fromisoformat(key.removeprefix("trade_date="))
            except ValueError as error:
                msg = "Sparse PIT component trade_date partition is invalid"
                raise AppProcessError(msg) from error
            if component_date <= cutoff:
                dates.add(component_date)
        return tuple(item.isoformat() for item in sorted(dates))

    @staticmethod
    def _request_error(request: SparsePITReattestationRequest) -> str | None:
        if not is_sparse_pit_dataset(request.dataset):
            return "SPARSE_REATTEST_DATASET_UNSUPPORTED"
        if not request.source.strip():
            return "SPARSE_REATTEST_SOURCE_REQUIRED"
        if request.source.strip().lower() == "auto":
            return "SPARSE_REATTEST_CONCRETE_SOURCE_REQUIRED"
        try:
            date.fromisoformat(request.signal_date)
        except ValueError:
            return "SPARSE_REATTEST_SIGNAL_DATE_INVALID"
        return None

    @staticmethod
    def _failed(
        request: SparsePITReattestationRequest,
        *,
        error: str,
        component_dates: tuple[str, ...] = (),
        components: tuple[SparsePITComponentRecoveryResult, ...] = (),
    ) -> SparsePITReattestationResult:
        return SparsePITReattestationResult(
            dataset=request.dataset,
            source=request.source,
            signal_date=request.signal_date,
            passed=False,
            component_dates=component_dates,
            components=components,
            error=error,
        )
