"""DecisionStage Protocol — Pipeline 阶段接口."""

from __future__ import annotations

from typing import Protocol

import polars as pl

from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.frame import FrameCol

__all__ = ["DecisionFrame", "DecisionStage", "FrameCol"]

type DecisionFrame = pl.DataFrame


class DecisionStage(Protocol):
    """
    Pipeline 阶段 — 每个 Stage 实现此接口。

    输入 DecisionFrame，输出处理后的 DecisionFrame。
    DecisionFrame 是 polars DataFrame 的类型别名，
    通过列名约定流转决策数据（instrument_id、signal 等）。
    """

    def process(
        self,
        frame: DecisionFrame,
        context: StrategyContext,
    ) -> DecisionFrame:
        """处理决策帧，返回处理后的 DataFrame。"""
        ...
