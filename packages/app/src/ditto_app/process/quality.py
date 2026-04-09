"""
质量服务 — re-export shim（向后兼容，计划下一迭代迁移消费者后删除）.

当前消费者（10 处）：
- 生产代码：providers.py, ingestion_config.py,
  coordinator_factory.py, interfaces/registry
- 测试代码：test_providers_unit.py, test_service_unit.py,
  test_l3_batch_unit.py, test_golden_unit.py,
  test_reconciliation_service_unit.py
"""

from __future__ import annotations

__all__ = [
    "ComparisonStoreProtocol",
    "InstrumentStoreProtocol",
    "L3BatchService",
    "L3CheckResult",
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
from ditto_app.process.quality_types import L3CheckResult
