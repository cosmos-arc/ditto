"""DQ severity level enumeration."""

from enum import Enum


class DQSeverity(Enum):
    """
    DQ severity level.

    Represents the severity level of a data quality issue.
    Used across all layers for consistent issue classification.
    """

    ERROR = "error"
    WARNING = "warning"
    ALERT = "alert"
