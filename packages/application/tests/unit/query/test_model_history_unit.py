"""Model history replay: saved targets only, pinned identity, PIT discipline."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.model_history import (
    GetModelHistoryQuery,
    ModelHistoryRequest,
)
from ditto_application.signal_package_contract import compute_signal_package_checksum
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.query.contracts import PITQueryContext
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_kernel.identity import InstrumentId
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord

_D = Decimal
_STRATEGY_ID = "strategy-model-history"
_KNOWLEDGE = datetime(2026, 3, 5, 16, 0, tzinfo=UTC)
_CREATED_AT = datetime(2026, 3, 2, 2, 0, tzinfo=UTC)
_LATE_CREATED_AT = datetime(2026, 3, 6, 2, 0, tzinfo=UTC)

_FIRST = {"1": 0.6, "2": 0.4}
_SECOND = {"1": 1.0}


class _ArtifactReader:
    def __init__(self, records: list[StrategyArtifactRecord]):
        self.records = records

    def list_by_strategy(self, strategy_id: str) -> tuple[StrategyArtifactRecord, ...]:
        return tuple(
            record for record in self.records if record.strategy_id == strategy_id
        )


class _SnapshotReader:
    def __init__(
        self,
        snapshot: ProviderSnapshot,
        *,
        expected_id: str | None = None,
    ):
        self._snapshot = snapshot
        self._expected_id = expected_id or snapshot.snapshot_id

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return self._snapshot if snapshot_id == self._expected_id else None

    def get_observed_at(self, snapshot_id: str) -> datetime | None:
        del snapshot_id
        return None

    def get_predecessor(self, snapshot_id: str) -> str | None:
        del snapshot_id
        return None

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        del dataset_id, source, canonical_asset
        return ()


class _ValuationSource:
    def __init__(self, bars: dict[int, tuple[TechnicalBar, ...]]):
        self._bars = bars
        self.contexts: list[PITQueryContext] = []

    def load(
        self,
        context: PITQueryContext,
        *,
        instrument_id: InstrumentId,
        instrument_code: str,
    ) -> tuple[TechnicalBar, ...]:
        self.contexts.append(context)
        assert instrument_code == str(instrument_id)
        return self._bars.get(int(instrument_id), ())


def _bar(day: str, close: float) -> TechnicalBar:
    occurred = datetime.fromisoformat(f"{day}T07:00:00+00:00")
    published = datetime.fromisoformat(f"{day}T10:00:00+00:00")
    return TechnicalBar(
        occurred_at=occurred,
        knowledge_at=published,
        publication_at=published,
        source_snapshot_id=_SNAPSHOT_ID,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
        turnover=close * 1000.0,
        adjustment_factor=1.0,
        suspended=False,
    )


def _snapshot(*, created_at: datetime | None = None) -> ProviderSnapshot:
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="model-history-fixture",
            request_start="2026-03-02",
            request_end="2026-03-05",
            schema_version="market.stock_daily.v1",
            checksum="sha256:model-history-bars",
            canonical_asset=DataAssetRef("stock_daily", "market"),
            request_parameters_hash="sha256:params",
            response_metadata=(("rows", "6"),),
            license_record_id="license:fixture",
            row_count=6,
            payload_uri="file:///tmp/model-history-bars.parquet",
            payload_retained=True,
            created_at=created_at or _CREATED_AT,
        )
    )


_SNAPSHOT = _snapshot()
_SNAPSHOT_ID = _SNAPSHOT.snapshot_id


def _artifact(
    artifact_id: str,
    signal_date: str,
    weights: dict[str, float],
    *,
    status: str = "active",
    created_at: datetime | None = None,
    tamper: bool = False,
    origin_version_id: str | None = None,
) -> StrategyArtifactRecord:
    payload: dict[str, object] = {
        "dataset_snapshot_ids": {"stock_daily": _SNAPSHOT_ID},
        "factor_ids": [],
        "factor_values": {},
        "intents": [],
        "risk_flags": [],
        "selection_reasons": {
            key: {"target_weight": weight} for key, weight in weights.items()
        },
        "signal_date": signal_date,
        "strategy_id": _STRATEGY_ID,
        "strategy_version": "1",
    }
    if origin_version_id is not None:
        payload["origin_version_id"] = origin_version_id
    checksum = compute_signal_package_checksum(payload)
    if tamper:
        checksum = "sha256:" + "0" * 64
    return StrategyArtifactRecord(
        artifact_id=artifact_id,
        strategy_id=_STRATEGY_ID,
        run_id=f"eod-{signal_date}-{_STRATEGY_ID}-1",
        artifact_type=ArtifactKind.SIGNAL_PACKAGE,
        file_path=f"evidence/{artifact_id}.json",
        metadata={
            **payload,
            "schema_version": "1.0",
            "business_payload": payload,
            "batch_key": f"eod-{signal_date}-{_STRATEGY_ID}-1",
            "checksum": checksum,
            "no_rebalance": True,
            "outcome": "no_rebalance",
        },
        status=status,
        created_at=(created_at or _CREATED_AT).isoformat(),
    )


_BARS: dict[int, tuple[TechnicalBar, ...]] = {
    1: (
        _bar("2026-03-02", 10.0),
        _bar("2026-03-03", 11.0),
        _bar("2026-03-04", 12.1),
    ),
    2: (
        _bar("2026-03-02", 20.0),
        _bar("2026-03-03", 22.0),
        _bar("2026-03-04", 20.0),
    ),
}


def _query(
    records: list[StrategyArtifactRecord],
    *,
    snapshot: ProviderSnapshot | None = None,
    bars: dict[int, tuple[TechnicalBar, ...]] | None = None,
) -> GetModelHistoryQuery:
    return GetModelHistoryQuery(
        artifact_reader=_ArtifactReader(records),
        snapshot_reader=_SnapshotReader(snapshot or _SNAPSHOT),
        valuation_source=_ValuationSource(bars or _BARS),
    )


def _request(
    *,
    artifact_ids: tuple[str, ...] = (),
    initial_capital: str = "100",
    start_date: str = "2026-03-02",
    end_date: str = "2026-03-04",
    origin_version_id: str | None = None,
) -> ModelHistoryRequest:
    return ModelHistoryRequest(
        strategy_id=_STRATEGY_ID,
        start_date=start_date,
        end_date=end_date,
        initial_capital=_D(initial_capital),
        knowledge_cutoff=_KNOWLEDGE,
        publication_cutoff=_KNOWLEDGE,
        artifact_ids=artifact_ids,
        origin_version_id=origin_version_id,
    )


def test_version_bound_history_excludes_other_saved_targets() -> None:
    records = [
        _artifact("version-a", "2026-03-02", _FIRST, origin_version_id="etf-v1"),
        _artifact("version-b", "2026-03-03", _SECOND, origin_version_id="etf-v2"),
    ]
    view = _query(records).history(_request(origin_version_id="etf-v1"))
    assert [target.artifact_id for target in view.targets] == ["version-a"]
    with pytest.raises(AppQueryError):
        _query(records).history(
            _request(artifact_ids=("version-b",), origin_version_id="etf-v1")
        )


def _base_records() -> list[StrategyArtifactRecord]:
    return [
        _artifact("model-a", "2026-03-02", _FIRST),
        _artifact("model-b", "2026-03-03", _SECOND),
    ]


def test_replays_saved_targets_with_drift_between_rebalances() -> None:
    view = _query(_base_records()).history(_request())
    values = [point.total_value for point in view.points]
    # 03-02: 60@10 + 40@20 = 100; 03-03 rebalance at 110; 03-04 drift 10@12.1.
    assert values == [_D("100.00"), _D("110.00"), _D("121.00")]
    assert [point.period_return for point in view.points][1:] == [
        _D("0.1"),
        _D("121") / _D("110") - _D("1"),
    ]
    assert view.segments[0].linked_return == _D("1.1") * (_D("121") / _D("110")) - _D(
        "1"
    )
    assert all(point.external_flow == _D("0") for point in view.points)
    assert [(target.signal_date, target.artifact_id) for target in view.targets] == [
        ("2026-03-02", "model-a"),
        ("2026-03-03", "model-b"),
    ]
    assert view.method == "twr-linked-v1"
    assert view.valuation_policy_version == "account-valuation-stale-evidence-v1"
    assert view.initial_capital == _D("100.00")
    assert view.empty_reason is None
    assert view.result_id.startswith("model-history:sha256:")


def test_same_date_active_packages_are_rejected_as_ambiguous() -> None:
    records = [
        _artifact("model-a", "2026-03-02", _FIRST),
        _artifact("model-b1", "2026-03-03", _SECOND),
        _artifact("model-b2", "2026-03-03", {"1": 0.5, "2": 0.5}),
    ]
    with pytest.raises(AppQueryError) as error:
        _query(records).history(_request())
    assert error.value.details["code"] == "MODEL_HISTORY_ARTIFACT_DATE_AMBIGUOUS"


def test_rounded_targets_exceeding_capital_fail_closed() -> None:
    # 0.01 capital with two 0.5 weights rounds both targets to 0.01,
    # leaving negative cash — an invalid target, not a partial replay.
    records = [_artifact("model-a", "2026-03-02", {"1": 0.5, "2": 0.5})]
    with pytest.raises(AppQueryError) as error:
        _query(records).history(_request(initial_capital="0.01"))
    assert error.value.details["code"] == "MODEL_HISTORY_TARGET_INVALID"


def test_rebalance_day_missing_target_price_defers_as_gap() -> None:
    # Instrument 1 stops trading after 03-02 with no resumption evidence;
    # the 03-03 target switch cannot price, so both later days defer as
    # explicit gaps instead of failing the whole replay.
    bars = {
        1: (_bar("2026-03-02", 10.0),),
        2: (
            _bar("2026-03-02", 20.0),
            _bar("2026-03-03", 22.0),
            _bar("2026-03-04", 24.0),
        ),
    }
    view = _query(_base_records(), bars=bars).history(_request())
    by_date = {point.on_date: point for point in view.points}
    assert by_date["2026-03-02"].total_value == _D("100.00")
    assert by_date["2026-03-03"].total_value is None
    assert by_date["2026-03-04"].total_value is None
    assert "price_missing" in {mark.code for mark in by_date["2026-03-03"].quality}


def test_pinned_artifacts_survive_future_supersession() -> None:
    records = _base_records()
    query = _query(records)
    before = query.history(_request())

    # A later publish supersedes the 03-03 target; the old artifact stays
    # readable and the pinned replay must not change.
    records[:] = [
        records[0],
        _artifact("model-b", "2026-03-03", _SECOND, status="archived"),
        _artifact("model-c", "2026-03-03", {"1": 0.5, "2": 0.5}),
    ]
    pinned = query.history(
        _request(artifact_ids=("model-a", "model-b")),
    )
    assert pinned.result_id == before.result_id
    assert pinned.points[2].total_value == _D("121.00")

    fresh = query.history(_request())
    assert fresh.result_id != before.result_id
    assert [t.artifact_id for t in fresh.targets] == ["model-a", "model-c"]
    # 03-03: 55@11 + 55@22 = 110; 03-04: 5@12.1 + 2.5@20 = 110.50.
    assert fresh.points[2].total_value == _D("110.50")


def test_days_before_the_first_saved_target_leave_explicit_gaps() -> None:
    records = [_artifact("model-b", "2026-03-03", _SECOND)]
    view = _query(records).history(_request())
    by_date = {point.on_date: point for point in view.points}
    assert by_date["2026-03-02"].total_value is None
    assert "target_missing" in {mark.code for mark in by_date["2026-03-02"].quality}
    assert by_date["2026-03-02"].period_return is None
    assert by_date["2026-03-03"].total_value == _D("100.00")
    assert by_date["2026-03-03"].period_return is None


def test_range_without_visible_packages_reports_missing_targets() -> None:
    records = [_artifact("model-early", "2026-03-01", _FIRST)]
    view = _query(records).history(_request())
    # Prices load only through package-declared snapshots: with no resolved
    # target there is nothing to value, and no day is fabricated.
    assert view.targets == ()
    assert view.segments == ()
    assert view.points == ()
    assert view.empty_reason == "no_visible_targets"


def test_unknown_strategy_is_rejected() -> None:
    with pytest.raises(AppQueryError) as error:
        _query([]).history(_request())
    assert error.value.details["code"] == "MODEL_HISTORY_STRATEGY_NOT_FOUND"


def test_pinned_artifact_must_exist_for_the_strategy() -> None:
    with pytest.raises(AppQueryError) as error:
        _query(_base_records()).history(_request(artifact_ids=("model-ghost",)))
    assert error.value.details["code"] == "MODEL_HISTORY_ARTIFACT_NOT_FOUND"


def test_pinned_artifact_must_stay_inside_the_range() -> None:
    with pytest.raises(AppQueryError) as error:
        _query(_base_records()).history(
            _request(
                start_date="2026-03-03",
                end_date="2026-03-04",
                artifact_ids=("model-a",),
            )
        )
    assert error.value.details["code"] == "MODEL_HISTORY_ARTIFACT_DATE_OUT_OF_RANGE"


def test_declared_snapshot_must_exist() -> None:
    missing = _SnapshotReader(_snapshot(), expected_id="snapshot:absent")
    query = GetModelHistoryQuery(
        artifact_reader=_ArtifactReader(_base_records()),
        snapshot_reader=missing,
        valuation_source=_ValuationSource(_BARS),
    )
    with pytest.raises(AppQueryError) as error:
        query.history(_request())
    assert error.value.details["code"] == "MODEL_HISTORY_SOURCE_SNAPSHOT_NOT_FOUND"


def test_package_snapshot_after_knowledge_cutoff_is_rejected() -> None:
    late = _snapshot(created_at=_LATE_CREATED_AT)
    late_id = late.snapshot_id
    records = [_artifact("model-a", "2026-03-02", _FIRST)]
    # Point the package at a snapshot created after the knowledge cutoff.
    for record in records:
        payload = cast(dict[str, object], record.metadata["business_payload"])
        payload["dataset_snapshot_ids"] = {"stock_daily": late_id}
        record.metadata["dataset_snapshot_ids"] = {"stock_daily": late_id}
        record.metadata["business_payload"] = payload
        record.metadata["checksum"] = compute_signal_package_checksum(payload)
    query = GetModelHistoryQuery(
        artifact_reader=_ArtifactReader(records),
        snapshot_reader=_SnapshotReader(late),
        valuation_source=_ValuationSource(_BARS),
    )
    with pytest.raises(AppQueryError) as error:
        query.history(_request())
    assert error.value.details["code"] == "MODEL_HISTORY_SOURCE_SNAPSHOT_FUTURE"


def test_future_published_package_is_invisible_to_fresh_resolution() -> None:
    records = [
        _artifact("model-a", "2026-03-02", _FIRST),
        _artifact("model-b", "2026-03-03", _SECOND, created_at=_LATE_CREATED_AT),
    ]
    view = _query(records).history(_request())
    assert [target.artifact_id for target in view.targets] == ["model-a"]
    # Only the 03-02 target is effective: 6@11 + 2@22 = 110, then drift.
    assert [point.total_value for point in view.points] == [
        _D("100.00"),
        _D("110.00"),
        _D("112.60"),
    ]


def test_weights_exceeding_one_are_rejected() -> None:
    records = [_artifact("model-a", "2026-03-02", {"1": 0.9, "2": 0.9})]
    with pytest.raises(AppQueryError) as error:
        _query(records).history(_request())
    assert error.value.details["code"] == "MODEL_HISTORY_TARGET_INVALID"


def test_tampered_package_checksum_is_rejected() -> None:
    records = [_artifact("model-a", "2026-03-02", _FIRST, tamper=True)]
    with pytest.raises(AppQueryError) as error:
        _query(records).history(_request())
    assert error.value.details["code"] == "MODEL_HISTORY_ARTIFACT_INTEGRITY_INVALID"


def test_result_identity_binds_capital_and_targets() -> None:
    records = _base_records()
    query = _query(records)
    first = query.history(_request())
    replay = query.history(_request())
    double_capital = query.history(_request(initial_capital="200"))
    assert first.result_id == replay.result_id
    assert double_capital.result_id != first.result_id
    assert double_capital.points[0].total_value == _D("200.00")


def test_non_positive_initial_capital_is_rejected() -> None:
    with pytest.raises(AppQueryError) as error:
        _query(_base_records()).history(_request(initial_capital="0"))
    assert error.value.details["code"] == "MODEL_HISTORY_REQUEST_INVALID"
