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
from ditto_kernel.identity import InstrumentId
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord


@pytest.mark.pit
def test_future_target_sentinel_and_visible_control() -> None:
    artifact = StrategyArtifactRecord(
        artifact_id="etf-version-1",
        strategy_id="etf-allocation:demo",
        run_id="save-1",
        artifact_type=ArtifactKind.TARGET_PORTFOLIO,
        file_path="inline://etf-version-1",
        metadata={
            "kind": "etf_allocation",
            "asof": "2026-09-01",
            "knowledge_cutoff": "2026-09-01T09:00:00Z",
        },
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
def test_cutoff_before_saved_evidence_cutoff_fails_closed() -> None:
    # The save path permits a knowledge_cutoff later than created_at; a
    # review cutoff between the two must not expose those future-derived
    # weights even though the version itself already exists.
    artifact = StrategyArtifactRecord(
        artifact_id="etf-version-2",
        strategy_id="etf-allocation:demo",
        run_id="save-2",
        artifact_type=ArtifactKind.TARGET_PORTFOLIO,
        file_path="inline://etf-version-2",
        metadata={
            "kind": "etf_allocation",
            "asof": "2026-09-01",
            "knowledge_cutoff": "2026-09-01T09:00:00Z",
        },
        created_at="2026-09-01T08:00:00+00:00",
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
            version_id="etf-version-2",
            account_kind="paper",
            account_id="paper-a",
            as_of="2026-09-02",
            knowledge_cutoff=cutoff,
            source_snapshot_ids=("price-1",),
        )

    with pytest.raises(AppQueryError, match="ETF target was not yet known"):
        query.get(request(datetime(2026, 9, 1, 8, 30, tzinfo=UTC)))
    with pytest.raises(RuntimeError, match="visible target reached ledger"):
        query.get(request(datetime(2026, 9, 1, 9, 0, tzinfo=UTC)))


@pytest.mark.pit
def test_unreadable_saved_cutoff_fails_closed() -> None:
    artifact = StrategyArtifactRecord(
        artifact_id="etf-version-3",
        strategy_id="etf-allocation:demo",
        run_id="save-3",
        artifact_type=ArtifactKind.TARGET_PORTFOLIO,
        file_path="inline://etf-version-3",
        metadata={"kind": "etf_allocation", "asof": "2026-09-01"},
        created_at="2026-09-01T08:00:00+00:00",
    )
    artifacts = MagicMock()
    artifacts.get_artifact.return_value = artifact
    query = GetETFAllocationReviewQuery(
        artifacts=artifacts,
        accounts=MagicMock(),
        metadata=MagicMock(),
        snapshots=MagicMock(),
        valuation=MagicMock(),
    )
    request = ETFAllocationReviewRequest(
        allocation_id="demo",
        version_id="etf-version-3",
        account_kind="paper",
        account_id="paper-a",
        as_of="2026-09-02",
        knowledge_cutoff=datetime(2026, 9, 2, 9, 0, tzinfo=UTC),
        source_snapshot_ids=("price-1",),
    )
    with pytest.raises(AppQueryError, match="saved ETF knowledge cutoff"):
        query.get(request)


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


@pytest.mark.pit
def test_zero_weight_target_without_price_or_holding_does_not_fail_review() -> None:
    """An unused zero-weight ETF needs no price of its own."""
    from decimal import Decimal

    from ditto_features.technical_analysis.contracts import TechnicalBar

    cutoff = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    artifact = StrategyArtifactRecord(
        artifact_id="etf-version-zero",
        strategy_id="etf-allocation:demo",
        run_id="save-zero",
        artifact_type=ArtifactKind.TARGET_PORTFOLIO,
        file_path="inline://etf-version-zero",
        metadata={
            "kind": "etf_allocation",
            "asof": "2026-09-01",
            "knowledge_cutoff": "2026-09-01T09:00:00Z",
            "weights": {"2000001": "0.8", "2000002": "0"},
            "cash_weight": "0.2",
            "tracking_exposure": {},
        },
        created_at="2026-09-01T08:00:00+00:00",
    )
    artifacts = MagicMock()
    artifacts.get_artifact.return_value = artifact
    account_snapshot = SimpleNamespace(
        account_id="paper-a",
        as_of="2026-09-02",
        currency="CNY",
        cash=SimpleNamespace(total=Decimal("100000")),
        total_value=Decimal("100000"),
        positions=(),
        valuation_complete=True,
        ledger_hash="account-ledger:sha256:paper-a",
    )
    accounts = MagicMock()
    accounts.get_paper.return_value = SimpleNamespace(snapshot=account_snapshot)
    snapshots = MagicMock()
    snapshots.get_snapshot.return_value = SimpleNamespace(
        snapshot_id="price-1",
        dataset_id="stock_daily",
        schema_version="1",
        source="tushare",
        created_at=datetime(2026, 9, 2, 8, 0, tzinfo=UTC),
    )
    metadata = MagicMock()
    metadata.get_source_ticker.return_value = "600519.SH"
    loaded_ids: list[InstrumentId] = []

    def load(
        _context: object, *, instrument_id: InstrumentId, instrument_code: str
    ) -> tuple[TechnicalBar, ...]:
        loaded_ids.append(instrument_id)
        assert instrument_code == "600519.SH"
        return (
            TechnicalBar(
                occurred_at=datetime(2026, 9, 1, 7, 0, tzinfo=UTC),
                knowledge_at=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
                publication_at=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
                source_snapshot_id="price-1",
                open=99.0,
                high=101.0,
                low=98.0,
                close=100.0,
                volume=1000.0,
                turnover=100_000.0,
                adjustment_factor=1.0,
                suspended=False,
            ),
        )

    query = GetETFAllocationReviewQuery(
        artifacts=artifacts,
        accounts=accounts,
        metadata=metadata,
        snapshots=snapshots,
        valuation=SimpleNamespace(load=load),
    )
    view = query.get(
        ETFAllocationReviewRequest(
            allocation_id="demo",
            version_id="etf-version-zero",
            account_kind="paper",
            account_id="paper-a",
            as_of="2026-09-02",
            knowledge_cutoff=cutoff,
            source_snapshot_ids=("price-1",),
        )
    )
    # Only the positive-weight instrument was priced; the zero-weight ETF did
    # not force a missing-price failure.
    assert loaded_ids == [InstrumentId(2000001)]
    assert [position.instrument_id for position in view.target.positions] == [2000001]
    assert view.actual.cash == Decimal("100000")
    assert view.knowledge_cutoff == cutoff.isoformat()
