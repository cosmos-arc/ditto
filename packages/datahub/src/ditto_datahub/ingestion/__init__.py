"""
Ingestion utilities for DataHub.

This module provides utilities for data ingestion
from external sources into DataHub stores.

Key components:
- IngestionDataWriter: Utility class for writing data to stores

Note: Business orchestration (IngestionCoordinator) has been moved to Port layer.
"""

from ditto_datahub.ingestion.data_writer import IngestionDataWriter

__all__ = [
    "IngestionDataWriter",
]
