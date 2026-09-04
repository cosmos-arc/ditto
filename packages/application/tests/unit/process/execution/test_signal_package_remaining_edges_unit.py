"""Fail-closed identity and lifecycle edges for signal-package publication."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal, cast

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.manual_sizing import (
    AShareTradeDateResolver,
    ManualSizingService,
)
from ditto_application.processes.execution.signal_package import (
    SignalPackage,
    SignalPackagePublisher,
    SignalPackagePublishRequest,
)
from ditto_application.processes.execution.signal_snapshot import SignalSnapshotProcess
from ditto_execution.models import FillRecord, SignalRecord
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.models import StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

_STRATEGY = "edge-signals"
_SIGNAL_DATE = "2026-01-30"
_NEXT_TRADE_DATE = "2026-02-02"
_BATCH = f"eod-{_SIGNAL_DATE}-{_STRATEGY}-1"


class _PositionReader:
    def get_current_positions(self, strategy_id: str) -> dict[int, float]:
        assert strategy_id == _STRATEGY
        return {1: 0.1}


@dataclass
class _IntentPort:
    rows: list[SignalRecord] = field(default_factory=list)
    denied_updates: set[tuple[str, str]] = field(default_factory=set)

    def save_intent(self, record: SignalRecord) -> None:
        self.rows.append(record)

    def get_intent(self, intent_id: str) -> SignalRecord | None:
        return next((item for item in self.rows if item.intent_id == intent_id), None)

    def list_intents(
        self,
        strategy_id: str,
        signal_date: str | None = None,
        status: str | None = None,
    ) -> list[SignalRecord]:
        return [
            item
            for item in self.rows
            if item.strategy_id == strategy_id
            and (signal_date is None or item.signal_date == signal_date)
            and (status is None or item.status == status)
        ]

    def update_intent_status(
        self,
        intent_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...],
    ) -> bool:
        if (intent_id, status) in self.denied_updates:
            return False
        for index, item in enumerate(self.rows):
            if item.intent_id == intent_id and item.status in expected_current:
                self.rows[index] = replace(item, status=status)
                return True
        return False


@dataclass
class _FillPort:
    rows: list[FillRecord] = field(default_factory=list)
    hidden_for_calls: int = 0
    calls: int = 0

    def save_fill(self, record: FillRecord) -> None:
        self.rows.append(record)

    def list_fills(
        self,
        strategy_id: str,
        trade_date: str | None = None,
        intent_id: str | None = None,
        end_date: str | None = None,
    ) -> list[FillRecord]:
        self.calls += 1
        if self.calls <= self.hidden_for_calls:
            return []
        return [
            item
            for item in self.rows
            if item.strategy_id == strategy_id
            and (trade_date is None or item.trade_date == trade_date)
            and (intent_id is None or item.intent_id == intent_id)
            and (end_date is None or item.trade_date <= end_date)
        ]


@dataclass
class _ArtifactStore:
    rows: list[StrategyArtifactRecord] = field(default_factory=list)
    hidden_once: set[str] = field(default_factory=set)
    claim_mode: Literal["normal", "converged", "reject"] = "normal"
    activate_mode: Literal["normal", "converged", "reject"] = "normal"

    def _raw_get(self, artifact_id: str) -> StrategyArtifactRecord | None:
        return next(
            (item for item in self.rows if item.artifact_id == artifact_id), None
        )

    def get(self, artifact_id: str) -> StrategyArtifactRecord | None:
        if artifact_id in self.hidden_once:
            self.hidden_once.remove(artifact_id)
            return None
        return self._raw_get(artifact_id)

    def list_all(self) -> list[StrategyArtifactRecord]:
        return list(self.rows)

    def list_by_strategy(self, strategy_id: str) -> list[StrategyArtifactRecord]:
        return [item for item in self.rows if item.strategy_id == strategy_id]

    def save(self, record: StrategyArtifactRecord) -> bool:
        if self._raw_get(record.artifact_id) is not None:
            return False
        self.rows.append(record)
        return True

    def update_status(
        self,
        artifact_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...] | None = None,
    ) -> bool:
        for index, item in enumerate(self.rows):
            if item.artifact_id == artifact_id and (
                expected_current is None or item.status in expected_current
            ):
                self.rows[index] = replace(item, status=status)
                return True
        return False

    def claim_replacement(
        self,
        candidate_artifact_id: str,
        replaced_artifact_id: str,
    ) -> bool:
        if self.claim_mode == "reject":
            return False
        claimed = self._claim(candidate_artifact_id, replaced_artifact_id)
        if self.claim_mode == "converged":
            assert claimed
            return False
        return claimed

    def _claim(self, candidate_artifact_id: str, replaced_artifact_id: str) -> bool:
        candidate = self._raw_get(candidate_artifact_id)
        existing = self._raw_get(replaced_artifact_id)
        if candidate is None or existing is None:
            return False
        if candidate.status != "staged" or existing.status != "active":
            return False
        return self.update_status(
            candidate_artifact_id,
            "replacing",
            expected_current=("staged",),
        )

    def activate_candidate(
        self,
        candidate_artifact_id: str,
        *,
        replaced_artifact_id: str | None = None,
    ) -> bool:
        if self.activate_mode == "reject":
            return False
        activated = self._activate(candidate_artifact_id, replaced_artifact_id)
        if self.activate_mode == "converged":
            assert activated
            return False
        return activated

    def _activate(
        self,
        candidate_artifact_id: str,
        replaced_artifact_id: str | None,
    ) -> bool:
        candidate = self._raw_get(candidate_artifact_id)
        if candidate is None:
            return False
        active = [
            item
            for item in self.rows
            if item.strategy_id == candidate.strategy_id
            and item.run_id == candidate.run_id
            and item.artifact_type == candidate.artifact_type
            and item.status == "active"
        ]
        if replaced_artifact_id is None:
            if active:
                return False
            expected_candidate = ("staged",)
        else:
            if [item.artifact_id for item in active] != [replaced_artifact_id]:
                return False
            if not self.update_status(
                replaced_artifact_id,
                "archived",
                expected_current=("active",),
            ):
                return False
            expected_candidate = ("replacing",)
        return self.update_status(
            candidate_artifact_id,
            "active",
            expected_current=expected_candidate,
        )


@dataclass(frozen=True)
class _Harness:
    publisher: SignalPackagePublisher
    intents: _IntentPort
    fills: _FillPort
    artifacts: _ArtifactStore


def _harness() -> _Harness:
    intents = _IntentPort()
    fills = _FillPort()
    artifacts = _ArtifactStore()
    publisher = SignalPackagePublisher(
        snapshot_process=SignalSnapshotProcess(
            position_reader=_PositionReader(),
            sizing_service=ManualSizingService(),
        ),
        intent_port=intents,
        fill_port=fills,
        date_resolver=AShareTradeDateResolver(
            trading_days=(_SIGNAL_DATE, _NEXT_TRADE_DATE)
        ),
        artifact_service=StrategyArtifactService(artifacts, artifacts),
    )
    return _Harness(publisher, intents, fills, artifacts)


def _target() -> TargetPortfolio:
    return TargetPortfolio(
        trade_date=_SIGNAL_DATE,
        strategy_id=_STRATEGY,
        run_id=_BATCH,
        positions={InstrumentId(1): 0.3, InstrumentId(2): 0.2},
        cash_target=0.5,
    )


def _request(*, risk_flags: tuple[str, ...] = ()) -> SignalPackagePublishRequest:
    return SignalPackagePublishRequest(
        target=_target(),
        strategy_version="1",
        account_id="paper-a",
        sleeve_id=f"manual-paper-a-{_STRATEGY}",
        sizing_contexts={},
        decision_date=_SIGNAL_DATE,
        intended_trade_date=_NEXT_TRADE_DATE,
        required_datasets=("stock_daily",),
        required_dataset_states=(
            {
                "dataset": "stock_daily",
                "knowledge_date": _SIGNAL_DATE,
                "snapshot_id": "sha256:as-of-close",
                "status": "ready",
            },
        ),
        dataset_snapshot_ids={"stock_daily": "sha256:as-of-close"},
        risk_flags=risk_flags,
    )


def _publish(harness: _Harness, *, risk_flags: tuple[str, ...] = ()) -> SignalPackage:
    return harness.publisher.publish(_request(risk_flags=risk_flags))


def _artifact(harness: _Harness, artifact_id: str) -> StrategyArtifactRecord:
    artifact = harness.artifacts._raw_get(artifact_id)
    assert artifact is not None
    return artifact


def _replace_artifact(
    harness: _Harness,
    artifact: StrategyArtifactRecord,
) -> None:
    for index, item in enumerate(harness.artifacts.rows):
        if item.artifact_id == artifact.artifact_id:
            harness.artifacts.rows[index] = artifact
            return
    raise AssertionError("artifact to replace is missing")


def _business_payload(artifact: StrategyArtifactRecord) -> dict[str, object]:
    payload = artifact.metadata.get("business_payload")
    assert isinstance(payload, dict)
    return dict(cast("dict[str, object]", payload))


@pytest.mark.parametrize(
    ("publish_request", "message"),
    [
        (replace(_request(), strategy_version=""), "strategy_version"),
        (replace(_request(), account_id=""), "account_id"),
        (replace(_request(), sleeve_id=""), "sleeve_id"),
    ],
)
def test_publish_requires_each_identity_component_before_persistence(
    publish_request: SignalPackagePublishRequest,
    message: str,
) -> None:
    harness = _harness()

    with pytest.raises(AppProcessError, match=message):
        harness.publisher.publish(publish_request)

    assert harness.artifacts.rows == []
    assert harness.intents.rows == []


@pytest.mark.pit
def test_trade_date_boundary_fails_before_signal_generation_or_persistence() -> None:
    for request in (
        replace(_request(), decision_date="2026-01-29"),
        replace(_request(), intended_trade_date=_SIGNAL_DATE),
    ):
        harness = _harness()
        with pytest.raises(AppProcessError):
            harness.publisher.publish(request)
        assert harness.artifacts.rows == []
        assert harness.intents.rows == []


@pytest.mark.pit
def test_future_snapshot_revision_cannot_alias_as_of_package_identity() -> None:
    as_of, future = _harness(), _harness()
    as_of_package = as_of.publisher.publish(_request())
    future_request = replace(
        _request(),
        dataset_snapshot_ids={"stock_daily": "sha256:future-revision"},
        required_dataset_states=(
            {
                "dataset": "stock_daily",
                "knowledge_date": "2026-02-02",
                "snapshot_id": "sha256:future-revision",
                "status": "ready",
            },
        ),
    )
    future_package = future.publisher.publish(future_request)

    assert future_package.checksum != as_of_package.checksum
    assert future_package.artifact_id != as_of_package.artifact_id
    as_of_artifact = _artifact(as_of, as_of_package.artifact_id)
    assert as_of_artifact.metadata["dataset_snapshot_ids"] == {
        "stock_daily": "sha256:as-of-close"
    }


def test_finalize_fails_when_staged_candidate_disappeared() -> None:
    package = _publish(_harness())

    with pytest.raises(AppProcessError, match="disappeared"):
        _harness().publisher.finalize(package)


def test_finalize_active_with_competing_active_persists_conflict() -> None:
    harness = _harness()
    package = _publish(harness)
    harness.publisher.finalize(package)
    active = _artifact(harness, package.artifact_id)
    harness.artifacts.rows.append(
        replace(active, artifact_id=f"{active.artifact_id}-duplicate")
    )

    result = harness.publisher.finalize(package)

    assert result.outcome == "rerun_conflict"
    conflict = _artifact(harness, result.artifact_id)
    assert conflict.metadata["conflict_reason"] == "MULTIPLE_ACTIVE_PACKAGES"


def test_finalize_archived_or_orphaned_replacement_aborts_candidate() -> None:
    archived_harness = _harness()
    archived = _publish(archived_harness)
    candidate = _artifact(archived_harness, archived.artifact_id)
    _replace_artifact(archived_harness, replace(candidate, status="archived"))

    archived_result = archived_harness.publisher.finalize(archived)

    assert archived_result.outcome == "rerun_conflict"
    assert (
        _artifact(archived_harness, archived_result.artifact_id).metadata[
            "conflict_reason"
        ]
        == "CANDIDATE_STATE_CONFLICT"
    )
    assert all(item.status == "superseded" for item in archived_harness.intents.rows)

    orphaned_harness = _harness()
    active = _publish(orphaned_harness)
    orphaned_harness.publisher.finalize(active)
    replacement = _publish(orphaned_harness, risk_flags=("changed",))
    orphaned_harness.artifacts.rows = [
        item
        for item in orphaned_harness.artifacts.rows
        if item.artifact_id != active.artifact_id
    ]

    orphaned_result = orphaned_harness.publisher.finalize(replacement)

    assert orphaned_result.outcome == "rerun_conflict"
    assert (
        _artifact(orphaned_harness, orphaned_result.artifact_id).metadata[
            "conflict_reason"
        ]
        == "CANDIDATE_STATE_CONFLICT"
    )


def test_find_staged_fails_closed_for_invalid_or_ambiguous_evidence() -> None:
    assert (
        _harness().publisher.find_staged(
            strategy_id=_STRATEGY,
            run_id=_BATCH,
            signal_date=_SIGNAL_DATE,
        )
        is None
    )

    invalid = _harness()
    package = _publish(invalid)
    with pytest.raises(AppProcessError, match="evidence is invalid"):
        invalid.publisher.find_staged(
            strategy_id=_STRATEGY,
            run_id=_BATCH,
            signal_date="2026-02-02",
        )

    staged = _artifact(invalid, package.artifact_id)
    invalid.artifacts.rows.append(
        replace(staged, artifact_id=f"{staged.artifact_id}-second")
    )
    with pytest.raises(AppProcessError, match="multiple staged"):
        invalid.publisher.find_staged(
            strategy_id=_STRATEGY,
            run_id=_BATCH,
            signal_date=_SIGNAL_DATE,
        )

    active = _harness()
    active_package = _publish(active)
    active.publisher.finalize(active_package)
    active_artifact = _artifact(active, active_package.artifact_id)
    active.artifacts.rows.append(
        replace(active_artifact, artifact_id=f"{active_artifact.artifact_id}-second")
    )
    with pytest.raises(AppProcessError, match="multiple active"):
        active.publisher.find_staged(
            strategy_id=_STRATEGY,
            run_id=_BATCH,
            signal_date=_SIGNAL_DATE,
        )


def test_new_candidate_fails_closed_when_multiple_active_packages_exist() -> None:
    harness = _harness()
    first = _publish(harness)
    harness.publisher.finalize(first)
    active = _artifact(harness, first.artifact_id)
    harness.artifacts.rows.append(
        replace(active, artifact_id=f"{active.artifact_id}-second")
    )

    result = _publish(harness, risk_flags=("changed",))

    assert result.outcome == "rerun_conflict"
    assert _artifact(harness, result.artifact_id).metadata["conflict_reason"] == (
        "MULTIPLE_ACTIVE_PACKAGES"
    )


def test_stale_point_read_handles_same_checksum_active_evidence() -> None:
    same = _harness()
    package = _publish(same)
    same.publisher.finalize(package)
    same.artifacts.hidden_once.add(package.artifact_id)

    retry = _publish(same)

    assert retry == package
    assert len(same.artifacts.rows) == 1

    duplicate = _harness()
    original = _publish(duplicate)
    duplicate.publisher.finalize(original)
    active = _artifact(duplicate, original.artifact_id)
    duplicate.artifacts.rows[0] = replace(
        active,
        artifact_id=f"{active.artifact_id}-replica",
    )

    conflict = _publish(duplicate)

    assert conflict.outcome == "rerun_conflict"
    assert _artifact(duplicate, conflict.artifact_id).metadata["conflict_reason"] == (
        "CHECKSUM_MISMATCH"
    )


def test_stale_point_read_rejects_invalid_active_metadata() -> None:
    harness = _harness()
    original = _publish(harness)
    harness.publisher.finalize(original)
    active = _artifact(harness, original.artifact_id)
    harness.artifacts.rows[0] = replace(
        active,
        artifact_id=f"{active.artifact_id}-replica",
        metadata={**active.metadata, "account_id": "tampered"},
    )

    conflict = _publish(harness, risk_flags=("changed",))

    assert conflict.outcome == "rerun_conflict"
    assert _artifact(harness, conflict.artifact_id).metadata["conflict_reason"] == (
        "CHECKSUM_MISMATCH"
    )


def test_replacement_candidate_retry_resumes_only_with_durable_predecessor() -> None:
    resumable = _harness()
    active = _publish(resumable)
    resumable.publisher.finalize(active)
    candidate = _publish(resumable, risk_flags=("changed",))

    retry = _publish(resumable, risk_flags=("changed",))

    assert retry == candidate
    assert len(resumable.artifacts.rows) == 2

    orphaned = _harness()
    old = _publish(orphaned)
    orphaned.publisher.finalize(old)
    staged = _publish(orphaned, risk_flags=("changed",))
    orphaned.artifacts.rows = [
        item for item in orphaned.artifacts.rows if item.artifact_id != old.artifact_id
    ]

    conflict = _publish(orphaned, risk_flags=("changed",))

    assert conflict.outcome == "rerun_conflict"
    assert _artifact(orphaned, conflict.artifact_id).metadata["conflict_reason"] == (
        "CANDIDATE_STATE_CONFLICT"
    )
    assert _artifact(orphaned, staged.artifact_id).status == "staged"

    invalid_state = _harness()
    prior = _publish(invalid_state)
    invalid_state.publisher.finalize(prior)
    archived = _publish(invalid_state, risk_flags=("changed",))
    row = _artifact(invalid_state, archived.artifact_id)
    _replace_artifact(invalid_state, replace(row, status="archived"))

    invalid_result = _publish(invalid_state, risk_flags=("changed",))

    assert invalid_result.outcome == "rerun_conflict"
    assert (
        _artifact(invalid_state, invalid_result.artifact_id).metadata["conflict_reason"]
        == "CANDIDATE_STATE_CONFLICT"
    )


def test_finalize_rejects_tampered_candidate_identity() -> None:
    harness = _harness()
    package = _publish(harness)
    candidate = _artifact(harness, package.artifact_id)
    _replace_artifact(
        harness,
        replace(candidate, metadata={**candidate.metadata, "account_id": "other"}),
    )

    with pytest.raises(AppProcessError, match="candidate evidence is invalid"):
        harness.publisher.finalize(package)


def test_replace_active_detects_candidate_disappearance_between_reads() -> None:
    source = _harness()
    package = _publish(source)
    candidate = _artifact(source, package.artifact_id)
    business_payload = _business_payload(candidate)

    with pytest.raises(AppProcessError, match="disappeared"):
        _harness().publisher._replace_active(
            package,
            business_payload,
            candidate,
        )


def test_concurrent_replacement_claim_that_already_converged_can_finish() -> None:
    harness = _harness()
    active = _publish(harness)
    harness.publisher.finalize(active)
    candidate = _publish(harness, risk_flags=("changed",))
    harness.artifacts.claim_mode = "converged"

    result = harness.publisher.finalize(candidate)

    assert result == candidate
    assert _artifact(harness, candidate.artifact_id).status == "active"
    assert _artifact(harness, active.artifact_id).status == "archived"


def test_invalid_predecessor_intent_manifest_aborts_replacement() -> None:
    harness = _harness()
    active = _publish(harness)
    harness.publisher.finalize(active)
    candidate = _publish(harness, risk_flags=("changed",))
    active_artifact = _artifact(harness, active.artifact_id)
    _replace_artifact(
        harness,
        replace(
            active_artifact,
            metadata={**active_artifact.metadata, "intents": "not-a-list"},
        ),
    )

    result = harness.publisher.finalize(candidate)

    assert result.outcome == "rerun_conflict"
    assert _artifact(harness, result.artifact_id).metadata["conflict_reason"] == (
        "UNSAFE_TO_SUPERSEDE"
    )
    assert all(item.status == "superseded" for item in harness.intents.rows[2:])


def test_intent_transition_race_restores_old_pending_state() -> None:
    harness = _harness()
    active = _publish(harness)
    harness.publisher.finalize(active)
    candidate = _publish(harness, risk_flags=("changed",))
    first_old_id = active.intents[0].intent_id
    harness.intents.denied_updates.add((first_old_id, "superseded"))

    result = harness.publisher.finalize(candidate)

    assert result.outcome == "rerun_conflict"
    assert _artifact(harness, result.artifact_id).metadata["conflict_reason"] == (
        "INTENT_TRANSITION_CONFLICT"
    )
    old_ids = {item.intent_id for item in active.intents}
    assert all(
        item.status == "pending"
        for item in harness.intents.rows
        if item.intent_id in old_ids
    )


def test_fill_appearing_during_replacement_aborts_and_restores() -> None:
    harness = _harness()
    active = _publish(harness)
    harness.publisher.finalize(active)
    candidate = _publish(harness, risk_flags=("changed",))
    first_old = active.intents[0]
    harness.fills.rows.append(
        FillRecord(
            fill_id="concurrent-fill",
            intent_id=first_old.intent_id,
            strategy_id=_STRATEGY,
            trade_date=_NEXT_TRADE_DATE,
            instrument_id=first_old.instrument_id,
            direction=first_old.direction,
            quantity=100,
            fill_price=10.0,
            fee=1.0,
        )
    )
    harness.fills.calls = 0
    harness.fills.hidden_for_calls = len(active.intents)

    result = harness.publisher.finalize(candidate)

    assert result.outcome == "rerun_conflict"
    assert _artifact(harness, result.artifact_id).metadata["conflict_reason"] == (
        "FILL_APPEARED_DURING_REPLACEMENT"
    )
    old_ids = {item.intent_id for item in active.intents}
    assert all(
        item.status == "pending"
        for item in harness.intents.rows
        if item.intent_id in old_ids
    )


@pytest.mark.parametrize("mode", ["converged", "reject"])
def test_replacement_activation_race_converges_or_fails_closed(
    mode: Literal["converged", "reject"],
) -> None:
    harness = _harness()
    active = _publish(harness)
    harness.publisher.finalize(active)
    candidate = _publish(harness, risk_flags=("changed",))
    harness.artifacts.activate_mode = mode

    result = harness.publisher.finalize(candidate)

    if mode == "converged":
        assert result == candidate
        assert _artifact(harness, candidate.artifact_id).status == "active"
        assert _artifact(harness, active.artifact_id).status == "archived"
    else:
        assert result.outcome == "rerun_conflict"
        assert _artifact(harness, result.artifact_id).metadata["conflict_reason"] == (
            "ARTIFACT_TRANSITION_CONFLICT"
        )
        assert _artifact(harness, active.artifact_id).status == "active"


@pytest.mark.parametrize("mode", ["converged", "reject"])
def test_initial_activation_race_converges_or_fails_closed(
    mode: Literal["converged", "reject"],
) -> None:
    harness = _harness()
    candidate = _publish(harness)
    harness.artifacts.activate_mode = mode

    result = harness.publisher.finalize(candidate)

    if mode == "converged":
        assert result == candidate
        assert _artifact(harness, candidate.artifact_id).status == "active"
    else:
        assert result.outcome == "rerun_conflict"
        assert _artifact(harness, candidate.artifact_id).status == "archived"
        assert _artifact(harness, result.artifact_id).metadata["conflict_reason"] == (
            "CONCURRENT_BATCH_PUBLICATION"
        )


def test_replacement_intents_require_complete_persisted_identity_set() -> None:
    harness = _harness()
    package = _publish(harness)
    harness.publisher.finalize(package)
    artifact = _artifact(harness, package.artifact_id)
    harness.intents.rows.pop()

    assert harness.publisher._replacement_intents(artifact, ("pending",)) is None


def test_supersede_is_idempotent_but_missing_identity_fails_closed() -> None:
    harness = _harness()
    _publish(harness)
    first = harness.intents.rows[0]
    harness.intents.rows[0] = replace(first, status="superseded")

    assert harness.publisher._supersede_intent(first.intent_id)
    assert not harness.publisher._supersede_intent("missing-intent")


def test_conflict_persistence_requires_a_durable_conflicting_artifact() -> None:
    harness = _harness()
    package = _publish(harness)
    candidate = _artifact(harness, package.artifact_id)

    with pytest.raises(AppProcessError, match="lost all durable artifacts"):
        harness.publisher._persist_conflict(
            package,
            _business_payload(candidate),
            None,
            "LOST_STATE",
        )


def test_intent_id_collision_with_different_payload_fails_closed() -> None:
    harness = _harness()
    package = _publish(harness)
    first = harness.intents.rows[0]
    harness.intents.rows[0] = replace(first, quantity=(first.quantity or 0) + 100)

    with pytest.raises(AppProcessError, match="identity conflicts"):
        harness.publisher._save_intents(package)
