"""CSV data source implementation for testing."""

from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation.logging_config import get_logger

from ..constants import DataSourceType
from ..exceptions import ValidationError
from .base import DataSource

# Initialize logger
logger = get_logger(__name__)


class CSVDataSource(DataSource):
    """CSV data source for testing with local CSV files."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize CSV data source.

        Args:
            config: Configuration dictionary containing:
                - data_dir: Root directory for CSV data files (default: "data/test")
                - etf_list_file: Name of ETF list CSV file (default: "etf_list.csv")

        """
        super().__init__(config)

        self.data_dir = Path(self.config.get("data_dir", "data/test"))
        self.etf_list_file = self.config.get("etf_list_file", "etf_list.csv")
        self.daily_dir = self.data_dir / "daily"

    def _get_source_type(self) -> str:
        """Get the data source type."""
        return DataSourceType.CSV if hasattr(DataSourceType, "CSV") else "csv"

    def connect(self) -> None:
        """Create necessary directories for CSV data storage."""
        logger.info(f"Connecting to CSV data source at {self.data_dir}")

        # Create directories if they don't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.daily_dir.mkdir(parents=True, exist_ok=True)

        logger.info("CSV data source connected successfully")

    def disconnect(self) -> None:
        """No connection to close for CSV data source."""
        logger.info("CSV data source disconnected")

    def get_etf_list(self) -> pl.DataFrame:
        """
        Get list of available ETFs from CSV file.

        Returns:
            DataFrame with columns: symbol, name, market, list_date

        Raises:
            ValidationError: If CSV file has invalid format

        """
        etf_file = self.data_dir / self.etf_list_file

        if not etf_file.exists():
            logger.warning(f"ETF list file not found: {etf_file}")
            return pl.DataFrame(
                schema={
                    "symbol": pl.String,
                    "name": pl.String,
                    "market": pl.String,
                    "list_date": pl.String,
                }
            )

        try:
            # Read CSV file with UTF-8 encoding
            df = pl.read_csv(etf_file, encoding="utf-8")

            # Validate columns
            required_columns = ["symbol", "name", "market", "list_date"]
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                raise ValidationError(
                    f"CSV missing required columns: {missing_columns}",
                    source=self.source_type,
                )

            # Return only required columns
            return df.select(required_columns)

        except pl.ComputeError as e:
            raise ValidationError(
                f"Invalid CSV format in {etf_file}: {e}", source=self.source_type
            ) from e
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            logger.error(f"Unexpected error reading ETF list: {e}")
            return pl.DataFrame(
                schema={
                    "symbol": pl.String,
                    "name": pl.String,
                    "market": pl.String,
                    "list_date": pl.String,
                }
            )

    def get_daily_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Get daily price data for a symbol from CSV file.

        Args:
            symbol: Stock/ETF symbol (e.g., "510300.SH")
            start_date: Start date in "YYYY-MM-DD" format
            end_date: End date in "YYYY-MM-DD" format

        Returns:
            DataFrame with columns: symbol, date, open, high, low, close, volume, amount

        Raises:
            ValidationError: If CSV file has invalid format

        """
        daily_file = self.daily_dir / f"{symbol}.csv"

        if not daily_file.exists():
            logger.warning(f"Daily data file not found: {daily_file}")
            return pl.DataFrame(
                schema={
                    "symbol": pl.String,
                    "date": pl.Date,
                    "open": pl.Float64,
                    "high": pl.Float64,
                    "low": pl.Float64,
                    "close": pl.Float64,
                    "volume": pl.Int64,
                    "amount": pl.Float64,
                }
            )

        try:
            # Read CSV file with UTF-8 encoding
            df = pl.read_csv(daily_file, encoding="utf-8")

            # Validate columns
            required_columns = [
                "symbol",
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
            ]
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                raise ValidationError(
                    f"CSV missing required columns: {missing_columns}",
                    source=self.source_type,
                )

            # Filter by symbol first
            df = df.filter(pl.col("symbol") == symbol)

            # Convert date column
            df = df.with_columns(pl.col("date").str.to_date(format="%Y-%m-%d"))

            # Filter by date range
            start_date_lit = pl.lit(start_date).str.to_date(format="%Y-%m-%d")
            end_date_lit = pl.lit(end_date).str.to_date(format="%Y-%m-%d")
            df = df.filter(
                (pl.col("date") >= start_date_lit) & (pl.col("date") <= end_date_lit)
            )

            # Sort by date
            df = df.sort("date")

            # Return only required columns
            return df.select(required_columns)

        except pl.ComputeError as e:
            raise ValidationError(
                f"Invalid CSV format in {daily_file}: {e}", source=self.source_type
            ) from e
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            logger.error(f"Unexpected error reading daily data for {symbol}: {e}")
            return pl.DataFrame(
                schema={
                    "symbol": pl.String,
                    "date": pl.Date,
                    "open": pl.Float64,
                    "high": pl.Float64,
                    "low": pl.Float64,
                    "close": pl.Float64,
                    "volume": pl.Int64,
                    "amount": pl.Float64,
                }
            )
