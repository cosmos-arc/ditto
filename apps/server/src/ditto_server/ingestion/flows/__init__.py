"""Prefect flows for data ingestion."""

from ditto_server.ingestion.flows.daily_ingest import daily_ingest_flow
from ditto_server.ingestion.flows.scheduled_ingest import (
    create_weekday_schedule,
    scheduled_daily_ingest_flow,
)

__all__ = [
    "create_weekday_schedule",
    "daily_ingest_flow",
    "scheduled_daily_ingest_flow",
]
