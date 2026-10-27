"""
SQLite 连接池，用于并发访问.

提供线程安全的 SQLite 连接管理，支持连接池、事务管理和 Schema 初始化。
"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, cast

from ditto_platform.foundation.observability import logger, span, traced

# 标识符引号（"name"）与标点旁空格不是结构差异（DDL 书写差异）
_QUOTED_IDENTIFIER = re.compile(r'"([^"]*)"')
_PUNCT_ADJACENT_SPACES = re.compile(r"\s*([,()])\s*")
# 纯常量 SQL，无外部输入
_SQLITE_MASTER_SQL = (
    "SELECT type, name, sql FROM sqlite_master"  # noqa: S608 - 纯常量 SQL
    + " WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
)


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

    def __init__(
        self,
        db_path: str,
        schema_path: Path | None = None,
        *,
        validate_schema_shape: bool = False,
        schema_drift_allowlist: frozenset[str] = frozenset(),
    ) -> None:
        """
        初始化连接池.

        Args:
            db_path: 数据库文件路径
            schema_path: 可选的 Schema 文件路径。如果提供，init_schema() 将使用该文件
                        初始化数据库结构。如果为 None，init_schema() 将不执行任何操作。
            validate_schema_shape: init_schema() 是否做影子库结构漂移校验（响亮
                        失败）。默认关闭——共享 schema 的域可能有自己的惰性迁移
                        （如 strategy_run，init 须容忍直至域迁移执行）；由知道
                        域迁移状态的组合根显式开启。
            schema_drift_allowlist: 漂移校验的豁免对象名（域自有惰性迁移的表，
                        漂移仅告警不拒绝）。

        """
        self._db_path = Path(db_path)
        self._schema_path = schema_path
        self._validate_schema_shape_enabled = validate_schema_shape
        self._schema_drift_allowlist = schema_drift_allowlist
        self._local = threading.local()
        self._connection_count = 0  # 连接数计数器（仅用于告警）
        self._count_lock = threading.Lock()
        self._all_connections: list[sqlite3.Connection] = []  # 追踪所有连接
        self._all_connections_lock = threading.Lock()  # 保护 _all_connections

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
        need_new_conn = False

        if not hasattr(self._local, "conn") or self._local.conn is None:
            need_new_conn = True
        else:
            # 检查连接是否已被 close_all() 关闭
            try:
                # 使用轻量级检查判断连接是否有效
                self._local.conn.execute("SELECT 1")
            except sqlite3.ProgrammingError:
                # 连接已关闭，需要创建新连接
                need_new_conn = True

        if need_new_conn:
            conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False, timeout=30.0
            )
            conn.row_factory = sqlite3.Row
            # 启用外键约束 + WAL 模式（并发读写性能 + 数据安全）
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            self._local.conn = conn

            # 追踪所有连接（用于 close_all）
            with self._all_connections_lock:
                self._all_connections.append(conn)

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
        # 先校验后建：漂移拒绝启动时库保持原状（correctness F5——executescript
        # 的 DDL 是 autocommit，先建后拒会留下「新增对象已落库」的部分迁移态）
        if self._validate_schema_shape_enabled:
            self._validate_schema_shape(conn, schema)
        conn.executescript(schema)
        conn.commit()

        logger.info(
            "Database schema initialized successfully",
            event="schema_init_complete",
            status="success",
        )

    def _validate_schema_shape(self, conn: sqlite3.Connection, schema: str) -> None:
        """
        影子库结构校验：DDL 演进后既有库的静默漂移在此响亮失败.

        ``CREATE ... IF NOT EXISTS`` 对既有对象静默跳过——schema.sql 演进后
        存量库保持旧结构（曾致 instrument_name_history 3 列 PK 与权威 4 列
        定义静默共存，写入器版本追加契约必然撞约束）。以同一 schema.sql 在
        内存建影子库，逐对象比较 sqlite_master 存储定义（表/索引/视图/触发
        器；sqlite_% 内部对象除外），任一定义漂移即拒绝启动。只比对既有对象
        ——schema.sql 新增对象由随后 executescript 正常创建；schema.sql 之外
        的多余对象（运行时表由写入器代码自建，属既有架构）只 debug 留痕。

        修复漂移 = 按对象手动迁移或携数据重建该表至与当前 schema.sql 一致
        （对齐后本校验自然通过）。``schema_drift_allowlist`` 内的对象（域自有
        惰性迁移的表，如 strategy_run 由 strategy 存储层首用时迁移）漂移只
        告警不拒绝。
        """
        expected = _master_objects(schema)
        actual = _sqlite_master_objects(conn)
        drifted = sorted(
            (name, obj_type)
            for name, (obj_type, sql) in expected.items()
            if name in actual and actual[name][1] != sql
        )
        blocking = [
            f"{obj_type} {name}"
            for name, obj_type in drifted
            if name not in self._schema_drift_allowlist
        ]
        tolerated = [
            name for name, _obj_type in drifted if name in self._schema_drift_allowlist
        ]
        if tolerated:
            logger.warning(
                "Schema drift tolerated (owned by domain lazy migration)",
                event="schema_drift_allowed",
                db_path=str(self._db_path),
                objects=tolerated,
            )
        extras = sorted(set(actual) - set(expected))
        if extras:
            logger.debug(
                "Database contains objects outside schema.sql",
                event="schema_extras",
                db_path=str(self._db_path),
                objects=extras,
            )
        if blocking:
            msg = (
                "Database schema drift detected: "
                + f"{', '.join(blocking)} differ from schema.sql "
                + "(CREATE IF NOT EXISTS never migrates existing objects); "
                + "migrate or rebuild the drifted objects to match schema.sql"
            )
            logger.error(
                "Database schema drift detected",
                event="schema_drift",
                db_path=str(self._db_path),
                drifted=blocking,
            )
            raise ValueError(msg)

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

    def close_all(self) -> None:
        """
        关闭所有线程的连接（用于应用 shutdown）.

        遍历所有追踪的连接并关闭它们，适用于应用关闭时清理资源。
        此方法是线程安全的，可以安全地调用多次。

        Note:
            关闭后，当前线程调用 get_connection() 会创建新连接。
            其他线程的 thread-local 连接引用会被设为 None，
            下次调用 get_connection() 时会创建新连接。

        """
        with self._all_connections_lock:
            closed_count = 0
            for conn in self._all_connections:
                try:
                    conn.close()
                    closed_count += 1
                except Exception as e:
                    logger.warning(
                        "Failed to close connection",
                        event="close_connection_failed",
                        error=str(e),
                    )
            self._all_connections.clear()

        # 重置连接计数
        with self._count_lock:
            self._connection_count = 0

        # 清除当前线程的 thread-local 连接引用
        # 注意：其他线程的引用无法直接清除，但 get_connection() 会检测到连接已关闭
        if hasattr(self._local, "conn"):
            self._local.conn = None

        logger.info(
            "All SQLite connections closed",
            event="all_connections_closed",
            closed_count=closed_count,
        )


def _strip_sql_comments(sql: str) -> str:
    """
    剥 `--` 行注释与 `/* */` 块注释（跳过字符串字面量内的注释符）.

    sqlite_master 原样保留建库时的注释文本（schema.sql 现存行内注释），
    注释-only 编辑不是结构漂移，不得阻断启动（correctness F4）。
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                out.append(sql[i])
                if sql[i] == quote:
                    if i + 1 < n and sql[i + 1] == quote:  # 双写转义
                        out.append(sql[i + 1])
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        if ch == "-" and sql[i : i + 2] == "--":
            newline = sql.find("\n", i)
            i = n if newline == -1 else newline  # 保留换行，丢弃注释体
            continue
        if ch == "/" and sql[i : i + 2] == "/*":
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _normalize_ddl(sql: str) -> str:
    """
    DDL 文本规范化：剥注释、折叠空白、剥标识符引号、收标点旁空格.

    同一引擎两侧各自存储原始文本，书写差异（注释、`name (` vs `name(`、
    带不带引号的标识符）不是结构漂移；列集/约束/索引列序的差异在此
    规范化后仍必然保留。已知边界（correctness F6，当前 schema 无此形态）
    ：空白折叠与标点收紧会侵入字符串字面量内容（如 DEFAULT 'a , b'），
    双引号字面量按标识符剥引号——仓库 DDL 约定不用这两种写法。
    """
    text = " ".join(_strip_sql_comments(sql).split())
    text = _QUOTED_IDENTIFIER.sub(r"\1", text)
    return _PUNCT_ADJACENT_SPACES.sub(r"\1", text)


def _sqlite_master_objects(conn: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    """
    sqlite_master 对象清单：{name: (type, 规范化 DDL 文本)}.

    sqlite_% 前缀内部对象（autoindex 等）与 sql 为 NULL 的条目排除。
    """
    rows = conn.execute(_SQLITE_MASTER_SQL).fetchall()
    return {
        str(name): (str(obj_type), _normalize_ddl(str(sql)))
        for obj_type, name, sql in rows
    }


def _master_objects(schema: str) -> dict[str, tuple[str, str]]:
    """以 schema DDL 建内存影子库并返回其对象清单（结构权威期望值）."""
    shadow = sqlite3.connect(":memory:")
    try:
        shadow.executescript(schema)
        return _sqlite_master_objects(shadow)
    finally:
        shadow.close()
