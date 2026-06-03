"""
PIT (Point-in-Time) 策略常量.

定义 PIT 数据查询的核心策略常量，确保数据一致性和防止前瞻偏差。
"""

from __future__ import annotations

from enum import StrEnum


class RollingWindowClosed(StrEnum):
    """
    滚动窗口闭合策略.

    决定窗口是左闭、右闭还是两端闭合。这对于 PIT 安全至关重要，
    可防止数据泄漏。

    Attributes:
        LEFT: 窗口包含 [T-window, T-1] (PIT 安全，无数据泄漏)
        RIGHT: 窗口包含 [T-window+1, T] (非 PIT 安全，有数据泄漏)
        BOTH: 窗口包含 [T-window, T] (非 PIT 安全，有数据泄漏)
        NONE: 窗口包含 [T-window+1, T-1] (PIT 安全)

    Examples:
        rolling_mean(20, closed="left")  → 使用到 T-1 的数据 (安全)
        rolling_mean(20, closed="right") → 使用到 T 的数据 (泄漏)

    """

    LEFT = "left"  # PIT 安全: 窗口 [T-window, T-1]
    RIGHT = "right"  # 非 PIT 安全: 窗口 [T-window+1, T]
    BOTH = "both"  # 非 PIT 安全: 窗口 [T-window, T]
    NONE = "none"  # PIT 安全: 窗口 [T-window+1, T-1]


class UnsafeResearchTimePolicy(StrEnum):
    """
    显式研究模式时间策略.

    生产路径默认不允许用 trade_date 代替 knowledge_date。研究迁移期如果必须
    使用非 PIT 安全的 trade_date fallback，调用方必须显式传入该策略。
    """

    ALLOW_TRADE_DATE_FALLBACK = "allow_trade_date_fallback"


# ═══════════════════════════════════════════════════════════════════
# PIT 核心策略常量
# ═══════════════════════════════════════════════════════════════════

# 知识日期延迟天数 (T+1 策略)
# 数据在交易日后 T 天才能被获知，防止使用未来数据
KNOWLEDGE_DATE_LAG_DAYS: int = 1

# PIT 查询操作符
# 使用 "<=" 确保只使用 "已知" 的数据
PIT_QUERY_OPERATOR: str = "<="

# 默认滚动窗口闭合策略
# LEFT 策略：窗口包含左端点，不包含当前点
DEFAULT_ROLLING_WINDOW_CLOSED: RollingWindowClosed = RollingWindowClosed.LEFT


# ═══════════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════════


def is_pit_safe_closed(closed: RollingWindowClosed | str) -> bool:
    """
    检查滚动窗口闭合策略是否 PIT 安全.

    Args:
        closed: 滚动窗口闭合策略

    Returns:
        True 如果是 PIT 安全的策略

    """
    if not isinstance(closed, RollingWindowClosed):
        closed = RollingWindowClosed(closed)
    return closed in (RollingWindowClosed.LEFT, RollingWindowClosed.NONE)


def is_trade_date_fallback_allowed(
    unsafe_time_policy: UnsafeResearchTimePolicy | str | None,
) -> bool:
    """
    检查调用方是否显式允许 trade_date fallback.

    Args:
        unsafe_time_policy: 研究模式 unsafe 时间策略。

    Returns:
        True 表示允许研究模式 trade_date fallback。

    """
    if unsafe_time_policy is None:
        return False
    if not isinstance(unsafe_time_policy, UnsafeResearchTimePolicy):
        unsafe_time_policy = UnsafeResearchTimePolicy(unsafe_time_policy)
    return unsafe_time_policy is UnsafeResearchTimePolicy.ALLOW_TRADE_DATE_FALLBACK


__all__ = [
    "DEFAULT_ROLLING_WINDOW_CLOSED",
    "KNOWLEDGE_DATE_LAG_DAYS",
    "PIT_QUERY_OPERATOR",
    "RollingWindowClosed",
    "UnsafeResearchTimePolicy",
    "is_pit_safe_closed",
    "is_trade_date_fallback_allowed",
]
