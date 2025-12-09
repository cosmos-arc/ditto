"""DuckDB adapter for analytical data storage."""

from pathlib import Path
from typing import Any

import duckdb
from logging_config import get_logger

from .base import DatabaseAdapter

logger = get_logger(__name__)


class DuckDBAdapter(DatabaseAdapter):
    """DuckDB database adapter for analytical queries and data storage."""

    def __init__(self, db_path: str) -> None:
        """
        Initialize DuckDB adapter.

        Args:
            db_path: Path to the DuckDB database file

        """
        self.db_path = Path(db_path)
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._initialize_database()

    def _initialize_database(self) -> None:
        """Initialize database with required schema."""
        logger.info(f"Initializing DuckDB database at {self.db_path}")

        # Connect to database (creates file if it doesn't exist)
        conn = duckdb.connect(str(self.db_path))

        try:
            # Create schema
            self._create_schema(conn)
            logger.info("DuckDB schema created successfully")
        finally:
            conn.close()

    def _create_schema(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create database schema tables."""
        # ETF information table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS etf_info (
                symbol VARCHAR PRIMARY KEY NOT NULL,
                name VARCHAR NOT NULL,
                fund_manager VARCHAR,
                tracking_index VARCHAR,
                establishment_date DATE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Daily price data table (non-adjusted prices only)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_price (
                symbol VARCHAR NOT NULL,
                trade_date DATE NOT NULL,
                open_price DECIMAL(10,3) NOT NULL,
                high_price DECIMAL(10,3) NOT NULL,
                low_price DECIMAL(10,3) NOT NULL,
                close_price DECIMAL(10,3) NOT NULL,
                volume BIGINT NOT NULL,
                amount DECIMAL(18,2) NOT NULL,
                turnover_rate DECIMAL(8,4),
                pe_ratio DECIMAL(8,2),
                pb_ratio DECIMAL(8,2),
                knowledge_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, trade_date)
            )
        """)

        # Adjustment factors table (for calculating adjusted prices)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS adjustment_factors (
                symbol VARCHAR NOT NULL,
                ex_date DATE NOT NULL,
                adj_factor DECIMAL(12,8) NOT NULL,
                adj_type VARCHAR(20) NOT NULL,  -- 'dividend', 'split', 'bonus'
                description VARCHAR,
                knowledge_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, ex_date, adj_type)
            )
        """)

        # Trading calendar table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_calendar (
                trade_date DATE PRIMARY KEY,
                is_trading_day BOOLEAN NOT NULL,
                market VARCHAR(10) NOT NULL DEFAULT 'SZSE',  -- SZSE, SSE
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for better performance
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_daily_price_symbol_date "
            "ON daily_price(symbol, trade_date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_daily_price_date ON daily_price(trade_date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_adjustment_factors_symbol "
            "ON adjustment_factors(symbol)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_adjustment_factors_date "
            "ON adjustment_factors(ex_date)"
        )

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """Get database connection, creating if necessary."""
        if self._connection is None:
            self._connection = duckdb.connect(str(self.db_path))
        return self._connection

    def execute(self, query: str, params: Any = None) -> Any:
        """Execute a query on the database."""
        return self.connection.execute(query, params)

    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("DuckDB connection closed")
