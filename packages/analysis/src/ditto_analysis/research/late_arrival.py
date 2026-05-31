"""Late-arrival detection and policy application for research datasets."""

from __future__ import annotations

import warnings
from typing import assert_never

import polars as pl

from .specs import LateArrivalError, LateArrivalPolicy

__all__ = [
    "_apply_late_arrival_policy",
    "_detect_late_arrivals",
]


def _detect_late_arrivals(frame: pl.DataFrame, derived_id: str) -> pl.DataFrame:
    """
    检测延迟到达的数据行。

    比较 known_at vs {derived_id}_availability_time 列，
    标记 availability_time > known_at 的行。

    Args:
        frame: 研究数据集 DataFrame
        derived_id: 派生数据 ID

    Returns:
        与 frame 结构相同的 DataFrame，包含 is_late 标记列

    """
    availability_col = f"{derived_id}_availability_time"
    if availability_col not in frame.columns:
        return frame.with_columns(pl.lit(False).alias("is_late"))

    return frame.with_columns(
        pl.when(pl.col(availability_col).is_null())
        .then(pl.lit(False))
        .when(pl.col(availability_col) > pl.col("known_at"))
        .then(pl.lit(True))
        .otherwise(pl.lit(False))
        .alias("is_late"),
    )


def _apply_late_arrival_policy(
    frame: pl.DataFrame,
    policy: LateArrivalPolicy,
    late_flags: pl.Series,
) -> pl.DataFrame:
    """
    应用延迟到达策略。

    Args:
        frame: 研究数据集 DataFrame
        policy: 策略名称 (EXCLUDE/SHIFT/REBUILD)
        late_flags: 延迟标记 Series

    Returns:
        处理后的 DataFrame

    Raises:
        LateArrivalError: 当策略为 REQUIRE_REBUILD 且存在延迟行时

    """
    has_late = late_flags.any()

    if not has_late:
        return frame

    if policy == LateArrivalPolicy.EXCLUDE_FROM_CURRENT_SNAPSHOT:
        return frame.filter(~late_flags)

    if policy == LateArrivalPolicy.SHIFT_TO_NEXT_SNAPSHOT:
        warnings.warn(
            (
                "SHIFT_TO_NEXT_SNAPSHOT is reserved (not implemented). "
                "Late arrival detected but frame returned unchanged."
            ),
            stacklevel=2,
        )
        return frame

    if policy == LateArrivalPolicy.REQUIRE_REBUILD:
        late_count = int(late_flags.sum())
        raise LateArrivalError(
            f"Late arrival detected ({late_count} rows), snapshot must be rebuilt"
        )

    assert_never(policy)
