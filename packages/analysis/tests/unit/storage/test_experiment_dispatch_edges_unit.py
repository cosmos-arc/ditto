"""Transaction and lineage edges for SQLite experiment dispatch."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from ditto_analysis.errors import (
    AnalysisError,
    ExperimentPersistenceError,
    ExperimentSpecError,
)
from ditto_analysis.experiments.models import (
    AttemptId,
    BacktestRunId,
    CandidateId,
    ContentHash,
    ExperimentDesiredState,
    ExperimentId,
    ExperimentStatus,
    FoldId,
)
from ditto_analysis.experiments.persistence import (
    AttemptPersistenceSpec,
    AttemptProjection,
    FoldKey,
    LeaseFence,
)
from ditto_analysis.storage.sqlite.experiments._dispatch import (
    SQLiteAtomicDispatchMixin,
)
from ditto_analysis.storage.sqlite.experiments.database import (
    ResearchExperimentDatabase,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
FINGERPRINT = ContentHash("a" * 64)


def _key(suffix: str = "one") -> FoldKey:
    return FoldKey(
        ExperimentId(f"experiment-{suffix}"),
        CandidateId(f"candidate-{suffix}"),
        FoldId(f"fold-{suffix}"),
    )


def _spec(
    key: FoldKey,
    *,
    ordinal: int = 2,
    parent_attempt_id: AttemptId | None = None,
    resume_from_run_id: BacktestRunId | None = None,
) -> AttemptPersistenceSpec:
    return cast(
        "AttemptPersistenceSpec",
        cast(
            "object",
            SimpleNamespace(
                attempt_id=AttemptId("attempt-new"),
                fold_key=key,
                ordinal=ordinal,
                parent_attempt_id=parent_attempt_id,
                resume_from_run_id=resume_from_run_id,
                reproduction_fingerprint=FINGERPRINT,
                created_at=NOW,
            ),
        ),
    )


def _reason(error: AnalysisError) -> object:
    return error.details["reason_code"]


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE experiment(
            experiment_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            desired_state TEXT NOT NULL
        );
        CREATE TABLE experiment_fold(
            experiment_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            fold_id TEXT NOT NULL,
            fold_role TEXT NOT NULL DEFAULT 'exploration',
            status TEXT NOT NULL,
            claim_owner_token TEXT,
            revision INTEGER NOT NULL,
            created_at_epoch_us INTEGER NOT NULL DEFAULT 0,
            updated_at_epoch_us INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE experiment_attempt(
            attempt_id TEXT PRIMARY KEY,
            experiment_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            fold_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            parent_attempt_id TEXT,
            reproduction_fingerprint TEXT NOT NULL,
            status TEXT NOT NULL,
            backtest_run_id TEXT,
            checkpoint_ref TEXT,
            failure_code TEXT,
            revision INTEGER NOT NULL,
            created_at_epoch_us INTEGER NOT NULL DEFAULT 0,
            updated_at_epoch_us INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    return connection


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    value = _connection()
    try:
        yield value
    finally:
        value.close()


def _insert_fold(
    connection: sqlite3.Connection,
    key: FoldKey,
    *,
    status: ExperimentStatus = ExperimentStatus.RUNNING,
    owner: str | None = "prior-owner",
    revision: int = 2,
) -> None:
    connection.execute(
        """
        INSERT INTO experiment_fold(
            experiment_id, candidate_id, fold_id, status,
            claim_owner_token, revision, created_at_epoch_us
        ) VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        (
            str(key.experiment_id),
            str(key.candidate_id),
            str(key.fold_id),
            status.value,
            owner,
            revision,
        ),
    )


def _insert_experiment(
    connection: sqlite3.Connection,
    key: FoldKey,
    *,
    status: ExperimentStatus = ExperimentStatus.RUNNING,
    desired_state: ExperimentDesiredState = ExperimentDesiredState.RUN,
) -> None:
    connection.execute(
        "INSERT INTO experiment VALUES (?, ?, ?)",
        (str(key.experiment_id), status.value, desired_state.value),
    )


