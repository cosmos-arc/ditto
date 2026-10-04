"""LeaseAuthority error-classification tests using an in-memory fake store."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Event, RLock, Thread, get_ident
from typing import Never, cast

import pytest
from ditto_analysis.errors import (
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentLeaseLostError,
    ExperimentSpecError,
    ResearchDatasetError,
)
from ditto_analysis.experiments import (
    ExperimentId,
    LeaseFence,
    SchedulerLease,
    SchedulerSlot,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.lease_authority import LeaseAuthority
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentExecutionControlChanged,
    ExperimentSchedulerStoreProtocol,
)

NOW = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
NOW_EPOCH_US = int(NOW.timestamp() * 1_000_000)
EXPERIMENT_ID = ExperimentId("experiment-lease-authority")


class _LeaseStore:
    """Implement only the ports exercised by LeaseAuthority."""

    def __init__(self) -> None:
        self.claim_calls = 0
        self.release_calls = 0

    def try_claim_lease(
        self,
        experiment_id: ExperimentId,
        owner_token: str,
        *,
        expected_revision: int,
        now_epoch_us: int,
    ) -> SchedulerLease:
        self.claim_calls += 1
        return SchedulerLease(
            experiment_id=experiment_id,
            owner_token=owner_token,
            revision=expected_revision + 1,
        )

    def release_lease(self, lease: SchedulerLease) -> SchedulerSlot:
        self.release_calls += 1
        return SchedulerSlot(
            "global",
            None,
            None,
            lease.revision + 1,
        )


class _ObservableRLock:
    """Expose one outer authority section and deterministic contention."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.depth = 0
        self.section_id = 0
        self.active_section_id: int | None = None
        self.owner_thread_id: int | None = None
        self.competitor_attempted = Event()

    def __enter__(self) -> None:
        thread_id = get_ident()
        if self.owner_thread_id not in {None, thread_id}:
            self.competitor_attempted.set()
        self._lock.acquire()
        if self.depth == 0:
            self.section_id += 1
            self.active_section_id = self.section_id
            self.owner_thread_id = thread_id
        self.depth += 1

    def __exit__(
        self,
        _exc_type: object,
        _exc_value: object,
        _traceback: object,
    ) -> None:
        self.depth -= 1
        if self.depth == 0:
            self.active_section_id = None
            self.owner_thread_id = None
        self._lock.release()


def _raise(error: Exception) -> Never:
    raise error


def _raise_base(error: BaseException) -> Never:
    raise error


def _acquired_authority(
    store: _LeaseStore | None = None,
) -> tuple[LeaseAuthority, _LeaseStore]:
    if store is None:
        store = _LeaseStore()
    authority = LeaseAuthority(
        cast(ExperimentSchedulerStoreProtocol, store),
        owner_token="lease-authority-test",
        clock=lambda: NOW,
    )
    assert authority.acquire(EXPERIMENT_ID, expected_revision=0) is True
    assert authority.has_lease is True
    return authority, store


def test_acquire_treats_stale_revision_as_retryable() -> None:
    class _StaleRevisionStore(_LeaseStore):
        def try_claim_lease(
            self,
            experiment_id: ExperimentId,
            owner_token: str,
            *,
            expected_revision: int,
            now_epoch_us: int,
        ) -> SchedulerLease | None:
            raise ExperimentLeaseLostError(
                "scheduler revision is stale",
                details={"reason_code": "scheduler_lease_stale_revision"},
            )

    store = _StaleRevisionStore()
    authority = LeaseAuthority(
        cast(ExperimentSchedulerStoreProtocol, store),
        owner_token="lease-authority-test",
        clock=lambda: NOW,
    )

    assert authority.acquire(EXPERIMENT_ID, expected_revision=0) is False
    assert authority.is_lost is False
    assert authority.has_lease is False


def test_acquire_treats_foreign_occupant_as_busy_without_poisoning() -> None:
    class _ReclaimRequiredStore(_LeaseStore):
        def try_claim_lease(
            self,
            experiment_id: ExperimentId,
            owner_token: str,
            *,
            expected_revision: int,
            now_epoch_us: int,
        ) -> SchedulerLease | None:
            self.claim_calls += 1
            raise ExperimentSpecError(
                "active scheduler slot must be reclaimed by its own experiment",
                details={"reason_code": "scheduler_reclaim_required"},
            )

    store = _ReclaimRequiredStore()
    authority = LeaseAuthority(
        cast(ExperimentSchedulerStoreProtocol, store),
        owner_token="lease-authority-test",
        clock=lambda: NOW,
    )

    # A control route claiming while another experiment occupies the slot is
    # ordinary busyness; the process-lifetime authority must stay usable.
    assert authority.acquire(EXPERIMENT_ID, expected_revision=0) is False
    assert authority.is_lost is False
    assert authority.has_lease is False
    assert store.claim_calls == 1


