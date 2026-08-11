"""PIT-safe return risk estimation contract tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest
from ditto_features.risk_estimation.covariance import (
    ReturnMatrixRequest,
    RiskEstimationError,
    RiskEstimationEvidence,
    ShrinkageCovarianceEstimator,
)


def _returns_frame(*, include_visible_boundary: bool = True) -> pl.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    observation_count = 60 if include_visible_boundary else 59
    for offset in range(observation_count):
        observed = start + timedelta(days=offset)
        for instrument_id, scale in ((1, 0.01), (2, 0.02)):
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "observation_time": observed,
                    "knowledge_time": observed + timedelta(hours=1),
                    "publication_time": observed + timedelta(minutes=30),
                    "source_snapshot_id": "snap-visible",
                    "return": scale * (((offset % 7) - 3) / 3),
                }
            )
    return pl.DataFrame(rows)


def _evidence() -> RiskEstimationEvidence:
    return RiskEstimationEvidence(
        decision_time=datetime(2026, 4, 1, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 3, 31, 23, 0, tzinfo=UTC),
        publication_cutoff=datetime(2026, 3, 31, 23, 0, tzinfo=UTC),
        source_snapshot_ids=("snap-visible",),
    )


@pytest.mark.pit
def test_future_sentinel_is_excluded_and_visible_boundary_is_consumed() -> None:
    estimator = ShrinkageCovarianceEstimator()
    visible = _returns_frame()
    sentinel_time = datetime(2026, 3, 1, tzinfo=UTC)
    future = pl.DataFrame(
        {
            "instrument_id": [1, 2],
            "observation_time": [sentinel_time, sentinel_time],
            "knowledge_time": [
                datetime(2026, 4, 2, tzinfo=UTC),
                datetime(2026, 4, 2, tzinfo=UTC),
            ],
            "publication_time": [
                datetime(2026, 4, 2, tzinfo=UTC),
                datetime(2026, 4, 2, tzinfo=UTC),
            ],
            "source_snapshot_id": ["snap-visible", "snap-visible"],
            "return": [99.0, -99.0],
        }
    )
    request = ReturnMatrixRequest(
        frame=visible,
        instrument_ids=(1, 2),
        evidence=_evidence(),
    )
    with_future = ReturnMatrixRequest(
        frame=pl.concat((visible, future)),
        instrument_ids=(1, 2),
        evidence=_evidence(),
    )

    expected = estimator.estimate(request)
    actual = estimator.estimate(with_future)

    assert actual.observation_count == 60
    assert actual.instrument_ids == (1, 2)
    np.testing.assert_allclose(actual.covariance, expected.covariance)
    assert np.linalg.eigvalsh(actual.covariance).min() >= -1e-12

    with pytest.raises(RiskEstimationError, match="at least 60"):
        estimator.estimate(
            ReturnMatrixRequest(
                frame=_returns_frame(include_visible_boundary=False),
                instrument_ids=(1, 2),
                evidence=_evidence(),
            )
        )


def test_missing_snapshot_evidence_fails_closed() -> None:
    with pytest.raises(RiskEstimationError, match="source_snapshot_ids"):
        RiskEstimationEvidence(
            decision_time=datetime(2026, 4, 1, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 3, 31, tzinfo=UTC),
            publication_cutoff=datetime(2026, 3, 31, tzinfo=UTC),
            source_snapshot_ids=(),
        )


def test_singular_covariance_repair_is_explicit_in_evidence() -> None:
    frame = _returns_frame().with_columns(pl.lit(0.0).alias("return"))

    result = ShrinkageCovarianceEstimator().estimate(
        ReturnMatrixRequest(
            frame=frame,
            instrument_ids=(1, 2),
            evidence=_evidence(),
        )
    )

    assert result.covariance_repaired is True
    assert np.linalg.eigvalsh(result.covariance).min() >= 1e-12
