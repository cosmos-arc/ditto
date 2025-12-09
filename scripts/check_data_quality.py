"""
Data quality check script.

This script provides command-line interface for running data quality
checks on stored market data, generating reports, and monitoring
data health.
"""

# Standard library imports
import argparse
import asyncio
import logging
import sys
import traceback
from datetime import date, datetime, timedelta

try:
    from data.clients.factory import DataSourceFactory, DataSourceType
    from ditto_foundation.config.settings import get_settings
    from data.service import DataService
except ImportError as e:
    print(f"导入失败: {e}")
    print("请确保在 pixi 环境中运行: pixi run python scripts/check_data_quality.py")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def check_symbol_quality(
    service: DataQualityService,
    symbol: str,
    start_date: date | None,
    end_date: date | None,
    validators: list[str] | None,
) -> None:
    """Check quality for a single symbol."""
    logger.info(f"Checking data quality for {symbol}")

    if not start_date:
        start_date = date.today() - timedelta(days=30)
    if not end_date:
        end_date = date.today()

    results = await service.validate_symbol(symbol, start_date, end_date, validators)

    # Print results
    print(f"\n{'=' * 60}")
    print(f"Quality Report for {symbol}")
    print(f"{'=' * 60}")
    print(f"Date Range: {start_date} to {end_date}")
    print(f"Validators Run: {len(results)}")

    total_issues = 0
    critical_count = 0
    error_count = 0

    for validator_name, result in results.items():
        print(f"\n{validator_name.upper()}:")
        print(f"  Status: {'✓ PASS' if result.is_valid else '✗ FAIL'}")
        print(f"  Issues: {len(result.issues)}")

        total_issues += len(result.issues)

        # Group issues by severity
        severity_counts = {
            "critical": 0,
            "error": 0,
            "warning": 0,
            "info": 0,
        }

        for issue in result.issues:
            severity_counts[issue.severity.value] += 1

        for severity, count in severity_counts.items():
            if count > 0:
                print(f"  {severity.capitalize()}: {count}")
                if severity == "critical":
                    critical_count += count
                elif severity == "error":
                    error_count += count

        # Show top issues
        if result.issues:
            print("\n  Top Issues:")
            for issue in result.issues[:5]:  # Show first 5
                print(f"    - [{issue.code}] {issue.message}")

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY:")
    print(f"Total Issues: {total_issues}")
    if critical_count > 0:
        print(f"✗ CRITICAL ISSUES: {critical_count}")
    if error_count > 0:
        print(f"✗ ERRORS: {error_count}")
    score = max(0, 100 - critical_count * 20 - error_count * 5)
    print(f"Overall Quality Score: {score}/100")


async def run_health_check(
    service: DataQualityService, sample_size: int, days_back: int
) -> None:
    """Run data health check."""
    logger.info("Running data health check")

    health = await service.run_health_check(
        sample_size=sample_size, days_back=days_back
    )

    print(f"\n{'=' * 60}")
    print("DATA HEALTH CHECK")
    print(f"{'=' * 60}")
    print(f"Health Status: {'✓ HEALTHY' if health['healthy'] else '✗ UNHEALTHY'}")
    print(f"Health Score: {health['score']:.1f}%")
    print(f"Symbols Checked: {len(health['symbols_checked'])}")
    print(
        f"Date Range: {health['date_range']['start']} to {health['date_range']['end']}"
    )
    print(f"Total Validations: {health['total_validations']}")
    print(f"Passed Validations: {health['passed_validations']}")
    print(f"Critical Issues: {health['critical_issues']}")

    if health["critical_issues"] > 0:
        print(
            f"\n⚠️ Found {health['critical_issues']} critical issues requiring attention"
        )
        print("Recommendation: Run detailed validation on affected symbols")


async def generate_quality_report(
    service: DataQualityService,
    symbols: list[str] | None,
    start_date: date | None,
    end_date: date | None,
    output_format: str = "json",
) -> None:
    """Generate comprehensive quality report."""
    logger.info("Generating quality report")

    report = await service.generate_quality_report(
        ts_codes=symbols,
        start_date=start_date,
        end_date=end_date,
        save_report=True,
    )

    print(f"\n{'=' * 60}")
    print("QUALITY REPORT")
    print(f"{'=' * 60}")

    # Summary
    summary = report["summary"]
    print(f"Validators Run: {summary['validators_run']}")
    print(f"Validators Passed: {summary['validators_passed']}")
    print(f"Success Rate: {summary['success_rate']:.1%}")
    print(f"Overall Quality Score: {summary['quality_score']:.1f}/100")
    print(f"Total Issues: {summary['total_issues']}")
    print(f"Records Validated: {summary['total_records_validated']}")

    # Issue breakdown
    print("\nIssue Breakdown:")
    for severity, count in summary["issue_breakdown"].items():
        if count > 0:
            print(f"  {severity.capitalize()}: {count}")

    # Quality scores
    print("\nQuality Scores by Validator:")
    for validator, score_info in report["quality_scores"].items():
        print(f"  {validator}: {score_info['score']:.1f} ({score_info['grade']})")

    # Top issues
    print("\nTop Issue Types:")
    for issue_code, count in report["issue_analysis"]["top_issue_codes"][:5]:
        print(f"  {issue_code}: {count} occurrences")

    # Recommendations
    if report["recommendations"]:
        print("\nRecommendations:")
        for rec in report["recommendations"][:3]:  # Show top 3
            print(f"  • {rec['title']}")
            print(f"    {rec['description']}")

    print("\nDetailed report saved to reports directory")


