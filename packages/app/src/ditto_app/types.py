"""
Re-exported domain types for interface layer consumption.

These types are re-exported from ditto_data so that the interfaces layer
does not need to import from ditto_data directly.
"""

# 设计决策: types.py 作为 app 层的集中 re-export 入口。
# 目的：将公共 API 类型聚合到一处，便于上层（interfaces）统一导入，
# 同时保持底层模块的内聚性。新增 re-export 前需确认：
#   1. 类型被 ≥ 2 个外部消费者使用
#   2. 类型不属于某个特定子模块的内部实现

from ditto_data.errors import (
    AmbiguousTickerError,
    IdentifierNotFoundError,
    NoIdentifierProvidedError,
)
from ditto_data.models import Dataset, MacroCategory, MacroFrequency
from ditto_data.models.ingestion import (
    BackfillResult,
    IngestionResult,
    InstrumentIngestParams,
    ResultCounts,
    RetryResult,
)
from ditto_data.quality import QualityEngine
from ditto_data.quality.spec import DQIssue, DQResult

__all__ = [
    "AmbiguousTickerError",
    "BackfillResult",
    "DQIssue",
    "DQResult",
    "Dataset",
    "IdentifierNotFoundError",
    "IngestionResult",
    "InstrumentIngestParams",
    "MacroCategory",
    "MacroFrequency",
    "NoIdentifierProvidedError",
    "QualityEngine",
    "ResultCounts",
    "RetryResult",
]
