"""Adjustment factor ingestion tasks."""

from __future__ import annotations

import polars as pl
from ditto_datahub import DataHub
from ditto_foundation import M, logger
from prefect import task


@task(
    name="ingest_adj_factor",
    description="Ingest stock adjustment factors from external source to DataHub",
    retries=3,
    retry_delay_seconds=[60, 300, 900],
    tags=["stock", "adj_factor", "ingestion"],
)
def ingest_adj_factor(
    trade_date: str,
    source: str = "tushare",
    data_root: str = "data",
) -> dict[str, object]:
    """
    Ingest stock adjustment factors for a specific trade date.

    Data flow:
    1. Fetch data from source (hub.sources.{source}.fetch_adj_factor)
    2. Resolve SIDs (hub.securities.resolve_identifiers_batch)
    3. Transform data format (src_code → sid)
    4. Write to DataHub (hub.adj_factor_store.write)

    Args:
        trade_date: Trade date (YYYY-MM-DD).
        source: Data source name ("tushare" or "akshare").
        data_root: DataHub root directory.

    Returns:
        Dict with ingestion statistics:
        - trade_date: str
        - source: str
        - rows_fetched: int - rows from source
        - rows_written: int - rows written to DataHub
        - skipped_unresolved: int - count of skipped records (unresolved src_codes)
        - status: str - "success" | "warning" | "failed"

    Raises:
        ValueError: If trade_date format is invalid.

    """
    logger.info(
        "Starting stock adjustment factors ingestion",
        event="ingestion_start",
        trade_date=trade_date,
        source=source,
    )

    hub = DataHub(data_root=data_root)

    # Step 1: Fetch data from source
    data_source = hub.sources.get(source)
    raw_df = data_source.fetch_adj_factor(trade_date=trade_date)

    if raw_df.is_empty():
        logger.warning(
            "No data fetched from source",
            event="ingestion_no_data",
            trade_date=trade_date,
            source=source,
        )
        return {
            "trade_date": trade_date,
            "source": source,
            "rows_fetched": 0,
            "rows_written": 0,
            "skipped_unresolved": 0,
            "status": "no_data",
        }

    rows_fetched = len(raw_df)
    logger.info(
        "Fetched data from source",
        event="ingestion_fetched",
        rows=rows_fetched,
    )

    # Step 2: Resolve SIDs
    src_codes = raw_df["src_code"].unique().to_list()
    sid_mapping = hub.securities.resolve_identifiers_batch(
        identifiers=src_codes,
        source=source,
        asof=trade_date,
    )

    # Step 3: Transform data (src_code → sid)
    transformed_df = raw_df.with_columns(
        pl.col("src_code").replace(sid_mapping).alias("sid")
    ).filter(pl.col("sid").is_not_null())

    skipped_unresolved = rows_fetched - len(transformed_df)

    # Step 4: Determine year partition
    year = int(trade_date[:4])

    # Step 5: Write to AdjFactorStore
    file_path, checksum = hub.adj_factor_store.write(
        dataset="adj_factor",
        df=transformed_df,
        year=year,
    )

    rows_written = len(transformed_df)

    logger.info(
        "Stock adjustment factors ingestion completed",
        event="ingestion_complete",
        trade_date=trade_date,
        source=source,
        rows_fetched=rows_fetched,
        rows_written=rows_written,
        skipped_unresolved=skipped_unresolved,
        file_path=file_path,
        checksum=checksum,
    )

    # Record metrics
    M.data_records.add(
        rows_written,
        {"dataset": "adj_factor", "source": source, "status": "success"},
    )

    # Determine status
    status = "warning" if skipped_unresolved > 0 else "success"

    return {
        "trade_date": trade_date,
        "source": source,
        "rows_fetched": rows_fetched,
        "rows_written": rows_written,
        "skipped_unresolved": skipped_unresolved,
        "status": status,
    }


@task(
    name="ingest_fund_adj",
    description="Ingest ETF/fund adjustment factors from external source to DataHub",
    retries=3,
    retry_delay_seconds=[60, 300, 900],
    tags=["etf", "fund_adj", "ingestion"],
)
def ingest_fund_adj(
    trade_date: str,
    source: str = "tushare",
    data_root: str = "data",
) -> dict[str, object]:
    """
    Ingest ETF/fund adjustment factors for a specific trade date.

    Data flow:
    1. Fetch data from source (hub.sources.{source}.fetch_fund_adj)
    2. Resolve SIDs (hub.securities.resolve_identifiers_batch)
    3. Transform data format (src_code → sid)
    4. Write to DataHub (hub.adj_factor_store.write)

    Args:
        trade_date: Trade date (YYYY-MM-DD).
        source: Data source name ("tushare" or "akshare").
        data_root: DataHub root directory.

    Returns:
        Dict with ingestion statistics:
        - trade_date: str
        - source: str
        - rows_fetched: int - rows from source
        - rows_written: int - rows written to DataHub
        - skipped_unresolved: int - count of skipped records (unresolved src_codes)
        - status: str - "success" | "warning" | "failed"

    Raises:
        ValueError: If trade_date format is invalid.

    """
    logger.info(
        "Starting ETF/fund adjustment factors ingestion",
        event="ingestion_start",
        trade_date=trade_date,
        source=source,
    )

    hub = DataHub(data_root=data_root)

    # Step 1: Fetch data from source
    data_source = hub.sources.get(source)
    raw_df = data_source.fetch_fund_adj(trade_date=trade_date)

    if raw_df.is_empty():
        logger.warning(
            "No data fetched from source",
            event="ingestion_no_data",
            trade_date=trade_date,
            source=source,
        )
        return {
            "trade_date": trade_date,
            "source": source,
            "rows_fetched": 0,
            "rows_written": 0,
            "skipped_unresolved": 0,
            "status": "no_data",
        }

    rows_fetched = len(raw_df)
    logger.info(
        "Fetched data from source",
        event="ingestion_fetched",
        rows=rows_fetched,
    )

    # Step 2: Resolve SIDs
    src_codes = raw_df["src_code"].unique().to_list()
    sid_mapping = hub.securities.resolve_identifiers_batch(
        identifiers=src_codes,
        source=source,
        asof=trade_date,
    )

    # Step 3: Transform data (src_code → sid)
    transformed_df = raw_df.with_columns(
        pl.col("src_code").replace(sid_mapping).alias("sid")
    ).filter(pl.col("sid").is_not_null())

    skipped_unresolved = rows_fetched - len(transformed_df)

    # Step 4: Determine year partition
    year = int(trade_date[:4])

    # Step 5: Write to AdjFactorStore
    file_path, checksum = hub.adj_factor_store.write(
        dataset="fund_adj",
        df=transformed_df,
        year=year,
    )

    rows_written = len(transformed_df)

    logger.info(
        "ETF/fund adjustment factors ingestion completed",
        event="ingestion_complete",
        trade_date=trade_date,
        source=source,
        rows_fetched=rows_fetched,
        rows_written=rows_written,
        skipped_unresolved=skipped_unresolved,
        file_path=file_path,
        checksum=checksum,
    )

    # Record metrics
    M.data_records.add(
        rows_written,
        {"dataset": "fund_adj", "source": source, "status": "success"},
    )

    # Determine status
    status = "warning" if skipped_unresolved > 0 else "success"

    return {
        "trade_date": trade_date,
        "source": source,
        "rows_fetched": rows_fetched,
        "rows_written": rows_written,
        "skipped_unresolved": skipped_unresolved,
        "status": status,
    }
