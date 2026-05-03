"""Generic storage types shared across packages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "OnDuplicate",
    "WriteResult",
    "WriteStoreResult",
]


class OnDuplicate(Enum):
    """Strategy for handling duplicate data during writes."""

    ERROR = "error"  # Raise on duplicate (default, safest)
    KEEP_FIRST = "keep_first"  # Keep existing data, ignore new
    KEEP_LAST = "keep_last"  # Overwrite existing with new (Last-Write-Wins)


@dataclass(frozen=True)
class WriteResult:
    """Write result statistics."""

    file_path: str
    checksum: str
    rows_written: int
    rows_total: int
    blocked: bool


@dataclass(frozen=True)
class WriteStoreResult:
    """Storage layer write result statistics."""

    file_path: str
    checksum: str
    added: int
    updated: int
    skipped: int
    is_merge: bool
