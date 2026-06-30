"""
DecisionFrame 列名常量与运行时 schema 校验.

FrameCol 定义 DecisionFrame 的列名约定，validate_frame 无条件校验
必需列是否存在，并对已知语义列做轻量 dtype 校验。
"""

from __future__ import annotations

import polars as pl

from ditto_strategy.errors import StrategySpecError

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


_KNOWN_COLUMN_DTYPES: dict[str, str] = {
    FrameCol.INSTRUMENT_ID: "identifier",
    FrameCol.SIGNAL: "numeric",
    FrameCol.SCORE: "numeric",
    FrameCol.WEIGHT: "numeric",
}


def validate_frame(
    frame: pl.DataFrame,
    required: tuple[str, ...],
    *,
    boundary: str | None = None,
    stage_name: str | None = None,
) -> None:
    """
    校验 DecisionFrame 是否包含必需列.

    同时对已知语义列做轻量 dtype 校验，避免低层 Polars/float
    转换异常泄漏到策略公共边界。
    """
    missing = set(required) - set(frame.columns)
    if missing:
        details = _frame_details(frame, boundary=boundary, stage_name=stage_name)
        details["missing_columns"] = tuple(sorted(missing))
        details["required_columns"] = required
        raise StrategySpecError(
            f"DecisionFrame missing required columns: {missing}",
            details=details,
        )

    for column_name, expected_dtype in _KNOWN_COLUMN_DTYPES.items():
        if column_name in frame.columns and not _matches_expected_dtype(
            column_name,
            frame.schema[column_name],
            expected_dtype,
            frame_height=frame.height,
        ):
            details = _frame_details(frame, boundary=boundary, stage_name=stage_name)
            details.update(
                {
                    "column_name": column_name,
                    "expected_dtype": expected_dtype,
                    "actual_dtype": str(frame.schema[column_name]),
                },
            )
            raise StrategySpecError(
                f"DecisionFrame column has invalid dtype: {column_name}",
                details=details,
            )


def _frame_details(
    frame: pl.DataFrame,
    *,
    boundary: str | None,
    stage_name: str | None,
) -> dict[str, object]:
    """Build common StrategySpecError details for DecisionFrame failures."""
    details: dict[str, object] = {"available_columns": tuple(frame.columns)}
    if boundary is not None:
        details["boundary"] = boundary
    if stage_name is not None:
        details["stage_name"] = stage_name
    return details


def _matches_expected_dtype(
    column_name: str,
    dtype: object,
    expected_dtype: str,
    *,
    frame_height: int,
) -> bool:
    """Return whether a Polars dtype matches a DecisionFrame semantic type."""
    if dtype == pl.Null:
        return frame_height == 0 or column_name in (FrameCol.SIGNAL, FrameCol.SCORE)
    if expected_dtype == "identifier":
        return _dtype_predicate(dtype, "is_integer") or dtype == pl.String
    if expected_dtype == "numeric":
        return _dtype_predicate(dtype, "is_numeric")
    return False


def _dtype_predicate(dtype: object, predicate_name: str) -> bool:
    """Call a Polars dtype predicate without depending on deprecated type classes."""
    predicate = getattr(dtype, predicate_name, None)
    if not callable(predicate):
        return False
    return bool(predicate())
