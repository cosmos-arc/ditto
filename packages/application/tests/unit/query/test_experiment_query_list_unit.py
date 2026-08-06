"""Tests for ExperimentQueryFacade.list_experiments — summary projection.

The list view projects only the durable experiment root (no candidate/fold
expansion), so it stays O(experiments) and never touches launch specs. The
facade delegates the raw projection tuple to the analysis reader and maps it
into an application-owned summary read model.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from ditto_analysis.experiments import (
    ExperimentDesiredState,
    ExperimentId,
    ExperimentProjection,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
)
from ditto_application.queries.experiments import (
    ExperimentQueryFacade,
    ExperimentSummaryReadModel,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _projection(
    experiment_id: str = "exp-1",
    *,
    status: ExperimentStatus = ExperimentStatus.RUNNING,
    queue_ordinal: int | None = 2,
) -> ExperimentProjection:
    return ExperimentProjection(
        record=ExperimentRecord(
            experiment_id=ExperimentId(experiment_id),
            status=status,
            desired_state=ExperimentDesiredState.RUN,
            stage=ExperimentStage.PREFLIGHT,
            created_at=_NOW,
        ),
        queue_ordinal=queue_ordinal,
        revision=1,
        updated_at=_NOW,
    )


def test_list_experiments_projects_summaries_in_stored_order() -> None:
    reader = MagicMock()
    reader.list_experiments.return_value = (
        _projection("exp-1", queue_ordinal=2),
        _projection("exp-2", status=ExperimentStatus.COMPLETED, queue_ordinal=None),
    )
    facade = ExperimentQueryFacade(reader=reader)

    result = facade.list_experiments()

    assert result == [
        ExperimentSummaryReadModel(
            experiment_id="exp-1",
            status="running",
            desired_state="run",
            stage="preflight",
            failure_code=None,
            queue_ordinal=2,
            revision=1,
            created_at=_NOW,
            updated_at=_NOW,
        ),
        ExperimentSummaryReadModel(
            experiment_id="exp-2",
            status="completed",
            desired_state="run",
            stage="preflight",
            failure_code=None,
            queue_ordinal=None,
            revision=1,
            created_at=_NOW,
            updated_at=_NOW,
        ),
    ]


def test_list_experiments_empty_when_no_experiments() -> None:
    reader = MagicMock()
    reader.list_experiments.return_value = ()
    facade = ExperimentQueryFacade(reader=reader)

    assert facade.list_experiments() == []