def _insert_attempt(
    connection: sqlite3.Connection,
    key: FoldKey,
    *,
    attempt_id: str = "attempt-old",
    ordinal: int = 1,
    parent_attempt_id: str | None = None,
    fingerprint: str = str(FINGERPRINT),
    status: ExperimentStatus = ExperimentStatus.FAILED,
    backtest_run_id: str | None = "run-old",
    revision: int = 3,
) -> None:
    connection.execute(
        """
        INSERT INTO experiment_attempt(
            attempt_id, experiment_id, candidate_id, fold_id, ordinal,
            parent_attempt_id, reproduction_fingerprint, status,
            backtest_run_id, checkpoint_ref, revision, created_at_epoch_us
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 0)
        """,
        (
            attempt_id,
            str(key.experiment_id),
            str(key.candidate_id),
            str(key.fold_id),
            ordinal,
            parent_attempt_id,
            fingerprint,
            status.value,
            backtest_run_id,
            revision,
        ),
    )


def test_atomic_dispatch_rejects_key_and_first_resume_mismatch_before_writes() -> None:
    harness = SQLiteAtomicDispatchMixin()
    initial = cast("AttemptProjection", object())
    key = _key()

    with pytest.raises(ExperimentSpecError) as exc_info:
        harness.claim_fold_and_add_attempt(
            key,
            _spec(_key("other")),
            initial,
            expected_fold_revision=0,
            lease_fence=cast("LeaseFence", object()),
            now_epoch_us=0,
            occurred_at=NOW,
        )
    assert _reason(exc_info.value) == "atomic_dispatch_lineage_mismatch"

    with pytest.raises(ExperimentSpecError) as exc_info:
        harness.claim_fold_and_add_attempt(
            key,
            _spec(
                key,
                ordinal=1,
                resume_from_run_id=BacktestRunId("run-old"),
            ),
            initial,
            expected_fold_revision=0,
            lease_fence=cast("LeaseFence", object()),
            now_epoch_us=0,
            occurred_at=NOW,
        )
    assert _reason(exc_info.value) == "first_attempt_cannot_resume"


def _harness(connection: sqlite3.Connection) -> SQLiteAtomicDispatchMixin:
    harness = SQLiteAtomicDispatchMixin()
    database = SimpleNamespace(get_connection=lambda: connection)
    harness._database = cast(
        "ResearchExperimentDatabase",
        cast("object", database),
    )
    return harness


def _fence(key: FoldKey) -> LeaseFence:
    return LeaseFence(
        experiment_id=key.experiment_id,
        owner_token="new-owner",
        revision=1,
        lease_until_epoch_us=2_000_000,
    )


def test_atomic_dispatch_checks_fold_existence_and_revision(
    connection: sqlite3.Connection,
) -> None:
    key = _key()
    _insert_experiment(connection, key)
    connection.commit()
    harness = _harness(connection)

    with pytest.raises(AnalysisError) as exc_info:
        harness.claim_fold_and_add_attempt(
            key,
            _spec(key),
            cast("AttemptProjection", object()),
            expected_fold_revision=2,
            lease_fence=_fence(key),
            now_epoch_us=1,
            occurred_at=NOW,
        )
    assert _reason(exc_info.value) == "fold_not_found"

    _insert_fold(
        connection,
        key,
        status=ExperimentStatus.QUEUED,
        owner=None,
        revision=2,
    )
    connection.commit()
    with pytest.raises(AnalysisError) as exc_info:
        harness.claim_fold_and_add_attempt(
            key,
            _spec(key),
            cast("AttemptProjection", object()),
            expected_fold_revision=1,
            lease_fence=_fence(key),
            now_epoch_us=1,
            occurred_at=NOW,
        )
    assert _reason(exc_info.value) == "stale_projection_revision"


