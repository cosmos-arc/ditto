"""
Ditto 共享模块.

提供跨项目的共享类型、配置和工具
"""

__version__ = "0.1.0"
__author__ = "Ditto Team"

# Export cache components
from ditto_foundation.cache import CacheStats, DataCache

# Export checksum components
from ditto_foundation.checksum import compute_checksum

# Export concurrency components
from ditto_foundation.concurrency import FileLockManager, LockAcquisitionError

# Export database components
from ditto_foundation.db import SQLitePool

# Export observability
from ditto_foundation.observability import (
    EffectiveConfig,
    M,
    ObservabilityConfig,
    get_recorded_metrics,
    get_recorded_spans,
    get_span_id,
    get_trace_id,
    init,
    logger,
    reset_for_testing,
    shutdown,
    span,
    traced,
)

__all__ = [
    "CacheStats",
    "DataCache",
    "EffectiveConfig",
    "FileLockManager",
    "LockAcquisitionError",
    "M",
    "ObservabilityConfig",
    "SQLitePool",
    "compute_checksum",
    "get_recorded_metrics",
    "get_recorded_spans",
    "get_span_id",
    "get_trace_id",
    "init",
    "logger",
    "reset_for_testing",
    "shutdown",
    "span",
    "traced",
]
