"""
Domain Accessors for data access.

注意：大部分 Accessor 已被 Domain Services 替代。
只保留 InstrumentsAccessor 用于数据摄入场景。
"""

from ditto_datahub.accessors.instrument_accessor import InstrumentsAccessor

__all__ = [
    "InstrumentsAccessor",
]
