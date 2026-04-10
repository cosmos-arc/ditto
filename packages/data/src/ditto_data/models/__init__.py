"""
Data models for data transfer objects.

仅聚合外部消费者实际使用的公共符号。
内部模块应直接引用叶模块，不应从此 barrel 导入。
"""

from ditto_data.models.common import (
    Dataset,
    DateScheduleType,
    Domain,
    InstrumentIdRange,
    OnDuplicate,
    Source,
)
from ditto_data.models.source_codes import (
    FX_CODE_TO_INSTRUMENT_ID,
    METAL_CODE_ALIASES,
    VIX_CODE_TO_INSTRUMENT_ID,
)

__all__ = [
    "FX_CODE_TO_INSTRUMENT_ID",
    "METAL_CODE_ALIASES",
    "VIX_CODE_TO_INSTRUMENT_ID",
    "Dataset",
    "DateScheduleType",
    "Domain",
    "InstrumentIdRange",
    "OnDuplicate",
    "Source",
]
