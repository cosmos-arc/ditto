"""DecisionStage Protocol — Pipeline 阶段接口."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import polars as pl

from ditto_core.strategy.context import StrategyContext

__all__ = ["DecisionStage"]


@runtime_checkable
class DecisionStage(Protocol):
    """
    Pipeline 阶段 — 每个 Stage 实现此接口。

    输入 DecisionFrame (pl.DataFrame)，输出处理后的 DecisionFrame。
    """

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """处理决策帧，返回处理后的 DataFrame。"""
        ...
