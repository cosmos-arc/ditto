"""
PIT (Point-in-Time) 模块.

提供 PIT 安全的数据查询能力，防止前瞻偏差。

包含:
- 策略常量: KNOWLEDGE_DATE_LAG_DAYS, PIT_QUERY_OPERATOR, RollingWindowClosed
- DataFrame API: filter_by_knowledge_date, parse_asof_date
- SQL API: PitHelper
"""

from ditto_data.helpers.pit.dataframe import (
    PIT_QUERY_OPERATOR,
    filter_by_knowledge_date,
    get_pit_filter_expr,
    parse_asof_date,
)
from ditto_data.helpers.pit.policy import (
    DEFAULT_ROLLING_WINDOW_CLOSED,
    KNOWLEDGE_DATE_LAG_DAYS,
    RollingWindowClosed,
    UnsafeResearchTimePolicy,
    is_pit_safe_closed,
)
from ditto_data.helpers.pit.sql import PitHelper

__all__ = [
    "DEFAULT_ROLLING_WINDOW_CLOSED",
    "KNOWLEDGE_DATE_LAG_DAYS",
    "PIT_QUERY_OPERATOR",
    "PitHelper",
    "RollingWindowClosed",
    "UnsafeResearchTimePolicy",
    "filter_by_knowledge_date",
    "get_pit_filter_expr",
    "is_pit_safe_closed",
    "parse_asof_date",
]
