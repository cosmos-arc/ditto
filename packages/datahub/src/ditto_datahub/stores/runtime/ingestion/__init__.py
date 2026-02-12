"""Runtime ingestion stores."""

from ditto_datahub.stores.runtime.ingestion.ingestion_log_reader import (
    IngestionLogReader,
)
from ditto_datahub.stores.runtime.ingestion.ingestion_log_writer import (
    IngestionLogWriter,
)

__all__ = ["IngestionLogReader", "IngestionLogWriter"]
