"""Re-export shim — module moved to ditto_data.ingestion."""

from ditto_data.ingestion.ingestion_log_service import IngestionLogService

__all__ = [
    "IngestionLogService",
]
