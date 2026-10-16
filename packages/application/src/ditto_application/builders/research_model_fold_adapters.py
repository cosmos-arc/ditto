"""Indexed production adapters for model-candidate fold execution (#565 W2)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import date
from io import BytesIO
from typing import cast

import polars as pl
from ditto_analysis.experiments import LeaseFence
from ditto_analysis.research.artifact_service import ResearchArtifactService

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._worker_contract import (
    ResearchWorkerCoordinator,
)
from ditto_application.processes.experiments.model_candidate_folds import (
    ModelFoldData,
    ModelFoldInputBinding,
    ModelFoldInputSet,
)

__all__ = [
    "CoordinatorBackedModelFoldPublicationAuthority",
    "IndexedModelFoldDataPort",
    "IndexedPredictionFrameInputSink",
]

_CALENDAR_COLUMNS = frozenset({"trade_date", "is_open", "source_snapshot_id"})


def _adapter_error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "model fold production adapter failed closed",
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
            **details,
        },
    )


def _load_input_bytes(
    artifacts: ResearchArtifactService,
    binding: ModelFoldInputBinding,
) -> bytes:
    payload = artifacts.read_frozen_research_input_bytes(binding.input_id)
    if hashlib.sha256(payload).hexdigest() != binding.content_hash:
        raise _adapter_error(
            "model_fold_input_content_drift",
            input_id=binding.input_id,
        )
    return payload


class IndexedModelFoldDataPort:
    """Load the three frozen training frames from the indexed artifact store."""

    def __init__(self, *, artifact_service: ResearchArtifactService) -> None:
        self._artifacts = artifact_service

    def load(self, inputs: ModelFoldInputSet) -> ModelFoldData:
        """Return verified frames or refuse with an explicit typed error."""
        label_prices = pl.read_parquet(
            BytesIO(
                _load_input_bytes(self._artifacts, inputs.label_prices),
            )
        )
        feature_frame = pl.read_parquet(
            BytesIO(_load_input_bytes(self._artifacts, inputs.feature_frame))
        )
        calendar = pl.read_parquet(
            BytesIO(_load_input_bytes(self._artifacts, inputs.calendar))
        )
        if not _CALENDAR_COLUMNS.issubset(set(calendar.columns)):
            raise _adapter_error(
                "model_fold_calendar_columns_invalid",
                columns=sorted(calendar.columns),
            )
        sessions = tuple(
            calendar.filter(pl.col("is_open"))
            .sort("trade_date")
            .get_column("trade_date")
            .to_list()
        )
        if not sessions or any(
            type(item) is not date for item in sessions
        ):  # pragma: no cover - parquet contract keeps the column typed
            raise _adapter_error("model_fold_calendar_sessions_invalid")
        return ModelFoldData(
            feature_frame=feature_frame,
            label_prices=label_prices,
            trading_sessions=cast("tuple[date, ...]", sessions),
        )


class IndexedPredictionFrameInputSink:
    """Register frozen prediction frames in the indexed research input store."""

    def __init__(self, *, artifact_service: ResearchArtifactService) -> None:
        self._artifacts = artifact_service

    def register_prediction_frame(self, input_id: str, frame_bytes: bytes) -> None:
        """Publish immutable frame bytes; byte-equal replay is idempotent."""
        self._artifacts.publish_frozen_research_input(input_id, frame_bytes)


class CoordinatorBackedModelFoldPublicationAuthority:
    """Expose the worker coordinator lease window to model publication."""

    def __init__(self, coordinator: ResearchWorkerCoordinator) -> None:
        self._coordinator = coordinator

    def publish_fold_artifacts(
        self,
        callback: Callable[[LeaseFence, int], object],
    ) -> object:
        """Run one lease-fenced publication callback and return its value."""
        return self._coordinator.publish_attempt_artifact(callback)
