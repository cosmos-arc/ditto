"""Fail-closed persistence edges for atomic SQLite holdout selection."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from ditto_analysis.errors import AnalysisError
from ditto_analysis.experiments.holdout import (
    HoldoutClaimAuthorityCommand,
    HoldoutSelectionReason,
    holdout_request_payload,
)
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
    SnapshotId,
)
from ditto_analysis.experiments.persistence import (
    DateWindow,
    FoldKey,
    HoldoutClaimRecord,
    ResearchCycleIdentity,
)
from ditto_analysis.experiments.specs import ExperimentLaunchSpec
from ditto_analysis.storage.sqlite.experiments import _holdout
from ditto_analysis.storage.sqlite.experiments._holdout import (
    SQLiteHoldoutClaimMixin,
)
from ditto_analysis.storage.sqlite.experiments._writer_reader_port import (
    SQLiteExperimentWriterReaderPort,
)
from ditto_analysis.storage.sqlite.experiments.database import (
    ResearchExperimentDatabase,
)

NOW = datetime(2024, 1, 31, tzinfo=UTC)
HASH_A = ContentHash("a" * 64)
HASH_B = ContentHash("b" * 64)
HASH_C = ContentHash("c" * 64)


def _command(
    *,
    fingerprint: ContentHash | None = HASH_C,
    expected_revision: int = 1,
) -> HoldoutClaimAuthorityCommand:
    return HoldoutClaimAuthorityCommand(
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-1"),
        expected_revision=expected_revision,
        expected_selection_evidence_hash=HASH_A,
        operator_confirmation="confirmed",
        selection_reason=HoldoutSelectionReason("selected", "Best candidate"),
        resolved_reproduction_fingerprint=fingerprint,
        occurred_at=NOW,
    )


def _record(command: HoldoutClaimAuthorityCommand | None = None) -> HoldoutClaimRecord:
    command = _command() if command is None else command
    fingerprint = command.resolved_reproduction_fingerprint
    assert fingerprint is not None
    cycle = ResearchCycleIdentity("cycle-1", HASH_B)
    fold_key = FoldKey(
        command.experiment_id,
        command.candidate_id,
        FoldId("holdout-1"),
    )
    claim_id = _holdout._claim_id(cycle)
    return HoldoutClaimRecord(
        claim_id=claim_id,
        cycle=cycle,
        fold_key=fold_key,
        resolved_spec_hash=HASH_A,
        parameters_hash=HASH_B,
        snapshot_id=SnapshotId("snapshot-1"),
        window=DateWindow(date(2024, 1, 1), date(2024, 1, 31)),
        reproduction_fingerprint=fingerprint,
        logical_run_id=_holdout._logical_run_id(claim_id, fold_key, fingerprint),
        operator_confirmation=command.operator_confirmation,
        selection_reason=holdout_request_payload(command),
        claimed_at=command.occurred_at,
    )


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE experiment(
            experiment_id TEXT PRIMARY KEY,
            research_cycle_id TEXT,
            research_cycle_hash TEXT,
            revision INTEGER,
            status TEXT,
            desired_state TEXT,
            stage TEXT,
            updated_at_epoch_us INTEGER
        );
        CREATE TABLE experiment_candidate(
            experiment_id TEXT,
            candidate_id TEXT,
            parameters_hash TEXT
        );
        CREATE TABLE experiment_fold(
            experiment_id TEXT,
            candidate_id TEXT,
            fold_id TEXT,
            fold_role TEXT,
            ordinal INTEGER,
            status TEXT,
            claim_owner_token TEXT,
            revision INTEGER,
            test_start TEXT,
            test_end TEXT,
            updated_at_epoch_us INTEGER
        );
        CREATE TABLE experiment_attempt(
            attempt_id TEXT,
            experiment_id TEXT,
            candidate_id TEXT,
            fold_id TEXT,
            status TEXT
        );
        CREATE TABLE holdout_claim(
            claim_id TEXT,
            research_cycle_id TEXT,
            research_cycle_hash TEXT,
            experiment_id TEXT,
            candidate_id TEXT,
            fold_id TEXT,
            fold_role TEXT,
            resolved_spec_hash TEXT,
            parameters_hash TEXT,
            snapshot_id TEXT,
            window_start TEXT,
            window_end TEXT,
            reproduction_fingerprint TEXT,
            logical_run_id TEXT,
            operator_confirmation TEXT,
            selection_reason_json TEXT,
            claim_payload_hash TEXT,
            claimed_at_epoch_us INTEGER
        );
        CREATE TABLE experiment_status_event(event_id TEXT);
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


def _reason(error: AnalysisError) -> object:
    return error.details["reason_code"]


def _harness(
    connection: sqlite3.Connection,
    *,
    launch: object | None = None,
) -> SQLiteHoldoutClaimMixin:
    harness = SQLiteHoldoutClaimMixin()
    harness._database = cast(
        "ResearchExperimentDatabase",
        cast("object", SimpleNamespace(get_connection=lambda: connection)),
    )
    harness._reader = cast(
        "SQLiteExperimentWriterReaderPort",
        cast(
            "object",
            SimpleNamespace(get_launch_spec=lambda _experiment_id: launch),
        ),
    )
    return harness


def _insert_experiment(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO experiment VALUES (
            'experiment-1', 'cycle-1', ?, 1,
            'running', 'run', 'candidate_selection', 0
        )
        """,
        (str(HASH_B),),
    )


