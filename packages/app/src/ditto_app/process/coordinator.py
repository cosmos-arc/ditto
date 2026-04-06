"""
摄取协调器 — re-export shim (模块拆分后保持向后兼容).

原始实现已迁移至:
- _coordinator_constants.py: 共享常量 + 指数工具函数
- coordinator_factory.py: create_coordinator 工厂 + re-export
- ingestion_coordinator.py: IngestionCoordinator
- backfill_manager.py: BackfillManager
- retry_manager.py: RetryManager
"""

from __future__ import annotations

import ditto_app.process.ingestion_coordinator as _ic
from ditto_app.process.backfill_manager import BackfillManager
from ditto_app.process.coordinator_factory import (
    EXCHANGE_PREFIX_MAP,
    MARKET_INDEX_CODES,
    STYLE_INDEX_CODES,
    SUPPORTED_INSTRUMENT_DATASETS,
    SWIndustryProvider,
    create_coordinator,
    get_all_index_codes,
    get_default_index_codes,
    get_sw_index_codes,
)
from ditto_app.process.retry_manager import RetryManager

# Re-export for backward compatibility
IngestionCoordinator = _ic.IngestionCoordinator
_infer_exchange_suffix = _ic._infer_exchange_suffix  # pyright: ignore[reportPrivateUsage]

__all__ = [
    "EXCHANGE_PREFIX_MAP",
    "MARKET_INDEX_CODES",
    "STYLE_INDEX_CODES",
    "SUPPORTED_INSTRUMENT_DATASETS",
    "BackfillManager",
    "IngestionCoordinator",
    "RetryManager",
    "SWIndustryProvider",
    "create_coordinator",
    "get_all_index_codes",
    "get_default_index_codes",
    "get_sw_index_codes",
]
