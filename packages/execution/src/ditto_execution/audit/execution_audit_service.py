"""
ExecutionAuditService — SQLite 审计日志持久化.

将回测运行中的 RiskScanPayload 和 PreTradeDecisionPayload 序列化写入
SQLite 的 execution_audit 表，并提供按 run_id / record_type / date_range
的查询接口。

注意：本服务使用 Data 本地 DTO (strategy_audit)，不依赖 Core 包。
"""

from __future__ import annotations

import dataclasses
import sqlite3
from typing import Any, cast

import orjson
from ditto_platform.foundation import SQLitePool, logger, traced

from ditto_execution.audit.models import (
    ExecutionTimelineEntry,
    PreTradeDecisionPayload,
    RepairExecutionPayload,
    RiskDecisionPayload,
    RiskScanPayload,
    TradeFillPayload,
)
from ditto_execution.audit.timeline_read_model import (
    query_account_snapshot_entries,
    query_broker_event_entries,
    query_order_event_entries,
    query_position_entries,
    timeline_sort_key,
)
from ditto_execution.errors import AuditError

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
    correlation_id TEXT NULL,
    order_id TEXT NULL,
    fill_id TEXT NULL,
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

_CREATE_INDEX_RUN_CORRELATION = (
    "CREATE INDEX IF NOT EXISTS idx_audit_run_correlation "
    "ON execution_audit(run_id, correlation_id);"
)

_CREATE_INDEX_RUN_ORDER = (
    "CREATE INDEX IF NOT EXISTS idx_audit_run_order "
    "ON execution_audit(run_id, order_id);"
)

_CREATE_INDEX_RUN_FILL = (
    "CREATE INDEX IF NOT EXISTS idx_audit_run_fill ON execution_audit(run_id, fill_id);"
)

_INSERT_SQL = """
INSERT INTO execution_audit
    (run_id, trade_date, record_type, instrument_id, instrument_scope,
     correlation_id, order_id, fill_id, payload)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_BASE_SELECT = """
SELECT id, run_id, trade_date, record_type,
       instrument_id, instrument_scope, correlation_id, order_id, fill_id,
       payload, created_at