def test_acquire_fail_closes_on_a_lost_slot_race() -> None:
    class _LostStore(_LeaseStore):
        def try_claim_lease(
            self,
            experiment_id: ExperimentId,
            owner_token: str,
            *,
            expected_revision: int,
            now_epoch_us: int,
        ) -> SchedulerLease | None:
            raise ExperimentLeaseLostError(
                "scheduler fencing token is stale",
                details={"reason_code": "scheduler_lease_lost"},
            )

    authority = LeaseAuthority(
        cast(ExperimentSchedulerStoreProtocol, _LostStore()),
        owner_token="lease-authority-test",
        clock=lambda: NOW,
    )

    with pytest.raises(AppProcessError) as exc_info:
        authority.acquire(EXPERIMENT_ID, expected_revision=0)

    assert exc_info.value.details["code"] == "LEASE_LOST"
    assert authority.is_lost is True


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_reason"),
    [
        pytest.param(
            AppProcessError(
                "operator input is invalid",
                details={"code": "SPEC_INVALID", "reason": "operator_input_invalid"},
            ),
            "SPEC_INVALID",
            "operator_input_invalid",
            id="app-process",
        ),
        pytest.param(
            ExperimentConflictError(
                "revision conflict",
                details={"reason_code": "stale_projection_revision"},
            ),
            "CONFLICT",
            "stale_projection_revision",
            id="conflict",
        ),
        pytest.param(
            ExperimentSpecError(
                "operator request is invalid",
                details={"reason_code": "terminal_retry_not_allowed"},
            ),
            "SPEC_INVALID",
            "terminal_retry_not_allowed",
            id="spec",
        ),
    ],
)
def test_execute_operator_rejection_does_not_poison_authority(
    error: Exception,
    expected_code: str,
    expected_reason: str,
) -> None:
    authority, store = _acquired_authority()

    with pytest.raises(AppProcessError) as exc_info:
        authority.execute_operator(lambda _lease, _now: _raise(error))

    assert exc_info.value.details["code"] == expected_code
    assert exc_info.value.details["reason"] == expected_reason
    assert authority.is_lost is False
    assert authority.has_lease is True
    observed_revision = authority.execute(lambda lease, _now: lease.fence.revision)
    assert observed_revision == 1
    assert store.claim_calls == 1


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        pytest.param(
            ExperimentLeaseLostError(
                "lease lost",
                details={"reason_code": "scheduler_lease_lost"},
            ),
            "LEASE_LOST",
            id="analysis-lease",
        ),
        pytest.param(
            ExperimentIntegrityError(
                "lineage corrupt",
                details={"reason_code": "attempt_lineage_invalid"},
            ),
            "EXPERIMENT_INTEGRITY_FAILED",
            id="analysis-integrity",
        ),
        pytest.param(
            AppProcessError(
                "lease lost",
                details={"code": "LEASE_LOST", "reason": "scheduler_lease_lost"},
            ),
            "LEASE_LOST",
            id="app-lease",
        ),
        pytest.param(
            AppProcessError(
                "integrity failed",
                details={
                    "code": "EXPERIMENT_INTEGRITY_FAILED",
                    "reason": "attempt_lineage_invalid",
                },
            ),
            "EXPERIMENT_INTEGRITY_FAILED",
            id="app-integrity",
        ),
    ],
)
def test_execute_operator_authority_failure_remains_fail_closed(
    error: Exception,
    expected_code: str,
) -> None:
    authority, store = _acquired_authority()

    with pytest.raises(AppProcessError) as exc_info:
        authority.execute_operator(lambda _lease, _now: _raise(error))

    assert exc_info.value.details["code"] == expected_code
    assert authority.is_lost is True
    assert authority.has_lease is False
    with pytest.raises(AppProcessError) as acquire_exc:
        authority.acquire(EXPERIMENT_ID, expected_revision=1)
    assert acquire_exc.value.details["code"] == "LEASE_LOST"
    assert acquire_exc.value.details["reason"] == "scheduler_authority_invalidated"
    assert store.claim_calls == 1


def test_execute_control_change_does_not_poison_authority() -> None:
    authority, store = _acquired_authority()
    control_change = ExperimentExecutionControlChanged(
        "durable execution control changed",
        details={"code": "CONFLICT", "reason": "execution_control_changed"},
    )

    with pytest.raises(ExperimentExecutionControlChanged) as exc_info:
        authority.execute(lambda _lease, _now: _raise(control_change))

    assert exc_info.value is control_change
    assert authority.is_lost is False
    assert authority.has_lease is True
    assert authority.execute(lambda lease, _now: lease.fence.revision) == 1
    assert store.claim_calls == 1


def test_release_clears_local_lease_without_poisoning_authority() -> None:
    authority, store = _acquired_authority()

    released = authority.release()

    assert released.experiment_id is None
    assert released.revision == 2
    assert store.release_calls == 1
    assert authority.has_lease is False
    assert authority.is_lost is False
    assert authority.acquire(ExperimentId("experiment-next"), expected_revision=2)


