"""SQLite adapter for transactional data storage."""

import sqlite3
from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation.logging_config import get_logger

from .base import DatabaseAdapter

logger = get_logger(__name__)


class SQLiteAdapter(DatabaseAdapter):
    """SQLite database adapter for transactional data storage."""

    def __init__(self, db_path: str) -> None:
        """
        Initialize SQLite adapter.

        Args:
            db_path: Path to the SQLite database file

        """
        self.db_path = Path(db_path)
        self._connection: sqlite3.Connection | None = None
        self._initialize_database()
        logger.info(f"SQLite adapter initialized at {self.db_path}")

    def _initialize_database(self) -> None:
        """Initialize database with required schema."""
        logger.info(f"Initializing SQLite database at {self.db_path}")

        # Connect to database (creates file if it doesn't exist)
        conn = sqlite3.connect(str(self.db_path))

        try:
            # Create schema
            self._create_schema(conn)
            logger.info("SQLite schema created successfully")
        finally:
            conn.close()

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        """Create database schema tables."""
        # Trades table - executed trades
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                trade_date TEXT NOT NULL,
                trade_time TEXT NOT NULL,
                order_id TEXT NOT NULL,
                broker TEXT NOT NULL,
                commission REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Orders table - placed orders
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                strategy_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                order_type TEXT NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT')),
                quantity INTEGER NOT NULL,
                price REAL,
                status TEXT NOT NULL CHECK (
                    status IN ('PENDING', 'FILLED', 'CANCELLED', 'REJECTED')
                ),
                order_date TEXT NOT NULL,
                order_time TEXT NOT NULL,
                filled_quantity INTEGER DEFAULT 0,
                filled_price REAL,
                broker TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Positions table - current positions
        conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                position_id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                avg_price REAL NOT NULL,
                market_value REAL,
                unrealized_pnl REAL,
                position_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(strategy_id, symbol)
            )
        """)

        # Portfolio snapshots table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                total_value REAL NOT NULL,
                cash_balance REAL NOT NULL,
                positions_value REAL NOT NULL,
                daily_pnl REAL DEFAULT 0,
                max_drawdown REAL DEFAULT 0,
                snapshot_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Strategy configurations
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_configs (
                config_id TEXT PRIMARY KEY,
                strategy_id TEXT NOT NULL,
                config_name TEXT NOT NULL,
                config_json TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Execution logs
        conn.execute("""
            CREATE TABLE IF NOT EXISTS execution_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                order_id TEXT,
                trade_id TEXT,
                log_level TEXT NOT NULL CHECK (
                    log_level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR')
                ),
                message TEXT NOT NULL,
                log_date TEXT NOT NULL,
                log_time TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for better performance
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trades_strategy_date "
            "ON trades(strategy_id, trade_date)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_strategy ON orders(strategy_id)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_positions_strategy "
            "ON positions(strategy_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_snapshots_strategy_date "
            "ON portfolio_snapshots(strategy_id, snapshot_date)"
        )

    @property
    def connection(self) -> sqlite3.Connection:
        """Get database connection, creating if necessary."""
        if self._connection is None:
            self._connection = sqlite3.connect(str(self.db_path))
        return self._connection

    def execute(self, query: str, params: Any = None) -> Any:
        """Execute a query on the database."""
        if params is not None:
            return self.connection.execute(query, params)
        return self.connection.execute(query)

    def executemany(self, query: str, params_list: list[Any]) -> Any:
        """Execute a query multiple times with different parameters."""
        return self.connection.executemany(query, params_list)

    def fetch_df(self, sql: str, params: dict[str, Any] | None = None) -> pl.DataFrame:
        """
        Execute SQL query and return DataFrame.

        Args:
            sql: SQL查询语句
            params: 查询参数字典

        Returns:
            查询结果的DataFrame

        """
        try:
            cursor = self.connection.execute(sql, params or ())
            columns = (
                [description[0] for description in cursor.description]
                if cursor.description
                else []
            )
            data = cursor.fetchall()

            return pl.DataFrame(
                {col: [row[i] for row in data] for i, col in enumerate(columns)}
            )
        except Exception as e:
            logger.error(f"查询失败: {sql}, 错误: {e}")
            raise

    def execute_many(self, sql: str, data: list[dict[str, Any]]) -> None:
        """
        Execute SQL statements in batch.

        Args:
            sql: SQL语句模板
            data: 参数字典列表

        """
        try:
            # Convert list of dicts to list of tuples in correct order
            if data:
                keys = list(data[0].keys())
                values_list = [tuple(row[key] for key in keys) for row in data]
                self.connection.executemany(sql, values_list)
        except Exception as e:
            logger.error(f"批量执行失败: {sql}, 错误: {e}")
            raise

    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("SQLite connection closed")