def _insert_fold(
    connection: sqlite3.Connection,
    *,
    candidate_id: str,
    fold_id: str,
    fold_role: str,
    ordinal: int,
    status: str,
    owner: str | None = None,
    revision: int = 0,
) -> None:
    connection.execute(
        """
        INSERT INTO experiment_fold VALUES (
            'experiment-1', ?, ?, ?, ?, ?, ?, ?,
            '2024-01-01', '2024-01-31', 0
        )
        """,
        (candidate_id, fold_id, fold_role, ordinal, status, owner, revision),
    )


def test_claim_row_rejects_invalid_json_and_nonobject_payload(
    connection: sqlite3.Connection,
) -> None:
    invalid_json = connection.execute("SELECT '{' AS selection_reason_json").fetchone()
    with pytest.raises(AnalysisError) as exc_info:
        _holdout.holdout_claim_from_row(invalid_json)
    assert _reason(exc_info.value) == "holdout_claim_payload_invalid"

    nonobject = connection.execute("SELECT '[]' AS selection_reason_json").fetchone()
    with pytest.raises(AnalysisError) as exc_info:
        _holdout.holdout_claim_from_row(nonobject)
    assert _reason(exc_info.value) == "holdout_claim_payload_invalid"


def test_claim_row_rejects_payload_hash_drift(
    connection: sqlite3.Connection,
) -> None:
    _holdout.SQLiteHoldoutClaimMixin._insert_claim(connection, _record())
    connection.execute("UPDATE holdout_claim SET claim_payload_hash=?", (str(HASH_C),))
    row = connection.execute("SELECT * FROM holdout_claim").fetchone()

    with pytest.raises(AnalysisError) as exc_info:
        _holdout.holdout_claim_from_row(row)

    assert _reason(exc_info.value) == "holdout_claim_hash_mismatch"


def test_event_detail_extension_cannot_replace_canonical_identity() -> None:
    with pytest.raises(AnalysisError) as exc_info:
        _holdout._event_detail(_record(), {"claim_id": "replacement"})

    assert _reason(exc_info.value) == "holdout_event_detail_extension_conflict"


def test_resolved_holdout_rows_reject_ambiguous_and_nonpristine_rows(
    connection: sqlite3.Connection,
) -> None:
    candidate_id = CandidateId("candidate-1")
    with pytest.raises(AnalysisError) as exc_info:
        _holdout._resolved_holdout_rows(connection, (), candidate_id)
    assert _reason(exc_info.value) == "holdout_fold_ambiguous"

    _insert_fold(
        connection,
        candidate_id="candidate-1",
        fold_id="holdout-1",
        fold_role="holdout",
        ordinal=1,
        status="running",
        owner="owner",
    )
    selected = tuple(connection.execute("SELECT * FROM experiment_fold").fetchall())
    with pytest.raises(AnalysisError) as exc_info:
        _holdout._resolved_holdout_rows(connection, selected, candidate_id)
    assert _reason(exc_info.value) == "holdout_fold_not_pristine"

    connection.execute("DELETE FROM experiment_fold")
    _insert_fold(
        connection,
        candidate_id="candidate-1",
        fold_id="holdout-1",
        fold_role="holdout",
        ordinal=1,
        status="queued",
    )
    _insert_fold(
        connection,
        candidate_id="candidate-2",
        fold_id="holdout-2",
        fold_role="holdout",
        ordinal=2,
        status="running",
        owner="owner",
    )
    rows = tuple(connection.execute("SELECT * FROM experiment_fold").fetchall())
    with pytest.raises(AnalysisError) as exc_info:
        _holdout._resolved_holdout_rows(connection, rows, candidate_id)
    assert _reason(exc_info.value) == "holdout_fold_not_pristine"


