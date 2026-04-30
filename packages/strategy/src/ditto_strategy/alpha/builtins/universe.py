"""UniverseStage -- instrument_id 白名单过滤."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
from ditto_kernel.identity import InstrumentId

from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.frame import FrameCol, validate_frame

__all__ = ["UniverseStage"]


@dataclass(frozen=True)
class UniverseStage:
    """
    Universe Stage -- 按 instrument_id 白名单过滤。

    Attributes:
        instrument_ids: 允许通过的标的 ID 集合。空集合返回空 frame。

    """

    instrument_ids: frozenset[InstrumentId]

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """保留白名单中的标的，其余过滤掉。"""
        validate_frame(frame, (FrameCol.INSTRUMENT_ID,))
        return frame.filter(pl.col("instrument_id").is_in(list(self.instrument_ids)))
