"""
DecisionFrame 列名常量与运行时 schema 校验.

FrameCol 定义 DecisionFrame 的列名约定，validate_frame 无条件校验
必需列是否存在。
"""

from __future__ import annotations

import polars as pl

__all__ = ["FrameCol", "validate_frame"]


class FrameCol:
    """
    DecisionFrame 列名常量.

    Pipeline 各阶段通过这些列名在 DecisionFrame 中流转决策数据。
    列名约定与 ``StrategyPipeline`` 文档保持一致。
    """

    __slots__ = ()

    INSTRUMENT_ID: str = "instrument_id"
    SIGNAL: str = "signal_value"
    SCORE: str = "score"
    WEIGHT: str = "weight"
    REGIME: str = "regime"
    REASON_CODES: str = "reason_codes"


def validate_frame(frame: pl.DataFrame, required: tuple[str, ...]) -> None:
    """
    校验 DecisionFrame 是否包含必需列.

    无条件执行校验，缺少列时抛出 ValueError。

    Args:
        frame: 待校验的 DataFrame。
        required: 必需列名元组。

    Raises:
        ValueError: 缺少必需列时。

    """
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError(f"DecisionFrame missing required columns: {missing}")
