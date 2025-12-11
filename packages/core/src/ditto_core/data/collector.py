"""Data collection service for fetching and storing market data."""

import logging
from datetime import date, datetime
from typing import Any, cast

import polars as pl

logger = logging.getLogger(__name__)

# For now, create minimal stub implementations to allow ruff checks to pass
# These will be properly implemented in a future task


class DataCollector:
    """Service for collecting and managing market data."""

    # Default tolerance for price validation (1%)
    DEFAULT_PRICE_TOLERANCE = 0.01

    def __init__(
        self,
        data_service: Any,
        batch_size: int = 1000,
        max_concurrent_fetches: int = 3,
    ) -> None:
        """Initialize data collector."""
        self.data_service = data_service
        self.batch_size = batch_size
        self.max_concurrent_fetches = max_concurrent_fetches

        # Initialize data sources and adapters
        self._sources: dict[str, Any] = {}
        self._analytics_adapter = (
            data_service.analytics_adapter
            if hasattr(data_service, "analytics_adapter")
            else None
        )

    def update_etf_list(self) -> dict[str, Any]:
        """Update ETF list from primary data source."""
        logger.info("开始更新ETF列表")

        # 获取主数据源
        primary_source = self._sources.get("tushare")
        if not primary_source:
            raise ValueError("未配置主数据源 Tushare")

        try:
            # 获取ETF列表
            etf_df = primary_source.get_etf_list()
            logger.info(f"获取到 {len(etf_df)} 只ETF")

            # 添加knowledge_date
            etf_df = etf_df.with_columns(
                [pl.lit(datetime.now()).alias("knowledge_date")]
            )

            # 存储到DuckDB
            if self._analytics_adapter is None:
                raise ValueError("Analytics adapter not configured")
            self._analytics_adapter.store_etf_info(etf_df)

            return {
                "total_updated": len(etf_df),
                "source": "tushare",
                "status": "success",
            }

        except Exception as e:
            logger.error(f"更新ETF列表失败: {e}")
            raise

    def update_daily_data(
        self, symbols: list[str], start_date: str, end_date: str, validate: bool = True
    ) -> dict[str, Any]:
        """批量下载日线数据."""
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

        primary_source = self._sources.get("tushare")
        backup_source = self._sources.get("akshare") if validate else None

        if primary_source is None:
            raise ValueError("未配置主数据源 Tushare")

        total_records = 0
        symbols_updated = []
        validation_errors = []

        for symbol in symbols:
            try:
                # 从主数据源获取
                primary_df = primary_source.get_daily_data(
                    symbol=symbol, start_date=start_date, end_date=end_date
                )

                if validate and backup_source:
                    # 交叉验证
                    backup_df = backup_source.get_daily_data(
                        symbol=symbol, start_date=start_date, end_date=end_date
                    )

                    # 验证一致性
                    if not self._validate_price_consistency(primary_df, backup_df):
                        validation_errors.append(f"{symbol}: 主备数据源价格差异过大")
                        continue

                # 添加knowledge_date
                primary_df = primary_df.with_columns(
                    [pl.lit(datetime.now()).alias("knowledge_date")]
                )

                # 存储到DuckDB
                if self._analytics_adapter is None:
                    raise ValueError("Analytics adapter not configured")
                self._analytics_adapter.store_daily_data(primary_df)

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
        ts_codes: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        force_update: bool = False,
    ) -> dict[str, Any]:
        """Update adjustment factors."""
        # Stub implementation
        return {
            "total_processed": 0,
            "total_records": 0,
            "new_records": 0,
            "updated_records": 0,
            "errors": [],
            "duration": 0.0,
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
            tolerance = self.DEFAULT_PRICE_TOLERANCE

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

    async def _validate_daily_data(self, symbol: str, data: Any) -> list[Any]:
        """Validate daily data for a symbol."""
        # Stub implementation
        return []
