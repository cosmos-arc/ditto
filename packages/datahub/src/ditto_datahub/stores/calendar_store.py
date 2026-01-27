"""
Trading calendar storage with in-memory cache optimization.

⚠️ DEPRECATED: 此模块已迁移到 domains/metadata/calendar/calendar_store.py

请使用新的导入路径：
    from ditto_datahub.domains.metadata.calendar import CalendarStore, CalendarDay

此文件保留用于向后兼容，将在未来版本中移除。
"""

import warnings

warnings.warn(
    "CalendarStore 已迁移到 ditto_datahub.domains.metadata.calendar",
    DeprecationWarning,
    stacklevel=2,
)

# 从新位置导入
from ditto_datahub.domains.metadata.calendar.calendar_store import (  # noqa: E402
    CalendarDay,
    CalendarStore,
)

__all__ = ["CalendarDay", "CalendarStore"]
