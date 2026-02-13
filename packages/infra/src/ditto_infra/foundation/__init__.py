"""
Ditto 共享模块.

提供跨项目的共享类型、配置和工具
"""

__version__ = "0.1.0"
__author__ = "Ditto Team"

# Export cache components
from ditto_infra.foundation.cache import CacheStats, DataCache

# Export checksum components
from ditto_infra.foundation.checksum import compute_checksum

# Export concurrency components
from ditto_infra.foundation.concurrency import FileLockManager, LockAcquisitionError

# Export database components
from ditto_infra.foundation.db import SQLitePool

# Export observability
from ditto_infra.foundation.observability import (
    EffectiveConfig,
    Metrics,
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

# Export quality types
from ditto_infra.foundation.quality import DQSeverity

__all__ = [
    "CacheStats",
    "DQSeverity",
    "DataCache",
    "EffectiveConfig",
    "FileLockManager",
    "LockAcquisitionError",
    "Metrics",
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