def test_atomic_dispatch_detects_fold_compare_and_swap_loss(
    connection: sqlite3.Connection,
) -> None:
    key = _key()
    _insert_experiment(connection, key)
    _insert_fold(
        connection,
        key,
        status=ExperimentStatus.QUEUED,
        owner=None,
        revision=2,
    )
    connection.executescript(
        """
        CREATE TRIGGER ignore_fold_claim
        BEFORE UPDATE ON experiment_fold
        BEGIN
            SELECT RAISE(IGNORE);
        END;
        """
    )
    connection.commit()

    with pytest.raises(AnalysisError) as exc_info:
        _harness(connection).claim_fold_and_add_attempt(
            key,
            _spec(key),
            cast("AttemptProjection", object()),
            expected_fold_revision=2,
            lease_fence=_fence(key),
            now_epoch_us=1,
            occurred_at=NOW,
        )

    assert _reason(exc_info.value) == "stale_projection_revision"


def test_retry_lineage_rejects_nonprior_and_live_parent(
    connection: sqlite3.Connection,
) -> None:
    key = _key()
    _insert_attempt(connection, key, ordinal=2)
    spec = _spec(key, ordinal=2, parent_attempt_id=AttemptId("attempt-old"))

    with pytest.raises(AnalysisError) as exc_info:
        SQLiteAtomicDispatchMixin._validate_dispatch_attempt_lineage(
            connection,
            key,
            spec,
        )
    assert _reason(exc_info.value) == "invalid_retry_parent_ordinal"

    connection.execute(
        "UPDATE experiment_attempt SET ordinal=1, status='queued' WHERE attempt_id=?",
        ("attempt-old",),
    )
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteAtomicDispatchMixin._validate_dispatch_attempt_lineage(
            connection,
            key,
            spec,
        )
    assert _reason(exc_info.value) == "retry_parent_not_terminal"


def test_resume_source_must_belong_to_parent_ancestry(
    connection: sqlite3.Connection,
) -> None:
    key = _key()
    _insert_attempt(connection, key, parent_attempt_id="missing-parent")
    parent = connection.execute(
        "SELECT * FROM experiment_attempt WHERE attempt_id='attempt-old'"
    ).fetchone()
    assert parent is not None

    with pytest.raises(AnalysisError) as exc_info:
        SQLiteAtomicDispatchMixin._validate_resume_source_lineage(
            connection,
            parent,
            BacktestRunId("unrelated-run"),
        )

    assert _reason(exc_info.value) == "retry_resume_source_mismatch"


def test_interrupted_work_loader_checks_each_persisted_boundary(
    connection: sqlite3.Connection,
) -> None:
    key = _key()
    attempt_id = AttemptId("attempt-old")

    with pytest.raises(AnalysisError) as exc_info:
        SQLiteAtomicDispatchMixin._load_interrupted_work(
            connection,
            key,
            attempt_id,
            expected_fold_revision=2,
            expected_attempt_revision=3,
            current_owner_token="new-owner",
        )
    assert _reason(exc_info.value) == "fold_not_found"

    _insert_fold(connection, key)
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteAtomicDispatchMixin._load_interrupted_work(
            connection,
            key,
            attempt_id,
            expected_fold_revision=1,
            expected_attempt_revision=3,
            current_owner_token="new-owner",
        )
    assert _reason(exc_info.value) == "stale_projection_revision"

    connection.execute("UPDATE experiment_fold SET status='queued'")
    with pytest.raises(ExperimentSpecError) as exc_info:
        SQLiteAtomicDispatchMixin._load_interrupted_work(
            connection,
            key,
            attempt_id,
            expected_fold_revision=2,
            expected_attempt_revision=3,
            current_owner_token="new-owner",
        )
    assert _reason(exc_info.value) == "interrupted_fold_not_running"

    connection.execute("UPDATE experiment_fold SET status='running'")
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteAtomicDispatchMixin._load_interrupted_work(
            connection,
            key,
            attempt_id,
            expected_fold_revision=2,
            expected_attempt_revision=3,
            current_owner_token="new-owner",
        )
    assert _reason(exc_info.value) == "invalid_interrupted_attempt_lineage"

    _insert_attempt(connection, _key("other"))
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteAtomicDispatchMixin._load_interrupted_work(
            connection,
            key,
            attempt_id,
            expected_fold_revision=2,
            expected_attempt_revision=3,
            current_owner_token="new-owner",
        )
    assert _reason(exc_info.value) == "invalid_interrupted_attempt_lineage"

    connection.execute(
        """
        UPDATE experiment_attempt
        SET experiment_id=?, candidate_id=?, fold_id=?
        WHERE attempt_id='attempt-old'
        """,
        (str(key.experiment_id), str(key.candidate_id), str(key.fold_id)),
    )
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteAtomicDispatchMixin._load_interrupted_work(
            connection,
            key,
            attempt_id,
            expected_fold_revision=2,
            expected_attempt_revision=2,
            current_owner_token="new-owner",
        )
    assert _reason(exc_info.value) == "stale_projection_revision"

    with pytest.raises(ExperimentSpecError) as exc_info:
        SQLiteAtomicDispatchMixin._load_interrupted_work(
            connection,
            key,
            attempt_id,
            expected_fold_revision=2,
            expected_attempt_revision=3,
            current_owner_token="new-owner",
        )
    assert _reason(exc_info.value) == "interrupted_attempt_not_live"


