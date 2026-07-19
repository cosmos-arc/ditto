"""SelectionStage -- 按 score 选取 top K 标的."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.frame import FrameCol, validate_frame
from ditto_strategy.alpha.selection_evidence import (
    ExclusionEvidence,
    ExclusionReason,
    SelectionEvidence,
    SelectionEvidenceSink,
)

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
    evidence_sink: SelectionEvidenceSink | None = None

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """按 score 排序并截取 top K。"""
        validate_frame(frame, (FrameCol.INSTRUMENT_ID,))
        if frame.is_empty():
            return frame.clear()

        if self.top_k <= 0:
            if self.evidence_sink is not None:
                ranked_frame = (
                    self._sort(frame) if self.score_column in frame.columns else frame
                )
                self._emit_selection(ranked_frame, selected_count=0)
            return frame.clear()

        sorted_frame = self._sort(frame)
        selected_count = min(self.top_k, sorted_frame.height)
        if self.evidence_sink is not None:
            self._emit_selection(sorted_frame, selected_count=selected_count)
        return sorted_frame.head(self.top_k)

    def _sort(self, frame: pl.DataFrame) -> pl.DataFrame:
        """Use the original selector ordering without an evidence tie-breaker."""
        return frame.sort(
            by=self.score_column,
            descending=not self.ascending,
            nulls_last=True,
        )

    def _emit_selection(
        self,
        ranked_frame: pl.DataFrame,
        *,
        selected_count: int,
    ) -> None:
        """Emit rank/selected state in exact business sort order."""
        if self.evidence_sink is None:
            return
        columns = [FrameCol.INSTRUMENT_ID]
        has_score = self.score_column in ranked_frame.columns
        if has_score:
            columns.append(self.score_column)
        rows = ranked_frame.select(columns).iter_rows()
        for rank, values in enumerate(rows, start=1):
            instrument_id = values[0]
            score = _selection_score(values[1]) if has_score else None
            selected = rank <= selected_count
            self.evidence_sink.emit(
                SelectionEvidence(
                    instrument_id=instrument_id,
                    score=score,
                    rank=rank,
                    selected=selected,
                ),
            )
            if not selected:
                self.evidence_sink.emit(
                    ExclusionEvidence(
                        instrument_id=instrument_id,
                        stage="selection",
                        reason_code=ExclusionReason.BELOW_TOP_K,
                    ),
                )


def _selection_score(value: object) -> float | None:
    """Normalize Polars scalar score into the immutable evidence contract."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("selection score must be a finite number or None")
    return float(value)
