"""L3 批量服务 - 统计检查编排（应用层）."""

from datetime import datetime, timedelta
from typing import Any, Literal

import polars as pl
import polars.exceptions as pl_exceptions
from ditto_core.quality import QualityEngine
from ditto_datahub.services.market_service import MarketBarsQuery, MarketService
from ditto_datahub.services.metadata_service import MetadataService
from loguru import logger


class L3BatchService:
    """
    L3 batch check service.

    Application Layer: Orchestrates L3 statistical anomaly checks.
    Fetches historical data from DataHub and injects into Core Engine.
    """

    def __init__(
        self,
        engine: QualityEngine,
        market_service: MarketService,
        metadata_service: MetadataService,
    ) -> None:
        """
        Initialize L3 batch service.

        Args:
            engine: Quality engine instance
            market_service: MarketService instance for data access
            metadata_service: MetadataService instance for data access

        """
        self._engine = engine
        self._market_service = market_service
        self._metadata_service = metadata_service

    def check_dataset(
        self,
        dataset: str,
        trade_date: str,
        asset_class: Literal["stock", "etf", "index"] | None = None,
        market_wide: bool = False,
    ) -> dict[str, Any]:
        """
        Orchestrate L3 check for a dataset.

        Args:
            dataset: Dataset identifier
            trade_date: Trade date to check (YYYY-MM-DD)
            asset_class: Asset class for market-wide queries
            market_wide: Whether to use market-wide query mode

        Returns:
            Check result summary

        """
        logger.info(
            "Starting L3 batch check",
            event="l3_batch_start",
            dataset=dataset,
            trade_date=trade_date,
        )

        try:
            # Get historical and current data from DataHub
            historical, current = self._fetch_data(
                trade_date=trade_date,
                asset_class=asset_class,
                market_wide=market_wide,
            )

            # Get calendar for completeness check
            calendar = self._fetch_calendar(trade_date=trade_date)

            # Execute L3 checks with injected data
            result = self._engine.check_statistical(
                dataset=dataset,
                current=current,
                historical=historical,
                calendar=calendar,
            )

            # Log results
            if result.issues:
                logger.warning(
                    "L3 issues found",
                    event="l3_batch_issues",
                    dataset=dataset,
                    count=len(result.issues),
                )
            else:
                logger.info(
                    "L3 check passed",
                    event="l3_batch_passed",
                    dataset=dataset,
                )

            # Send alerts if needed
            if result.has_alerts:
                self._send_alert(trade_date, dataset, result.issues)

            return {
                "dataset": dataset,
                "trade_date": trade_date,
                "passed": result.passed,
                "issue_count": len(result.issues),
                "alert_count": result.alert_count,
                "issues": result.issues,
            }

        except (pl_exceptions.ComputeError, pl_exceptions.SchemaError, ValueError) as e:
            # 数据处理相关异常
            logger.exception(
                "l3_batch_check_data_processing_failed",
                event="l3_batch_error",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
            return {
                "dataset": dataset,
                "trade_date": trade_date,
                "passed": False,
                "error": f"{type(e).__name__}: {e!s}",
            }
        except Exception as e:
            # 未知异常
            logger.exception(
                "l3_batch_check_unknown_error",
                event="l3_batch_error",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
            return {
                "dataset": dataset,
                "trade_date": trade_date,
                "passed": False,
                "error": f"{type(e).__name__}: {e!s}",
            }

    def _fetch_data(
        self,
        trade_date: str,
        window: int = 120,
        asset_class: Literal["stock", "etf", "index"] | None = None,
        market_wide: bool = False,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """
        Fetch historical and current data from DataHub.

        Args:
            trade_date: Trade date (YYYY-MM-DD)
            window: Lookback window for historical data (days)
            asset_class: Asset class filter
            market_wide: Market-wide query mode

        Returns:
            Tuple of (historical_df, current_df)

        """
        # Calculate start date with buffer for weekends
        trade_dt = datetime.fromisoformat(trade_date)
        start_dt = trade_dt - timedelta(days=window * 2)
        start_date = start_dt.strftime("%Y-%m-%d")

        # Fetch historical data using MarketService
        historical_query = MarketBarsQuery(
            instrument_ids=None,
            start=start_date,
            end=trade_date,
            asset_class=asset_class,
            market_wide=market_wide,
        )
        historical = self._market_service.find_bars(historical_query)

        # Fetch current data using MarketService
        current_query = MarketBarsQuery(
            instrument_ids=None,
            start=trade_date,
            end=trade_date,
            asset_class=asset_class,
            market_wide=market_wide,
        )
        current = self._market_service.find_bars(current_query)

        return historical, current

    def _fetch_calendar(self, trade_date: str, lookback_days: int = 10) -> pl.DataFrame:
        """
        Fetch trading calendar from DataHub.

        Args:
            trade_date: Trade date (YYYY-MM-DD)
            lookback_days: Days to look back

        Returns:
            Calendar DataFrame

        """
        # Calculate start date
        trade_dt = datetime.fromisoformat(trade_date)
        start_dt = trade_dt - timedelta(days=lookback_days * 2)
        start_date = start_dt.strftime("%Y-%m-%d")

        return self._metadata_service.list_calendar_range(
            start=start_date,
            end=trade_date,
            only_open=True,
        )

    def _send_alert(
        self,
        trade_date: str,
        dataset: str,
        issues: list[Any],
    ) -> None:
        """
        Send DQ alert notification.

        Args:
            trade_date: Trade date
            dataset: Dataset name
            issues: List of DQ issues

        """
        logger.warning(
            "DQ alert notification",
            event="dq_alert",
            trade_date=trade_date,
            dataset=dataset,
            issue_count=len(issues),
            issues=[
                {"level": i.level.value, "rule": i.rule_name, "message": i.message}
                for i in issues
            ],
        )
