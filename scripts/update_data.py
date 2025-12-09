"""
Data update script for fetching and storing market data.

This script provides command-line interface for updating various
types of market data from external sources.
"""

import argparse
import asyncio
import logging
import sys
import traceback
from datetime import date, datetime, timedelta
from typing import Any

try:
    from ditto_foundation.config.settings import get_settings
    from ditto_foundation.data import (
        DataCollector,
        DataService,
    )
    from ditto_foundation.data.constants import DataSourceType
    from ditto_foundation.data.datasources import DataSourceFactory
except ImportError as e:
    print(f"导入失败: {e}")
    print("请确保在 pixi 环境中运行: pixi run python scripts/update_data.py")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/data_update.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)


async def update_etf_list(
    collector: DataCollector,
    force: bool = False,
) -> dict[str, Any]:
    """Update ETF list."""
    logger.info("Starting ETF list update")
    stats = await collector.update_etf_list(force_update=force)

    logger.info("ETF list update completed:")
    logger.info(f"  Total processed: {stats['total_processed']}")
    logger.info(f"  New records: {stats['new_records']}")
    logger.info(f"  Updated records: {stats['updated_records']}")
    logger.info(f"  Duration: {stats['duration']:.2f} seconds")

    if stats["errors"]:
        logger.warning(f"Encountered {len(stats['errors'])} errors:")
        for error in stats["errors"][:5]:  # Show first 5 errors
            logger.warning(f"  - {error}")

    return stats


async def update_daily_data(
    collector: DataCollector,
    symbols: list[str] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Update daily market data."""
    logger.info(
        f"Starting daily data update for {len(symbols) if symbols else 'all'} ETFs"
    )

    if start_date and end_date:
        logger.info(f"Date range: {start_date} to {end_date}")

    stats = await collector.update_daily_data(
        ts_codes=symbols,
        start_date=start_date,
        end_date=end_date,
        force_update=force,
    )

    logger.info("Daily data update completed:")
    logger.info(f"  ETFs processed: {stats['total_processed']}")
    logger.info(f"  Total records: {stats['total_records']}")
    logger.info(f"  New records: {stats['new_records']}")
    logger.info(f"  Updated records: {stats['updated_records']}")
    logger.info(f"  Duration: {stats['duration']:.2f} seconds")

    if stats["errors"]:
        logger.warning(f"Encountered {len(stats['errors'])} errors:")
        for error in stats["errors"][:5]:  # Show first 5 errors
            logger.warning(f"  - {error}")

    return stats


async def update_adj_factors(
    collector: DataCollector,
    symbols: list[str] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Update adjustment factors."""
    symbol_count = len(symbols) if symbols else 0
    count_text = str(symbol_count) if symbol_count > 0 else "all"
    logger.info(f"Starting adjustment factor update for {count_text} ETFs")

    stats = await collector.update_adj_factors(
        ts_codes=symbols,
        start_date=start_date,
        end_date=end_date,
        force_update=force,
    )

    logger.info("Adjustment factor update completed")
    # Implementation would log statistics similar to update_daily_data

    return stats


async def verify_data_quality(
    collector: DataCollector,
    symbol: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    """Verify data quality for a specific ETF."""
    if not start_date:
        start_date = date.today() - timedelta(days=30)
    if not end_date:
        end_date = date.today()

    logger.info(f"Verifying data quality for {symbol} from {start_date} to {end_date}")

    report = await collector.verify_data_quality(symbol, start_date, end_date)

    logger.info(f"Data quality report for {symbol}:")
    logger.info(f"  Quality score: {report.get('quality_score', 0)}")
    logger.info(f"  Daily records: {report.get('daily_records', 0)}")
    logger.info(f"  Adj factor records: {report.get('adj_factor_records', 0)}")

    issues = report.get("issues", [])
    if issues:
        logger.warning(f"Found {len(issues)} issues:")
        for issue in issues[:10]:  # Show first 10 issues
            logger.warning(f"  - {issue}")
    else:
        logger.info("No issues found")

    return report


async def show_status(collector: DataCollector) -> None:
    """Show current data update status."""
    logger.info("Fetching data update status...")

    status = await collector.get_update_status()

    logger.info("Data Update Status:")
    logger.info(f"  ETF count: {status.get('etf_count', 0)}")
    logger.info(
        f"  Recent data coverage: {status.get('recent_data_coverage', 'Unknown')}"
    )

    if "error" in status:
        logger.error(f"Error fetching status: {status['error']}")


async def main() -> None:
    """Update market data."""
    parser = argparse.ArgumentParser(
        description="Update market data from external sources"
    )
    parser.add_argument(
        "command",
        choices=["etfs", "daily", "adj", "verify", "status", "all"],
        help="Command to execute",
    )
    parser.add_argument(
        "--symbols", nargs="+", help="ETF symbols to update (default: all)"
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--force", action="store_true", help="Force update existing data"
    )
    parser.add_argument(
        "--source",
        choices=["tushare", "akshare"],
        default="tushare",
        help="Primary data source",
    )
    parser.add_argument("--verify-symbol", help="Symbol to verify (for verify command)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Load configuration
        settings = get_settings()

        # Initialize data source factory
        data_factory = DataSourceFactory(
            primary_source=(
                DataSourceType.TUSHARE
                if args.source == "tushare"
                else DataSourceType.AKSHARE
            ),
            tushare_api_key=settings.data_source.tushare_token,
            tushare_pro_account=settings.tushare.pro_account,
        )

        # Initialize data service
        data_service = DataService(
            duckdb_path=settings.database.duckdb_path,
            sqlite_path=settings.database.sqlite_path,
        )

        # Initialize data collector
        collector = DataCollector(
            data_factory=data_factory,
            data_service=data_service,
        )

        # Execute command
        if args.command == "etfs":
            await update_etf_list(collector, force=args.force)

        elif args.command == "daily":
            await update_daily_data(
                collector,
                symbols=args.symbols,
                start_date=args.start_date,
                end_date=args.end_date,
                force=args.force,
            )

        elif args.command == "adj":
            await update_adj_factors(
                collector,
                symbols=args.symbols,
                start_date=args.start_date,
                end_date=args.end_date,
                force=args.force,
            )

        elif args.command == "verify":
            if not args.verify_symbol:
                logger.error("--verify-symbol is required for verify command")
                sys.exit(1)
            await verify_data_quality(
                collector,
                args.verify_symbol,
                start_date=args.start_date,
                end_date=args.end_date,
            )

        elif args.command == "status":
            await show_status(collector)

        elif args.command == "all":
            # Run all updates in sequence
            logger.info("Running full data update sequence...")

            # 1. Update ETF list
            await update_etf_list(collector, force=args.force)

            # 2. Update daily data
            await update_daily_data(
                collector,
                symbols=args.symbols,
                start_date=args.start_date,
                end_date=args.end_date,
                force=args.force,
            )

            # 3. Update adjustment factors
            await update_adj_factors(
                collector,
                symbols=args.symbols,
                start_date=args.start_date,
                end_date=args.end_date,
                force=args.force,
            )

            logger.info("Data update completed successfully")

    except KeyboardInterrupt:
        logger.info("Data update interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Data update failed: {e}")
        if args.verbose:
            logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
