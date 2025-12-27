"""Prefect flows for data ingestion."""

from ditto_server.ingestion.flows.daily_ingest import daily_ingest_flow

__all__ = ["daily_ingest_flow"]
