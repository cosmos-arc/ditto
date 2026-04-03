"""TradingRuleWriter -- PIT 版本化交易规则写入."""

from __future__ import annotations

import sqlite3

import orjson
from ditto_infra.foundation import SQLitePool, logger, traced
from ditto_kernel.identity import InstrumentId as _InstrumentId

from ditto_data.storage.metadata._pit_base import PITRecordWriter
from ditto_data.storage.metadata.trading_rule_reader import TradingRuleRecord

InstrumentId = _InstrumentId

__all__ = ["SQLiteTradingRuleWriter", "TradingRuleWriter"]

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS trading_rule (
    instrument_id INTEGER NOT NULL,
    as_of_date TEXT NOT NULL,
    settlement_cycle INT NOT NULL,
    fund_settlement_cycle INT NOT NULL,
    price_limit_pct REAL,
    order_types_supported TEXT NOT NULL,
    call_auction_sessions TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    PRIMARY KEY (instrument_id, effective_from)
);
"""

_INSERT_OR_REPLACE = """
INSERT OR REPLACE INTO trading_rule (
    instrument_id, as_of_date, settlement_cycle, fund_settlement_cycle,
    price_limit_pct, order_types_supported, call_auction_sessions,
    effective_from, effective_to
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_ALL = """
SELECT instrument_id, as_of_date, settlement_cycle, fund_settlement_cycle,
       price_limit_pct, order_types_supported, call_auction_sessions,
       effective_from, effective_to
FROM trading_rule
"""


class TradingRuleWriter(PITRecordWriter[TradingRuleRecord]):
    """交易规则 Writer. V1 内存实现."""


class SQLiteTradingRuleWriter(PITRecordWriter[TradingRuleRecord]):
    """交易规则 Writer -- SQLite PIT 版本化写入."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("trading_rule.init_schema")
    def init_schema(self) -> None:
        """创建 trading_rule 表（幂等操作）。"""
        conn = self._pool.get_connection()
        conn.executescript(_CREATE_TABLE)
        self._pool.commit()
        logger.debug(
            "trading_rule schema initialized",
            event="trading_rule_schema_init",
        )

    def write(self, record: TradingRuleRecord) -> None:
        """写入一条记录（INSERT OR REPLACE）。"""
        conn = self._pool.get_connection()
        conn.execute(
            _INSERT_OR_REPLACE,
            (
                record.instrument_id,
                record.as_of_date,
                record.settlement_cycle,
                record.fund_settlement_cycle,
                record.price_limit_pct,
                orjson.dumps(record.order_types_supported).decode("utf-8"),
                orjson.dumps(record.call_auction_sessions).decode("utf-8"),
                record.effective_from,
                record.effective_to,
            ),
        )
        self._pool.commit()

    def get_records(self) -> list[TradingRuleRecord]:
        """获取所有已写入的记录。"""
        conn = self._pool.get_connection()
        rows = conn.execute(_SELECT_ALL).fetchall()
        return [self._row_to_record(row) for row in rows]

    def _row_to_record(self, row: sqlite3.Row) -> TradingRuleRecord:
        """将数据库行转换为 TradingRuleRecord."""
        return TradingRuleRecord(
            instrument_id=InstrumentId(row["instrument_id"]),
            as_of_date=row["as_of_date"],
            settlement_cycle=row["settlement_cycle"],
            fund_settlement_cycle=row["fund_settlement_cycle"],
            price_limit_pct=row["price_limit_pct"],
            order_types_supported=tuple(orjson.loads(row["order_types_supported"])),
            call_auction_sessions=tuple(orjson.loads(row["call_auction_sessions"])),
            effective_from=row["effective_from"],
            effective_to=row["effective_to"],
        )
