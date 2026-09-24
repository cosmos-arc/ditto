"""Saved ETF versions cannot be reviewed before their recorded creation."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.etf_allocation_review import (
    ETFAllocationReviewRequest,
    GetETFAllocationReviewQuery,
)
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord


@pytest.mark.pit
def test_future_target_sentinel_and_visible_control() -> None:
    artifact = StrategyArtifactRecord(
        artifact_id="etf-version-1",
        strategy_id="etf-allocation:demo",
        run_id="save-1",
        artifact_type=ArtifactKind.TARGET_PORTFOLIO,
        file_path="inline://etf-version-1",
        metadata={"kind": "etf_allocation", "asof": "2026-09-01"},
        created_at="2026-09-02T09:00:00+00:00",
    )
    artifacts = MagicMock()
    artifacts.get_artifact.return_value = artifact
    accounts = MagicMock()
    accounts.get_paper.side_effect = RuntimeError("visible target reached ledger")
    query = GetETFAllocationReviewQuery(
        artifacts=artifacts,
        accounts=accounts,
        metadata=MagicMock(),
        snapshots=MagicMock(),
        valuation=MagicMock(),
    )

    def request(cutoff: datetime) -> ETFAllocationReviewRequest:
        return ETFAllocationReviewRequest(
            allocation_id="demo",
            version_id="etf-version-1",
            account_kind="paper",
            account_id="paper-a",
            as_of="2026-09-02",
            knowledge_cutoff=cutoff,
            source_snapshot_ids=("price-1",),
        )

    with pytest.raises(AppQueryError, match="ETF target was not yet known"):
        query.get(request(datetime(2026, 9, 2, 8, 59, 59, tzinfo=UTC)))
    with pytest.raises(RuntimeError, match="visible target reached ledger"):
        query.get(request(datetime(2026, 9, 2, 9, 0, tzinfo=UTC)))
