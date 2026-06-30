"""Date range helpers for ingestion routes."""

from __future__ import annotations

from datetime import date, timedelta

from ditto_data.models import Dataset, DateScheduleType
from ditto_data.services.metadata_service import MetadataService

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.dataset_registry import (
    DatasetRegistry,
    default_dataset_registry,
)

__all__ = [
    "list_ingestion_dates",
    "list_natural_days",
]


def list_ingestion_dates(
    dataset: str,
    start_date: str,
    end_date: str,
    *,
    metadata_service: MetadataService,
    registry: DatasetRegistry | None = None,
) -> list[str]:
    """Return the date sequence used by a dataset's date-level ingestion route."""
    registry = registry or default_dataset_registry()
    try:
        dataset_enum = Dataset(dataset)
        registration = registry.require(dataset_enum)
    except (ValueError, AppProcessError):
        schedule_type = DateScheduleType.TRADING_DAYS
    else:
        schedule_type = registration.date_schedule

    match schedule_type:
        case DateScheduleType.TRADING_DAYS:
            return metadata_service.list_trading_days(start_date, end_date)
        case DateScheduleType.NATURAL_DAYS | DateScheduleType.SOURCE_DEFINED:
            return list_natural_days(start_date, end_date)


def list_natural_days(start_date: str, end_date: str) -> list[str]:
    """Generate natural days in the inclusive [start_date, end_date] range."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days
