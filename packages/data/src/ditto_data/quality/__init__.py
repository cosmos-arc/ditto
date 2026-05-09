"""
Data Quality Module.

Domain Layer: Pure business logic for data quality checks.
No data access dependencies - all data is injected via parameters.
"""

from ditto_data.quality.checkers.business import BusinessChecker
from ditto_data.quality.checkers.statistical import StatisticalChecker
from ditto_data.quality.checkers.technical import TechnicalChecker
from ditto_data.quality.config import DQSettings
from ditto_data.quality.engine import QualityEngine
from ditto_data.quality.golden import GoldenDatasetOptions, GoldenDatasetSpec
from ditto_data.quality.kernel_types import DQIssue, DQLevel, DQResult, DQSeverity
from ditto_data.quality.protocols import (
    ComparisonStoreProtocol,
    InstrumentStoreProtocol,
    QualityEngineProtocol,
    QuarantineWriterProtocol,
    TdxSourceProtocol,
)
from ditto_data.quality.report import DQReportGenerator
from ditto_data.quality.spec import (
    DatasetRules,
    DQSpec,
)

__all__ = [
    "BusinessChecker",
    "ComparisonStoreProtocol",
    "DQIssue",
    "DQLevel",
    "DQReportGenerator",
    "DQResult",
    "DQSettings",
    "DQSeverity",
    "DQSpec",
    "DatasetRules",
    "GoldenDatasetOptions",
    "GoldenDatasetSpec",
    "InstrumentStoreProtocol",
    "QualityEngine",
    "QualityEngineProtocol",
    "QuarantineWriterProtocol",
    "StatisticalChecker",
    "TdxSourceProtocol",
    "TechnicalChecker",
]