async def validate_new_data(
    collector: DataCollector,
    symbol: str,
    days_back: int,
) -> None:
    """Validate newly collected data."""
    logger.info(f"Validating new data for {symbol}")

    # Get recent data
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)

    # Get data from source (primary and backup if available)
    try:
        # Fetch data from primary source
        primary_data = await collector.data_factory.get_daily_data(
            symbol, start_date, end_date
        )

        if primary_data.is_empty():
            print(f"No data found for {symbol} in specified date range")
            return

        # Validate the data
        validation_issues = await collector._validate_daily_data(symbol, primary_data)

        # Print results
        print(f"\n{'=' * 60}")
        print(f"NEW DATA VALIDATION for {symbol}")
        print(f"{'=' * 60}")
        print(f"Records Found: {primary_data.height}")
        print(f"Date Range: {start_date} to {end_date}")

        if not validation_issues:
            print("\n✓ No issues found - data quality is excellent")
        else:
            print(f"\nFound {len(validation_issues)} validation issues:")

            # Group by severity
            by_severity = {
                "critical": [],
                "error": [],
                "warning": [],
                "info": [],
            }

            for issue in validation_issues:
                by_severity[issue.severity.value].append(issue)

            for severity in ["critical", "error", "warning", "info"]:
                issues = by_severity[severity]
                if issues:
                    print(f"\n{severity.upper()} ({len(issues)}):")
                    for issue in issues[:5]:  # Show first 5
                        print(f"  • {issue.message}")

        # Store data if validation passed (or has only warnings/info)
        critical_errors = [
            issue
            for issue in validation_issues
            if issue.severity.value in ["critical", "error"]
        ]

        if not critical_errors:
            print("\n✓ Data can be stored (no critical errors)")
        else:
            print(
                f"\n✗ Data should NOT be stored "
                f"({len(critical_errors)} critical errors)"
            )

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        print(f"\nError: {e}")


async def main() -> None:
    """Check data quality."""
    parser = argparse.ArgumentParser(description="Check data quality")
    parser.add_argument(
        "command",
        choices=["symbol", "health", "report", "validate-new"],
        help="Command to execute",
    )
    parser.add_argument(
        "--symbol",
        help="ETF symbol to check (for 'symbol' and 'validate-new' commands)",
    )
    parser.add_argument(
        "--symbols", nargs="+", help="ETF symbols to check (for 'report' command)"
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
        "--validators",
        nargs="+",
        choices=["ohlc", "price_continuity", "volume", "limit_up_down"],
        help="Validators to run",
    )
    parser.add_argument(
        "--sample-size", type=int, default=5, help="Sample size for health check"
    )
    parser.add_argument("--days-back", type=int, default=7, help="Days to look back")
    parser.add_argument(
        "--format",
        choices=["json", "html"],
        default="json",
        help="Report output format",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Load configuration
        settings = get_settings()

        # Initialize services
        data_factory = DataSourceFactory(
            primary_source=DataSourceType.TUSHARE,
            tushare_api_key=settings.data_source.tushare_token,
        )
        data_service = DataService()
        quality_service = DataQualityService(
            data_service=data_service,
        )
        collector = DataCollector(
            data_factory=data_factory,
            data_service=data_service,
        )

        # Execute command
        if args.command == "symbol":
            if not args.symbol:
                parser.error("--symbol is required for 'symbol' command")
            await check_symbol_quality(
                quality_service,
                args.symbol,
                args.start_date,
                args.end_date,
                args.validators,
            )

        elif args.command == "health":
            await run_health_check(
                quality_service,
                args.sample_size,
                args.days_back,
            )

        elif args.command == "report":
            await generate_quality_report(
                quality_service,
                args.symbols,
                args.start_date,
                args.end_date,
                args.format,
            )

        elif args.command == "validate-new":
            if not args.symbol:
                parser.error("--symbol is required for 'validate-new' command")
            await validate_new_data(
                collector,
                args.symbol,
                args.days_back,
            )

        logger.info("Data quality check completed")

    except KeyboardInterrupt:
        logger.info("Check interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Check failed: {e}")
        if args.verbose:
            logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
