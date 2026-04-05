"""数据摄取服务 -- Backward-compatible re-exports (模块拆分后的 shim)."""

from ditto_app.process.coordinator import (
    EXCHANGE_PREFIX_MAP,
    MARKET_INDEX_CODES,
    STYLE_INDEX_CODES,
    SUPPORTED_INSTRUMENT_DATASETS,
    BackfillManager,
    IngestionCoordinator,
    RetryManager,
    SWIndustryProvider,
    create_coordinator,
    get_all_index_codes,
    get_default_index_codes,
    get_sw_index_codes,
)
from ditto_app.process.data_writer import IngestionDataWriter
from ditto_app.process.ingestion_config import (
    IngestionConfig,
    IngestionCoordinatorConfig,
)
from ditto_app.process.list_date_inference import (
    API_LIMITS,
    EARLIEST_LIST_DATE_INFERENCE,
    TRADING_DAYS_PER_YEAR,
    ListDateInferenceService,
)
from ditto_app.process.metadata_manager import MetadataManager
from ditto_app.process.result_handler import IngestionResultHandler, count_results

__all__ = [
    "API_LIMITS",
    "EARLIEST_LIST_DATE_INFERENCE",
    "EXCHANGE_PREFIX_MAP",
    "MARKET_INDEX_CODES",
    "STYLE_INDEX_CODES",
    "SUPPORTED_INSTRUMENT_DATASETS",
    "TRADING_DAYS_PER_YEAR",
    "BackfillManager",
    "IngestionConfig",
    "IngestionCoordinator",
    "IngestionCoordinatorConfig",
    "IngestionDataWriter",
    "IngestionResultHandler",
    "ListDateInferenceService",
    "MetadataManager",
    "RetryManager",
    "SWIndustryProvider",
    "count_results",
    "create_coordinator",
    "get_all_index_codes",
    "get_default_index_codes",
    "get_sw_index_codes",
]
