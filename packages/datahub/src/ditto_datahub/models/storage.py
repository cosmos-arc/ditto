"""Storage models for DataHub."""

from dataclasses import dataclass, field

__all__ = [
    "FreezeManifest",
    "WriteResult",
    "WriteResultStore",
]


@dataclass(frozen=True)
class WriteResult:
    """写入结果统计"""

    file_path: str
    checksum: str
    rows_written: int
    rows_total: int
    blocked: bool


@dataclass(frozen=True)
class WriteResultStore:
    """存储层写入结果统计"""

    file_path: str
    checksum: str
    added: int
    updated: int
    skipped: int
    is_merge: bool


@dataclass(frozen=True)
class FreezeManifest:
    """Freeze manifest for data version tracking."""

    freeze_id: str
    description: str
    created_at: str
    version: str = "2.0"
    checksum_type: str = "sha256"  # "md5" for legacy, "sha256" for new
    # Mapping: relative_path -> checksum
    files: dict[str, str] = field(default_factory=lambda: {})

    @property
    def file_count(self) -> int:
        """Number of files in freeze."""
        return len(self.files)
