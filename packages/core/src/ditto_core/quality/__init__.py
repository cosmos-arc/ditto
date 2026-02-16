"""
Data Quality Module.

Domain Layer: Pure business logic for data quality checks.
No data access dependencies - all data is injected via parameters.
"""

from ditto_core.quality.checkers.business import BusinessChecker
from ditto_core.quality.checkers.statistical import StatisticalChecker
from ditto_core.quality.checkers.technical import TechnicalChecker
from ditto_core.quality.config import DQSettings
from ditto_core.quality.engine import QualityEngine
from ditto_core.quality.report import DQReportGenerator
from ditto_core.quality.severity import DQSeverity
from ditto_core.quality.spec import (
    DatasetRules,
    DQIssue,
    DQLevel,
    DQResult,
    DQSpec,
)

__all__ = [
    "BusinessChecker",
    "DQIssue",
    "DQLevel",
    "DQReportGenerator",
    "DQResult",
    "DQSettings",
    "DQSeverity",
    "DQSpec",
    "DatasetRules",
    "QualityEngine",
    "StatisticalChecker",
    "TechnicalChecker",
]
