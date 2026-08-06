"""Canonical preflight authority validation for sealed holdout access."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import cast

from ditto_analysis.errors import AnalysisError, ExperimentIntegrityError
from ditto_analysis.experiments._time import epoch_us as _epoch_us
from ditto_analysis.experiments.models import (
    ContentHash,
    ExperimentDesiredState,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
)
from ditto_analysis.experiments.persistence import (
    canonical_payload,
    decode_launch_spec,
    encode_launch_spec,
)
from ditto_analysis.experiments.preflight_authority import (
    DecodedPreflightAuthority,
    decode_preflight_authority,
)
from ditto_analysis.experiments.specs import ExperimentLaunchSpec
from ditto_analysis.storage.sqlite.experiments._enqueue_fence import (
    fold_fence_from_row,
    gate_fence_from_row,
)
from ditto_analysis.storage.sqlite.experiments._events import (
    canonical_status_event_id,
)


def _integrity(
    message: str,
    reason_code: str = "holdout_preflight_authority_invalid",
) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(
        message,
        details={"reason_code": reason_code},
    )


def _validated_authority_event(
    connection: sqlite3.Connection,
    experiment_id: ExperimentId,
) -> DecodedPreflightAuthority:
    events = connection.execute(
        """
        SELECT * FROM experiment_status_event
        WHERE experiment_id=? AND subject_type='experiment'
          AND reason_code='preflight_passed'
        ORDER BY subject_revision, event_id
        """,
        (str(experiment_id),),
    ).fetchall()
    if len(events) != 1:
        raise _integrity("canonical preflight authority is missing or ambiguous")
    event = events[0]
    try:
        detail = json.loads(event["detail_json"])
    except json.JSONDecodeError as exc:
        raise _integrity("preflight authority payload is invalid") from exc
    if not isinstance(detail, dict):
        raise _integrity("preflight authority payload is not an object")
    detail_mapping = cast("Mapping[str, object]", detail)
    canonical = canonical_payload(detail_mapping)
    canonical_event_id = canonical_status_event_id(
        subject_type="experiment",
        experiment_id=str(experiment_id),
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        revision=event["subject_revision"],
    )
    if (
        canonical.json_bytes.decode("utf-8") != event["detail_json"]
        or str(canonical.content_hash) != event["detail_hash"]
        or event["event_id"] != canonical_event_id
        or event["previous_status"]
        not in {ExperimentStatus.DRAFT.value, ExperimentStatus.BLOCKED.value}
        or event["status"] != ExperimentStatus.QUEUED.value
        or event["desired_state"] != ExperimentDesiredState.RUN.value
        or event["stage"] != ExperimentStage.PREFLIGHT.value
        or event["failure_code"] is not None
    ):
        raise _integrity("preflight authority is absent, restricted, or drifted")
    try:
        authority = decode_preflight_authority(detail_mapping)
    except AnalysisError as exc:
        raise _integrity("preflight authority cannot be reconstructed") from exc
    if authority.status != "ready" or authority.detail_hash != canonical.content_hash:
        raise _integrity("preflight authority is not ready or content-addressed")
    return authority


def _validated_launch(
    connection: sqlite3.Connection,
    experiment_id: ExperimentId,
    authority: DecodedPreflightAuthority,
) -> ExperimentLaunchSpec:
    experiment = connection.execute(
        "SELECT * FROM experiment WHERE experiment_id=?",
        (str(experiment_id),),
    ).fetchone()
    if experiment is None:
        raise _integrity("preflight experiment is missing")
    try:
        launch = decode_launch_spec(
            experiment["launch_spec_json"].encode("utf-8"),
            ContentHash(experiment["launch_spec_hash"]),
        )
        canonical_launch = encode_launch_spec(launch)
    except (AnalysisError, UnicodeError, ValueError) as exc:
        raise _integrity("preflight launch cannot be reconstructed") from exc
    expected_strategy_version = (
        f"{authority.strategy_family_id}@{authority.strategy_version}"
    )
    if (
        canonical_launch.json_bytes.decode("utf-8") != experiment["launch_spec_json"]
        or canonical_launch.content_hash != authority.launch_spec_hash
        or experiment["launch_spec_hash"] != str(authority.launch_spec_hash)
        or experiment["research_cycle_id"] != authority.research_cycle_id
        or experiment["research_cycle_hash"] != str(authority.research_cycle_hash)
        or experiment["strategy_version"] != expected_strategy_version
        or str(launch.strategy_version) != expected_strategy_version
        or experiment["snapshot_id"] != authority.snapshot_id
        or str(launch.snapshot_id) != authority.snapshot_id
        or launch.fold_protocol.protocol_id != authority.fold_protocol_id
        or launch.fold_protocol.protocol_version != authority.fold_protocol_version
        or launch.fold_protocol.protocol_hash != authority.fold_protocol_hash
    ):
        raise _integrity("preflight launch, cycle, or snapshot linkage drifted")
    return launch


def _validate_gate_links(
    connection: sqlite3.Connection,
    experiment_id: ExperimentId,
    launch: ExperimentLaunchSpec,
    authority: DecodedPreflightAuthority,
) -> None:
    gate_rows = connection.execute(
        "SELECT * FROM gate_evaluation WHERE experiment_id=?",
        (str(experiment_id),),
    ).fetchall()
    gate_by_id = {row["evaluation_id"]: row for row in gate_rows}
    expected_gate_ids = tuple(
        f"{experiment_id}:preflight:{index}:{check.rule_id}"
        for index, check in enumerate(authority.gate_checks, start=1)
    )
    if (
        len(gate_rows) != len(expected_gate_ids)
        or len(gate_by_id) != len(expected_gate_ids)
        or set(gate_by_id) != set(expected_gate_ids)
    ):
        raise _integrity("preflight gate set drifted")
    actual_gate_hashes: list[ContentHash] = []
    for event_id, check in zip(expected_gate_ids, authority.gate_checks, strict=True):
        row = gate_by_id[event_id]
        if (
            row["experiment_id"] != str(experiment_id)
            or row["candidate_id"] is not None
            or row["fold_id"] is not None
            or row["attempt_id"] is not None
            or row["rule_id"] != check.rule_id
            or row["policy_version"] != authority.policy_version
            or row["layer"] != "hard"
            or row["outcome"] != check.outcome
            or row["observed_json"] != check.observed_json
            or row["policy_json"] != check.policy_json
            or row["artifact_id"] is not None
            or row["evaluated_at_epoch_us"] != _epoch_us(launch.created_at)
        ):
            raise _integrity("preflight gate linkage drifted")
        actual_gate_hashes.append(gate_fence_from_row(row).payload_hash)
    if tuple(actual_gate_hashes) != authority.gate_payload_hashes:
        raise _integrity("preflight gate payload hashes drifted")


def _ordered_fold_rows(
    connection: sqlite3.Connection,
    experiment_id: ExperimentId,
    launch: ExperimentLaunchSpec,
    authority: DecodedPreflightAuthority,
) -> tuple[sqlite3.Row, ...]:
    fold_rows = connection.execute(
        """
        SELECT * FROM experiment_fold WHERE experiment_id=?
        ORDER BY candidate_id, ordinal, fold_id
        """,
        (str(experiment_id),),
    ).fetchall()
    rows_by_candidate = {
        str(candidate.candidate_id): tuple(
            row
            for row in fold_rows
            if row["candidate_id"] == str(candidate.candidate_id)
        )
        for candidate in launch.candidates
    }
    if any(not rows for rows in rows_by_candidate.values()):
        raise _integrity("preflight fold candidate set drifted")
    holdouts = tuple(row for row in fold_rows if row["fold_role"] == "holdout")
    if len(holdouts) != len(launch.candidates):
        raise _integrity(
            "holdout fold cardinality differs from frozen candidates",
            "holdout_fold_cardinality_drift",
        )
    ordered_rows = tuple(
        row
        for candidate in launch.candidates
        for row in sorted(
            rows_by_candidate[str(candidate.candidate_id)],
            key=lambda item: (item["ordinal"], item["fold_id"]),
        )
    )
    if len(ordered_rows) != len(fold_rows):
        raise _integrity("preflight fold set contains an unknown candidate")
    canonical_hash_rows = tuple(
        row for row in ordered_rows if row["fold_role"] != "holdout"
    ) + tuple(row for row in ordered_rows if row["fold_role"] == "holdout")
    actual_fold_hashes = tuple(
        fold_fence_from_row(row).payload_hash for row in canonical_hash_rows
    )
    if actual_fold_hashes != authority.fold_payload_hashes:
        raise _integrity("preflight fold payload hashes drifted")
    return ordered_rows


def _validate_fold_links(
    rows: tuple[sqlite3.Row, ...],
    launch: ExperimentLaunchSpec,
    authority: DecodedPreflightAuthority,
) -> None:
    expected_folds = authority.fold_authorities
    for candidate in launch.candidates:
        candidate_rows = tuple(
            row for row in rows if row["candidate_id"] == str(candidate.candidate_id)
        )
        if len(candidate_rows) != len(expected_folds):
            raise _integrity("preflight candidate fold plan is incomplete")
        for row, expected in zip(candidate_rows, expected_folds, strict=True):
            expected_train_start = (
                None
                if expected.train_window is None
                else expected.train_window.start.isoformat()
            )
            expected_train_end = (
                None
                if expected.train_window is None
                else expected.train_window.end.isoformat()
            )
            if (
                row["ordinal"] != expected.ordinal
                or row["fold_role"] != expected.role
                or row["train_start"] != expected_train_start
                or row["train_end"] != expected_train_end
                or row["test_start"] != expected.test_window.start.isoformat()
                or row["test_end"] != expected.test_window.end.isoformat()
                or row["purge_sessions"] != expected.purge_sessions
                or row["embargo_sessions"] != expected.embargo_sessions
            ):
                raise _integrity("preflight fold plan linkage drifted")


def validate_holdout_preflight(
    connection: sqlite3.Connection,
    experiment_id: ExperimentId,
) -> DecodedPreflightAuthority:
    """Reconstruct full preflight authority and bind it to immutable SQL rows."""
    authority = _validated_authority_event(connection, experiment_id)
    launch = _validated_launch(connection, experiment_id, authority)
    _validate_gate_links(connection, experiment_id, launch, authority)
    rows = _ordered_fold_rows(connection, experiment_id, launch, authority)
    _validate_fold_links(rows, launch, authority)
    return authority
