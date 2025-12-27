"""Stock data ingestion tasks."""

from __future__ import annotations

import polars as pl
from ditto_datahub import DataHub
from ditto_foundation import M, logger
from prefect import task


@task(
    name="ingest_stock_basic",
    description="Ingest stock basic information and register securities",
    retries=3,
    retry_delay_seconds=[60, 300, 900],
    tags=["stock", "basic", "ingestion"],
)
def ingest_stock_basic(
    source: str = "tushare",
    data_root: str = "data",
) -> dict[str, object]:
    """
    Ingest stock basic information and register securities.

    This task fetches the complete stock list from the source and registers
    all securities. It should be run initially and periodically to ensure
    the securities catalog is up-to-date.

    Data flow:
    1. Fetch data from source (hub.sources.{source}.fetch_stock_basic)
    2. Register each security (hub.securities.register)
    3. Log results

    Args:
        source: Data source name ("tushare" or "akshare").
        data_root: DataHub root directory.

    Returns:
        Dict with ingestion statistics:
        - source: str
        - rows_fetched: int - stocks from source
        - new_securities_registered: int - count of newly registered securities
        - skipped_securities: int - count of skipped securities (already exists)
        - status: str - "success" | "warning" | "failed"

    Raises:
        ValueError: If source is invalid.

    """
    logger.info(
        "Starting stock basic info ingestion",
        event="ingestion_start",
        source=source,
    )

    hub = DataHub(data_root=data_root)

    # Step 1: Fetch stock basic info
    data_source = hub.sources.get(source)
    raw_df = data_source.fetch_stock_basic()

    if raw_df.is_empty():
        logger.warning(
            "No data fetched from source",
            event="ingestion_no_data",
            source=source,
        )
        return {
            "source": source,
            "rows_fetched": 0,
            "new_securities_registered": 0,
            "skipped_securities": 0,
            "status": "no_data",
        }

    rows_fetched = len(raw_df)
    logger.info(
        "Fetched stock basic info from source",
        event="ingestion_fetched",
        rows=rows_fetched,
    )

    # Step 2: Register all securities
    new_securities_registered = 0
    skipped_securities = 0

    for row in raw_df.iter_rows(named=True):
        try:
            sid = hub.securities.register(
                src_code=row["src_code"],
                symbol=row["symbol"],
                name=row["name"],
                exchange=row["exchange"],
                asset_class="stock",
                list_date=str(row["list_date"]),
                source=source,
            )
            new_securities_registered += 1
            logger.debug(
                "Registered stock security",
                event="security_registered",
                symbol=row["symbol"],
                src_code=row["src_code"],
                sid=sid,
            )
        except Exception as e:
            # Likely already registered
            skipped_securities += 1
            logger.debug(
                "Skipped stock security (already registered)",
                event="security_skipped",
                symbol=row.get("symbol"),
                src_code=row.get("src_code"),
                reason=str(e),
            )

    logger.info(
        "Stock basic ingestion completed",
        event="ingestion_complete",
        source=source,
        rows_fetched=rows_fetched,
        new_securities_registered=new_securities_registered,
        skipped_securities=skipped_securities,
    )

    # Record metrics
    M.data_records.add(
        new_securities_registered,
        {"dataset": "stock_basic", "source": source, "status": "success"},
    )

    # Determine status
    status = "warning" if rows_fetched == 0 else "success"

    return {
        "source": source,
        "rows_fetched": rows_fetched,
        "new_securities_registered": new_securities_registered,
        "skipped_securities": skipped_securities,
        "status": status,
    }


