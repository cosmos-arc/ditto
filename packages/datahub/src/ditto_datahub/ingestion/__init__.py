"""
Ingestion layer for DataHub.

This module provides utilities and services for data ingestion
from external sources into DataHub stores.

Key components:
- IngestionCoordinator: Router for domain-specific ingestion services
- IngestionDataWriter: Utility class for writing data to stores
"""

from ditto_datahub.ingestion.coordinator import IngestionCoordinator, IngestionResult
from ditto_datahub.ingestion.data_writer import IngestionDataWriter

__all__ = [
    "IngestionCoordinator",
    "IngestionDataWriter",
    "IngestionResult",
]
