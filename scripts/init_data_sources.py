"""
Initialize data sources and perform initial data fetch.

This script performs the initial setup of data sources and fetches
historical data for the Golden Dataset ETFs.
"""

import asyncio
import logging
import sys
import traceback
from datetime import date, timedelta

try:
    from ditto_foundation.config.settings import get_settings
    from ditto_foundation.data import (
        DataCollector,
        DataService,
    )
    from ditto_foundation.data.datasources import DataSourceFactory
except ImportError as e:
    print(f"导入失败: {e}")
    print("请确保在 pixi 环境中运行: pixi run python scripts/init_data_sources.py")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Quality thresholds
MIN_QUALITY_SCORE = 70

# Golden Dataset ETFs
GOLDEN_ETFS = [
    "510300.SH",  # 沪深300 ETF -流动性最好, 基准
    "516010.SH",  # 游戏 ETF - 流动性较差, 测试极端情况
    "513100.SH",  # 纳指 ETF - 跨境ETF, 有溢价和熔断
]

# Golden Dataset Index
GOLDEN_INDEX = "000300.SH"  # 沪深300 指数 - Regime基准指数


async def test_data_sources(data_factory: DataSourceFactory) -> bool:
    """Test data source connectivity."""
    logger.info("Testing data source connectivity...")

    # Test primary source
    try:
        client = await data_factory.get_client()
        logger.info(f"Primary source ({client.__class__.__name__}) is accessible")
    except Exception as e:
        logger.error(f"Primary source test failed: {e}")
        return False

    # Test backup source
    try:
        backup_clients = await data_factory.get_backup_clients()
        if backup_clients:
            logger.info(
                f"Backup source ({backup_clients[0].__class__.__name__}) is accessible"
            )
        else:
            logger.warning("No backup sources configured")
    except Exception as e:
        logger.warning(f"Backup source test failed: {e}")

    return True


async def fetch_golden_dataset(collector: DataCollector) -> None:
    """
    Fetch historical data for Golden Dataset ETFs.

    Fetches 1 year of historical data for the Golden Dataset ETFs
    to establish baseline data for testing and validation.
    """
    logger.info("Fetching Golden Dataset historical data...")

    # Calculate date range (last 1 year)
    end_date = date.today()
    start_date = end_date - timedelta(days=365)

    logger.info(f"Date range: {start_date} to {end_date}")

    # Update ETF list first
    logger.info("Step 1: Updating ETF list...")
    etf_stats = await collector.update_etf_list(force_update=True)

    if etf_stats["errors"]:
        logger.error(f"ETF list update had errors: {len(etf_stats['errors'])}")
        # Continue anyway, as some ETFs might already be in the database

    # Fetch data for each Golden ETF
    for etf_code in GOLDEN_ETFS:
        logger.info(f"Step 2: Fetching data for {etf_code}...")

        try:
            # Update daily data
            daily_stats = await collector.update_daily_data(
                ts_codes=[etf_code],
                start_date=start_date,
                end_date=end_date,
                force_update=True,
            )

            logger.info(f"  Daily data: {daily_stats['total_records']} records")

            # Update adjustment factors
            adj_stats = await collector.update_adj_factors(
                ts_codes=[etf_code],
                start_date=start_date,
                end_date=end_date,
                force_update=True,
            )

            logger.info(f"  Adj factors: {adj_stats.get('total_records', 0)} records")

        except Exception as e:
            logger.error(f"Failed to fetch data for {etf_code}: {e}")

    logger.info("Golden Dataset fetch completed")


async def validate_golden_dataset(collector: DataCollector) -> None:
    """
    Validate the Golden Dataset data quality.

    Performs basic validation checks on the fetched data.
    """
    logger.info("Validating Golden Dataset data quality...")

    # Check data for each Golden ETF
    for etf_code in GOLDEN_ETFS:
        logger.info(f"Validating {etf_code}...")

        try:
            # Get last 30 days for validation
            end_date = date.today()
            start_date = end_date - timedelta(days=30)

            report = await collector.verify_data_quality(etf_code, start_date, end_date)

            if report.get("quality_score", 0) < MIN_QUALITY_SCORE:
                logger.warning(
                    f"Low quality score for {etf_code}: "
                    f"{report.get('quality_score', 0)}"
                )

            issues = report.get("issues", [])
            if issues:
                logger.warning(f"Found {len(issues)} issues for {etf_code}:")
                for issue in issues[:5]:  # Show first 5 issues
                    logger.warning(f"  - {issue}")

        except Exception as e:
            logger.error(f"Failed to validate {etf_code}: {e}")


async def create_data_summary(data_service: DataService) -> None:
    """
    Create a summary of the data in the database.

    Generates a summary report of the data stored in the database
    for verification purposes.
    """
    logger.info("Creating data summary...")

    try:
        # Get ETF list
        etf_df = await data_service.get_etf_list()
        logger.info(f"Total ETFs in database: {etf_df.height}")

        # Get data coverage for Golden ETFs
        for etf_code in GOLDEN_ETFS:
            # Get latest data
            latest_df = await data_service.get_daily_data(
                etf_code,
                start_date=date.today() - timedelta(days=7),
                end_date=date.today(),
            )

            if not latest_df.is_empty():
                latest_date = latest_df["trade_date"].max()
                logger.info(f"{etf_code}: Latest data available for {latest_date}")
            else:
                logger.warning(f"{etf_code}: No recent data available")

        # Get total data counts
        # Note: These would need to be implemented in DataService
    # logger.info(
    #     f"Total daily data records: {await data_service.get_daily_data_count()}"
    # )
    # logger.info(
    #     f"Total adj factor records: {await data_service.get_adj_factor_count()}"
    # )

    except Exception as e:
        logger.error(f"Failed to create data summary: {e}")


async def main() -> None:
    """Initialize data sources."""
    logger.info("Starting data source initialization...")

    try:
        # Load configuration
        settings = get_settings()

        # Check if Tushare API key is configured
        if not settings.data_source.tushare_token:
            logger.error(
                "Tushare API key not configured. Please set TUSHARE_API_KEY in .env"
            )
            sys.exit(1)

        # For now, create a simple data factory wrapper
        # TODO: Update DataCollector to use new DataSourceFactory directly
        data_factory = DataSourceFactory()

        # Initialize data service
        data_service = DataService(
            duckdb_path=settings.database.duckdb_path,
            sqlite_path=settings.database.sqlite_path,
        )

        # Initialize data collector
        collector = DataCollector(
            data_factory=data_factory,
            data_service=data_service,
            batch_size=1000,
            max_concurrent_fetches=3,  # Conservative for initial fetch
        )

        # Step 1: Test data source connectivity
        if not await test_data_sources(data_factory):
            logger.error("Data source connectivity test failed")
            sys.exit(1)

        # Step 2: Fetch Golden Dataset
        await fetch_golden_dataset(collector)

        # Step 3: Validate data quality
        await validate_golden_dataset(collector)

        # Step 4: Create data summary
        await create_data_summary(data_service)

        logger.info("Data source initialization completed successfully!")
        logger.info("\nNext steps:")
        logger.info("1. Review the data quality report above")
        logger.info("2. Run manual verification of key data points")
        logger.info("3. Proceed to Phase 0.5: Data Quality Validation")

    except KeyboardInterrupt:
        logger.info("Initialization interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
