"""AkShare data source implementation."""

import time
from datetime import datetime, timedelta
from typing import Any

import polars as pl

from ..constants import DataSourceType
from .base import DataSource

# Check if akshare is available
try:
    import akshare as ak

    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    ak = None


class AkShareDataSource(DataSource):
    """AkShare data source for Chinese market data."""

    min_request_interval: float
    last_request_time: float

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize AkShare data source.

        Args:
            config: Configuration dictionary containing:
                - min_request_interval: Minimum interval between requests (seconds)

        """
        super().__init__(config)

        if not AKSHARE_AVAILABLE:
            raise ImportError(
                "AkShare not available. Install with: pip install akshare"
            )

        # AkShare has no strict rate limits, but set minimum interval
        self.min_request_interval = self.config.get(
            "min_request_interval", 0.5
        )  # seconds
        self.last_request_time: float = 0.0

    def _get_source_type(self) -> str:
        """Get the data source type."""
        return DataSourceType.AKSHARE

    def connect(self) -> None:
        """
        Establish AkShare connection.

        AkShare is a pure Python library, no connection needed.
        """
        pass

    def disconnect(self) -> None:
        """Close AkShare connection."""
        pass

    def _rate_limit(self) -> None:
        """Apply rate limiting to API calls."""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = current_time

    def get_etf_list(self) -> pl.DataFrame:
        """Get list of available ETFs from AkShare."""
        self._rate_limit()

        try:
            # Get ETF data
            df = ak.fund_etf_category_sina(symbol="ETF基金")

            if df is None or df.empty:
                return pl.DataFrame(
                    schema={
                        "symbol": str,
                        "name": str,
                        "fund_manager": str,
                        "tracking_index": str,
                        "establishment_date": str,
                    }
                )

            # Select and rename columns
            result_df = df[
                ["代码", "名称", "基金管理人", "跟踪标的", "成立日期"]
            ].copy()
            result_df.columns = [
                "symbol",
                "name",
                "fund_manager",
                "tracking_index",
                "establishment_date",
            ]

            return pl.from_pandas(result_df)

        except Exception as e:
            print(f"Error fetching ETF list from AkShare: {e}")
            return pl.DataFrame(
                schema={
                    "symbol": str,
                    "name": str,
                    "fund_manager": str,
                    "tracking_index": str,
                    "establishment_date": str,
                }
            )

    def get_daily_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Get daily price data from AkShare.

        Args:
            symbol: Stock code (e.g., sh000001)
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            DataFrame with daily price data

        """
        self._rate_limit()

        try:
            # Use stock_zh_a_hist for A-share data
            if symbol.startswith(("SH", "SZ")):
                # Remove prefix, keep only numbers
                code = symbol[2:]
                df = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_date.replace("-", ""),
                    end_date=end_date.replace("-", ""),
                    adjust="",
                )
                df["symbol"] = symbol
            else:
                # For other symbols, use general stock data
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start_date.replace("-", ""),
                    end_date=end_date.replace("-", ""),
                    adjust="",
                )
                df["symbol"] = symbol

            if df is None or df.empty:
                # Return empty DataFrame with consistent column structure
                return pl.DataFrame(
                    schema={
                        "symbol": str,
                        "trade_date": str,
                        "open_price": float,
                        "high_price": float,
                        "low_price": float,
                        "close_price": float,
                        "volume": int,
                        "amount": float,
                    }
                )

            # Select and rename columns
            result_df = df[
                ["symbol", "日期", "开盘", "最高", "最低", "收盘", "成交量", "成交额"]
            ].copy()
            result_df.columns = [
                "symbol",
                "trade_date",
                "open_price",
                "high_price",
                "low_price",
                "close_price",
                "volume",
                "amount",
            ]

            # Add knowledge_date (same as trade_date for AkShare)
            result_df["knowledge_date"] = result_df["trade_date"]

            return pl.from_pandas(result_df)

        except Exception as e:
            print(f"Error fetching daily data for {symbol}: {e}")
            return pl.DataFrame(
                schema={
                    "symbol": str,
                    "trade_date": str,
                    "open_price": float,
                    "high_price": float,
                    "low_price": float,
                    "close_price": float,
                    "volume": int,
                    "amount": float,
                    "knowledge_date": str,
                }
            )

    def get_adjustment_factors(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Get adjustment factors from AkShare.

        Note: AkShare mainly provides adjusted prices, factors need calculation.

        Args:
            symbol: Stock code (e.g., sh000001)
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            DataFrame with adjustment factors (usually all 1.0)

        """
        self._rate_limit()

        try:
            # AkShare doesn't provide direct adjustment factors
            # We'll return a DataFrame with all factors as 1.0
            # In practice, you would use the adjusted prices directly

            # Create date range using datetime
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            dates = []
            current = start
            while current <= end:
                dates.append(current.strftime("%Y-%m-%d"))
                current += timedelta(days=1)

            df = pl.DataFrame(
                {
                    "symbol": symbol,
                    "ex_date": dates,
                    "adj_factor": 1.0,
                    "adj_type": "cumulative",
                    "knowledge_date": dates,
                }
            )

            return df

        except Exception as e:
            print(f"Error calculating adjustment factors for {symbol}: {e}")
            return pl.DataFrame(
                schema={
                    "symbol": str,
                    "ex_date": str,
                    "adj_factor": float,
                    "adj_type": str,
                    "knowledge_date": str,
                }
            )
