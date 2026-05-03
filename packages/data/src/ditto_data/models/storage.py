"""
Storage models for Data.

WriteResult / WriteStoreResult are re-exported from platform;
FreezeManifest is data-specific and stays local.
"""

from dataclasses import dataclass, field

from ditto_platform.foundation.storage.types import (
    WriteResult,
    WriteStoreResult,
)

__all__ = [
    "FreezeManifest",
    "WriteResult",
    "WriteStoreResult",
]


@dataclass(frozen=True)
class FreezeManifest:
    """Freeze manifest for data version tracking."""

    freeze_id: str
    description: str
    created_at: str
    version: str = "2.0"
    checksum_type: str = "sha256"
    # Mapping: relative_path -> checksum
    files: dict[str, str] = field(default_factory=lambda: {})

    @property
    def file_count(self) -> int:
        """Number of files in freeze."""
        return len(self.files)
