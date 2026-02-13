"""
SQLite 连接池，用于并发访问.

提供线程安全的 SQLite 连接管理，支持连接池、事务管理和 Schema 初始化。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, cast

from ditto_infra.foundation.observability import logger, span, traced


class SQLitePool:
    """
    SQLite 连接池包装器（轻量级改进版）.

    提供线程本地连接，支持并发访问和事务管理。

    改进内容：
    - 添加 ping() 健康检查方法
    - 添加连接数监控（告警阈值 WARN_CONNECTION_COUNT）

    Example:
        >>> pool = SQLitePool("data.db")
        >>> pool.init_schema()  # 如果提供了 schema_path
        >>> pool.execute("SELECT * FROM users")

    """

    # 连接数告警阈值（只告警，不限制）
    WARN_CONNECTION_COUNT = 50

    def __init__(self, db_path: str, schema_path: Path | None = None) -> None:
        """
        初始化连接池.

        Args:
            db_path: 数据库文件路径
            schema_path: 可选的 Schema 文件路径。如果提供，init_schema() 将使用该文件
                        初始化数据库结构。如果为 None，init_schema() 将不执行任何操作。

        """
        self._db_path = Path(db_path)
        self._schema_path = schema_path
        self._local = threading.local()
        self._connection_count = 0  # 连接数计数器（仅用于告警）
        self._count_lock = threading.Lock()

        logger.debug(
            "SQLite pool initialized",
            event="pool_init_complete",
            db_path=str(self._db_path),
            has_schema=schema_path is not None,
        )

    def get_connection(self) -> sqlite3.Connection:
        """
        获取线程本地连接（带连接数监控）.

        如果当前线程还没有连接，则创建新连接并启用外键约束。
        连接数达到 WARN_CONNECTION_COUNT 时记录警告日志。

        Returns:
            SQLite 连接对象，row_factory 设置为 sqlite3.Row

        """
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False, timeout=30.0
            )
            conn.row_factory = sqlite3.Row
            # 启用外键约束
            conn.execute("PRAGMA foreign_keys = ON;")
            self._local.conn = conn

            # 连接数计数（仅用于告警）
            with self._count_lock:
                self._connection_count += 1
                if self._connection_count >= self.WARN_CONNECTION_COUNT:
                    logger.warning(
                        "SQLite connection count exceeds warning threshold",
                        event="connection_count_warning",
                        count=self._connection_count,
                        threshold=self.WARN_CONNECTION_COUNT,
                    )

            logger.debug(
                "SQLite connection created",
                event="connection_created",
                thread_id=threading.get_ident(),
                total_count=self._connection_count,
            )
        # Cast to help pyright infer type from threading.local
        return cast(sqlite3.Connection, self._local.conn)

    @traced("db.execute")
    def execute(self, sql: str, params: list[Any] | None = None) -> sqlite3.Cursor:
        """
        执行 SQL 查询.

        Args:
            sql: SQL 语句
            params: 查询参数列表

        Returns:
            SQLite 游标对象

        """
        conn = self.get_connection()
        if params is None:
            params = []
        return conn.execute(sql, params)

    def rollback(self) -> None:
        """回滚事务."""
        conn = self.get_connection()
        conn.rollback()
        logger.debug(
            "Rolling back transaction",
            event="transaction_rollback",
        )

    def commit(self) -> None:
        """提交事务."""
        conn = self.get_connection()
        conn.commit()
        logger.debug(
            "Committing transaction",
            event="transaction_commit",
        )

    @traced("db.init_schema")
    def init_schema(self) -> None:
        """
        初始化数据库 Schema.

        从构造函数中指定的 schema_path 文件读取 Schema DDL 并执行。
        如果未提供 schema_path，则记录警告日志并直接返回。

        Raises:
            ValueError: 如果 schema_path 不存在或无法读取
            sqlite3.Error: 如果 SQL 执行失败

        """
        if self._schema_path is None:
            logger.warning(
                "No schema path provided, skipping schema initialization",
                event="schema_init_skipped",
                db_path=str(self._db_path),
            )
            return

        logger.info(
            "Initializing database schema",
            event="schema_init_start",
            db_path=str(self._db_path),
            schema_path=str(self._schema_path),
        )

        schema = self._get_schema()
        if not schema:
            logger.warning(
                "Schema is empty, skipping initialization",
                event="schema_init_empty",
                schema_path=str(self._schema_path),
            )
            return

        conn = self.get_connection()
        if self._needs_schema_rebuild(conn):
            self._reset_all_user_tables(conn)
        conn.executescript(schema)
        conn.commit()

        logger.info(
            "Database schema initialized successfully",
            event="schema_init_complete",
            status="success",
        )

    @staticmethod
    def _needs_schema_rebuild(conn: sqlite3.Connection) -> bool:
        """
        Detect schema shape mismatch and rebuild from canonical schema.

        v5 does not keep compatibility layers. If existing tables do not satisfy
        required identifier columns, reset all user tables and re-initialize.
        """
        table_names_query = (
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        table_rows = conn.execute(table_names_query).fetchall()
        table_names = {cast(str, row[0]) for row in table_rows}
        if not table_names:
            return False

        required_tables = {"instrument", "instrument_mapping"}
        if not required_tables.issubset(table_names):
            return True

        instrument_columns = {
            cast(str, item[1])
            for item in conn.execute("PRAGMA table_info(instrument)").fetchall()
        }
        required_instrument_columns = {
            "instrument_id",
            "ticker",
            "asset_class",
            "exchange",
        }
        if not required_instrument_columns.issubset(instrument_columns):
            return True

        mapping_columns = {
            cast(str, item[1])
            for item in conn.execute("PRAGMA table_info(instrument_mapping)").fetchall()
        }
        required_mapping_columns = {"instrument_id", "source", "source_ticker"}
        return not required_mapping_columns.issubset(mapping_columns)

    def _reset_all_user_tables(self, conn: sqlite3.Connection) -> None:
        """
        Drop all user tables when legacy schema is detected.

        v5 does not require backward compatibility. Rebuilding the schema is
        safer than running mixed legacy/new structures.
        """
        logger.warning(
            "Legacy schema detected, rebuilding all tables",
            event="schema_legacy_rebuild",
            db_path=str(self._db_path),
        )

        conn.execute("PRAGMA foreign_keys = OFF")
        table_query = """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """
        table_rows = conn.execute(table_query).fetchall()
        table_names = [cast(str, row[0]) for row in table_rows]

        for table_name in table_names:
            # table_name comes from sqlite_master (database metadata).
            conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')

        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()

    def _get_schema(self) -> str:
        """
        从外部文件获取数据库 Schema DDL.

        Returns:
            Schema SQL 字符串

        Raises:
            ValueError: 如果 schema_path 未设置或文件不存在

        """
        with span("db.read_schema"):
            if self._schema_path is None:
                raise ValueError(
                    "schema_path is not set. "
                    + "Cannot initialize schema without a schema file."
                )

        if not self._schema_path.exists():
            raise ValueError(f"Schema file does not exist: {self._schema_path}")

        return self._schema_path.read_text(encoding="utf-8")

    def ping(self) -> bool:
        """
        健康检查 - 测试连接是否可用.

        Returns:
            True 如果连接正常，False 否则

        """
        try:
            self.execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning(
                "SQLite ping failed",
                event="ping_failed",
                error=str(e),
            )
            return False

    def close(self) -> None:
        """关闭当前线程的连接（减少连接数计数）."""
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            delattr(self._local, "conn")

            # 减少连接数计数
            with self._count_lock:
                self._connection_count -= 1

            logger.debug(
                "SQLite connection closed",
                event="connection_closed",
                thread_id=threading.get_ident(),
                total_count=self._connection_count,
            )
