"""Content-addressed experiment artifact manifest contract tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ditto_analysis.errors import ExperimentIntegrityError, ExperimentSpecError
from ditto_analysis.experiments.artifact_manifest import (
    ArtifactFormat,
    ArtifactManifest,
    ArtifactPublicationSpec,
)
from ditto_analysis.experiments.models import (
    AttemptId,
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
)

NOW = datetime(2026, 7, 23, 1, 2, 3, 456789, tzinfo=UTC)


def _spec(**changes: object) -> ArtifactPublicationSpec:
    values: dict[str, object] = {
        "artifact_id": "artifact-attempt-1-nav",
        "experiment_id": ExperimentId("experiment-1"),
        "candidate_id": CandidateId("candidate-1"),
        "fold_id": FoldId("fold-1"),
        "attempt_id": AttemptId("attempt-1"),
        "artifact_kind": "nav",
        "relative_path": (
            "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
            "attempts/attempt-1/nav.parquet"
        ),
        "reproduction_fingerprint": ContentHash("a" * 64),
        "audit": {
            "run_id": "run-1",
            "attempt_id": "attempt-1",
            "created_at": "2026-07-23T01:02:03.456789Z",
        },
        "created_at": NOW,
    }
    values.update(changes)
    return ArtifactPublicationSpec(**values)  # type: ignore[arg-type]


def _manifest() -> ArtifactManifest:
    return ArtifactManifest.create(
        spec=_spec(),
        artifact_format=ArtifactFormat.PARQUET,
        content_hash=ContentHash("b" * 64),
        schema_hash=ContentHash("c" * 64),
        row_count=2,
        byte_size=128,
    )


def test_manifest_round_trips_complete_index_record() -> None:
    manifest = _manifest()
    record = manifest.to_record()

    assert record.artifact_id == "artifact-attempt-1-nav"
    assert record.content_hash == ContentHash("b" * 64)
    assert record.schema_hash == ContentHash("c" * 64)
    assert record.row_count == 2
    assert record.byte_size == 128
    assert record.reproduction_fingerprint == ContentHash("a" * 64)
    assert record.manifest == manifest.payload
    assert record.is_pinned is False
    assert record.revision == 0
    assert ArtifactManifest.from_record(record) == manifest


def test_audit_identity_is_retained_but_never_replaces_fingerprint() -> None:
    first = _manifest()
    later = datetime(2026, 7, 24, tzinfo=UTC)
    second = ArtifactManifest.create(
        spec=_spec(
            created_at=later,
            audit={
                "run_id": "run-2",
                "attempt_id": "attempt-1",
                "created_at": later.isoformat(),
            },
        ),
        artifact_format=ArtifactFormat.PARQUET,
        content_hash=first.content_hash,
        schema_hash=first.schema_hash,
        row_count=first.row_count,
        byte_size=first.byte_size,
    )

    assert first.audit != second.audit
    assert first.reproduction_fingerprint == second.reproduction_fingerprint
    assert first.payload["audit"] != second.payload["audit"]


@pytest.mark.parametrize(
    "relative_path",
    [
        "",
        "/absolute.json",
        "C:/drive.json",
        "a\\windows.json",
        "a/./dot.json",
        "a/../traversal.json",
        "a//empty.json",
        "nul\x00.json",
    ],
)
def test_publication_spec_rejects_noncanonical_paths(relative_path: str) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _spec(relative_path=relative_path)

    assert exc_info.value.details["reason_code"] == "invalid_artifact_relative_path"


@pytest.mark.parametrize(
    ("changes", "relative_path"),
    [
        ({}, "experiments/experiment-other/result.parquet"),
        (
            {"candidate_id": None, "fold_id": None, "attempt_id": None},
            "experiments/experiment-1/candidates/candidate-1/result.parquet",
        ),
        (
            {"fold_id": None, "attempt_id": None},
            "experiments/experiment-1/candidates/candidate-1/folds/fold-1/result.parquet",
        ),
        (
            {"attempt_id": None},
            "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
            "attempts/attempt-1/result.parquet",
        ),
        (
            {"attempt_id": AttemptId("attempt-2")},
            "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
            "attempts/attempt-1/result.parquet",
        ),
    ],
)
def test_publication_path_exactly_binds_typed_lineage(
    changes: dict[str, object],
    relative_path: str,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _spec(relative_path=relative_path, **changes)

    assert exc_info.value.details["reason_code"] == "artifact_path_lineage_mismatch"


def test_manifest_hash_binds_typed_created_at() -> None:
    manifest = _manifest()

    assert manifest.payload["created_at"] == NOW.isoformat()
    record = manifest.to_record()
    with pytest.raises(ExperimentIntegrityError) as exc_info:
        ArtifactManifest.from_record(
            replace(record, created_at=datetime(2026, 7, 24, tzinfo=UTC))
        )

    assert exc_info.value.details["reason_code"] == "invalid_artifact_manifest"


@pytest.mark.parametrize(
    "filename",
    [
        ".nav.parquet",
        ".nav.parquet.ditto-manifest.json",
        "nav.ditto-manifest.json",
        "nav.parquet.tmp",
    ],
)
def test_publication_path_reserves_internal_sidecar_and_temp_names(
    filename: str,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _spec(
            relative_path=(
                "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
                f"attempts/attempt-1/{filename}"
            )
        )

    assert exc_info.value.details["reason_code"] == "artifact_path_reserved"


def test_manifest_rejects_invalid_measurements() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        ArtifactManifest.create(
            spec=_spec(),
            artifact_format=ArtifactFormat.JSON,
            content_hash=ContentHash("b" * 64),
            schema_hash=ContentHash("c" * 64),
            row_count=-1,
            byte_size=20,
        )

    assert exc_info.value.details["reason_code"] == "invalid_artifact_measurement"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_id", "other-artifact"),
        ("content_hash", "d" * 64),
        ("schema_hash", "e" * 64),
        ("row_count", 99),
        ("byte_size", 999),
        ("reproduction_fingerprint", "f" * 64),
        ("relative_path", "experiments/other.json"),
    ],
)
def test_record_manifest_drift_fails_closed(field: str, value: object) -> None:
    record = _manifest().to_record()
    payload = dict(record.manifest)
    if field in {"content_hash", "schema_hash", "row_count", "byte_size"}:
        content = dict(payload["content"])  # type: ignore[arg-type]
        content[field] = value
        payload["content"] = content
    else:
        payload[field] = value

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        ArtifactManifest.from_record(replace(record, manifest=payload))

    assert exc_info.value.details["reason_code"] == "artifact_manifest_mismatch"


def test_manifest_rejects_unknown_or_missing_fields() -> None:
    record = _manifest().to_record()
    payload = dict(record.manifest)
    payload["unexpected"] = True

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        ArtifactManifest.from_record(replace(record, manifest=payload))

    assert exc_info.value.details["reason_code"] == "invalid_artifact_manifest"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("experiment_id", "experiment-other"),
        ("candidate_id", "candidate-other"),
        ("fold_id", "fold-other"),
        ("attempt_id", "attempt-other"),
        ("reproduction_fingerprint", "f" * 64),
        ("created_at", "2026-07-23T01:02:03Z"),
    ],
)
def test_audit_cannot_contradict_typed_identity(
    field_name: str,
    value: object,
) -> None:
    audit = {
        "run_id": "run-1",
        "attempt_id": "attempt-1",
        "created_at": NOW.isoformat(),
        field_name: value,
    }

    with pytest.raises(ExperimentSpecError) as exc_info:
        _spec(audit=audit)

    assert exc_info.value.details["reason_code"] in {
        "artifact_audit_lineage_mismatch",
        "artifact_audit_fingerprint_mismatch",
        "artifact_audit_timestamp_mismatch",
    }


def test_audit_is_detached_and_deeply_immutable() -> None:
    raw_items = [{"kind": "nav"}]
    raw: dict[str, object] = {
        "run_id": "run-1",
        "attempt_id": "attempt-1",
        "created_at": NOW.isoformat(),
        "items": raw_items,
    }
    spec = _spec(audit=raw)
    raw_items[0]["kind"] = "tampered"
    raw["run_id"] = "tampered"

    assert spec.audit["run_id"] == "run-1"
    assert spec.audit["items"] != raw_items
    with pytest.raises(TypeError):
        spec.audit["run_id"] = "mutated"  # type: ignore[index]


def test_equivalent_utc_audit_timestamps_have_one_canonical_form() -> None:
    zulu = _spec(
        audit={
            "run_id": "run-1",
            "attempt_id": "attempt-1",
            "created_at": "2026-07-23T01:02:03.456789Z",
        }
    )
    offset = _spec(
        audit={
            "run_id": "run-1",
            "attempt_id": "attempt-1",
            "created_at": "2026-07-23T01:02:03.456789+00:00",
        }
    )

    assert zulu.audit == offset.audit
    assert zulu.audit["created_at"] == NOW.isoformat()


@pytest.mark.parametrize(
    "created_at",
    ["2026-07-23T01:02:03.456789", "2026-07-23T09:02:03.456789+08:00"],
)
def test_audit_timestamp_must_be_strict_utc(created_at: str) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _spec(
            audit={
                "run_id": "run-1",
                "attempt_id": "attempt-1",
                "created_at": created_at,
            }
        )

    assert exc_info.value.details["reason_code"] == "invalid_artifact_audit"


def test_attempt_audit_requires_run_attempt_and_timestamp_identity() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _spec(audit={})

    assert exc_info.value.details["reason_code"] == "artifact_audit_identity_missing"
    assert exc_info.value.details["missing_fields"] == [
        "attempt_id",
        "created_at",
        "run_id",
    ]


def test_manifest_content_hash_detects_audit_only_tampering() -> None:
    record = _manifest().to_record()
    payload = dict(record.manifest)
    audit = dict(payload["audit"])  # type: ignore[arg-type]
    audit["run_id"] = "run-tampered"
    payload["audit"] = audit

    with pytest.raises(ExperimentIntegrityError) as exc_info:
        ArtifactManifest.from_record(replace(record, manifest=payload))

    assert exc_info.value.details["reason_code"] == "artifact_manifest_mismatch"
