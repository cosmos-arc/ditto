"""
Logging usage example for Ditto system.

This example demonstrates how to use the unified logging system
based on loguru in the Ditto quantitative trading system.
"""

import time

from ditto_foundation import initialize_app
from loguru import logger

# Initialize application first (sets up logging, directories, etc.)
initialize_app()


def example_basic_logging() -> None:
    """Example 1: Basic logging at different levels."""
    # DEBUG: Detailed information for debugging
    logger.debug("Variable state", event="debug_info", variable="x", value=42)

    # INFO: Normal business flow
    logger.info("Application started", event="app_start", component="data_loader")

    # WARNING: Warning conditions (recoverable)
    logger.warning(
        "Data source degraded",
        event="data_source_degraded",
        source="tushare",
        fallback="cache",
    )

    # ERROR: Error events (system can continue)
    logger.error(
        "Operation failed",
        event="operation_error",
        operation="write_data",
        error_type="IOError",
    )


def example_performance_logging() -> None:
    """Example 2: Logging with performance metrics."""
    start_time = time.time()

    # Simulate some work
    time.sleep(0.1)

    duration_ms = (time.time() - start_time) * 1000

    logger.info(
        "Data update complete",
        event="data_update",
        records_inserted=1000,
        records_updated=500,
        duration_ms=round(duration_ms, 2),
    )


def example_contextual_logging() -> None:
    """Example 3: Logging with rich context."""
    # Security resolution
    logger.info(
        "resolve_sid_start",
        event="sid_resolve",
        src_code="600000.SH",
        source="tushare",
        asof="2024-01-01",
    )

    # Found
    logger.debug(
        "resolve_sid_found",
        event="sid_resolve",
        src_code="600000.SH",
        sid=100000001,
    )

    # Not found
    logger.warning(
        "resolve_sid_not_found",
        event="sid_resolve",
        src_code="999999.SH",
        source="tushare",
        asof="2024-01-01",
    )


def example_sql_logging() -> None:
    """Example 4: SQL operation logging."""
    # SQL execution (typically logged at DEBUG level)
    logger.debug(
        "sql_execute",
        event="sql_execute",
        sql="SELECT * FROM security WHERE sid = ?",
        has_params=True,
    )

    # Transaction commit
    logger.debug(
        "transaction_commit",
        event="transaction",
        action="commit",
    )

    # Transaction rollback (typically WARNING level)
    logger.warning(
        "transaction_rollback",
        event="transaction",
        action="rollback",
        reason="constraint_violation",
    )


def example_error_handling() -> None:
    """Example 5: Error handling with logging."""
    try:
        # Simulate an error
        raise ValueError("Invalid parameter value")
    except ValueError as e:
        logger.error(
            "Validation error",
            event="validation_error",
            error_type=type(e).__name__,
            error_message=str(e),
            parameter="price",
            value=-100,
        )


def example_business_logging() -> None:
    """Example 6: Business event logging."""
    # Data quality check
    logger.info(
        "dq_check_start",
        event="dq_check",
        dataset_id="market_daily",
        rules_count=5,
        row_count=10000,
    )

    logger.info(
        "dq_check_complete",
        event="dq_check",
        dataset_id="market_daily",
        passed=True,
        fail_count=0,
        warn_count=2,
    )

    # Pipeline run
    logger.info(
        "pipeline_run_inserted",
        event="pipeline_run",
        run_id="run_20241223_001",
        task_name="update_market_data",
        dataset_id="market_daily",
        status="running",
    )


if __name__ == "__main__":
    print("Running Ditto logging examples...\n")

    print("=" * 60)
    print("Example 1: Basic logging at different levels")
    print("=" * 60)
    example_basic_logging()
    print()

    print("=" * 60)
    print("Example 2: Performance logging")
    print("=" * 60)
    example_performance_logging()
    print()

    print("=" * 60)
    print("Example 3: Contextual logging")
    print("=" * 60)
    example_contextual_logging()
    print()

    print("=" * 60)
    print("Example 4: SQL operation logging")
    print("=" * 60)
    example_sql_logging()
    print()

    print("=" * 60)
    print("Example 5: Error handling with logging")
    print("=" * 60)
    example_error_handling()
    print()

    print("=" * 60)
    print("Example 6: Business event logging")
    print("=" * 60)
    example_business_logging()
    print()

    print("All examples completed!")
