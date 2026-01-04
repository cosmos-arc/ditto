"""Type definitions for data hub."""

from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple


class SidRange(NamedTuple):
    """
    SID range for asset classes.

    统一使用百万级范围，与 SecurityMapper 保持一致:
    - stock: 1M (1,000,000 - 1,999,999)
    - etf: 2M (2,000,000 - 2,999,999)
    - index: 3M (3,000,000 - 3,999,999)

    避免未来 SID 冲突，并保持范围一致性。
    """

    min_sid: int
    max_sid: int

    @classmethod
    def get_range(cls, asset_class: str) -> "SidRange":
        """Get SID range for asset class."""
        ranges = {
            "stock": cls(1_000_000, 1_999_999),
            "etf": cls(2_000_000, 2_999_999),
            "index": cls(3_000_000, 3_999_999),
        }

        if asset_class not in ranges:
            raise ValueError(f"Unknown asset class: {asset_class}")

        return ranges[asset_class]


# ============ DQ 枚举 ============
class DQSeverity(str, Enum):
    """DQ severity levels (B.5: 统一三级定义)."""

    ERROR = "error"
    WARNING = "warning"
    ALERT = "alert"


# ============ Store 枚举 ============
class OnDuplicate(Enum):
    """策略：处理写入时的重复数据."""

    ERROR = "error"  # 遇到重复时报错（默认，最安全）
    KEEP_FIRST = "keep_first"  # 保留现有数据，忽略新数据
    KEEP_LAST = "keep_last"  # 使用新数据覆盖现有数据（Last-Write-Wins）


@dataclass(frozen=True)
class DQResult:
    """Data quality check result (legacy, for runtime/dq_checker.py compatibility)."""

    passed: bool
    severity: DQSeverity
    rule_name: str
    message: str
    affected_rows: int = 0


# ============ Freeze 数据结构 ============
@dataclass(frozen=True)
class FreezeManifest:
    """Freeze manifest for data version tracking."""

    freeze_id: str
    description: str
    created_at: str
    version: str = "2.0"
    checksum_type: str = "sha256"  # "md5" for legacy, "sha256" for new
    files: dict[str, str] = field(default_factory=dict)  # {relative_path: checksum}

    @property
    def file_count(self) -> int:
        """Number of files in freeze."""
        return len(self.files)
