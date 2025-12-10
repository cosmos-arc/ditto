"""Tushare data source implementation."""

import time
from typing import Any

import polars as pl
import requests
from ditto_foundation.logging_config import get_logger

from ..constants import DataSourceType
from ..exceptions import NetworkError, ValidationError
from .base import DataSource

# Initialize logger
logger = get_logger(__name__)

# Check if tushare is available
try:
    import tushare as ts

    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False
    ts = None  # type: ignore


class TushareDataSource(DataSource):
    """Tushare data source for Chinese market data."""

    min_request_interval: float
    last_request_time: float

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize Tushare data source.

        Args:
            config: Configuration dictionary containing:
                - token: Tushare API token
                - min_request_interval: Minimum interval between requests (seconds)

        """
        super().__init__(config)

        if not TUSHARE_AVAILABLE:
            raise ImportError(
                "Tushare not available. Install with: pip install tushare"
            )

        # Initialize Tushare with token
        token = self.config.get("token")
        if token:
            ts.set_token(token)
            self.pro = ts.pro_api()
        else:
            raise ValueError("Tushare token is required in config")

        # Rate limiting
        self.min_request_interval = self.config.get(
            "min_request_interval", 0.2
        )  # seconds
        self.last_request_time: float = 0.0

    def _get_source_type(self) -> str:
        """Get the data source type."""
        return DataSourceType.TUSHARE

    def connect(self) -> None:
        """Establish Tushare connection."""
        # Tushare uses HTTP API, no persistent connection needed
        # Test connection with a simple API call
        try:
            self.pro.trade_cal(
                exchange="SSE", start_date="20240101", end_date="20240102"
            )
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Tushare: {e}") from e

    def disconnect(self) -> None:
        """Close Tushare connection."""
        # No persistent connection to close
        pass

    def _rate_limit(self) -> None:
        """Apply rate limiting to API calls."""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = current_time

    def get_etf_list(self) -> pl.DataFrame:
        """Get list of available ETFs from Tushare."""
        self._rate_limit()

        try:
            # Get fund basic info
            df = self.pro.fund_basic(market="E")

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
                ["ts_code", "name", "management", "benchmark", "establish_date"]
            ].copy()
            result_df.columns = [
                "symbol",
                "name",
                "fund_manager",
                "tracking_index",
                "establishment_date",
            ]

            return pl.from_pandas(result_df)

        except requests.exceptions.RequestException as e:
            logger.error("Network error fetching ETF list from Tushare", error=str(e))
            raise NetworkError("Failed to connect to Tushare", source="tushare") from e
        except (ValueError, KeyError) as e:
            logger.error("Data validation error fetching ETF list", error=str(e))
            raise ValidationError(
                "Invalid data format from Tushare", source="tushare"
            ) from e
        except Exception as e:
            logger.error(
                "Unexpected error fetching ETF list from Tushare", error=str(e)
            )
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
        Get daily price data from Tushare.

        Args:
            symbol: Stock symbol (e.g., 000001.SZ)
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format

        Returns:
            DataFrame with daily price data

        """
        self._rate_limit()

        try:
            # Convert date format
            start = start_date.replace("-", "")
            end = end_date.replace("-", "")

            # Fetch daily data
            df = self.pro.daily(ts_code=symbol, start_date=start, end_date=end)

            if df is None or df.empty:
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
                [
                    "ts_code",
                    "trade_date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "vol",
                    "amount",
                ]
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

            # Convert data types
            result_df["volume"] = result_df["volume"].astype(int)

            # Add knowledge_date (same as trade_date for Tushare)
            result_df["knowledge_date"] = result_df["trade_date"]

            return pl.from_pandas(result_df)

        except requests.exceptions.RequestException as e:
            logger.error(
                "Network error fetching daily data", symbol=symbol, error=str(e)
            )
            raise NetworkError(
                "Failed to connect to Tushare", source="tushare", symbol=symbol
            ) from e
        except (ValueError, KeyError) as e:
            logger.error(
                "Data validation error fetching daily data", symbol=symbol, error=str(e)
            )
            raise ValidationError(
                "Invalid data format from Tushare", source="tushare", symbol=symbol
            ) from e
        except Exception as e:
            logger.error(
                "Unexpected error fetching daily data", symbol=symbol, error=str(e)
            )
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
        Get adjustment factors from Tushare.

        Args:
            symbol: Stock symbol (e.g., 000001.SZ)
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format

        Returns:
            DataFrame with adjustment factors

        """
        self._rate_limit()

        try:
            # Convert date format
            start = start_date.replace("-", "")
            end = end_date.replace("-", "")

            # Fetch adjustment factors
            df = self.pro.adj_factor(ts_code=symbol, start_date=start, end_date=end)

            if df is None or df.empty:
                return pl.DataFrame(
                    schema={
                        "symbol": str,
                        "ex_date": str,
                        "adj_factor": float,
                        "adj_type": str,
                        "knowledge_date": str,
                    }
                )

            # Select and rename columns
            result_df = df[["ts_code", "trade_date", "adj_factor"]].copy()
            result_df.columns = ["symbol", "ex_date", "adj_factor"]

            # Tushare provides cumulative adjustment factors
            result_df["adj_type"] = "cumulative"
            result_df["knowledge_date"] = result_df["ex_date"]

            return pl.from_pandas(result_df)

        except requests.exceptions.RequestException as e:
            logger.error(
                "Network error fetching adjustment factors", symbol=symbol, error=str(e)
            )
            raise NetworkError(
                "Failed to connect to Tushare", source="tushare", symbol=symbol
            ) from e
        except (ValueError, KeyError) as e:
            logger.error(
                "Data validation error fetching adjustment factors",
                symbol=symbol,
                error=str(e),
            )
            raise ValidationError(
                "Invalid data format from Tushare", source="tushare", symbol=symbol
            ) from e
        except Exception as e:
            logger.error(
                "Unexpected error fetching adjustment factors",
                symbol=symbol,
                error=str(e),
            )
            return pl.DataFrame(
                schema={
                    "symbol": str,
                    "ex_date": str,
                    "adj_factor": float,
                    "adj_type": str,
                    "knowledge_date": str,
                }
            )