def test_pause_requeue_preconditions_check_parent_fold_and_owner(
    connection: sqlite3.Connection,
) -> None:
    key = _key()

    with pytest.raises(AnalysisError) as exc_info:
        SQLiteAtomicDispatchMixin._validate_pause_requeue_preconditions(
            connection,
            key,
            2,
        )
    assert _reason(exc_info.value) == "experiment_not_found"

    connection.execute(
        "INSERT INTO experiment VALUES (?, 'pause_requested', 'pause')",
        (str(key.experiment_id),),
    )
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteAtomicDispatchMixin._validate_pause_requeue_preconditions(
            connection,
            key,
            2,
        )
    assert _reason(exc_info.value) == "fold_not_found"

    _insert_fold(connection, key)
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteAtomicDispatchMixin._validate_pause_requeue_preconditions(
            connection,
            key,
            1,
        )
    assert _reason(exc_info.value) == "stale_projection_revision"

    connection.execute("UPDATE experiment_fold SET status='queued'")
    with pytest.raises(ExperimentSpecError) as exc_info:
        SQLiteAtomicDispatchMixin._validate_pause_requeue_preconditions(
            connection,
            key,
            2,
        )
    assert _reason(exc_info.value) == "pause_requeue_fold_not_running"

    connection.execute(
        "UPDATE experiment_fold SET status='running', claim_owner_token=NULL"
    )
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteAtomicDispatchMixin._validate_pause_requeue_preconditions(
            connection,
            key,
            2,
        )
    assert _reason(exc_info.value) == "running_fold_missing_claim_owner"


def test_pause_requeue_detects_fold_compare_and_swap_loss(
    connection: sqlite3.Connection,
) -> None:
    key = _key()
    _insert_experiment(
        connection,
        key,
        status=ExperimentStatus.PAUSE_REQUESTED,
        desired_state=ExperimentDesiredState.PAUSE,
    )
    _insert_fold(connection, key)
    connection.executescript(
        """
        CREATE TRIGGER ignore_pause_requeue
        BEFORE UPDATE ON experiment_fold
        BEGIN
            SELECT RAISE(IGNORE);
        END;
        """
    )
    connection.commit()

    with pytest.raises(AnalysisError) as exc_info:
        _harness(connection).requeue_fold_for_pause(
            key,
            expected_fold_revision=2,
            lease_fence=_fence(key),
            now_epoch_us=1,
            occurred_at=NOW,
            detail={},
        )

    assert _reason(exc_info.value) == "stale_projection_revision"


