"""SQLite connection pool for concurrent access."""

import sqlite3
import threading
from pathlib import Path
from typing import Any, cast

from ditto_foundation import logger


class SQLitePool:
    """Simple SQLite connection wrapper."""

    def __init__(self, db_path: str) -> None:
        """Initialize with database path."""
        self._db_path = Path(db_path)
        self._local = threading.local()

        logger.debug(
            "SQLite pool initialized",
            event="pool_init_complete",
            db_path=str(self._db_path),
        )

    def get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False, timeout=30.0
            )
            conn.row_factory = sqlite3.Row
            # Enable foreign key constraints
            conn.execute("PRAGMA foreign_keys = ON;")
            self._local.conn = conn

            logger.debug(
                "SQLite connection created",
                event="connection_created",
                thread_id=threading.get_ident(),
            )
        return cast(sqlite3.Connection, self._local.conn)

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection (deprecated, use get_connection)."""
        return self.get_connection()

    def execute(self, sql: str, params: list[Any] | None = None) -> sqlite3.Cursor:
        """Execute SQL query."""
        conn = self.get_connection()
        if params is None:
            params = []
        return conn.execute(sql, params)

    def rollback(self) -> None:
        """Rollback transaction."""
        conn = self.get_connection()
        conn.rollback()
        logger.debug(
            "Rolling back transaction",
            event="transaction_rollback",
        )

    def commit(self) -> None:
        """Commit transaction."""
        conn = self.get_connection()
        conn.commit()
        logger.debug(
            "Committing transaction",
            event="transaction_commit",
        )

    def init_schema(self) -> None:
        """Initialize database schema."""
        logger.info(
            "Initializing database schema",
            event="schema_init_start",
            db_path=str(self._db_path),
        )

        conn = self.get_connection()
        schema = self._get_schema()
        conn.executescript(schema)
        conn.commit()

        logger.info(
            "Database schema initialized successfully",
            event="schema_init_complete",
            status="success",
        )

    def _get_schema(self) -> str:
        """Get database schema DDL."""
        return """
        -- SID 序列
        CREATE TABLE IF NOT EXISTS sid_sequence (
            asset_class TEXT PRIMARY KEY,
            current_max INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT OR IGNORE INTO sid_sequence (asset_class, current_max)
        VALUES ('stock', 100000000);
        INSERT OR IGNORE INTO sid_sequence (asset_class, current_max)
        VALUES ('etf', 200000000);
        INSERT OR IGNORE INTO sid_sequence (asset_class, current_max)
        VALUES ('index', 300000000);
        INSERT OR IGNORE INTO sid_sequence (asset_class, current_max)
        VALUES ('bond', 400000000);
        INSERT OR IGNORE INTO sid_sequence (asset_class, current_max)
        VALUES ('future', 500000000);

        -- 证券主表
        CREATE TABLE IF NOT EXISTS security (
            sid INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            name TEXT,
            display_name TEXT,
            exchange TEXT NOT NULL,
            board TEXT,
            asset_class TEXT NOT NULL,
            list_date DATE NOT NULL,
            delist_date DATE,
            is_st BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_security_symbol ON security(symbol);
        CREATE INDEX IF NOT EXISTS idx_security_asset_class ON security(asset_class);

        -- 证券映射 (PIT support)
        CREATE TABLE IF NOT EXISTS security_mapping (
            sid INTEGER NOT NULL,
            source TEXT NOT NULL,
            src_code TEXT NOT NULL,
            effective_from DATE NOT NULL DEFAULT '1990-01-01',
            effective_to DATE,
            is_primary BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (source, src_code, effective_from),
            FOREIGN KEY (sid) REFERENCES security(sid)
        );
        CREATE INDEX IF NOT EXISTS idx_mapping_current
            ON security_mapping(source, src_code) WHERE effective_to IS NULL;
        CREATE INDEX IF NOT EXISTS idx_mapping_sid ON security_mapping(sid);

        -- 交易日历
        CREATE TABLE IF NOT EXISTS trading_calendar (
            trade_date DATE PRIMARY KEY,
            is_open BOOLEAN NOT NULL,
            prev_trade_date DATE,
            next_trade_date DATE,
            week_of_year INTEGER,
            month INTEGER,
            quarter INTEGER,
            year INTEGER,
            is_week_end BOOLEAN,
            is_month_end BOOLEAN,
            is_quarter_end BOOLEAN
        );

        -- Pipeline 运行
        CREATE TABLE IF NOT EXISTS pipeline_run (
            run_id TEXT PRIMARY KEY,
            task_name TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            year INTEGER,
            rows_read INTEGER,
            rows_written INTEGER,
            status TEXT NOT NULL,
            error_message TEXT,
            dq_passed BOOLEAN,
            dq_fail_count INTEGER DEFAULT 0,
            dq_warn_count INTEGER DEFAULT 0,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            duration_sec REAL
        );

        -- DQ 异常
        CREATE TABLE IF NOT EXISTS dq_issue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            year INTEGER,
            sid INTEGER,
            trade_date DATE,
            rule_name TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Freeze 冻结点
        CREATE TABLE IF NOT EXISTS freeze_point (
            freeze_id TEXT PRIMARY KEY,
            description TEXT,
            manifest_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 涨跌幅配置
        CREATE TABLE IF NOT EXISTS price_limit_config (
            config_id INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange TEXT,
            board TEXT,
            is_st BOOLEAN,
            min_list_days INTEGER,
            max_list_days INTEGER,
            limit_pct REAL NOT NULL,
            priority INTEGER DEFAULT 0,
            description TEXT
        );
        INSERT OR IGNORE INTO price_limit_config
            (config_id, limit_pct, priority, description)
        VALUES
            (1, 1000, 100, '新股前5日'),
            (2, 5, 90, 'ST股'),
            (3, 30, 80, '北交所'),
            (4, 20, 70, '科创板/创业板'),
            (5, 10, 0, '默认');

        -- 标的池定义
        CREATE TABLE IF NOT EXISTS universe (
            universe_id     TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            description     TEXT,
            universe_type   TEXT NOT NULL,
            source_ref      TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP
        );

        -- 标的池成分 (PIT support)
        CREATE TABLE IF NOT EXISTS universe_constituent (
            universe_id     TEXT NOT NULL,
            sid             INTEGER NOT NULL,
            effective_from  DATE NOT NULL,
            effective_to    DATE,
            weight          REAL DEFAULT 1.0,
            source          TEXT,
            src_code        TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (universe_id, sid, effective_from),
            FOREIGN KEY (universe_id) REFERENCES universe(universe_id),
            FOREIGN KEY (sid) REFERENCES security(sid)
        );

        -- 当前有效成分快速查询
        CREATE INDEX IF NOT EXISTS idx_constituent_current
            ON universe_constituent(universe_id, sid) WHERE effective_to IS NULL;

        -- PIT 查询优化
        CREATE INDEX IF NOT EXISTS idx_constituent_pit
            ON universe_constituent(universe_id, effective_from, effective_to);
        """

    def close(self) -> None:
        """Close connection."""
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            delattr(self._local, "conn")

            logger.debug(
                "SQLite connection closed",
                event="connection_closed",
                thread_id=threading.get_ident(),
            )