@task(
    name="ingest_stock_daily",
    description="Ingest stock daily bars from external source to DataHub",
    retries=3,
    retry_delay_seconds=[60, 300, 900],
    tags=["stock", "bars", "ingestion"],
)
def ingest_stock_daily(
    trade_date: str,
    source: str = "tushare",
    data_root: str = "data",
) -> dict[str, object]:
    """
    Ingest stock daily bars for a specific trade date.

    Data flow:
    1. Fetch data from source (hub.sources.{source}.fetch_stock_daily)
    2. Resolve SIDs (hub.securities.resolve_identifiers_batch)
    3. Auto-register new securities (hub.securities.register)
    4. Transform data format (src_code → sid)
    5. Write to DataHub (hub.bars.write with DQ L1+L2 check)

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
        - new_securities_registered: int - count of newly registered securities
        - skipped_securities: int - count of skipped securities (registration failed)
        - skipped_list: list[str] - list of skipped src_codes
        - failed_checks: int - DQ check failures
        - status: str - "success" | "warning" | "failed"

    Raises:
        ValueError: If trade_date format is invalid.

    """
    logger.info(
        "Starting stock daily bars ingestion",
        event="ingestion_start",
        trade_date=trade_date,
        source=source,
    )

    hub = DataHub(data_root=data_root)

    # Step 1: Fetch data from source
    data_source = hub.sources.get(source)
    raw_df = data_source.fetch_stock_daily(trade_date=trade_date)

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
            "new_securities_registered": 0,
            "skipped_securities": 0,
            "skipped_list": [],
            "failed_checks": 0,
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

    # Step 3: Identify and register new securities
    unresolved = [code for code in src_codes if code not in sid_mapping]
    new_securities_registered = 0
    skipped_securities = 0
    skipped_list: list[str] = []

    if unresolved:
        logger.info(
            "Found unresolved securities, fetching basic info",
            event="ingestion_new_securities",
            count=len(unresolved),
        )

        # Fetch basic stock info
        stock_basic_df = data_source.fetch_stock_basic()

        if not stock_basic_df.is_empty():
            # Filter for unresolved securities
            new_securities = stock_basic_df.filter(pl.col("src_code").is_in(unresolved))

            # Register each new security
            for row in new_securities.iter_rows(named=True):
                try:
                    sid = hub.securities.register(
                        src_code=row["src_code"],
                        symbol=row["symbol"],
                        name=row["name"],
                        exchange=row["exchange"],
                        asset_class="stock",
                        list_date=str(row["list_date"]),
                        source=source,
                    )
                    sid_mapping[row["src_code"]] = sid
                    new_securities_registered += 1
                    logger.info(
                        "Registered new stock security",
                        event="security_registered",
                        symbol=row["symbol"],
                        src_code=row["src_code"],
                        sid=sid,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to register stock security",
                        event="security_register_failed",
                        src_code=row.get("src_code"),
                        error=str(e),
                    )
                    skipped_securities += 1
                    skipped_list.append(row.get("src_code", "unknown"))

    # Step 4: Transform data (src_code → sid)
    transformed_df = raw_df.with_columns(
        pl.col("src_code").replace(sid_mapping).alias("sid")
    ).filter(pl.col("sid").is_not_null())

    # Step 5: Select columns matching BarsStore schema
    transformed_df = transformed_df.select(
        [
            "sid",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "volume",
            "amount",
            "pct_change",
        ]
    )

    # Step 6: Determine year partition
    year = int(trade_date[:4])

    # Step 7: Write to BarsStore
    write_result = hub.bars.write(
        df=transformed_df,
        year=year,
        dataset="stock_daily",
        source=source,
        run_dq_check=True,
    )

    rows_written = write_result.rows_written
    failed_checks = len(write_result.failed_checks) if write_result.failed_checks else 0

    logger.info(
        "Stock daily bars ingestion completed",
        event="ingestion_complete",
        trade_date=trade_date,
        source=source,
        rows_fetched=rows_fetched,
        rows_written=rows_written,
        new_securities_registered=new_securities_registered,
        skipped_securities=skipped_securities,
        failed_checks=failed_checks,
    )

    # Record metrics
    M.data_records.add(
        rows_written,
        {"dataset": "stock_daily", "source": source, "status": "success"},
    )

    # Determine status
    status = "warning" if failed_checks > 0 or skipped_securities > 0 else "success"

    return {
        "trade_date": trade_date,
        "source": source,
        "rows_fetched": rows_fetched,
        "rows_written": rows_written,
        "new_securities_registered": new_securities_registered,
        "skipped_securities": skipped_securities,
        "skipped_list": skipped_list,
        "failed_checks": failed_checks,
        "status": status,
    }
