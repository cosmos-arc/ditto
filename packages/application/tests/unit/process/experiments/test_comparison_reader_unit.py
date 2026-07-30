# pyright: reportPrivateUsage=false
"""Unit tests for the read-only candidate-comparison reader."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ditto_analysis.experiments import ExperimentReaderProtocol
from ditto_application.processes.experiments import comparison_reader as module
from ditto_application.processes.experiments.comparison_reader import (
    ExperimentComparisonReader,
)


def _reader(assembled: SimpleNamespace) -> ExperimentComparisonReader:
    reader = MagicMock(spec=ExperimentReaderProtocol)
    reader.get_experiment_projection.return_value = SimpleNamespace()
    reader.list_status_events.return_value = ()
    scheduler_store = MagicMock()
    scheduler_store.load_snapshot.return_value = SimpleNamespace()
    assembler = MagicMock()
    assembler.assemble.return_value = assembled
    return ExperimentComparisonReader(
        scheduler_store=scheduler_store,
        reader=reader,
        walk_forward_assembler=assembler,
    )


def test_load_comparison_projects_canonical_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"baseline": {"candidate_id": "candidate-1"}, "folds": []}
    assembled = SimpleNamespace(
        comparison=SimpleNamespace(canonical_payload=lambda: payload)
    )
    monkeypatch.setattr(module, "read_unique_preflight_detail", lambda events, eid: {})
    monkeypatch.setattr(module, "project_snapshot_manifest", lambda detail: object())
    reader = _reader(assembled)

    view = reader.load_comparison("exp-1")

    assert view is not None
    assert view.experiment_id == "exp-1"
    assert dict(view.payload) == payload


def test_load_comparison_returns_none_when_experiment_absent() -> None:
    reader = _reader(SimpleNamespace(comparison=SimpleNamespace()))
    reader.reader.get_experiment_projection.return_value = None  # type: ignore[method-assign]

    assert reader.load_comparison("exp-1") is None
    reader.scheduler_store.load_snapshot.assert_not_called()
