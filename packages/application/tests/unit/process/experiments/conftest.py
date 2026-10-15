"""Shared fixtures for model-candidate artifact publication/recovery tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Lock

import pytest
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    LeaseFence,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_application.exceptions import AppProcessError


class MemoryArtifactIndex:
    """Minimal in-memory reader/writer port pair for indexed publication."""

    def __init__(self, root: Path) -> None:
        self.artifact_root = root
        self.records: dict[str, ArtifactRecord] = {}
        self._lock = Lock()

    # -- reader ---------------------------------------------------------------
    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.records.get(artifact_id)

    def get_artifact_by_relative_path(
        self, relative_path: str
    ) -> ArtifactRecord | None:
        for record in self.records.values():
            if record.relative_path == relative_path:
                return record
        return None

    # -- writer ---------------------------------------------------------------
    def add_artifact(
        self,
        record: ArtifactRecord,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        commit_guard: Callable[[], None],
    ) -> None:
        _ = lease_fence, now_epoch_us
        with self._lock:
            existing = self.records.get(record.artifact_id)
            if existing is not None:
                if existing.content_hash != record.content_hash:
                    raise AppProcessError("artifact replay drift")
                commit_guard()
                return
            self.records[record.artifact_id] = record
            commit_guard()

    def pin_artifact(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: object,
        commit_guard: Callable[[], None],
    ) -> ArtifactRecord:
        raise NotImplementedError


@pytest.fixture
def memory_artifact_index(tmp_path: Path) -> MemoryArtifactIndex:
    return MemoryArtifactIndex(tmp_path)


@pytest.fixture
def artifact_service(
    tmp_path: Path, memory_artifact_index: MemoryArtifactIndex
) -> ResearchArtifactService:
    return ResearchArtifactService(
        artifact_root=tmp_path,
        indexed_artifact_root=tmp_path,
        artifact_reader=memory_artifact_index,
        artifact_writer=memory_artifact_index,
    )
