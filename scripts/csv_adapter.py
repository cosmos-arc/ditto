"""
CSV adapter for DataReader/DataWriter testing.

This module provides a CSV-based adapter that implements the DatabaseAdapter
protocol for testing scripts without requiring a real database.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl


class CSVAdapter:
    """CSV-based adapter for testing DataReader/DataWriter."""

    def __init__(self, data_dir: str | Path = "data/test") -> None:
        """
        Initialize CSV adapter.

        Args:
            data_dir: Directory containing CSV data files

        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize subdirectories
        (self.data_dir / "daily").mkdir(exist_ok=True)
        (self.data_dir / "etf_info").mkdir(exist_ok=True)
        (self.data_dir / "adjustment_factors").mkdir(exist_ok=True)

    def fetch_df(self, sql: str, params: dict[str, Any] | None = None) -> pl.DataFrame:
        """
        Execute SQL-like query and return DataFrame.

        This is a simplified implementation that handles basic queries
        for testing purposes.

        Args:
            sql: SQL query string
            params: Query parameters

        Returns:
            DataFrame with query results

        """
        # Handle different query types
        if "etf_info" in sql:
            return self._fetch_etf_list(params)
        elif "daily_price" in sql or "daily_price_adjusted" in sql:
            return self._fetch_daily_data(params)
        elif "adjustment_factors" in sql:
            return self._fetch_adjustment_factors(params)
        elif "trading_calendar" in sql:
            return self._fetch_trading_calendar(params)
        else:
            # Return empty DataFrame for unsupported queries
            return pl.DataFrame()

    def execute(self, query: str, params: Any = None) -> Any:
        """
        Execute a SQL statement.

        Args:
            query: SQL query string
            params: Query parameters

        """
        # Handle single INSERT statements
        if "INSERT" in query and "etf_info" in query and params:
            self._store_etf_info(
                [
                    {
                        "symbol": params[0],
                        "name": params[1],
                        "list_date": params[2],
                        "knowledge_date": params[3],
                    }
                ]
            )
        elif "INSERT" in query and "daily_price" in query and params:
            # Handle daily_price insert
            pass
        elif "INSERT" in query and "adjustment_factors" in query and params:
            # Handle adjustment_factors insert
            pass
        elif "INSERT" in query and "trading_calendar" in query and params:
            # Handle trading_calendar insert
            pass

    def execute_many(self, sql: str, data: list[dict[str, Any]]) -> None:
        """
        Execute SQL statement with multiple parameter sets.

        Args:
            sql: SQL query string
            data: List of parameter dictionaries

        """
        # Determine table from SQL
        if "etf_info" in sql:
            self._store_etf_info(data)
        elif "daily_price" in sql:
            self._store_daily_data(data)
        elif "adjustment_factors" in sql:
            self._store_adjustment_factors(data)
        elif "trading_calendar" in sql:
            self._store_trading_calendar(data)

    @property
    def connection(self) -> Any:
        """Get database connection (not applicable for CSV)."""
        return self

    def close(self) -> None:
        """Close connection (not applicable for CSV)."""
        pass

    # Helper methods for reading data
    def _fetch_etf_list(self, params: dict[str, Any] | None) -> pl.DataFrame:
        """Fetch ETF list from CSV file."""
        etf_file = self.data_dir / "etf_list.csv"

        if not etf_file.exists():
            # Create empty DataFrame with expected schema
            return pl.DataFrame(
                schema={
                    "symbol": pl.String,
                    "name": pl.String,
                    "list_date": pl.String,
                    "knowledge_date": pl.Datetime,
                }
            )

        df = pl.read_csv(etf_file, try_parse_dates=True)

        # Add knowledge_date if not present
        if "knowledge_date" not in df.columns:
            df = df.with_columns([pl.lit(datetime.now()).alias("knowledge_date")])

        # Select only required columns
        return df.select(["symbol", "name", "list_date", "knowledge_date"])

    def _fetch_daily_data(self, params: dict[str, Any] | None) -> pl.DataFrame:
        """Fetch daily data for a symbol."""
        if not params or "symbol" not in params:
            return pl.DataFrame()

        symbol = params["symbol"]
        daily_file = self.data_dir / "daily" / f"{symbol}.csv"

        if not daily_file.exists():
            return pl.DataFrame(
                schema={
                    "date": pl.Date,
                    "open": pl.Float64,
                    "high": pl.Float64,
                    "low": pl.Float64,
                    "close": pl.Float64,
                    "volume": pl.Float64,
                    "knowledge_date": pl.Datetime,
                }
            )

        df = pl.read_csv(daily_file, try_parse_dates=True)

        # Filter by date range if provided
        if "start_date" in params and "end_date" in params:
            start_date = params["start_date"]
            end_date = params["end_date"]

            if "date" in df.columns:
                df = df.filter(
                    (pl.col("date") >= pl.lit(start_date).str.to_date())
                    & (pl.col("date") <= pl.lit(end_date).str.to_date())
                )

        # Add knowledge_date if not present
        if "knowledge_date" not in df.columns:
            df = df.with_columns([pl.lit(datetime.now()).alias("knowledge_date")])

        # Sort by date
        if "date" in df.columns:
            df = df.sort("date")

        # Select only required columns
        required_cols = [
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "knowledge_date",
        ]
        available_cols = [col for col in required_cols if col in df.columns]
        return df.select(available_cols)

    def _fetch_adjustment_factors(self, params: dict[str, Any] | None) -> pl.DataFrame:
        """Fetch adjustment factors for a symbol."""
        if not params or "symbol" not in params:
            return pl.DataFrame()

        symbol = params["symbol"]
        adj_file = self.data_dir / "adjustment_factors" / f"{symbol}.csv"

        if not adj_file.exists():
            return pl.DataFrame(
                schema={
                    "symbol": pl.String,
                    "ex_date": pl.Date,
                    "adj_factor": pl.Float64,
                    "knowledge_date": pl.Datetime,
                }
            )

        df = pl.read_csv(adj_file, try_parse_dates=True)

        # Add knowledge_date if not present
        if "knowledge_date" not in df.columns:
            df = df.with_columns([pl.lit(datetime.now()).alias("knowledge_date")])

        # Filter by symbol and sort
        df = df.filter(pl.col("symbol") == symbol).sort("ex_date")

        # Select only required columns
        return df.select(["symbol", "ex_date", "adj_factor", "knowledge_date"])

    def _fetch_trading_calendar(self, params: dict[str, Any] | None) -> pl.DataFrame:
        """Fetch trading calendar."""
        cal_file = self.data_dir / "trading_calendar.csv"

        if not cal_file.exists():
            return pl.DataFrame(
                schema={
                    "date": pl.Date,
                    "is_trading_day": pl.Boolean,
                    "knowledge_date": pl.Datetime,
                }
            )

        df = pl.read_csv(cal_file, try_parse_dates=True)

        # Filter by date range if provided
        if params and "start_date" in params and "end_date" in params:
            start_date = params["start_date"]
            end_date = params["end_date"]

            if "date" in df.columns:
                df = df.filter(
                    (pl.col("date") >= pl.lit(start_date).str.to_date())
                    & (pl.col("date") <= pl.lit(end_date).str.to_date())
                )

        # Add knowledge_date if not present
        if "knowledge_date" not in df.columns:
            df = df.with_columns([pl.lit(datetime.now()).alias("knowledge_date")])

        return df.select(["date", "is_trading_day", "knowledge_date"])

    # Helper methods for storing data
    def _store_etf_info(self, data: list[dict[str, Any]]) -> None:
        """Store ETF info to CSV."""
        if not data:
            return

        df = pl.DataFrame(data)
        etf_file = self.data_dir / "etf_list.csv"

        # Convert datetime to string for CSV storage
        if "knowledge_date" in df.columns:
            df = df.with_columns(
                [pl.col("knowledge_date").dt.strftime("%Y-%m-%d %H:%M:%S")]
            )

        # Read existing data if file exists
        if etf_file.exists():
            existing_df = pl.read_csv(etf_file, try_parse_dates=False)
            # Filter out existing symbols to avoid duplicates
            existing_symbols = set(existing_df["symbol"].to_list())
            new_data = df.filter(~pl.col("symbol").is_in(existing_symbols))
            if len(new_data) > 0:
                # Use concat with rechunk to avoid schema issues
                df = pl.concat([existing_df, new_data], rechunk=True)
        else:
            df = df.select(["symbol", "name", "list_date", "knowledge_date"])

        # Write to CSV
        df.write_csv(etf_file)

    def _store_daily_data(self, data: list[dict[str, Any]]) -> None:
        """Store daily data to CSV."""
        if not data:
            return

        # Group data by symbol
        df = pl.DataFrame(data)

        for symbol in df["symbol"].unique():
            symbol_data = df.filter(pl.col("symbol") == symbol)
            daily_file = self.data_dir / "daily" / f"{symbol}.csv"

            # Convert date column to proper format (handle both date and trade_date)
            if "date" in symbol_data.columns:
                symbol_data = symbol_data.with_columns([pl.col("date").cast(pl.Date)])
                # Sort by date
                symbol_data = symbol_data.sort("date")
            elif "trade_date" in symbol_data.columns:
                symbol_data = symbol_data.rename({"trade_date": "date"})
                symbol_data = symbol_data.with_columns([pl.col("date").cast(pl.Date)])
                # Sort by date
                symbol_data = symbol_data.sort("date")
            else:
                # No date column, skip sorting
                pass

            # Write to CSV
            symbol_data.write_csv(daily_file)

    def _store_adjustment_factors(self, data: list[dict[str, Any]]) -> None:
        """Store adjustment factors to CSV."""
        if not data:
            return

        df = pl.DataFrame(data)

        for symbol in df["symbol"].unique():
            symbol_data = df.filter(pl.col("symbol") == symbol)
            adj_file = self.data_dir / "adjustment_factors" / f"{symbol}.csv"

            # Convert date column
            if "ex_date" in symbol_data.columns:
                symbol_data = symbol_data.with_columns(
                    [pl.col("ex_date").cast(pl.Date)]
                )

            # Sort by date
            symbol_data = symbol_data.sort("ex_date")

            # Write to CSV
            symbol_data.write_csv(adj_file)

    def _store_trading_calendar(self, data: list[dict[str, Any]]) -> None:
        """Store trading calendar to CSV."""
        if not data:
            return

        df = pl.DataFrame(data)

        # Convert date column (handle both date and trade_date)
        if "date" in df.columns:
            df = df.with_columns([pl.col("date").cast(pl.Date)])
            # Sort by date
            df = df.sort("date")
        elif "trade_date" in df.columns:
            df = df.rename({"trade_date": "date"})
            df = df.with_columns([pl.col("date").cast(pl.Date)])
            # Sort by date
            df = df.sort("date")
        else:
            # No date column, skip sorting
            pass

        # Write to CSV
        cal_file = self.data_dir / "trading_calendar.csv"
        df.write_csv(cal_file)
