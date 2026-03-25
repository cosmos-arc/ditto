"""StrategyArtifactService -- 策略产物 CRUD 与归档生命周期."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_datahub.models.strategy import StrategyArtifactRecord

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

    def save(self, record: StrategyArtifactRecord) -> None:
        """保存策略产物记录."""
        ...

    def update_status(self, artifact_id: str, status: str) -> bool:
        """更新产物状态，成功返回 True."""
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

    def save_artifact(self, record: StrategyArtifactRecord) -> None:
        """保存策略产物."""
        self._writer.save(record)

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
        return self._writer.update_status(artifact_id, "archived")
