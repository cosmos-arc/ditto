"""Data collection service for fetching and storing market data."""

import logging
import time
from datetime import date, datetime, timedelta
from typing import Any, cast

import polars as pl

from ..config.sources_config import SourcesConfig, get_sources_config
from .datasources.base import DataSource
from .datasources.factory import DataSourceFactory
from .services.data_writer import DataWriter

logger = logging.getLogger(__name__)


class DataCollector:
    """Service for collecting and managing market data."""

    def __init__(
        self,
        data_writer: DataWriter,
        config: SourcesConfig | None = None,
    ) -> None:
        """
        Initialize data collector with configuration.

        Args:
            data_writer: Data writer instance for storing data
            config: Sources configuration. If None, loads from default location

        """
        self.data_writer = data_writer
        self.config = config or get_sources_config()

        # Initialize data sources based on configuration
        self._sources: dict[str, DataSource] = {}
        self._initialize_sources()

    def _initialize_sources(self) -> None:
        """Initialize data sources based on configuration."""
        enabled_sources = self.config.get_enabled_sources()

        for source_name, source_config in enabled_sources.items():
            try:
                # Create data source instance using factory
                source = DataSourceFactory.create(
                    source_type=source_config.type, config=source_config.config
                )

                # Connect to the source
                source.connect()

                # Store the source
                self._sources[source_name] = source

                logger.info(
                    f"Initialized {source_name} data source: {source_config.type}"
                )

            except Exception as e:
                logger.error(f"Failed to initialize {source_name} data source: {e}")
                if source_name == "primary":
                    # Primary source is required
                    raise

    def update_etf_list(self) -> dict[str, Any]:
        """Update ETF list from primary data source."""
        logger.info("开始更新ETF列表")

        # Get primary data source
        primary_source = self._sources.get("primary")
        if not primary_source:
            raise ValueError("未配置主数据源")

        try:
            # Get ETF list
            etf_df = primary_source.get_etf_list()
            logger.info(f"获取到 {len(etf_df)} 只ETF")

            # Store to database
            self.data_writer.store_etf_info(etf_df)

            return {
                "total_updated": len(etf_df),
                "source": self.config.primary.type,
                "status": "success",
            }

        except Exception as e:
            logger.error(f"更新ETF列表失败: {e}")
            raise

    def update_daily_data(
        self, symbols: list[str], start_date: str, end_date: str, validate: bool = True
    ) -> dict[str, Any]:
        """
        批量下载日线数据.

        Args:
            symbols: List of symbols to update
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            validate: Whether to validate with backup source

        Returns:
            Dictionary containing update results

        """
        if not symbols:
            logger.warning("空的股票代码列表, 跳过更新")
            return {
                "total_records": 0,
                "symbols_updated": [],
                "validation_errors": [],
                "status": "completed",
            }

        logger.info(
            f"开始更新日线数据: {len(symbols)} 只股票, {start_date} 至 {end_date}"
        )

        # Get primary source
        primary_source = self._sources.get("primary")
        if primary_source is None:
            raise ValueError("未配置主数据源")

        # Get backup source if validation is enabled
        backup_source = None
        if validate and self.config.backup.enabled:
            backup_source = self._sources.get("backup")

        total_records = 0
        symbols_updated = []
        validation_errors = []

        # Get batch size from config
        batch_size = self.config.collection.batch_size

        # Process symbols in batches
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            logger.debug(f"Processing batch {i // batch_size + 1}: {batch}")

            for symbol in batch:
                try:
                    # Fetch from primary source
                    primary_df = primary_source.get_daily_data(
                        symbol=symbol, start_date=start_date, end_date=end_date
                    )

                    # Cross-validate if enabled
                    if (
                        validate
                        and backup_source
                        and self.config.collection.validate_consistency
                    ):
                        backup_df = backup_source.get_daily_data(
                            symbol=symbol, start_date=start_date, end_date=end_date
                        )

                        # Validate consistency
                        tolerance = self.config.quality.cross_validation.tolerance
                        if not self._validate_price_consistency(
                            primary_df, backup_df, tolerance
                        ):
                            validation_errors.append(
                                f"{symbol}: 主备数据源价格差异过大"
                            )
                            continue

                    # Store to database
                    self.data_writer.store_daily_data(primary_df)

                    total_records += len(primary_df)
                    symbols_updated.append(symbol)

                    logger.info(f"✅ {symbol}: 更新 {len(primary_df)} 条记录")

                except Exception as e:
                    logger.error(f"❌ {symbol}: 更新失败 - {e}")
                    validation_errors.append(f"{symbol}: {e!s}")

        return {
            "total_records": total_records,
            "symbols_updated": symbols_updated,
            "validation_errors": validation_errors,
            "status": "completed",
        }

    async def update_adj_factors(
        self,
        symbols: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        force_update: bool = False,
    ) -> dict[str, Any]:
        """Update adjustment factors for symbols."""
        start_time = time.time()
        logger.info("开始更新复权因子")

        # Get primary data source
        primary_source = self._sources.get("primary")
        if not primary_source:
            raise ValueError("未配置主数据源")

        # If no symbols specified, get all ETFs
        if not symbols:
            etf_df = primary_source.get_etf_list()
            if etf_df.is_empty():
                logger.warning("未获取到ETF列表")
                return {
                    "total_processed": 0,
                    "total_records": 0,
                    "new_records": 0,
                    "updated_records": 0,
                    "errors": ["未获取到ETF列表"],
                    "duration": 0.0,
                }
            symbols = etf_df["symbol"].to_list()

        # Set default date range if not provided
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            # Default to 1 year ago
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

        total_records = 0
        errors = []
        symbols_updated = []

        logger.info(f"开始为 {len(symbols)} 只股票更新复权因子")

        for symbol in symbols:
            try:
                logger.info(f"更新 {symbol} 复权因子...")

                # Get adjustment factors
                adj_df = primary_source.get_adjustment_factors(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                )

                if adj_df.is_empty():
                    logger.warning(f"⚠️ {symbol}: 无复权因子数据")
                    continue

                # Store to database
                self.data_writer.store_adjustment_factors(adj_df)

                total_records += len(adj_df)
                symbols_updated.append(symbol)

                logger.info(f"✅ {symbol}: 更新 {len(adj_df)} 条复权因子记录")

            except Exception as e:
                logger.error(f"❌ {symbol}: 更新复权因子失败 - {e}")
                errors.append(f"{symbol}: {e!s}")

        duration = time.time() - start_time

        return {
            "total_processed": len(symbols),
            "total_records": total_records,
            "symbols_updated": symbols_updated,
            "new_records": total_records,  # Simplified - not tracking new vs updated
            "updated_records": 0,
            "errors": errors,
            "duration": duration,
            "start_date": start_date,
            "end_date": end_date,
        }

    async def update_trading_calendar(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Update trading calendar."""
        start_time = time.time()
        logger.info("开始更新交易日历")

        # Get primary data source
        primary_source = self._sources.get("primary")
        if not primary_source:
            raise ValueError("未配置主数据源")

        # Set default date range if not provided
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            # Default to 1 year ahead
            start_date = datetime.now().strftime("%Y-%m-%d")
            end_date = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")

        try:
            logger.info(f"获取交易日历: {start_date} 到 {end_date}")

            # Get trading calendar
            cal_df = primary_source.get_trading_calendar(
                start_date=start_date,
                end_date=end_date,
            )

            if cal_df.is_empty():
                logger.warning("未获取到交易日历数据")
                return {
                    "total_records": 0,
                    "start_date": start_date,
                    "end_date": end_date,
                    "errors": ["未获取到交易日历数据"],
                    "duration": 0.0,
                }

            # Store to database
            self.data_writer.store_trading_calendar(cal_df)

            duration = time.time() - start_time
            logger.info(f"✅ 交易日历更新完成: {len(cal_df)} 条记录")

            return {
                "total_records": len(cal_df),
                "start_date": start_date,
                "end_date": end_date,
                "errors": [],
                "duration": duration,
            }

        except Exception as e:
            logger.error(f"❌ 更新交易日历失败: {e}")
            duration = time.time() - start_time
            return {
                "total_records": 0,
                "start_date": start_date,
                "end_date": end_date,
                "errors": [str(e)],
                "duration": duration,
            }

    async def verify_data_quality(
        self,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Verify data quality for a symbol."""
        # Stub implementation
        return {
            "symbol": symbol,
            "total_records": 0,
            "issues": [],
            "quality_score": 100.0,
        }

    def _validate_price_consistency(
        self, df1: pl.DataFrame, df2: pl.DataFrame, tolerance: float | None = None
    ) -> bool:
        """验证两个数据源的价格一致性."""
        # Use default tolerance if not provided
        if tolerance is None:
            tolerance = self.config.quality.cross_validation.tolerance

        # Early returns for invalid inputs
        validation_result = self._validate_price_inputs(df1, df2)
        if not validation_result:
            return validation_result

        # 合并数据对比
        merged = df1.join(df2, on="date", suffix="_backup")

        if merged.is_empty():
            return False

        # Handle null values in price data
        merged = merged.filter(
            pl.col("close").is_not_null() & pl.col("close_backup").is_not_null()
        )

        if merged.is_empty():
            logger.warning("过滤空值后没有可用于比较的数据")
            return False

        # 计算价格差异百分比
        price_diff = (merged["close"] - merged["close_backup"]).abs() / merged["close"]

        # 检查是否所有差异都在容忍范围内
        max_diff_val = price_diff.max()
        # Handle both Series and scalar return types
        if max_diff_val is None:
            return False

        # Convert to float - handle different Polars return types
        try:
            # Cast to Any first to satisfy type checker, then convert to float
            max_diff = float(cast(Any, max_diff_val))
        except (TypeError, ValueError):
            # If conversion fails, this is an unexpected type
            logger.error(f"无法转换价格差异值为浮点数: {max_diff_val}")
            return False

        # 更详细的错误报告
        if max_diff > tolerance:
            # Find the date with maximum difference
            max_diff_rows = merged.filter(price_diff == max_diff)
            if not max_diff_rows.is_empty():
                date_val = max_diff_rows["date"][0]
                date_str = (
                    date_val.item() if hasattr(date_val, "item") else str(date_val)
                )
                close_val = max_diff_rows["close"][0]
                close_float = (
                    close_val.item() if hasattr(close_val, "item") else float(close_val)
                )
                close_backup_val = max_diff_rows["close_backup"][0]
                close_backup_float = (
                    close_backup_val.item()
                    if hasattr(close_backup_val, "item")
                    else float(close_backup_val)
                )

                logger.warning(
                    f"价格差异过大: 日期={date_str}, 最大差异={max_diff:.4f}, "
                    f"阈值={tolerance}, 主数据源价格={close_float}, "
                    f"备份数据源价格={close_backup_float}"
                )
        else:
            logger.debug(f"价格差异: 最大={max_diff:.4f}, 阈值={tolerance}")

        return max_diff <= tolerance

    def _validate_price_inputs(self, df1: pl.DataFrame, df2: pl.DataFrame) -> bool:
        """验证价格数据的输入."""
        # Check for empty DataFrames using is_empty()
        if df1.is_empty() or df2.is_empty():
            return False

        # Check for required columns
        if "date" not in df1.columns or "close" not in df1.columns:
            logger.error("主数据源缺少必需的列: date 或 close")
            return False
        if "date" not in df2.columns or "close" not in df2.columns:
            logger.error("备份数据源缺少必需的列: date 或 close")
            return False

        return True

    def cleanup(self) -> None:
        """Cleanup resources by disconnecting all data sources."""
        logger.info("Cleaning up data collector...")

        for source_name, source in self._sources.items():
            try:
                source.disconnect()
                logger.debug(f"Disconnected {source_name} data source")
            except Exception as e:
                logger.error(f"Failed to disconnect {source_name} data source: {e}")

        self._sources.clear()
        logger.info("Data collector cleanup completed")

    def __del__(self) -> None:
        """Destructor to ensure cleanup."""
        try:
            self.cleanup()
        except Exception:
            # Ignore errors during cleanup in destructor
            pass

    async def _validate_daily_data(self, symbol: str, data: Any) -> list[Any]:
        """Validate daily data for a symbol."""
        # Stub implementation
        return []
