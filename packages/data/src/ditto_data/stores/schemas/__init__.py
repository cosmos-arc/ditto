"""StoreSchema 统一导出."""

from __future__ import annotations

from ditto_data.stores.schemas.market_schemas import (
    ADJ_FACTOR_STORE_SCHEMA,
    ETF_DAILY_STORE_SCHEMA,
    INDEX_DAILY_STORE_SCHEMA,
    STOCK_DAILY_STORE_SCHEMA,
    STOCK_STATUS_STORE_SCHEMA,
)
from ditto_data.stores.schemas.metadata_schemas import (
    INDEX_WEIGHT_STORE_SCHEMA,
    UNIVERSE_CONSTITUENT_STORE_SCHEMA,
)
from ditto_data.stores.schemas.store_schema import StoreSchema

__all__ = [
    "ADJ_FACTOR_STORE_SCHEMA",
    "ETF_DAILY_STORE_SCHEMA",
    "INDEX_DAILY_STORE_SCHEMA",
    "INDEX_WEIGHT_STORE_SCHEMA",
    "STOCK_DAILY_STORE_SCHEMA",
    "STOCK_STATUS_STORE_SCHEMA",
    "UNIVERSE_CONSTITUENT_STORE_SCHEMA",
    "StoreSchema",
]
