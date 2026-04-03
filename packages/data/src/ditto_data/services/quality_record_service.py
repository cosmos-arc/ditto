"""Re-export shim — module moved to ditto_data.ingestion."""

from ditto_data.ingestion.quality_record_service import (
    QualityRecordService,
)

__all__ = [
    "QualityRecordService",
]
