"""LeaseAuthority error-classification tests using an in-memory fake store."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Never, cast

import pytest
from ditto_analysis.errors import (
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentLeaseLostError,
    ExperimentSpecError,
)
from ditto_analysis.experiments import ExperimentId, SchedulerLease, SchedulerSlot
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
    """Implement only the two ports exercised by LeaseAuthority."""

    def __init__(self) -> None:
        self.renew_calls = 0
        self.release_calls = 0

    def try_claim_lease(
        self,
        experiment_id: ExperimentId,
        owner_token: str,
        *,
        expected_revision: int,
        now_epoch_us: int,
        lease_until_epoch_us: int,
    ) -> SchedulerLease:
        return SchedulerLease(
            experiment_id=experiment_id,
            owner_token=owner_token,
            lease_until_epoch_us=lease_until_epoch_us,
            acquired_at_epoch_us=now_epoch_us,
            renewed_at_epoch_us=now_epoch_us,
            revision=expected_revision + 1,
        )

    def renew_lease(
        self,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
        new_lease_until_epoch_us: int,
    ) -> SchedulerLease:
        self.renew_calls += 1
        return replace(
            lease,
            lease_until_epoch_us=new_lease_until_epoch_us,
            renewed_at_epoch_us=now_epoch_us,
            revision=lease.revision + 1,
        )

    def release_lease(
        self,
        lease: SchedulerLease,
        *,
        now_epoch_us: int,
    ) -> SchedulerSlot:
        self.release_calls += 1
        return SchedulerSlot(
            "global",
            None,
            None,
            None,
            None,
            None,
            lease.revision + 1,
        )


def _raise(error: Exception) -> Never:
    raise error


def _acquired_authority() -> tuple[LeaseAuthority, _LeaseStore]:
    store = _LeaseStore()
    authority = LeaseAuthority(
        cast(ExperimentSchedulerStoreProtocol, store),
        owner_token="lease-authority-test",
        lease_duration=timedelta(minutes=5),
        clock=lambda: NOW,
    )
    assert authority.acquire(EXPERIMENT_ID, expected_revision=0) is True
    assert authority.has_lease is True
    return authority, store


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
    renewed = authority.renew()
    assert renewed.revision == 2
    assert renewed.renewed_at_epoch_us == NOW_EPOCH_US
    assert store.renew_calls == 1


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
    with pytest.raises(AppProcessError) as renew_exc:
        authority.renew()
    assert renew_exc.value.details["code"] == "LEASE_LOST"
    assert renew_exc.value.details["reason"] == "scheduler_authority_invalidated"
    assert store.renew_calls == 0


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
    assert authority.renew().revision == 2
    assert store.renew_calls == 1


def test_release_clears_local_lease_without_poisoning_authority() -> None:
    authority, store = _acquired_authority()

    released = authority.release()

    assert released.experiment_id is None
    assert released.revision == 2
    assert store.release_calls == 1
    assert authority.has_lease is False
    assert authority.is_lost is False
    assert authority.acquire(ExperimentId("experiment-next"), expected_revision=2)
