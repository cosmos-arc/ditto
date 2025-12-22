"""Type definitions for data hub."""

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple


class SidRange(NamedTuple):
    """SID range for asset classes."""

    min_sid: int
    max_sid: int

    @classmethod
    def get_range(cls, asset_class: str) -> "SidRange":
        """Get SID range for asset class."""
        ranges = {
            "stock": cls(100_000_000, 199_999_999),
            "etf": cls(200_000_000, 299_999_999),
            "index": cls(300_000_000, 399_999_999),
        }

        if asset_class not in ranges:
            raise ValueError(f"Unknown asset class: {asset_class}")

        return ranges[asset_class]


# ============ DQ 枚举 ============
class DQSeverity(Enum):
    """DQ severity levels."""

    FAIL = "fail"
    WARN = "warn"


@dataclass(frozen=True)
class DQResult:
    """Data quality check result."""

    passed: bool
    severity: DQSeverity
    rule_name: str
    message: str
    affected_rows: int = 0