def test_matching_claims_handles_missing_experiment_and_uniqueness_drift(
    connection: sqlite3.Connection,
) -> None:
    command = _command()
    assert SQLiteHoldoutClaimMixin._matching_claims(connection, command, None) == ()

    connection.execute(
        """
        INSERT INTO holdout_claim(claim_id, experiment_id)
        VALUES ('one', 'experiment-1')
        """
    )
    connection.execute(
        """
        INSERT INTO holdout_claim(claim_id, experiment_id)
        VALUES ('two', 'experiment-1')
        """
    )
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteHoldoutClaimMixin._matching_claims(connection, command, None)
    assert _reason(exc_info.value) == "holdout_claim_uniqueness_drift"


def test_exact_replay_requires_its_canonical_event(
    connection: sqlite3.Connection,
) -> None:
    command = _command()
    _holdout.SQLiteHoldoutClaimMixin._insert_claim(connection, _record(command))
    row = connection.execute("SELECT * FROM holdout_claim").fetchone()
    assert row is not None

    with pytest.raises(AnalysisError) as exc_info:
        SQLiteHoldoutClaimMixin._exact_replay(connection, command, (row,))

    assert _reason(exc_info.value) == "holdout_claim_event_drift"


def test_new_claim_requires_experiment_launch_and_fingerprint(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(AnalysisError) as exc_info:
        _harness(connection).claim_holdout_candidate(
            _command(),
            lease_fence=None,
            now_epoch_us=None,
        )
    assert _reason(exc_info.value) == "experiment_not_found"

    _insert_experiment(connection)
    connection.commit()
    monkeypatch.setattr(_holdout, "validate_holdout_preflight", lambda *_args: object())
    monkeypatch.setattr(
        _holdout,
        "find_holdout_consumption_conflict",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        SQLiteHoldoutClaimMixin,
        "_validate_new_authority",
        lambda *_args: None,
    )
    with pytest.raises(AnalysisError) as exc_info:
        _harness(connection).claim_holdout_candidate(
            _command(),
            lease_fence=None,
            now_epoch_us=None,
        )
    assert _reason(exc_info.value) == "launch_spec_missing"

    launch = cast("ExperimentLaunchSpec", object())
    monkeypatch.setattr(
        SQLiteHoldoutClaimMixin,
        "_resolve_selection",
        lambda *_args: (object(), object(), object(), ()),
    )
    with pytest.raises(AnalysisError) as exc_info:
        _harness(connection, launch=launch).claim_holdout_candidate(
            _command(fingerprint=None),
            lease_fence=None,
            now_epoch_us=None,
        )
    assert _reason(exc_info.value) == "holdout_fingerprint_required"


def test_existing_consumption_conflict_is_reported_before_new_authority(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _insert_experiment(connection)
    connection.commit()
    conflict = _record()
    monkeypatch.setattr(_holdout, "validate_holdout_preflight", lambda *_args: object())
    monkeypatch.setattr(
        _holdout,
        "find_holdout_consumption_conflict",
        lambda *_args: conflict,
    )

    with pytest.raises(AnalysisError) as exc_info:
        _harness(connection).claim_holdout_candidate(
            _command(),
            lease_fence=None,
            now_epoch_us=None,
        )

    assert _reason(exc_info.value) == "holdout_consumption_already_claimed"


def _launch() -> ExperimentLaunchSpec:
    candidate = SimpleNamespace(
        candidate_id=CandidateId("candidate-1"),
        parameter_hash=HASH_B,
    )
    binding = SimpleNamespace(
        candidate_id=CandidateId("candidate-1"),
        parameter_hash=HASH_B,
        resolved_spec_hash=HASH_A,
    )
    return cast(
        "ExperimentLaunchSpec",
        cast(
            "object",
            SimpleNamespace(
                candidates=(candidate,),
                execution_bindings=(binding,),
                snapshot_id=SnapshotId("snapshot-1"),
            ),
        ),
    )


def test_selection_resolution_checks_every_frozen_relational_boundary(
    connection: sqlite3.Connection,
) -> None:
    command = _command()
    empty_launch = cast(
        "ExperimentLaunchSpec",
        cast("object", SimpleNamespace(candidates=(), execution_bindings=())),
    )
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteHoldoutClaimMixin._resolve_selection(connection, command, empty_launch)
    assert _reason(exc_info.value) == "holdout_candidate_invalid"

    launch = _launch()
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteHoldoutClaimMixin._resolve_selection(connection, command, launch)
    assert _reason(exc_info.value) == "holdout_candidate_binding_drift"

    connection.execute(
        "INSERT INTO experiment_candidate VALUES ('experiment-1', 'candidate-1', ?)",
        (str(HASH_B),),
    )
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteHoldoutClaimMixin._resolve_selection(connection, command, launch)
    assert _reason(exc_info.value) == "holdout_candidate_not_completed"

    _insert_fold(
        connection,
        candidate_id="candidate-1",
        fold_id="prior-1",
        fold_role="walk_forward",
        ordinal=1,
        status="completed",
    )
    _insert_fold(
        connection,
        candidate_id="candidate-2",
        fold_id="prior-2",
        fold_role="walk_forward",
        ordinal=1,
        status="queued",
    )
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteHoldoutClaimMixin._resolve_selection(connection, command, launch)
    assert _reason(exc_info.value) == "holdout_preselection_incomplete"

    connection.execute(
        "UPDATE experiment_fold SET status='completed' WHERE candidate_id='candidate-2'"
    )
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteHoldoutClaimMixin._resolve_selection(connection, command, launch)
    assert _reason(exc_info.value) == "holdout_fold_cardinality_drift"

    _insert_fold(
        connection,
        candidate_id="candidate-1",
        fold_id="holdout-1",
        fold_role="holdout",
        ordinal=2,
        status="queued",
    )
    connection.execute(
        """
        INSERT INTO experiment_attempt VALUES (
            'attempt-1', 'experiment-1', 'candidate-1', 'holdout-1', 'queued'
        )
        """
    )
    with pytest.raises(AnalysisError) as exc_info:
        SQLiteHoldoutClaimMixin._resolve_selection(connection, command, launch)
    assert _reason(exc_info.value) == "holdout_attempt_before_claim"


def test_claim_stage_compare_and_swap_rolls_back_inserted_claim(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = _command()
    launch = _launch()
    candidate = launch.candidates[0]
    binding = launch.execution_bindings[0]
    selected = {
        "fold_id": "holdout-1",
        "test_start": "2024-01-01",
        "test_end": "2024-01-31",
    }
    _insert_experiment(connection)
    connection.executescript(
        """
        CREATE TRIGGER ignore_holdout_stage
        BEFORE UPDATE ON experiment
        BEGIN
            SELECT RAISE(IGNORE);
        END;
        """
    )
    connection.commit()
    monkeypatch.setattr(_holdout, "validate_holdout_preflight", lambda *_args: object())
    monkeypatch.setattr(
        _holdout,
        "find_holdout_consumption_conflict",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        SQLiteHoldoutClaimMixin,
        "_validate_new_authority",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        SQLiteHoldoutClaimMixin,
        "_resolve_selection",
        lambda *_args: (candidate, binding, selected, ()),
    )

    with pytest.raises(AnalysisError) as exc_info:
        _harness(connection, launch=launch).claim_holdout_candidate(
            command,
            lease_fence=None,
            now_epoch_us=None,
        )

    assert _reason(exc_info.value) == "stale_projection_revision"
    assert connection.execute("SELECT count(*) FROM holdout_claim").fetchone()[0] == 0


def test_unselected_cancellation_detects_compare_and_swap_loss(
    connection: sqlite3.Connection,
) -> None:
    _insert_fold(
        connection,
        candidate_id="candidate-2",
        fold_id="holdout-2",
        fold_role="holdout",
        ordinal=2,
        status="queued",
    )
    fold = connection.execute("SELECT * FROM experiment_fold").fetchone()
    assert fold is not None
    connection.executescript(
        """
        CREATE TRIGGER ignore_holdout_cancel
        BEFORE UPDATE ON experiment_fold
        BEGIN
            SELECT RAISE(IGNORE);
        END;
        """
    )

    with pytest.raises(AnalysisError) as exc_info:
        _harness(connection)._cancel_unselected(connection, _record(), (fold,))

    assert _reason(exc_info.value) == "holdout_unselected_fold_conflict"
