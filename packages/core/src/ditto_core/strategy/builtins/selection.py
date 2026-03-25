"""SelectionStage -- 按 score 选取 top K 标的."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_core.strategy.context import StrategyContext

__all__ = ["SelectionStage"]


@dataclass(frozen=True)
class SelectionStage:
    """
    Selection Stage -- 按 score 选取 top K 标的。

    Attributes:
        top_k: 选取数量。
        score_column: 排序依据列。
        ascending: False 表示 score 大的优先。

    """

    top_k: int
    score_column: str = "score"
    ascending: bool = False

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """按 score 排序并截取 top K。"""
        if self.top_k <= 0 or frame.is_empty():
            return frame.clear()

        sorted_frame = frame.sort(
            by=self.score_column,
            descending=not self.ascending,
            nulls_last=True,
        )
        return sorted_frame.head(self.top_k)
