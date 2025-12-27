"""Daily data ingestion flow."""

from ditto_foundation.observability import logger
from prefect import flow

from ditto_server.ingestion.tasks.adj_factor import ingest_adj_factor, ingest_fund_adj
from ditto_server.ingestion.tasks.bars import ingest_etf_bars
from ditto_server.ingestion.tasks.stock import ingest_stock_basic, ingest_stock_daily


@flow(
    name="daily_ingest_flow",
    description="Complete daily data ingestion flow for all datasets",
)
def daily_ingest_flow(
    trade_date: str,
    source: str = "tushare",
    data_root: str = "data",
    run_stock_basic: bool = False,
) -> dict[str, object]:
    """
    Complete daily data ingestion flow.

    This flow orchestrates the ingestion of all market data:
    - Stock basic info (optional, run once initially)
    - ETF daily bars
    - Stock daily bars
    - Stock adjustment factors
    - ETF/fund adjustment factors

    Args:
        trade_date: Trade date in YYYY-MM-DD format
        source: Data source name (default: tushare)
        data_root: Root directory for DataHub storage
        run_stock_basic: Whether to run stock_basic ingestion (default: False)

    Returns:
        dict: Flow execution summary with status and per-task results

    Examples:
        >>> # Initial run with stock basic info
        >>> result = daily_ingest_flow("2024-01-02", run_stock_basic=True)
        >>> # Daily run without stock basic info
        >>> result = daily_ingest_flow("2024-01-03")
        >>> print(result["status"])
        'success'

    """
    logger.info(
        "Starting daily ingestion flow",
        event="flow_start",
        trade_date=trade_date,
        source=source,
        run_stock_basic=run_stock_basic,
    )

    results: dict[str, object] = {}

    # Step 1: Stock basic info (optional, run once)
    if run_stock_basic:
        stock_basic_future = ingest_stock_basic.submit(
            source=source,
            data_root=data_root,
        )
        results["stock_basic"] = stock_basic_future.result()

    # Step 2: Daily bars (parallel execution)
    logger.info(
        "Starting daily bars ingestion (parallel)",
        event="bars_ingestion_start",
    )
    etf_bars_future = ingest_etf_bars.submit(
        trade_date=trade_date,
        source=source,
        data_root=data_root,
    )
    stock_bars_future = ingest_stock_daily.submit(
        trade_date=trade_date,
        source=source,
        data_root=data_root,
    )

    results["etf_bars"] = etf_bars_future.result()
    results["stock_bars"] = stock_bars_future.result()

    # Step 3: Adjustment factors (parallel execution)
    logger.info(
        "Starting adjustment factors ingestion (parallel)",
        event="adj_factor_ingestion_start",
    )
    adj_factor_future = ingest_adj_factor.submit(
        trade_date=trade_date,
        source=source,
        data_root=data_root,
    )
    fund_adj_future = ingest_fund_adj.submit(
        trade_date=trade_date,
        source=source,
        data_root=data_root,
    )

    results["adj_factor"] = adj_factor_future.result()
    results["fund_adj"] = fund_adj_future.result()

    # Determine overall flow status
    statuses = [
        r.get("status", "failed")  # type: ignore[attr-defined]
        for r in results.values()
    ]
    if all(s == "success" for s in statuses):
        flow_status = "success"
    elif all(s in ("success", "warning", "no_data") for s in statuses):
        flow_status = "warning"
    else:
        flow_status = "failed"

    # Log summary
    logger.info(
        "Daily ingestion flow completed",
        event="flow_complete",
        trade_date=trade_date,
        status=flow_status,
        tasks_count=len(results),
        etf_rows_written=results["etf_bars"]["rows_written"],  # type: ignore[index]
        stock_rows_written=results["stock_bars"]["rows_written"],  # type: ignore[index]
        adj_factor_rows_written=results["adj_factor"]["rows_written"],  # type: ignore[index]
        fund_adj_rows_written=results["fund_adj"]["rows_written"],  # type: ignore[index]
        new_etf_securities=results["etf_bars"]["new_securities_registered"],  # type: ignore[index]
        new_stock_securities=results.get("stock_basic", {}).get(  # type: ignore[attr-defined]
            "new_securities_registered",
            0,
        ),
    )

    return {
        "trade_date": trade_date,
        "source": source,
        "status": flow_status,
        "tasks": results,
    }