FROM execution_audit
WHERE run_id = ?
"""

_LINK_COLUMNS = {
    "correlation_id": "TEXT NULL",
    "order_id": "TEXT NULL",
    "fill_id": "TEXT NULL",
}


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
        """创建 execution_audit 表和索引（幂等操作）。"""
        conn = self._pool.get_connection()
        conn.execute(_CREATE_TABLE)
        self._ensure_link_columns(conn)
        conn.executescript(
            _CREATE_INDEX_RUN_DATE
            + _CREATE_INDEX_RUN_TYPE
            + _CREATE_INDEX_RUN_CORRELATION
            + _CREATE_INDEX_RUN_ORDER
            + _CREATE_INDEX_RUN_FILL
        )
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
            payload = self._serialize_record(rec, run_id=run_id)
            correlation_id, order_id, fill_id = self._link_fields(rec)
            conn.execute(
                _INSERT_SQL,
                (
                    run_id,
                    rec.trade_date,
                    "risk_scan",
                    rec.instrument_id,
                    str(rec.scope),
                    correlation_id,
                    order_id,
                    fill_id,
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
            payload = self._serialize_record(rec, run_id=run_id)
            correlation_id, order_id, fill_id = self._link_fields(rec)
            conn.execute(
                _INSERT_SQL,
                (
                    run_id,
                    rec.trade_date,
                    "pre_trade_decision",
                    rec.instrument_id,
                    "instrument",
                    correlation_id,
                    order_id,
                    fill_id,
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

    @traced("audit.save_trade_fill_log")
    def save_trade_fill_log(
        self,
        run_id: str,
        records: tuple[TradeFillPayload, ...],
    ) -> int:
        """
        批量保存成交审计记录.

        Args:
            run_id: 回测运行 ID.
            records: TradeFillPayload 不可变元组.

        Returns:
            成功插入的记录数.

        """
        if not records:
            return 0
        conn = self._pool.get_connection()
        count = 0
        for rec in records:
            payload = self._serialize_record(rec, run_id=run_id)
            correlation_id, order_id, fill_id = self._link_fields(rec)
            conn.execute(
                _INSERT_SQL,
                (
                    run_id,
                    rec.trade_date,
                    "trade_fill",
                    rec.instrument_id,
                    "instrument",
                    correlation_id,
                    order_id,
                    fill_id,
                    payload,
                ),
            )
            count += 1
        self._pool.commit()
        logger.debug(
            "trade fill records saved",
            event="audit_trade_fill_save",
            run_id=run_id,
            count=count,
        )
        return count

    @traced("audit.save_risk_decision")
    def save_risk_decision(
        self,
        run_id: str,
        records: tuple[RiskDecisionPayload, ...],
    ) -> int:
        """
        批量保存风控决策审计记录（accept/reject/modify）.

        Args:
            run_id: 回测运行 ID.
            records: RiskDecisionPayload 不可变元组.

        Returns:
            成功插入的记录数.

        """
        if not records:
            return 0
        conn = self._pool.get_connection()
        count = 0
        for rec in records:
            payload = self._serialize_record(rec, run_id=run_id)
            correlation_id, order_id, fill_id = self._link_fields(rec)
            conn.execute(
                _INSERT_SQL,
                (
                    run_id,
                    rec.trade_date,
                    "risk_decision",
                    rec.instrument_id,
                    "instrument",
                    correlation_id,
                    order_id,
                    fill_id,
                    payload,
                ),
            )
            count += 1
        self._pool.commit()
        logger.debug(
            "risk decision records saved",
            event="audit_risk_decision_save",
            run_id=run_id,
            count=count,
        )
        return count

    @traced("audit.save_repair_execution_log")
    def save_repair_execution_log(
        self,
        run_id: str,
        records: tuple[RepairExecutionPayload, ...],
    ) -> int:
        """
        Save reconciliation repair execution audit records.

        These records are workflow-scoped because a repair action may affect an
        order or fill without carrying a single instrument identifier.
        """
        if not records:
            return 0
        conn = self._pool.get_connection()
        count = 0
        for rec in records:
            payload = self._serialize_record(rec, run_id=run_id)
            correlation_id, order_id, fill_id = self._link_fields(rec)
            conn.execute(
                _INSERT_SQL,
                (
                    run_id,
                    rec.trade_date,
                    "repair_execution",
                    None,
                    "workflow",
                    correlation_id,
                    order_id,
                    fill_id,
                    payload,
                ),
            )
            count += 1
        self._pool.commit()
        logger.debug(
            "repair execution records saved",
            event="audit_repair_execution_save",
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
        order_id: str | None = None,
        fill_id: str | None = None,
        correlation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        查询审计记录，支持可选过滤条件.

        Args:
            run_id: 回测运行 ID（必填）.
            record_type: 记录类型过滤 ('risk_scan' | 'pre_trade_decision').
            start_date: 起始交易日期 (YYYY-MM-DD, 含).
            end_date: 结束交易日期 (YYYY-MM-DD, 含).
            order_id: 订单 ID 过滤.
            fill_id: 成交 ID 过滤.
            correlation_id: 跨审计记录关联 ID 过滤.

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

        if order_id is not None:
            clauses.append("order_id = ?")
            params.append(order_id)

        if fill_id is not None:
            clauses.append("fill_id = ?")
            params.append(fill_id)

        if correlation_id is not None:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)

        where = (" AND " + " AND ".join(clauses)) if clauses else ""

        sql = _BASE_SELECT + where + " ORDER BY trade_date ASC, id ASC"

        conn = self._pool.get_connection()
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    @traced("audit.query_timeline")
    def query_timeline(
        self,
        run_id: str,
        *,
        record_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        order_id: str | None = None,
        fill_id: str | None = None,
        correlation_id: str | None = None,
    ) -> tuple[ExecutionTimelineEntry, ...]:
        """Return normalized execution audit entries with top-level link keys."""
        rows = self.query(
            run_id,
            record_type=record_type,
            start_date=start_date,
            end_date=end_date,
            order_id=order_id,
            fill_id=fill_id,
            correlation_id=correlation_id,
        )
        return tuple(self._row_to_timeline_entry(row) for row in rows)

    @traced("audit.query_operating_timeline")
    def query_operating_timeline(
        self,
        run_id: str,
        *,
        strategy_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        order_id: str | None = None,
    ) -> tuple[ExecutionTimelineEntry, ...]:
        """
        Return a merged execution operating timeline from known SQLite stores.

        Audit rows, account snapshots and current position snapshots are scoped
        by ``run_id``. ``strategy_id`` remains an optional narrowing filter for
        strategy-owned storage rows.
        """
        conn = self._pool.get_connection()
        entries = [
            *self.query_timeline(
                run_id,
                start_date=start_date,
                end_date=end_date,
                order_id=order_id,
            ),
            *query_order_event_entries(
                conn,
                run_id=run_id,
                start_date=start_date,
                end_date=end_date,
                order_id=order_id,
            ),
            *query_broker_event_entries(
                conn,
                run_id=run_id,
                start_date=start_date,
                end_date=end_date,
                order_id=order_id,
            ),
            *query_position_entries(
                conn,
                run_id=run_id,
                strategy_id=strategy_id,
                start_date=start_date,
                end_date=end_date,
            ),
            *query_account_snapshot_entries(
                conn,
                run_id=run_id,
                strategy_id=strategy_id,
                start_date=start_date,
                end_date=end_date,
            ),
        ]
        return tuple(sorted(entries, key=timeline_sort_key))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    _PayloadT = (
        RiskScanPayload
        | PreTradeDecisionPayload
        | TradeFillPayload
        | RiskDecisionPayload
        | RepairExecutionPayload
    )

    @staticmethod
    def _serialize_record(
        record: _PayloadT,
        *,
        run_id: str,
    ) -> str:
        """将 frozen dataclass 序列化为 orjson 字符串。"""
        try:
            return orjson.dumps(dataclasses.asdict(record)).decode("utf-8")
        except (TypeError, orjson.JSONEncodeError) as exc:
            raise AuditError(
                "failed to serialize audit payload",
                run_id=run_id,
                record_type=type(record).__name__,
            ) from exc

    @staticmethod
    def _link_fields(record: _PayloadT) -> tuple[str | None, str | None, str | None]:
        """Extract common audit link keys from known payload records."""
        order_id = _string_or_none(getattr(record, "order_id", None))
        fill_id = _string_or_none(getattr(record, "fill_id", None))
        correlation_id = _string_or_none(getattr(record, "correlation_id", None))
        if correlation_id is None and order_id is not None:
            correlation_id = order_id
        return correlation_id, order_id, fill_id

    @staticmethod
    def _row_to_timeline_entry(row: dict[str, Any]) -> ExecutionTimelineEntry:
        payload = cast(dict[str, object], orjson.loads(row["payload"]))
        return ExecutionTimelineEntry(
            id=int(row["id"]),
            run_id=str(row["run_id"]),
            trade_date=str(row["trade_date"]),
            record_type=str(row["record_type"]),
            instrument_id=cast(int | None, row["instrument_id"]),
            instrument_scope=str(row["instrument_scope"]),
            order_id=cast(str | None, row["order_id"]),
            fill_id=cast(str | None, row["fill_id"]),
            correlation_id=cast(str | None, row["correlation_id"]),
            payload=payload,
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _ensure_link_columns(conn: sqlite3.Connection) -> None:
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(execution_audit)")
        }
        for column_name, column_type in _LINK_COLUMNS.items():
            if column_name not in existing:
                sql = (
                    "ALTER TABLE execution_audit "
                    f"ADD COLUMN {column_name} {column_type}"
                )
                conn.execute(sql)


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
