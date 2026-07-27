"""Tests for the indexed R3 backtest-report artifact adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentConflictError, ExperimentIntegrityError
from ditto_analysis.experiments import (
    ArtifactRecord,
    AttemptId,
    BacktestRunId,
    CandidateId,
    ContentHash,
    DateWindow,
    ExperimentId,
    FoldId,
    LeaseFence,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_application.processes.experiments._report_evidence import (
    BACKTEST_REPORT_ARTIFACT_KIND,
    BacktestReportArtifactIdentity,
    BacktestReportEvidence,
)
from ditto_backtest.statistics import (
    BacktestReport,
    empty_aggregated_trade_statistics,
    empty_alpha_statistics,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting import FillEvent

NOW = datetime(2026, 1, 3, 4, 5, 6, 789012, tzinfo=UTC)
NOW_US = 1_767_412_306_789_012
EXPERIMENT_ID = ExperimentId("experiment-1")
CANDIDATE_ID = CandidateId("candidate-1")
FOLD_ID = FoldId("fold-1")
ATTEMPT_ID = AttemptId("attempt-1")
RUN_ID = BacktestRunId("run-report-1")
FINGERPRINT = ContentHash("a" * 64)
WINDOW = DateWindow(date(2026, 1, 1), date(2026, 1, 2))
FENCE = LeaseFence(
    experiment_id=EXPERIMENT_ID,
    owner_token="worker-1",
    revision=3,
    lease_until_epoch_us=NOW_US + 1_000,
)


class _InjectedIndexFailure(RuntimeError):
    """Simulate one crash after immutable files land but before index commit."""


class _DateTime(datetime):
    """Prove persisted durable timestamps also require exact datetimes."""


class _MemoryArtifactIndex:
    """Minimal immutable index used only with a tmp_path artifact root."""

    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root.resolve()
        self.records: dict[str, ArtifactRecord] = {}
        self.add_attempts = 0
        self.fail_next_add = False

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.records.get(artifact_id)

    def get_artifact_by_relative_path(
        self,
        relative_path: str,
    ) -> ArtifactRecord | None:
        return next(
            (
                record
                for record in self.records.values()
                if record.relative_path == relative_path
            ),
            None,
        )

    def add_artifact(
        self,
        record: ArtifactRecord,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        commit_guard: Callable[[], None],
    ) -> None:
        _ = (lease_fence, now_epoch_us)
        commit_guard()
        self.add_attempts += 1
        if self.fail_next_add:
            self.fail_next_add = False
            raise _InjectedIndexFailure("injected failure before index add")
        matches = tuple(
            item
            for item in self.records.values()
            if item.artifact_id == record.artifact_id
            or item.relative_path == record.relative_path
        )
        if not matches:
            self.records[record.artifact_id] = record
            return
        existing = matches[0]
        if replace(existing, is_pinned=False, pinned_at=None, revision=0) != record:
            raise ExperimentConflictError(
                "artifact replay drift",
                details={"reason_code": "artifact_replay_drift"},
            )

    def pin_artifact(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: datetime,
        commit_guard: Callable[[], None],
    ) -> ArtifactRecord:
        _ = (artifact_id, expected_revision, pinned_at, commit_guard)
        raise AssertionError("pin is outside this adapter boundary")


def _identity(
    *,
    attempt_created_at: datetime = NOW,
) -> BacktestReportArtifactIdentity:
    return BacktestReportArtifactIdentity(
        experiment_id=EXPERIMENT_ID,
        candidate_id=CANDIDATE_ID,
        fold_id=FOLD_ID,
        attempt_id=ATTEMPT_ID,
        attempt_created_at=attempt_created_at,
        run_id=RUN_ID,
        test_window=WINDOW,
        reproduction_fingerprint=FINGERPRINT,
    )


def _report(*, final_nav: float = 101_000.0) -> BacktestReport:
    return BacktestReport(
        run_id=str(RUN_ID),
        period=(WINDOW.start.isoformat(), WINDOW.end.isoformat()),
        initial_cash=100_000.0,
        final_nav=final_nav,
        trade_stats=(),
        portfolio_stats=(),
        aggregated_trade_stats=empty_aggregated_trade_statistics(),
        alpha_stats=empty_alpha_statistics(),
        nav_series=(
            (WINDOW.start.isoformat(), 100_000.0),
            (WINDOW.end.isoformat(), final_nav),
        ),
        trade_log=(),
        fill_log=(
            FillEvent(
                fill_id="fill-1",
                order_id="order-1",
                instrument_id=InstrumentId(2_000_001),
                direction=OrderSide.BUY,
                filled_quantity=100,
                fill_price=10.0,
                fee=5.0,
                slippage=0.01,
                event_time=datetime(2026, 1, 2, 9, 31, tzinfo=UTC),
                cumulative_quantity=100,
                leaves_quantity=0,
            ),
        ),
    )


def _adapter(
    tmp_path: Path,
) -> tuple[object, _MemoryArtifactIndex]:
    from ditto_application.builders.research_artifact_loader import (
        IndexedBacktestReportArtifactAdapter,
    )

    index = _MemoryArtifactIndex(tmp_path)
    service = ResearchArtifactService(
        artifact_root=tmp_path,
        artifact_reader=index,
        artifact_writer=index,
    )
    return (
        IndexedBacktestReportArtifactAdapter(
            artifact_service=service,
            artifact_index_reader=index,
        ),
        index,
    )


def test_publish_and_read_round_trip_through_verified_schema_v1(
    tmp_path: Path,
) -> None:
    from ditto_application.builders.research_artifact_loader import (
        IndexedBacktestReportArtifactAdapter,
    )

    adapter_value, _index = _adapter(tmp_path)
    adapter = adapter_value
    assert isinstance(adapter, IndexedBacktestReportArtifactAdapter)
    identity = _identity()
    evidence = BacktestReportEvidence.from_report(_report())

    record = adapter.publish(
        identity,
        evidence,
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )
    loaded = adapter.read(identity)

    assert record.artifact_kind == BACKTEST_REPORT_ARTIFACT_KIND
    assert record.artifact_id == identity.artifact_id
    assert record.relative_path == identity.relative_path
    assert record.content_hash == evidence.content_hash
    assert record.row_count == 1
    assert record.manifest["format"] == "json"
    assert record.created_at == identity.attempt_created_at
    audit = cast("Mapping[str, object]", record.manifest["audit"])
    assert audit["created_at"] == identity.attempt_created_at.isoformat()
    assert loaded is not None
    assert loaded.record == record
    assert loaded.evidence == evidence


def test_missing_index_fact_returns_none_without_fabricating_evidence(
    tmp_path: Path,
) -> None:
    from ditto_application.builders.research_artifact_loader import (
        IndexedBacktestReportArtifactAdapter,
    )

    adapter_value, _index = _adapter(tmp_path)
    assert isinstance(adapter_value, IndexedBacktestReportArtifactAdapter)

    assert adapter_value.read(_identity()) is None


def test_same_path_with_drifted_durable_identity_fails_closed(
    tmp_path: Path,
) -> None:
    from ditto_application.builders.research_artifact_loader import (
        IndexedBacktestReportArtifactAdapter,
    )

    adapter_value, _index = _adapter(tmp_path)
    assert isinstance(adapter_value, IndexedBacktestReportArtifactAdapter)
    original = _identity()
    adapter_value.publish(
        original,
        BacktestReportEvidence.from_report(_report()),
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )
    drifted = _identity(
        attempt_created_at=original.attempt_created_at + timedelta(microseconds=1)
    )

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        adapter_value.read(drifted)

    assert exc_info.value.details["reason"] == "artifact_identity_path_cross_conflict"


@pytest.mark.parametrize("index_drift", ["id_only", "different_records"])
def test_id_and_path_index_facts_must_both_exist_and_match(
    tmp_path: Path,
    index_drift: str,
) -> None:
    from ditto_application.builders.research_artifact_loader import (
        IndexedBacktestReportArtifactAdapter,
    )

    adapter_value, index = _adapter(tmp_path)
    assert isinstance(adapter_value, IndexedBacktestReportArtifactAdapter)
    identity = _identity()
    record = adapter_value.publish(
        identity,
        BacktestReportEvidence.from_report(_report()),
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )
    if index_drift == "id_only":
        index.records[identity.artifact_id] = replace(
            record,
            relative_path="experiments/other/report.json",
        )
    else:
        path_record = replace(record, artifact_id="other-artifact")
        index.records = {
            path_record.artifact_id: path_record,
            identity.artifact_id: record,
        }

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        adapter_value.read(identity)

    assert exc_info.value.details["reason"] == "artifact_identity_path_cross_conflict"


def test_verified_read_maps_non_object_json_to_report_integrity(
    tmp_path: Path,
) -> None:
    from ditto_application.builders.research_artifact_loader import (
        IndexedBacktestReportArtifactAdapter,
    )

    adapter_value, _index = _adapter(tmp_path)
    assert isinstance(adapter_value, IndexedBacktestReportArtifactAdapter)
    identity = _identity()
    adapter_value.publish(
        identity,
        BacktestReportEvidence.from_report(_report()),
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )
    (tmp_path / identity.relative_path).write_bytes(b"[]")

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        adapter_value.read(identity)

    assert (
        exc_info.value.details["reason_code"]
        == "backtest_report_artifact_integrity_mismatch"
    )


def test_identical_replay_is_allowed_but_different_content_conflicts(
    tmp_path: Path,
) -> None:
    from ditto_application.builders.research_artifact_loader import (
        IndexedBacktestReportArtifactAdapter,
    )

    adapter_value, _index = _adapter(tmp_path)
    assert isinstance(adapter_value, IndexedBacktestReportArtifactAdapter)
    identity = _identity()
    evidence = BacktestReportEvidence.from_report(_report())

    first = adapter_value.publish(
        identity,
        evidence,
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )
    replayed = adapter_value.publish(
        identity,
        evidence,
        lease_fence=FENCE,
        now_epoch_us=NOW_US + 1,
    )

    assert replayed == first
    assert replayed.created_at == identity.attempt_created_at
    audit = cast("Mapping[str, object]", replayed.manifest["audit"])
    assert audit["created_at"] == identity.attempt_created_at.isoformat()
    with pytest.raises(ExperimentConflictError):
        adapter_value.publish(
            identity,
            BacktestReportEvidence.from_report(_report(final_nav=102_000.0)),
            lease_fence=FENCE,
            now_epoch_us=NOW_US + 2,
        )


def test_orphaned_file_and_sidecar_recover_into_index_on_retry(
    tmp_path: Path,
) -> None:
    from ditto_application.builders.research_artifact_loader import (
        IndexedBacktestReportArtifactAdapter,
    )

    adapter_value, index = _adapter(tmp_path)
    assert isinstance(adapter_value, IndexedBacktestReportArtifactAdapter)
    identity = _identity()
    evidence = BacktestReportEvidence.from_report(_report())
    index.fail_next_add = True

    with pytest.raises(_InjectedIndexFailure):
        adapter_value.publish(
            identity,
            evidence,
            lease_fence=FENCE,
            now_epoch_us=NOW_US,
        )

    target = tmp_path / identity.relative_path
    sidecar = target.with_name(f".{target.name}.ditto-manifest.json")
    assert target.is_file()
    assert sidecar.is_file()
    assert index.get_artifact(identity.artifact_id) is None

    recovered = adapter_value.publish(
        identity,
        evidence,
        lease_fence=FENCE,
        now_epoch_us=NOW_US + 1,
    )

    assert index.add_attempts == 2
    assert index.get_artifact(identity.artifact_id) == recovered
    assert recovered.created_at == identity.attempt_created_at


@pytest.mark.parametrize(
    ("field_name", "drifted"),
    [
        ("artifact_kind", "other_kind"),
        ("experiment_id", ExperimentId("other-experiment")),
        ("candidate_id", CandidateId("other-candidate")),
        ("fold_id", FoldId("other-fold")),
        ("attempt_id", AttemptId("other-attempt")),
        ("relative_path", "experiments/other/report.json"),
        ("reproduction_fingerprint", ContentHash("b" * 64)),
        (
            "created_at",
            _DateTime(2026, 1, 3, 4, 5, 6, 789012, tzinfo=UTC),
        ),
        ("row_count", 2),
    ],
)
def test_existing_record_lineage_kind_and_measurement_drift_fail_closed(
    tmp_path: Path,
    field_name: str,
    drifted: object,
) -> None:
    from ditto_application.builders.research_artifact_loader import (
        IndexedBacktestReportArtifactAdapter,
    )

    adapter_value, index = _adapter(tmp_path)
    assert isinstance(adapter_value, IndexedBacktestReportArtifactAdapter)
    identity = _identity()
    evidence = BacktestReportEvidence.from_report(_report())
    record = adapter_value.publish(
        identity,
        evidence,
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )
    index.records[identity.artifact_id] = replace(record, **{field_name: drifted})

    with pytest.raises(ExperimentIntegrityError):
        adapter_value.read(identity)


@pytest.mark.parametrize(
    ("field_name", "drifted"),
    [
        ("content_hash", ContentHash("c" * 64)),
        ("schema_hash", ContentHash("d" * 64)),
        ("byte_size", 1),
    ],
)
def test_existing_record_content_schema_and_hash_measurement_drift_fail_closed(
    tmp_path: Path,
    field_name: str,
    drifted: object,
) -> None:
    from ditto_application.builders.research_artifact_loader import (
        IndexedBacktestReportArtifactAdapter,
    )

    adapter_value, index = _adapter(tmp_path)
    assert isinstance(adapter_value, IndexedBacktestReportArtifactAdapter)
    identity = _identity()
    record = adapter_value.publish(
        identity,
        BacktestReportEvidence.from_report(_report()),
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )
    index.records[identity.artifact_id] = replace(record, **{field_name: drifted})

    with pytest.raises(ExperimentIntegrityError):
        adapter_value.read(identity)


@pytest.mark.parametrize(
    ("field_name", "drifted"),
    [
        ("run_id", "other-run"),
        ("attempt_id", "other-attempt"),
    ],
)
def test_existing_record_audit_run_or_attempt_drift_fails_closed(
    tmp_path: Path,
    field_name: str,
    drifted: str,
) -> None:
    from ditto_application.builders.research_artifact_loader import (
        IndexedBacktestReportArtifactAdapter,
    )

    adapter_value, index = _adapter(tmp_path)
    assert isinstance(adapter_value, IndexedBacktestReportArtifactAdapter)
    identity = _identity()
    record = adapter_value.publish(
        identity,
        BacktestReportEvidence.from_report(_report()),
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )
    manifest = dict(record.manifest)
    audit = dict(manifest["audit"])
    audit[field_name] = drifted
    manifest["audit"] = audit
    index.records[identity.artifact_id] = replace(record, manifest=manifest)

    with pytest.raises(ExperimentIntegrityError):
        adapter_value.read(identity)


def test_existing_record_cannot_replace_durable_attempt_creation_time(
    tmp_path: Path,
) -> None:
    from ditto_application.builders.research_artifact_loader import (
        IndexedBacktestReportArtifactAdapter,
    )

    adapter_value, index = _adapter(tmp_path)
    assert isinstance(adapter_value, IndexedBacktestReportArtifactAdapter)
    identity = _identity()
    record = adapter_value.publish(
        identity,
        BacktestReportEvidence.from_report(_report()),
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )
    drifted_at = identity.attempt_created_at + timedelta(microseconds=1)
    manifest = dict(record.manifest)
    audit = dict(cast("Mapping[str, object]", manifest["audit"]))
    audit["created_at"] = drifted_at.isoformat()
    manifest["audit"] = audit
    index.records[identity.artifact_id] = replace(
        record,
        created_at=drifted_at,
        manifest=manifest,
    )

    with pytest.raises(ExperimentIntegrityError):
        adapter_value.read(identity)
