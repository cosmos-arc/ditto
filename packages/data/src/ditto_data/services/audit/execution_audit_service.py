"""
ExecutionAuditService — SQLite 审计日志持久化.

将回测运行中的 RiskScanPayload 和 PreTradeDecisionPayload 序列化写入
SQLite 的 execution_audit 表，并提供按 run_id / record_type / date_range
的查询接口。

注意：本服务使用 DataHub 本地 DTO (strategy_audit)，不依赖 Core 包。
"""

from __future__ import annotations

import dataclasses
from typing import Any

import orjson
from ditto_infra.foundation import SQLitePool, logger, traced

from ditto_data.models.strategy_audit import (
    PreTradeDecisionPayload,
    RiskScanPayload,
)

__all__ = [
    "ExecutionAuditService",
]

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS execution_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT    NOT NULL,
    trade_date  TEXT    NOT NULL,
    record_type TEXT    NOT NULL,
    instrument_id INTEGER NULL,
    instrument_scope TEXT NOT NULL DEFAULT 'instrument',
    payload     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_INDEX_RUN_DATE = (
    "CREATE INDEX IF NOT EXISTS idx_audit_run_date "
    "ON execution_audit(run_id, trade_date);"
)

_CREATE_INDEX_RUN_TYPE = (
    "CREATE INDEX IF NOT EXISTS idx_audit_run_type "
    "ON execution_audit(run_id, record_type);"
)

_INSERT_SQL = """
INSERT INTO execution_audit
    (run_id, trade_date, record_type, instrument_id, instrument_scope, payload)
VALUES (?, ?, ?, ?, ?, ?)
"""

_BASE_SELECT = """
SELECT id, run_id, trade_date, record_type,
       instrument_id, instrument_scope, payload, created_at
FROM execution_audit
WHERE run_id = ?
"""


class ExecutionAuditService:
    """
    回测执行审计日志服务.

    负责将风控扫描记录 (RiskScanPayload) 和盘前决策记录
    (PreTradeDecisionPayload) 持久化到 SQLite，并提供带过滤条件的查询。
    """

    def __init__(self, pool: SQLitePool) -> None:
        """
        初始化服务.

        Args:
            pool: SQLite 连接池实例.

        """
        self._pool = pool

    @traced("audit.init_schema")
    def init_schema(self) -> None:
        """
        创建 execution_audit 表和索引（幂等操作）。

        对于已存在但缺少 instrument_scope 列的旧表，自动执行
        ALTER TABLE ADD COLUMN 补齐。
        """
        conn = self._pool.get_connection()
        conn.executescript(
            _CREATE_TABLE + _CREATE_INDEX_RUN_DATE + _CREATE_INDEX_RUN_TYPE
        )
        # Legacy migration: add instrument_scope if missing
        cursor = conn.execute("PRAGMA table_info(execution_audit)")
        columns = {row[1] for row in cursor.fetchall()}
        if "instrument_scope" not in columns:
            _ADD_COL = (
                "ALTER TABLE execution_audit "
                "ADD COLUMN instrument_scope "
                "TEXT NOT NULL DEFAULT 'instrument'"
            )
            conn.execute(_ADD_COL)
        self._pool.commit()
        logger.debug(
            "execution_audit schema initialized",
            event="audit_schema_init",
        )

    @traced("audit.save_risk_log")
    def save_risk_log(
        self,
        run_id: str,
        records: tuple[RiskScanPayload, ...],
    ) -> int:
        """
        批量保存风控扫描记录.

        Args:
            run_id: 回测运行 ID.
            records: RiskScanPayload 不可变元组.

        Returns:
            成功插入的记录数.

        """
        if not records:
            return 0
        conn = self._pool.get_connection()
        count = 0
        for rec in records:
            payload = self._serialize_record(rec)
            conn.execute(
                _INSERT_SQL,
                (
                    run_id,
                    rec.trade_date,
                    "risk_scan",
                    rec.instrument_id,
                    str(rec.scope),
                    payload,
                ),
            )
            count += 1
        self._pool.commit()
        logger.debug(
            "risk scan records saved",
            event="audit_risk_save",
            run_id=run_id,
            count=count,
        )
        return count

    @traced("audit.save_pre_trade_log")
    def save_pre_trade_log(
        self,
        run_id: str,
        records: tuple[PreTradeDecisionPayload, ...],
    ) -> int:
        """
        批量保存盘前决策记录.

        Args:
            run_id: 回测运行 ID.
            records: PreTradeDecisionPayload 不可变元组.

        Returns:
            成功插入的记录数.

        """
        if not records:
            return 0
        conn = self._pool.get_connection()
        count = 0
        for rec in records:
            payload = self._serialize_record(rec)
            conn.execute(
                _INSERT_SQL,
                (
                    run_id,
                    rec.trade_date,
                    "pre_trade_decision",
                    rec.instrument_id,
                    "instrument",
                    payload,
                ),
            )
            count += 1
        self._pool.commit()
        logger.debug(
            "pre-trade decision records saved",
            event="audit_pre_trade_save",
            run_id=run_id,
            count=count,
        )
        return count

    @traced("audit.query")
    def query(
        self,
        run_id: str,
        record_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        查询审计记录，支持可选过滤条件.

        Args:
            run_id: 回测运行 ID（必填）.
            record_type: 记录类型过滤 ('risk_scan' | 'pre_trade_decision').
            start_date: 起始交易日期 (YYYY-MM-DD, 含).
            end_date: 结束交易日期 (YYYY-MM-DD, 含).

        Returns:
            匹配的审计记录列表，每条记录为 dict.

        """
        clauses: list[str] = []
        params: list[Any] = [run_id]

        if record_type is not None:
            clauses.append("record_type = ?")
            params.append(record_type)

        if start_date is not None:
            clauses.append("trade_date >= ?")
            params.append(start_date)

        if end_date is not None:
            clauses.append("trade_date <= ?")
            params.append(end_date)

        where = (" AND " + " AND ".join(clauses)) if clauses else ""

        sql = _BASE_SELECT + where + " ORDER BY trade_date ASC, id ASC"

        conn = self._pool.get_connection()
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_record(record: Any) -> str:
        """将 frozen dataclass 序列化为 orjson 字符串。"""
        return orjson.dumps(dataclasses.asdict(record)).decode("utf-8")