def test_interrupted_requeue_detects_attempt_compare_and_swap_loss(
    connection: sqlite3.Connection,
) -> None:
    key = _key()
    _insert_fold(connection, key)
    _insert_attempt(
        connection,
        key,
        status=ExperimentStatus.QUEUED,
    )
    connection.executescript(
        """
        CREATE TRIGGER ignore_attempt_requeue
        BEFORE UPDATE ON experiment_attempt
        BEGIN
            SELECT RAISE(IGNORE);
        END;
        """
    )
    connection.commit()

    with pytest.raises(AnalysisError) as exc_info:
        _harness(connection).requeue_interrupted_fold(
            key,
            AttemptId("attempt-old"),
            expected_fold_revision=2,
            expected_attempt_revision=3,
            lease_fence=_fence(key),
            now_epoch_us=1,
            occurred_at=NOW,
            detail={},
        )

    assert _reason(exc_info.value) == "stale_projection_revision"


def test_interrupted_requeue_rolls_back_attempt_when_fold_cas_is_lost(
    connection: sqlite3.Connection,
) -> None:
    key = _key()
    _insert_fold(connection, key)
    _insert_attempt(
        connection,
        key,
        status=ExperimentStatus.QUEUED,
    )
    connection.executescript(
        """
        CREATE TRIGGER ignore_interrupted_fold_requeue
        BEFORE UPDATE ON experiment_fold
        BEGIN
            SELECT RAISE(IGNORE);
        END;
        """
    )
    connection.commit()

    with pytest.raises(AnalysisError) as exc_info:
        _harness(connection).requeue_interrupted_fold(
            key,
            AttemptId("attempt-old"),
            expected_fold_revision=2,
            expected_attempt_revision=3,
            lease_fence=_fence(key),
            now_epoch_us=1,
            occurred_at=NOW,
            detail={},
        )

    assert _reason(exc_info.value) == "stale_projection_revision"
    attempt = connection.execute(
        "SELECT status, revision FROM experiment_attempt WHERE attempt_id='attempt-old'"
    ).fetchone()
    assert attempt is not None
    assert (attempt["status"], attempt["revision"]) == ("queued", 3)


class _BrokenConnection:
    def __init__(self) -> None:
        self.rollback_count = 0

    def execute(self, _statement: str) -> None:
        raise sqlite3.OperationalError("database unavailable")

    def rollback(self) -> None:
        self.rollback_count += 1


def _broken_harness(
    connection: _BrokenConnection,
) -> SQLiteAtomicDispatchMixin:
    harness = SQLiteAtomicDispatchMixin()
    database = SimpleNamespace(get_connection=lambda: connection)
    harness._database = cast(
        "ResearchExperimentDatabase",
        cast("object", database),
    )
    return harness


def test_dispatch_operations_translate_sqlite_failures_after_rollback() -> None:
    connection = _BrokenConnection()
    harness = _broken_harness(connection)
    key = _key()
    fence = cast("LeaseFence", object())

    with pytest.raises(ExperimentPersistenceError) as exc_info:
        harness.claim_fold_and_add_attempt(
            key,
            _spec(key),
            cast("AttemptProjection", object()),
            expected_fold_revision=0,
            lease_fence=fence,
            now_epoch_us=0,
            occurred_at=NOW,
        )
    assert _reason(exc_info.value) == "atomic_dispatch_failed"

    with pytest.raises(ExperimentPersistenceError) as exc_info:
        harness.requeue_fold_for_pause(
            key,
            expected_fold_revision=0,
            lease_fence=fence,
            now_epoch_us=0,
            occurred_at=NOW,
            detail={},
        )
    assert _reason(exc_info.value) == "pause_requeue_failed"

    with pytest.raises(ExperimentPersistenceError) as exc_info:
        harness.requeue_interrupted_fold(
            key,
            AttemptId("attempt-old"),
            expected_fold_revision=0,
            expected_attempt_revision=0,
            lease_fence=fence,
            now_epoch_us=0,
            occurred_at=NOW,
            detail={},
        )
    assert _reason(exc_info.value) == "crash_recovery_failed"
    assert connection.rollback_count == 3


def test_pause_state_enum_matches_persisted_values_used_by_fixture() -> None:
    assert ExperimentStatus.PAUSE_REQUESTED.value == "pause_requested"
    assert ExperimentDesiredState.PAUSE.value == "pause"
