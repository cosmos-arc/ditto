"""StrategyArtifactService -- 策略产物 CRUD 与归档生命周期."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import orjson

from ditto_strategy.models import StrategyArtifactRecord

__all__ = [
    "StrategyArtifactReaderProtocol",
    "StrategyArtifactService",
    "StrategyArtifactWriterProtocol",
]


@runtime_checkable
class StrategyArtifactReaderProtocol(Protocol):
    """策略产物读取协议."""

    def get(self, artifact_id: str) -> StrategyArtifactRecord | None:
        """获取策略产物."""
        ...

    def list_all(self) -> list[StrategyArtifactRecord]:
        """列出所有策略产物."""
        ...

    def list_by_strategy(self, strategy_id: str) -> list[StrategyArtifactRecord]:
        """按策略 ID 列出产物."""
        ...


@runtime_checkable
class StrategyArtifactWriterProtocol(Protocol):
    """策略产物写入协议."""

    def save(self, record: StrategyArtifactRecord) -> bool:
        """追加策略产物记录；ID 已存在时返回 False 且不得覆盖."""
        ...

    def update_status(
        self,
        artifact_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...] | None = None,
    ) -> bool:
        """更新产物状态，成功返回 True."""
        ...

    def claim_replacement(
        self,
        candidate_artifact_id: str,
        replaced_artifact_id: str,
    ) -> bool:
        """Claim one candidate as the batch replacement owner."""
        ...

    def activate_candidate(
        self,
        candidate_artifact_id: str,
        *,
        replaced_artifact_id: str | None = None,
    ) -> bool:
        """Activate a candidate, atomically archiving its predecessor."""
        ...


class StrategyArtifactService:
    """策略产物服务 -- CRUD + ACTIVE/ARCHIVED 归档生命周期."""

    def __init__(
        self,
        reader: StrategyArtifactReaderProtocol,
        writer: StrategyArtifactWriterProtocol,
    ) -> None:
        self._reader = reader
        self._writer = writer

    def save_artifact(self, record: StrategyArtifactRecord) -> StrategyArtifactRecord:
        """Append immutable evidence, accepting only an identical-ID replay."""
        if self._writer.save(record):
            return record
        existing = self._reader.get(record.artifact_id)
        if existing is not None and _same_artifact_payload(existing, record):
            return existing
        raise ValueError(f"Artifact ID conflict: {record.artifact_id}")

    def get_artifact(self, artifact_id: str) -> StrategyArtifactRecord | None:
        """获取策略产物."""
        return self._reader.get(artifact_id)

    def list_artifacts(self) -> list[StrategyArtifactRecord]:
        """列出所有策略产物."""
        return self._reader.list_all()

    def list_by_strategy(self, strategy_id: str) -> list[StrategyArtifactRecord]:
        """按策略 ID 列出产物."""
        return self._reader.list_by_strategy(strategy_id)

    def archive_artifact(self, artifact_id: str) -> bool:
        """归档策略产物（active -> archived）."""
        return self._writer.update_status(
            artifact_id,
            "archived",
            expected_current=("active",),
        )

    def transition_artifact(
        self,
        artifact_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...],
    ) -> bool:
        """Apply a compare-and-set lifecycle transition."""
        return self._writer.update_status(
            artifact_id,
            status,
            expected_current=expected_current,
        )

    def claim_replacement(
        self,
        candidate_artifact_id: str,
        replaced_artifact_id: str,
    ) -> bool:
        """Claim one candidate as the batch replacement owner."""
        return self._writer.claim_replacement(
            candidate_artifact_id,
            replaced_artifact_id,
        )

    def activate_candidate(
        self,
        candidate_artifact_id: str,
        *,
        replaced_artifact_id: str | None = None,
    ) -> bool:
        """Activate a candidate and atomically retire its predecessor."""
        return self._writer.activate_candidate(
            candidate_artifact_id,
            replaced_artifact_id=replaced_artifact_id,
        )


def _same_artifact_payload(
    existing: StrategyArtifactRecord,
    candidate: StrategyArtifactRecord,
) -> bool:
    """Compare immutable evidence while preserving lifecycle/time fields."""
    return (
        existing.artifact_id == candidate.artifact_id
        and existing.strategy_id == candidate.strategy_id
        and existing.run_id == candidate.run_id
        and existing.artifact_type == candidate.artifact_type
        and existing.file_path == candidate.file_path
        and _canonical_metadata(existing.metadata)
        == _canonical_metadata(candidate.metadata)
    )


def _canonical_metadata(metadata: dict[str, object]) -> bytes:
    """Compare metadata using the same JSON semantics as SQLite persistence."""
    return orjson.dumps(
        metadata,
        option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SORT_KEYS,
    )
