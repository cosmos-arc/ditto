"""运行血统查询 — 提供 lineage chain 查询能力."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_data.models.strategy_run import StrategyRunRecord
from ditto_data.services.strategy.strategy_run_service import StrategyRunService

__all__ = ["LineageChain", "LineageQueryFacade"]


@dataclass(frozen=True)
class LineageChain:
    """
    运行血统链.

    Attributes:
        runs: 血统链（原始运行 → ... → 当前运行，按时间正序）
        depth: 当前运行的重放深度（0 = 原始运行）

    """

    runs: tuple[StrategyRunRecord, ...]
    depth: int


class LineageQueryFacade:
    """运行血统查询 facade — 提供血统链查询."""

    def __init__(self, run_service: StrategyRunService) -> None:
        self._service = run_service

    def get_lineage(self, run_id: str) -> LineageChain | None:
        """
        获取运行血统链.

        Returns:
            LineageChain 或 None（运行不存在时）

        """
        chain = self._service.get_lineage(run_id)
        if not chain:
            return None
        return LineageChain(
            runs=tuple(chain),
            depth=len(chain) - 1,
        )

    def list_replays(self, run_id: str) -> list[StrategyRunRecord]:
        """列出指定运行的所有直接重放记录."""
        return self._service.list_replays(run_id)
