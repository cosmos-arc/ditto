"""共享的 artifact 查找 + 回测指标计算工具函数."""

from __future__ import annotations

from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

__all__ = ["compute_total_return", "find_artifact"]


def compute_total_return(*, initial_cash: float, final_nav: float) -> float:
    """
    计算总收益率（小数形式）.

    Args:
        initial_cash: 初始资金.
        final_nav: 最终净值.

    Returns:
        总收益率（小数），如 0.05 表示 5%. initial_cash <= 0 时返回 0.0.

    """
    if initial_cash > 0:
        return final_nav / initial_cash - 1
    return 0.0


def find_artifact(
    artifact_service: StrategyArtifactService,
    run_id: str,
    artifact_type: ArtifactKind | None = None,
) -> StrategyArtifactRecord | None:
    """从产物列表中查找匹配 run_id 和可选类型的第一条记录."""
    artifacts = artifact_service.list_artifacts()
    for record in artifacts:
        if record.run_id == run_id and (
            artifact_type is None or record.artifact_type is artifact_type
        ):
            return record
    return None
