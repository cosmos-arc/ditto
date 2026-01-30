"""
Capital Domain - 资金与资本市场数据域。

提供估值指标、融资融券、股权质押、期货、指数成分股等数据的存储和查询，
支持完整的 PIT（Point-in-Time）能力。

命名映射：
- instrument_id: 标的 ID（统一标识符）
- PIT 时间: effective_from, effective_to
"""

from ditto_datahub.domains.capital.capital_ingestion import (
    CapitalIngestion,
    IngestionResult,
)
from ditto_datahub.domains.capital.capital_service import CapitalService
from ditto_datahub.domains.capital.capital_store import CapitalStore

__all__ = [
    "CapitalIngestion",
    "CapitalService",
    "CapitalStore",
    "IngestionResult",
]
