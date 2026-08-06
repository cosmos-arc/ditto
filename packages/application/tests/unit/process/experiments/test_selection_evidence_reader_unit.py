# pyright: reportPrivateUsage=false
"""Unit tests for the read-only selection-evidence view reader."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from ditto_analysis.experiments import (
    ArtifactRecord,
    ContentHash,
    ExperimentId,
    ExperimentReaderProtocol,
)
from ditto_application.processes.experiments.selection_evidence_reader import (
    ExperimentSelectionEvidenceReader,
)


def _record() -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id="selection-evidence-" + "a" * 64,
        experiment_id=ExperimentId("exp-1"),
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        artifact_kind="selection_evidence",
        relative_path="experiments/exp-1/selection-evidence.json",
        content_hash=ContentHash("a" * 64),
        schema_hash=ContentHash("b" * 64),
        row_count=0,
        byte_size=128,
        reproduction_fingerprint=ContentHash("d" * 64),
        manifest={"format": "json"},
        is_pinned=True,
        pinned_at=datetime(2026, 7, 30, 1, 0, 0, tzinfo=UTC),
        created_at=datetime(2026, 7, 30, 0, 0, 0, tzinfo=UTC),
        revision=1,
    )


def _reader(
    record: ArtifactRecord | None,
    published: SimpleNamespace,
) -> ExperimentSelectionEvidenceReader:
    mock_reader = MagicMock(spec=ExperimentReaderProtocol)
    mock_reader.get_artifact_by_relative_path.return_value = record
    selection_service = MagicMock()
    selection_service.read_selection_evidence.return_value = published
    return ExperimentSelectionEvidenceReader(
        reader=mock_reader, selection_service=selection_service
    )


def test_load_view_returns_verified_ledger_payload() -> None:
    published = SimpleNamespace(
        ledger=SimpleNamespace(canonical_payload=lambda: {"selected": ["candidate-1"]})
    )
    reader = _reader(_record(), published)

    view = reader.load_view("exp-1")

    assert view is not None
    assert view.artifact_id == "selection-evidence-" + "a" * 64
    assert view.experiment_id == "exp-1"
    assert view.content_hash == "a" * 64
    assert view.byte_size == 128
    assert view.is_pinned is True
    assert view.created_at == datetime(2026, 7, 30, 0, 0, 0, tzinfo=UTC)
    assert dict(view.payload) == {"selected": ["candidate-1"]}


def test_load_view_returns_none_when_artifact_absent() -> None:
    reader = _reader(None, SimpleNamespace(ledger=SimpleNamespace()))

    assert reader.load_view("exp-1") is None
