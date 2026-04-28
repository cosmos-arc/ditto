"""
延迟到达检查服务.

提供数据摄入层的延迟到达检测逻辑，根据 ``DataLateArrivalPolicy`` 策略
决定是否接受、拒绝或标记需要重建的延迟数据。
"""

from __future__ import annotations

from datetime import date

from ditto_data.errors import LateArrivalRejectedError
from ditto_data.models.ingestion import (
    DataLateArrivalPolicy,
    LateArrivalCheckResult,
)

__all__ = [
    "check_late_arrival",
]

# 不传 max_delay_days 时的默认值，相当于"不限制"
_DEFAULT_MAX_DELAY_DAYS = 999_999


def check_late_arrival(
    *,
    knowledge_date: date,
    trade_date: date,
    policy: DataLateArrivalPolicy,
    max_delay_days: int = _DEFAULT_MAX_DELAY_DAYS,
) -> LateArrivalCheckResult:
    """
    检查数据是否延迟到达，并根据策略返回处理结果.

    Args:
        knowledge_date: 数据可知日期（如财报公告日）.
        trade_date: 数据所属交易日期.
        policy: 延迟到达策略.
        max_delay_days: REJECT 策略下允许的最大延迟天数.
            默认为一个很大的数（即不限制），仅对 REJECT 有效.

    Returns:
        检查结果，包含是否接受、是否需要重建和延迟天数.

    Raises:
        LateArrivalRejectedError: 当策略为 REJECT 且延迟超过阈值时.

    """
    delay_days = max((knowledge_date - trade_date).days, 0)

    if policy == DataLateArrivalPolicy.ACCEPT:
        return LateArrivalCheckResult(
            accepted=True,
            needs_rebuild=False,
            delay_days=delay_days,
            policy=policy,
        )

    if policy == DataLateArrivalPolicy.REJECT:
        if delay_days > max_delay_days:
            raise LateArrivalRejectedError(
                delay_days=delay_days,
                max_delay_days=max_delay_days,
                trade_date=trade_date.isoformat(),
                knowledge_date=knowledge_date.isoformat(),
            )
        return LateArrivalCheckResult(
            accepted=True,
            needs_rebuild=False,
            delay_days=delay_days,
            policy=policy,
        )

    # REBUILD: 始终接受，延迟 > 0 时标记需要重建
    return LateArrivalCheckResult(
        accepted=True,
        needs_rebuild=delay_days > 0,
        delay_days=delay_days,
        policy=policy,
    )
