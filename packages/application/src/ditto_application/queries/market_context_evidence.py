"""Completed historical snapshot-set adapter for Agent MarketContext evidence."""

from __future__ import annotations

from collections.abc import Mapping

from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.partition_state import PartitionLifecycleReader

from ditto_application.catalog_freshness import (
    aggregate_source_snapshot_ids,
    observed_snapshot_ids,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.evidence_contracts import (
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
    MarketContextEvidenceReadModel,
)
from ditto_application.queries.market_context import (
    MarketContextFacade,
    MarketContextRequest,
    MarketContextView,
)

__all__ = ["MARKET_CONTEXT_DATASETS", "MarketContextEvidenceQueryFacade"]

MARKET_CONTEXT_DATASETS = (
    "commodity_daily",
    "fx_daily",
    "global_index_daily",
    "index_daily",
    "index_weight",
    "macro_indicators",
    "stock_daily",
)
_REQUIRED_DATASETS = frozenset({"index_daily", "stock_daily"})


def _error(code: str, reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"market context evidence failed closed: {reason}",
        details={"code": code, "reason": reason, **details},
    )


def _payload(view: MarketContextView) -> Mapping[str, object]:
    return {
        "as_of": view.as_of,
        "knowledge_cutoff": view.knowledge_cutoff,
        "publication_cutoff": view.publication_cutoff,
        "source_snapshot_set_id": view.source_snapshot_set_id,
        "source_snapshot_ids": view.source_snapshot_ids,
        "status": view.status,
        "feature_set_id": view.feature_set_id,
        "feature_version": view.feature_version,
        "regime_label": view.regime_label,
        "regime_score": view.regime_score,
        "drivers": view.drivers,
        "metrics": view.metrics,
        "impacts": view.impacts,
        "missing_inputs": view.missing_inputs,
        "data_conflicts": view.data_conflicts,
        "uncertainties": view.uncertainties,
        "evidence_refs": view.evidence_refs,
    }


class MarketContextEvidenceQueryFacade:
    """Resolve the observed PIT snapshot set before reading MarketContext."""

    def __init__(
        self,
        *,
        snapshots: ProviderSnapshotReader,
        lifecycle: PartitionLifecycleReader,
        market_context: MarketContextFacade,
    ) -> None:
        self._snapshots = snapshots
        self._lifecycle = lifecycle
        self._market_context = market_context

    def get_evidence(
        self,
        *,
        context: EvidenceTemporalContext,
    ) -> MarketContextEvidenceReadModel:
        """Read a context only when the host identity matches observed history."""
        snapshot_ids = observed_snapshot_ids(
            self._snapshots,
            self._lifecycle,
            dataset_ids=MARKET_CONTEXT_DATASETS,
            knowledge_cutoff=context.knowledge_cutoff,
        )
        dataset_with_snapshot = {
            snapshot.dataset_id
            for snapshot_id in snapshot_ids
            if (snapshot := self._snapshots.get_snapshot(snapshot_id)) is not None
        }
        missing_core = tuple(sorted(_REQUIRED_DATASETS - dataset_with_snapshot))
        if missing_core:
            raise _error(
                "MARKET_CONTEXT_SNAPSHOT_REQUIRED",
                "core_dataset_snapshot_missing",
                missing_datasets=missing_core,
            )
        snapshot_set_id = aggregate_source_snapshot_ids(snapshot_ids)
        if snapshot_set_id is None:
            raise _error(
                "MARKET_CONTEXT_SNAPSHOT_REQUIRED",
                "observed_snapshot_set_empty",
            )
        if snapshot_set_id != context.source_snapshot_id:
            raise _error(
                "MARKET_CONTEXT_SNAPSHOT_MISMATCH",
                "host_snapshot_set_does_not_match_observed_history",
                expected_snapshot_set_id=snapshot_set_id,
                actual_snapshot_set_id=context.source_snapshot_id,
            )
        view = self._market_context.get_context(
            MarketContextRequest(
                as_of=context.decision_time,
                knowledge_cutoff=context.knowledge_cutoff,
                publication_cutoff=context.publication_cutoff,
                source_snapshot_ids=snapshot_ids,
            )
        )
        if (
            view.source_snapshot_ids != snapshot_ids
            or view.source_snapshot_set_id != snapshot_set_id
        ):
            raise _error(
                "MARKET_CONTEXT_PROVENANCE_MISMATCH",
                "market_context_changed_source_snapshot_set",
            )
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value=_payload(view),
        )
        lineage = tuple(
            dict.fromkeys(
                (
                    f"market-context:{view.feature_set_id}",
                    *(f"snapshot:{snapshot_id}" for snapshot_id in snapshot_ids),
                    *view.evidence_refs,
                )
            )
        )
        return MarketContextEvidenceReadModel(
            status=view.status,
            source_snapshot_set_id=snapshot_set_id,
            source_snapshot_ids=snapshot_ids,
            temporal_context=context,
            payload=payload,
            artifact_refs=(),
            lineage=lineage,
        )