def test_recoverable_publication_runs_in_one_outer_authority_section() -> None:
    authority, _store = _acquired_authority()
    lock = _ObservableRLock()
    authority._lock = lock
    current_now_section_ids: list[int | None] = []

    def observed_clock() -> datetime:
        current_now_section_ids.append(lock.active_section_id)
        return NOW

    authority._clock = observed_clock
    observed: list[tuple[LeaseFence, int, int, int | None]] = []

    result = authority.execute_recoverable_publication(
        lambda fence, now_epoch_us: (
            observed.append(
                (
                    fence,
                    now_epoch_us,
                    lock.depth,
                    lock.active_section_id,
                )
            )
            or "published"
        )
    )

    assert result == "published"
    outer_section_id = current_now_section_ids[0]
    assert outer_section_id is not None
    assert current_now_section_ids == [outer_section_id]
    assert observed == [
        (
            LeaseFence(
                experiment_id=EXPERIMENT_ID,
                owner_token=observed[0][0].owner_token,
                revision=1,
            ),
            NOW_EPOCH_US,
            1,
            outer_section_id,
        )
    ]
    assert lock.depth == 0


def test_recoverable_publication_blocks_a_second_section_until_callback_returns() -> (
    None
):
    lock = _ObservableRLock()
    publication_started = Event()

    authority, _store = _acquired_authority()
    authority._lock = lock
    competitor_finished = Event()
    competitor_errors: list[BaseException] = []
    callback_observed: list[tuple[int | None, bool]] = []

    def competitor() -> None:
        try:
            assert publication_started.wait(timeout=5)
            authority.execute(lambda _lease, _now: None)
        except BaseException as error:
            competitor_errors.append(error)
        finally:
            competitor_finished.set()

    thread = Thread(target=competitor)
    thread.start()

    def publish(_fence: LeaseFence, _now_epoch_us: int) -> None:
        publication_started.set()
        assert lock.competitor_attempted.wait(timeout=5)
        callback_observed.append((lock.active_section_id, competitor_finished.is_set()))

    authority.execute_recoverable_publication(publish)
    thread.join(timeout=5)

    assert thread.is_alive() is False
    assert competitor_finished.is_set() is True
    assert competitor_errors == []
    publication_section_id = callback_observed[0][0]
    assert publication_section_id is not None
    assert callback_observed == [(publication_section_id, False)]


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("publisher exploded"),
        OSError("artifact fsync failed"),
        ResearchDatasetError("artifact service rejected input"),
        ExperimentSpecError(
            "artifact spec invalid",
            details={"reason_code": "invalid_artifact_spec"},
        ),
        AppProcessError(
            "publication rejected",
            details={"code": "SPEC_INVALID", "reason": "invalid_artifact"},
        ),
    ],
)
def test_recoverable_publication_error_preserves_authority(error: Exception) -> None:
    authority, _store = _acquired_authority()

    with pytest.raises(type(error)) as exc_info:
        authority.execute_recoverable_publication(
            lambda _fence, _now_epoch_us: _raise(error)
        )

    assert exc_info.value is error
    assert authority.is_lost is False
    assert authority.has_lease is True
    assert authority.execute(lambda lease, _now: lease.fence.revision) == 1


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (
            ExperimentLeaseLostError(
                "lease lost",
                details={"reason_code": "scheduler_lease_lost"},
            ),
            "LEASE_LOST",
        ),
        (
            ExperimentIntegrityError(
                "artifact corrupt",
                details={"reason_code": "artifact_integrity_failed"},
            ),
            "EXPERIMENT_INTEGRITY_FAILED",
        ),
        (
            AppProcessError(
                "lease lost",
                details={"code": "LEASE_LOST", "reason": "scheduler_lease_lost"},
            ),
            "LEASE_LOST",
        ),
        (
            AppProcessError(
                "integrity failed",
                details={
                    "code": "EXPERIMENT_INTEGRITY_FAILED",
                    "reason": "artifact_integrity_failed",
                },
            ),
            "EXPERIMENT_INTEGRITY_FAILED",
        ),
        (
            ExperimentConflictError(
                "artifact replay drift",
                details={"reason_code": "artifact_replay_drift"},
            ),
            "EXPERIMENT_INTEGRITY_FAILED",
        ),
    ],
)
def test_recoverable_publication_terminal_error_invalidates_authority(
    error: Exception,
    expected_code: str,
) -> None:
    authority, store = _acquired_authority()

    with pytest.raises(AppProcessError) as exc_info:
        authority.execute_recoverable_publication(
            lambda _fence, _now_epoch_us: _raise(error)
        )

    assert exc_info.value.details["code"] == expected_code
    assert authority.is_lost is True
    assert authority.has_lease is False
    with pytest.raises(AppProcessError) as acquire_info:
        authority.acquire(EXPERIMENT_ID, expected_revision=1)
    assert acquire_info.value.details["code"] == "LEASE_LOST"
    assert store.claim_calls == 1


class _PublicationInterrupt(BaseException):
    """Represent an unknown publication outcome such as process interruption."""


def test_recoverable_publication_base_exception_invalidates_and_reraises() -> None:
    authority, _store = _acquired_authority()
    interrupt = _PublicationInterrupt()

    with pytest.raises(_PublicationInterrupt) as exc_info:
        authority.execute_recoverable_publication(
            lambda _fence, _now: _raise_base(interrupt)
        )

    assert exc_info.value is interrupt
    assert authority.is_lost is True
    assert authority.has_lease is False
