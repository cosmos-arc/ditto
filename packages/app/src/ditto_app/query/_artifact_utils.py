"""共享的 artifact 查找工具函数."""

from __future__ import annotations

from ditto_data.models.strategy import StrategyArtifactRecord
from ditto_data.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)

__all__ = ["find_artifact"]


def find_artifact(
    artifact_service: StrategyArtifactService,
    run_id: str,
) -> StrategyArtifactRecord | None:
    """从产物列表中查找匹配 run_id 的第一条记录."""
    artifacts = artifact_service.list_artifacts()
    for record in artifacts:
        if record.run_id == run_id:
            return record
    return None
