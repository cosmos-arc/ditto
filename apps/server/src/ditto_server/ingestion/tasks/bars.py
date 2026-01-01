"""ETF bars ingestion task."""

from __future__ import annotations

import polars as pl
from ditto_datahub import DataHub
from ditto_datahub.sources.metadata import IncrementalMode
from ditto_foundation import M, logger
from prefect import task


@task(
    name="ingest_etf_bars",
    description="Ingest ETF daily bars from external source to DataHub",
    retries=3,
    retry_delay_seconds=[60, 300, 900],  # Exponential backoff
    tags=["etf", "bars", "ingestion"],
)
def ingest_etf_bars(  # noqa: PLR0915
    trade_date: str,
    source: str = "tushare",
    data_root: str = "data",
    incremental_mode: str = "quick",
) -> dict[str, object]:
    """
    Ingest ETF daily bars for a specific trade date.

    Data flow:
    1. Fetch data from source (hub.sources.{source}.fetch_etf_daily)
    2. Resolve SIDs (hub.securities.resolve_identifiers_batch)
    3. Auto-register new securities (hub.securities.register)
    4. Transform data format (src_code → sid)
    5. Write to DataHub (hub.bars.write with DQ L1+L2 check)

    Args:
        trade_date: Trade date (YYYY-MM-DD).
        source: Data source name ("tushare" or "akshare").
        data_root: DataHub root directory.
        incremental_mode: Incremental mode ("quick" or "precise").

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
        "Starting ETF bars ingestion",
        event="ingestion_start",
        trade_date=trade_date,
        source=source,
        incremental_mode=incremental_mode,
    )

    # Use context manager to ensure SQLite connections are properly closed
    hub = DataHub(data_root=data_root)

    try:
        # Validate trade_date is a trading day
        if not hub.is_trading_day(trade_date):
            logger.warning(
                "Trade date is not a trading day, skipping ingestion",
                event="ingestion_skipped_non_trading_day",
                trade_date=trade_date,
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
                "status": "skipped",
                "skip_reason": "non_trading_day",
                "incremental_mode": incremental_mode,
                "is_incremental": False,  # Don't know yet since we skip early
            }

        # Parse incremental mode
        mode = (
            IncrementalMode.QUICK
            if incremental_mode == "quick"
            else IncrementalMode.PRECISE
        )

        # Step 1: Read ingestion metadata
        metadata_store = hub.ingestion_metadata_store
        metadata = metadata_store.get_metadata("etf_daily", source)

        # Step 2: Fetch data from source (incremental)
        data_source = hub.sources.get(source)

        last_trade_date = (
            metadata.last_trade_date if metadata and metadata.last_trade_date else None
        )
        last_checksum = metadata.last_checksum if metadata else None

        raw_df, new_metadata = data_source.fetch_etf_daily_incremental(
            trade_date=trade_date,
            mode=mode,
            last_trade_date=last_trade_date,
            last_checksum=last_checksum,
        )

        if raw_df.is_empty():
            logger.warning(
                "No data fetched from source",
                event="ingestion_no_data",
                trade_date=trade_date,
                source=source,
                incremental_mode=incremental_mode,
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
                "incremental_mode": incremental_mode,
                "is_incremental": metadata is not None,
            }

        rows_fetched = len(raw_df)
        logger.info(
            "Fetched data from source",
            event="ingestion_fetched",
            rows=rows_fetched,
            incremental_mode=incremental_mode,
        )

        # Step 3: Resolve SIDs
        src_codes = raw_df["src_code"].unique().to_list()
        sid_mapping = hub.securities.resolve_identifiers_batch(
            identifiers=src_codes,
            source=source,
            asof=trade_date,
        )

        # Step 4: Identify and register new securities
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

            # Fetch basic ETF info
            etf_basic_df = data_source.fetch_etf_basic()

            if not etf_basic_df.is_empty():
                # Filter for unresolved securities
                new_securities = etf_basic_df.filter(
                    pl.col("src_code").is_in(unresolved)
                )

                # Register each new security
                for row in new_securities.iter_rows(named=True):
                    try:
                        sid = hub.securities.register(
                            src_code=row["src_code"],
                            symbol=row["symbol"],
                            name=row["name"],
                            exchange=row["exchange"],
                            asset_class="etf",
                            list_date=str(row["list_date"]),
                            source=source,
                        )
                        sid_mapping[row["src_code"]] = sid
                        new_securities_registered += 1
                        logger.info(
                            "Registered new security",
                            event="security_registered",
                            symbol=row["symbol"],
                            src_code=row["src_code"],
                            sid=sid,
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to register security",
                            event="security_register_failed",
                            src_code=row.get("src_code"),
                            error=str(e),
                        )
                        skipped_securities += 1
                        skipped_list.append(row.get("src_code", "unknown"))

        # Step 5: Transform data (src_code → sid)
        transformed_df = raw_df.with_columns(
            pl.col("src_code").replace(sid_mapping).alias("sid")
        ).filter(pl.col("sid").is_not_null())

        # Step 6: Select columns matching BarsStore schema
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

        # Step 7: Determine year partition
        year = int(trade_date[:4])

        # Step 8: Write to BarsStore
        write_result = hub.bars.write(
            df=transformed_df,
            year=year,
            dataset="etf_daily",
            source=source,
            run_dq_check=True,
        )

        rows_written = write_result.rows_written
        failed_checks = (
            len(write_result.failed_checks) if write_result.failed_checks else 0
        )

        # Step 9: Save ingestion metadata
        metadata_store.save_metadata(new_metadata)

        logger.info(
            "Ingestion metadata saved",
            event="ingestion_metadata_saved",
            dataset="etf_daily",
            source=source,
            last_trade_date=new_metadata.last_trade_date
            if new_metadata.last_trade_date
            else None,
            last_rows=new_metadata.last_rows,
        )

        logger.info(
            "ETF bars ingestion completed",
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
            {"dataset": "etf_daily", "source": source, "status": "success"},
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
            "incremental_mode": incremental_mode,
            "is_incremental": metadata is not None,
            "dq_result": write_result.dq_result,
        }
    finally:
        # Always close hub to prevent SQLite connection leaks
        hub.close()
