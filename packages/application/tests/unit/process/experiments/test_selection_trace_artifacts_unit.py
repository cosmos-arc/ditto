"""Contract tests for attempt-scoped durable selection-trace artifacts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from io import BytesIO

import polars as pl
import pytest
from ditto_analysis.experiments import (
    ArtifactRecord,
    AttemptId,
    BacktestRunId,
    CandidateId,
    ContentHash,
    DateWindow,
    ExperimentId,
    FoldId,
)
from ditto_analysis.experiments.artifact_manifest import (
    ArtifactFormat,
    ArtifactManifest,
    ArtifactPublicationSpec,
)
from ditto_analysis.research.artifact_measurement import measure_parquet_bytes
from ditto_application.processes.execution.backtest_serialization import (
    serialize_selection_evidence,
)
from ditto_application.processes.experiments._fold_selection_trace_artifact_validation import (  # noqa: E501
    FoldSelectionTraceArtifactValidationError,
    validate_fold_selection_trace_artifacts,
)
from ditto_application.processes.experiments._fold_selection_trace_artifacts import (
    FOLD_SELECTION_TRACE_ARTIFACT_KINDS,
    FoldSelectionTraceArtifactIdentity,
    FoldSelectionTraceArtifactKind,
    FoldSelectionTraceArtifactReceipt,
)
from ditto_strategy.alpha.selection_evidence import (
    InitialUniverseEvidence,
    SelectionEvidenceLog,
)

NOW = datetime(2026, 7, 28, 1, 2, 3, 456789, tzinfo=UTC)


def _identity() -> FoldSelectionTraceArtifactIdentity:
    return FoldSelectionTraceArtifactIdentity(
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId("fold-1"),
        attempt_id=AttemptId("attempt-1"),
        attempt_created_at=NOW,
        run_id=BacktestRunId("run-1"),
        test_window=DateWindow(date(2026, 7, 1), date(2026, 7, 31)),
        reproduction_fingerprint=ContentHash("a" * 64),
    )


def _measurement(frame: pl.DataFrame):
    buffer = BytesIO()
    frame.write_parquet(buffer)
    return measure_parquet_bytes(buffer.getvalue())


def _record(identity, kind, frame: pl.DataFrame) -> ArtifactRecord:
    measurement = _measurement(frame)
    return ArtifactManifest.create(
        spec=ArtifactPublicationSpec(
            artifact_id=identity.artifact_id(kind),
            experiment_id=identity.experiment_id,
            candidate_id=identity.candidate_id,
            fold_id=identity.fold_id,
            attempt_id=identity.attempt_id,
            artifact_kind=kind.value,
            relative_path=identity.relative_path(kind),
            reproduction_fingerprint=identity.reproduction_fingerprint,
            audit=identity.audit(kind),
            created_at=identity.attempt_created_at,
        ),
        artifact_format=ArtifactFormat.PARQUET,
        content_hash=measurement.content_hash,
        schema_hash=measurement.schema_hash,
        row_count=measurement.row_count,
        byte_size=measurement.byte_size,
    ).to_record()


def _receipt(
    identity: FoldSelectionTraceArtifactIdentity,
    log: SelectionEvidenceLog,
) -> FoldSelectionTraceArtifactReceipt:
    tables = serialize_selection_evidence(str(identity.run_id), log)
    return FoldSelectionTraceArtifactReceipt(
        candidate_universe=_record(
            identity,
            FoldSelectionTraceArtifactKind.CANDIDATE_UNIVERSE,
            tables["initial_universe_evidence"],
        ),
        candidate_exclusions=_record(
            identity,
            FoldSelectionTraceArtifactKind.CANDIDATE_EXCLUSIONS,
            tables["exclusion_evidence"],
        ),
        candidate_selections=_record(
            identity,
            FoldSelectionTraceArtifactKind.CANDIDATE_SELECTIONS,
            tables["selection_evidence"],
        ),
        factor_contributions=_record(
            identity,
            FoldSelectionTraceArtifactKind.FACTOR_CONTRIBUTIONS,
            tables["factor_contribution_evidence"],
        ),
    )


def test_selection_trace_identity_derives_four_unique_versioned_artifacts() -> None:
    identity = _identity()
    artifact_ids = tuple(
        identity.artifact_id(kind) for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS
    )
    paths = tuple(
        identity.relative_path(kind) for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS
    )

    assert len(FOLD_SELECTION_TRACE_ARTIFACT_KINDS) == 4
    assert len(set(artifact_ids)) == 4
    assert len(set(paths)) == 4
    assert all(
        kind.value.startswith("fold_selection_trace_") and kind.value.endswith("_v1")
        for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS
    )
    assert all(
        kind.value != "selection_evidence"
        for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS
    )
    assert all(
        path.startswith(
            "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
            "attempts/attempt-1/"
        )
        and path.endswith(".parquet")
        for path in paths
    )


def test_selection_trace_identity_binds_run_time_and_reproduction() -> None:
    identity = _identity()
    kind = FoldSelectionTraceArtifactKind.CANDIDATE_SELECTIONS

    assert identity.artifact_id(kind) != replace(
        identity,
        run_id=BacktestRunId("run-2"),
    ).artifact_id(kind)
    assert identity.artifact_id(kind) != replace(
        identity,
        attempt_created_at=datetime(2026, 7, 28, 1, 2, 4, tzinfo=UTC),
    ).artifact_id(kind)
    assert identity.artifact_id(kind) != replace(
        identity,
        reproduction_fingerprint=ContentHash("b" * 64),
    ).artifact_id(kind)
    assert identity.artifact_id(kind) != replace(
        identity,
        test_window=DateWindow(date(2026, 8, 1), date(2026, 8, 31)),
    ).artifact_id(kind)
    assert identity.audit(kind)["test_window"] == {
        "start": "2026-07-01",
        "end": "2026-07-31",
    }


def test_empty_selection_trace_is_four_existing_verified_artifacts() -> None:
    identity = _identity()
    receipt = _receipt(identity, SelectionEvidenceLog())

    validated = validate_fold_selection_trace_artifacts(
        identity,
        SelectionEvidenceLog(),
        receipt,
    )

    assert validated is receipt
    assert len(validated.records) == 4
    assert all(record.row_count == 0 for record in validated.records)


def test_selection_trace_validation_rejects_one_wrong_receipt() -> None:
    identity = _identity()
    receipt = _receipt(identity, SelectionEvidenceLog())
    wrong = replace(
        receipt,
        candidate_selections=replace(
            receipt.candidate_selections,
            content_hash=ContentHash("f" * 64),
        ),
    )

    with pytest.raises(FoldSelectionTraceArtifactValidationError) as exc_info:
        validate_fold_selection_trace_artifacts(
            identity,
            SelectionEvidenceLog(),
            wrong,
        )

    assert exc_info.value.reason == "selection_trace_content_hash_drift"


@pytest.mark.parametrize(
    ("record_transform", "expected_reason"),
    [
        (
            lambda record: replace(record, manifest={}),
            "fold_selection_trace_artifact_manifest_drift",
        ),
        (
            lambda record: replace(
                record,
                schema_hash=ContentHash("b" * 64),
            ),
            "selection_trace_schema_fingerprint_drift",
        ),
        (
            lambda record: replace(record, row_count=record.row_count + 1),
            "selection_trace_row_count_drift",
        ),
        (
            lambda record: replace(record, byte_size=record.byte_size + 1),
            "selection_trace_byte_size_drift",
        ),
        (
            lambda record: replace(record, artifact_id="drifted-artifact-id"),
            "fold_selection_trace_artifact_identity_drift",
        ),
        (
            lambda record: replace(
                record,
                relative_path=record.relative_path.replace(
                    "candidate_universe.parquet",
                    "drifted.parquet",
                ),
            ),
            "fold_selection_trace_artifact_identity_drift",
        ),
    ],
    ids=("manifest", "schema", "row", "byte", "artifact-id", "path"),
)
def test_selection_trace_validation_rejects_each_receipt_drift_branch(
    record_transform: Callable[[ArtifactRecord], ArtifactRecord],
    expected_reason: str,
) -> None:
    identity = _identity()
    log = SelectionEvidenceLog()
    receipt = _receipt(identity, log)
    wrong = replace(
        receipt,
        candidate_universe=record_transform(receipt.candidate_universe),
    )

    with pytest.raises(FoldSelectionTraceArtifactValidationError) as exc_info:
        validate_fold_selection_trace_artifacts(identity, log, wrong)

    assert exc_info.value.reason == expected_reason


def test_selection_trace_validation_rejects_poisoned_event_before_receipt_diff() -> (
    None
):
    identity = _identity()
    event = InitialUniverseEvidence(
        trade_date="2026-07-28",
        instrument_id=1,
        ordinal=1,
    )
    log = SelectionEvidenceLog(initial_universe=(event,))
    receipt = _receipt(identity, log)
    object.__setattr__(event, "trade_date", "20260728")

    with pytest.raises(FoldSelectionTraceArtifactValidationError) as exc_info:
        validate_fold_selection_trace_artifacts(identity, log, receipt)

    assert exc_info.value.reason == "invalid_fold_selection_trace_evidence"


def test_selection_trace_validation_rejects_trade_date_outside_test_window() -> None:
    identity = _identity()
    log = SelectionEvidenceLog(
        initial_universe=(
            InitialUniverseEvidence(
                trade_date="2026-08-01",
                instrument_id="000001.SZ",
                ordinal=1,
            ),
        ),
    )
    receipt = _receipt(identity, log)

    with pytest.raises(FoldSelectionTraceArtifactValidationError) as exc_info:
        validate_fold_selection_trace_artifacts(identity, log, receipt)

    assert exc_info.value.reason == "selection_trace_trade_date_outside_test_window"


@pytest.mark.parametrize("receipt", [None, object()])
def test_selection_trace_validation_rejects_missing_or_untyped_receipt(
    receipt: object,
) -> None:
    with pytest.raises(FoldSelectionTraceArtifactValidationError) as exc_info:
        validate_fold_selection_trace_artifacts(
            _identity(),
            SelectionEvidenceLog(),
            receipt,
        )

    assert exc_info.value.reason == "invalid_selection_trace_artifact_receipt"
