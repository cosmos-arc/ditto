"""SqliteOrderEventJournal — SQLite append-only 持久化订单事件日志。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from types import TracebackType

import orjson

from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.trigger import OrderTrigger

__all__ = ["SqliteOrderEventJournal"]

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS order_events (
    event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id  TEXT    NOT NULL,
    event_type TEXT    NOT NULL,
    event_json TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);
"""

_CREATE_INDEX = """\
CREATE INDEX IF NOT EXISTS ix_order_events_client_id
    ON order_events (client_id);
"""


def _serialize_event(event: OrderEvent) -> str:
    return orjson.dumps(
        {
            "client_id": event.client_id.value,
            "trigger": event.trigger.value,
            "status": event.status.value,
            "fill_price": event.fill_price,
            "fill_quantity": event.fill_quantity,
            "fee": event.fee,
            "message": event.message,
            "timestamp": event.timestamp.isoformat(),
        },
    ).decode()


def _deserialize_event(json_str: str) -> OrderEvent:
    d = orjson.loads(json_str)
    return OrderEvent(
        client_id=ClientOrderId(value=d["client_id"]),
        trigger=OrderTrigger(d["trigger"]),
        status=OrderStatus(d["status"]),
        fill_price=d.get("fill_price"),
        fill_quantity=d.get("fill_quantity", 0),
        fee=d.get("fee", 0.0),
        message=d.get("message"),
        timestamp=datetime.fromisoformat(d["timestamp"]),
    )


class SqliteOrderEventJournal:
    """
    SQLite-backed append-only order event journal.

    线程不安全：单连接绑定创建线程，仅适用于单线程场景
    （回测引擎、测试）。多线程场景应使用 SQLitePool。
    """

    _conn: sqlite3.Connection | None

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        # WAL 模式（并发读写性能 + 数据安全）
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA busy_timeout=5000;")
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_INDEX)
        self._conn.commit()

    _INSERT_SQL = (
        "INSERT INTO order_events"
        " (client_id, event_type, event_json, created_at)"
        " VALUES (?, ?, ?, ?)"
    )
    _SELECT_BY_CLIENT = (
        "SELECT event_json FROM order_events WHERE client_id = ? ORDER BY event_seq"
    )
    _SELECT_ALL = "SELECT event_json FROM order_events ORDER BY event_seq"

    @property
    def _db(self) -> sqlite3.Connection:
        """获取活跃连接，关闭后访问抛出异常。"""
        if self._conn is None:
            msg = "Journal is closed"
            raise RuntimeError(msg)
        return self._conn

    def append(self, event: OrderEvent) -> None:
        """追加事件。"""
        self._db.execute(
            self._INSERT_SQL,
            (
                event.client_id.value,
                event.trigger.value,
                _serialize_event(event),
                event.timestamp.isoformat(),
            ),
        )
        self._db.commit()

    def events_for(self, client_id: ClientOrderId) -> tuple[OrderEvent, ...]:
        """获取指定订单的全部事件。"""
        cursor = self._db.execute(
            self._SELECT_BY_CLIENT,
            (client_id.value,),
        )
        return tuple(_deserialize_event(row[0]) for row in cursor.fetchall())

    def all_events(self) -> tuple[OrderEvent, ...]:
        """获取全部事件。"""
        cursor = self._db.execute(self._SELECT_ALL)
        return tuple(_deserialize_event(row[0]) for row in cursor.fetchall())

    def close(self) -> None:
        """关闭数据库连接（幂等）。"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> SqliteOrderEventJournal:
        """进入上下文管理器。"""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """退出上下文管理器，关闭数据库连接。"""
        self.close()
