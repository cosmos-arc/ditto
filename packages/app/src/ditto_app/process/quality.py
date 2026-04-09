"""质量服务 — re-export shim（向后兼容）."""

from __future__ import annotations

__all__ = [
    "ComparisonStoreProtocol",
    "InstrumentStoreProtocol",
    "L3BatchService",
    "QualityEngineProtocol",
    "QualityReconciliationService",
    "QualityService",
    "ReconciliationResult",
    "TdxSourceProtocol",
]

from ditto_app.process.quality_check import QualityService
from ditto_app.process.quality_l3 import L3BatchService
from ditto_app.process.quality_protocols import (
    ComparisonStoreProtocol,
    InstrumentStoreProtocol,
    QualityEngineProtocol,
    ReconciliationResult,
    TdxSourceProtocol,
)
from ditto_app.process.quality_reconciliation import QualityReconciliationService
