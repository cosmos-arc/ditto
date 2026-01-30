"""
Capital Domain - 财务与公司基本面数据域。

提供财务报表、估值指标、衍生品、成分股等数据的存储和查询，
支持完整的 PIT（Point-in-Time）能力。

命名映射：
- instrument_id: 标的 ID（统一标识符）
- PIT 时间: effective_from, effective_to
"""

from ditto_datahub.domains.capital.capital_ingestion import (
    CapitalIngestion,
    IngestionResult,
)
from ditto_datahub.domains.capital.capital_store import CapitalStore

__all__ = ["CapitalIngestion", "CapitalStore", "IngestionResult"]
