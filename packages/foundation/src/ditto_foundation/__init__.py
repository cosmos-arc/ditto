"""
Ditto 共享模块.

提供跨项目的共享类型、配置和工具
"""

__version__ = "0.1.0"
__author__ = "Ditto Team"

# Export app initializer
from ditto_foundation.app_initializer import AppInitializer, initialize_app
from ditto_foundation.app_initializer import reset_for_testing as reset_initializer

# Export cache components
from ditto_foundation.cache import CacheStats, DataCache

# Export concurrency components
from ditto_foundation.concurrency import FileLockManager, LockAcquisitionError

# Export database components
from ditto_foundation.db import SQLitePool

# Export observability
from ditto_foundation.observability import (
    M,
    Mode,
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

# Export version management
from ditto_foundation.version import compute_checksum

__all__ = [
    "AppInitializer",
    "CacheStats",
    "DataCache",
    "FileLockManager",
    "LockAcquisitionError",
    "M",
    "Mode",
    "ObservabilityConfig",
    "SQLitePool",
    "compute_checksum",
    "get_recorded_metrics",
    "get_recorded_spans",
    "get_span_id",
    "get_trace_id",
    "init",
    "initialize_app",
    "logger",
    "reset_for_testing",
    "reset_initializer",
    "shutdown",
    "span",
    "traced",
]
