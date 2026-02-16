"""
Concurrency module.

Provides cross-project concurrency control infrastructure including
file locks and other general-purpose technical components.
"""

from ditto_infra.foundation.concurrency.filelock import (
    FileLockManager,
    LockAcquisitionError,
)

__all__ = [
    "FileLockManager",
    "LockAcquisitionError",
]
