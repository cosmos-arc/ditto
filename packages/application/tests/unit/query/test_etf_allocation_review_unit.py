"""Saved ETF versions cannot be reviewed before their recorded creation."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.etf_allocation_review import (
    ETFAllocationReviewRequest,
    GetETFAllocationReviewQuery,
    _actual_indexes,
)
from ditto_application.queries.etf_candidates import _validate_cutoff
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


@pytest.mark.pit
def test_same_day_index_uses_saved_canonical_cutoff_and_later_date_is_unknown() -> None:
    metadata = MagicMock()

    def candidates(*, asof: str, cutoff: str, source_snapshot_id: str) -> list[object]:
        assert asof == "2026-09-01"
        assert _validate_cutoff(cutoff) == datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
        assert source_snapshot_id == "etf-reference-1"
        return [
            SimpleNamespace(
                instrument_id=1,
                fields={"tracking_index": SimpleNamespace(value="000300.SH")},
            )
        ]

    metadata.list_etf_candidates.side_effect = candidates
    saved = {
        "asof": "2026-09-01",
        "knowledge_cutoff": "2026-09-01T09:00:00Z",
        "source_snapshot_id": "etf-reference-1",
    }
    assert _actual_indexes(metadata, saved, "2026-09-01") == {1: "000300.SH"}
    assert _actual_indexes(metadata, saved, "2026-09-02") == {}
