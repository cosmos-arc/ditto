"""
TradeService — 交易意图/人工成交/实际持仓 CRUD 服务.

使用 SQLite 持久化交易闭环的本地数据记录（TradeIntentRecord、
ManualExecutionFillRecord、ActualPositionSnapshotRecord），
提供幂等建表、按条件查询、状态更新等操作。

注意：本服务仅操作 *Record 数据类，不依赖 app/engine 包。
"""

from __future__ import annotations

from typing import Any

from ditto_data.models.trade import (
    ActualPositionSnapshotRecord,
    ManualExecutionFillRecord,
    TradeIntentRecord,
)
from ditto_data.storage.sqlite_client import SQLiteClient

__all__ = [
    "TradeService",
]

# ---------------------------------------------------------------------------
# SQL: trade_intents
# ---------------------------------------------------------------------------

_CREATE_INTENTS_TABLE = """
CREATE TABLE IF NOT EXISTS trade_intents (
    intent_id      TEXT PRIMARY KEY,
    strategy_id    TEXT    NOT NULL,
    signal_date    TEXT    NOT NULL,
    instrument_id  INTEGER NOT NULL,
    direction      TEXT    NOT NULL,
    target_weight  REAL    NOT NULL,
    current_weight REAL    NOT NULL,
    delta_weight   REAL    NOT NULL,
    quantity       INTEGER,
    status         TEXT    NOT NULL DEFAULT 'pending',
    created_at     TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_IDX_INTENTS_STRATEGY_DATE = (
    "CREATE INDEX IF NOT EXISTS idx_trade_intents_strategy_date "
    "ON trade_intents(strategy_id, signal_date);"
)

_CREATE_IDX_INTENTS_STATUS = (
    "CREATE INDEX IF NOT EXISTS idx_trade_intents_status ON trade_intents(status);"
)

_INSERT_INTENT = """
INSERT INTO trade_intents
    (intent_id, strategy_id, signal_date, instrument_id, direction,
     target_weight, current_weight, delta_weight, quantity, status, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_INTENT_BY_ID = "SELECT * FROM trade_intents WHERE intent_id = ?"

_LIST_INTENTS_BASE = "SELECT * FROM trade_intents WHERE strategy_id = ?"

_UPDATE_INTENT_STATUS = "UPDATE trade_intents SET status = ? WHERE intent_id = ?"

# ---------------------------------------------------------------------------
# SQL: execution_fills
# ---------------------------------------------------------------------------

_CREATE_FILLS_TABLE = """
CREATE TABLE IF NOT EXISTS execution_fills (
    fill_id        TEXT PRIMARY KEY,
    intent_id      TEXT    NOT NULL,
    strategy_id    TEXT    NOT NULL,
    trade_date     TEXT    NOT NULL,
    instrument_id  INTEGER NOT NULL,
    direction      TEXT    NOT NULL,
    quantity       INTEGER NOT NULL,
    fill_price     REAL    NOT NULL,
    fee            REAL    NOT NULL,
    slippage       REAL    NOT NULL DEFAULT 0.0,
    notes          TEXT    NOT NULL DEFAULT '',
    settlement_date TEXT   NOT NULL DEFAULT '',
    created_at     TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_IDX_FILLS_STRATEGY_DATE = (
    "CREATE INDEX IF NOT EXISTS idx_execution_fills_strategy_date "
    "ON execution_fills(strategy_id, trade_date);"
)

_CREATE_IDX_FILLS_INTENT = (
    "CREATE INDEX IF NOT EXISTS idx_execution_fills_intent "
    "ON execution_fills(intent_id);"
)

_INSERT_FILL = """
INSERT INTO execution_fills
    (fill_id, intent_id, strategy_id, trade_date, instrument_id, direction,
     quantity, fill_price, fee, slippage, notes, settlement_date, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_FILL_BY_ID = "SELECT * FROM execution_fills WHERE fill_id = ?"

_LIST_FILLS_BASE = "SELECT * FROM execution_fills WHERE strategy_id = ?"

# ---------------------------------------------------------------------------
# SQL: actual_positions
# ---------------------------------------------------------------------------

_CREATE_POSITIONS_TABLE = """
CREATE TABLE IF NOT EXISTS actual_positions (
    snapshot_id       TEXT PRIMARY KEY,
    strategy_id       TEXT    NOT NULL,
    snapshot_date     TEXT    NOT NULL,
    instrument_id     INTEGER NOT NULL,
    quantity          INTEGER NOT NULL,
    available_quantity INTEGER NOT NULL,
    average_cost      REAL    NOT NULL,
    market_value      REAL    NOT NULL,
    unrealized_pnl    REAL    NOT NULL,
    realized_pnl      REAL    NOT NULL,
    total_fees        REAL    NOT NULL,
    created_at        TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_IDX_POSITIONS_STRATEGY_DATE = (
    "CREATE INDEX IF NOT EXISTS idx_actual_positions_strategy_date "
    "ON actual_positions(strategy_id, snapshot_date);"
)

_CREATE_IDX_POSITIONS_STRATEGY_INSTRUMENT_DATE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_actual_positions_strategy_instrument_date "
    "ON actual_positions(strategy_id, instrument_id, snapshot_date);"
)

_INSERT_POSITION = """
INSERT OR REPLACE INTO actual_positions
    (snapshot_id, strategy_id, snapshot_date, instrument_id, quantity,
     available_quantity, average_cost, market_value, unrealized_pnl,
     realized_pnl, total_fees, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_GET_LATEST_POSITION = """
SELECT * FROM actual_positions
WHERE strategy_id = ? AND instrument_id = ?
ORDER BY snapshot_date DESC
LIMIT 1
"""

_LIST_POSITIONS_BASE = "SELECT * FROM actual_positions WHERE strategy_id = ?"


def _build_where_clause(
    base_sql: str,
    strategy_id: str,
    filters: dict[str, Any],
    order_by: str,
) -> tuple[str, list[Any]]:
    """
    构建带 WHERE 子句和排序的完整 SQL.

    Args:
        base_sql: 基础 SELECT 语句（含 WHERE strategy_id = ?）.
        strategy_id: 策略 ID（第一个参数）.
        filters: 额外过滤条件 {列名: 值}, None 值自动跳过.
        order_by: ORDER BY 子句（含排序方向）.

    Returns:
        (完整 SQL, 参数列表) 元组.

    """
    clauses: list[str] = []
    params: list[Any] = [strategy_id]

    for column, value in filters.items():
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)

    where = (" AND " + " AND ".join(clauses)) if clauses else ""
    return base_sql + where + f" ORDER BY {order_by}", params


# ===========================================================================
# TradeService
# ===========================================================================


class TradeService:
    """
    交易意图/人工成交/实际持仓 CRUD 服务.

    负责三类交易闭环记录的 SQLite 持久化：
    - TradeIntentRecord: 交易意图
    - ManualExecutionFillRecord: 人工成交
    - ActualPositionSnapshotRecord: 实际持仓快照
    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        初始化服务.

        Args:
            client: SQLiteClient 实例.

        """
        self._client = client

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def init_schema(self) -> None:
        """创建三张表及索引（幂等操作）。"""
        self._client.executescript(
            _CREATE_INTENTS_TABLE
            + _CREATE_IDX_INTENTS_STRATEGY_DATE
            + _CREATE_IDX_INTENTS_STATUS
            + _CREATE_FILLS_TABLE
            + _CREATE_IDX_FILLS_STRATEGY_DATE
            + _CREATE_IDX_FILLS_INTENT
            + _CREATE_POSITIONS_TABLE
            + _CREATE_IDX_POSITIONS_STRATEGY_DATE
            + _CREATE_IDX_POSITIONS_STRATEGY_INSTRUMENT_DATE
        )
        self._client.commit()

    # ------------------------------------------------------------------
    # Intent CRUD
    # ------------------------------------------------------------------

    def save_intent(self, record: TradeIntentRecord) -> None:
        """
        保存交易意图记录.

        Args:
            record: TradeIntentRecord 实例.

        """
        self._client.execute(
            _INSERT_INTENT,
            (
                record.intent_id,
                record.strategy_id,
                record.signal_date,
                record.instrument_id,
                record.direction,
                record.target_weight,
                record.current_weight,
                record.delta_weight,
                record.quantity,
                record.status,
                record.created_at,
            ),
        )
        self._client.commit()

    def get_intent(self, intent_id: str) -> TradeIntentRecord | None:
        """
        按 intent_id 查询单条交易意图.

        Args:
            intent_id: 意图唯一标识.

        Returns:
            TradeIntentRecord 或 None.

        """
        row = self._client.fetchone(_SELECT_INTENT_BY_ID, (intent_id,))
        return self._row_to_intent(row) if row else None

    def list_intents(
        self,
        strategy_id: str,
        signal_date: str | None = None,
        status: str | None = None,
    ) -> list[TradeIntentRecord]:
        """
        按条件查询交易意图列表.

        Args:
            strategy_id: 策略 ID（必填）.
            signal_date: 信号日期过滤.
            status: 状态过滤.

        Returns:
            匹配的 TradeIntentRecord 列表.

        """
        sql, params = _build_where_clause(
            _LIST_INTENTS_BASE,
            strategy_id,
            {"signal_date": signal_date, "status": status},
            "signal_date ASC",
        )
        rows = self._client.fetchall(sql, params)
        return [self._row_to_intent(row) for row in rows]

    def update_intent_status(self, intent_id: str, status: str) -> None:
        """
        更新交易意图状态.

        Args:
            intent_id: 意图唯一标识.
            status: 新状态.

        """
        self._client.execute(_UPDATE_INTENT_STATUS, (status, intent_id))
        self._client.commit()

    # ------------------------------------------------------------------
    # Fill CRUD
    # ------------------------------------------------------------------

    def save_fill(self, record: ManualExecutionFillRecord) -> None:
        """
        保存人工成交记录.

        Args:
            record: ManualExecutionFillRecord 实例.

        """
        self._client.execute(
            _INSERT_FILL,
            (
                record.fill_id,
                record.intent_id,
                record.strategy_id,
                record.trade_date,
                record.instrument_id,
                record.direction,
                record.quantity,
                record.fill_price,
                record.fee,
                record.slippage,
                record.notes,
                record.settlement_date,
                record.created_at,
            ),
        )
        self._client.commit()

    def get_fill(self, fill_id: str) -> ManualExecutionFillRecord | None:
        """
        按 fill_id 查询单条成交记录.

        Args:
            fill_id: 成交唯一标识.

        Returns:
            ManualExecutionFillRecord 或 None.

        """
        row = self._client.fetchone(_SELECT_FILL_BY_ID, (fill_id,))
        return self._row_to_fill(row) if row else None

    def list_fills(
        self,
        strategy_id: str,
        trade_date: str | None = None,
        intent_id: str | None = None,
        end_date: str | None = None,
    ) -> list[ManualExecutionFillRecord]:
        """
        按条件查询成交记录列表.

        Args:
            strategy_id: 策略 ID（必填）.
            trade_date: 成交日期过滤（仅 trade_date 时精确匹配）.
            intent_id: 关联意图 ID 过滤.
            end_date: 结束日期过滤（<=），与 trade_date 组合使用时形成日期范围.

        Returns:
            匹配的 ManualExecutionFillRecord 列表.

        """
        clauses: list[str] = []
        params: list[Any] = [strategy_id]

        if trade_date is not None and end_date is not None:
            clauses.append("trade_date >= ?")
            params.append(trade_date)
            clauses.append("trade_date <= ?")
            params.append(end_date)
        elif trade_date is not None:
            clauses.append("trade_date = ?")
            params.append(trade_date)
        elif end_date is not None:
            clauses.append("trade_date <= ?")
            params.append(end_date)

        if intent_id is not None:
            clauses.append("intent_id = ?")
            params.append(intent_id)

        where = (" AND " + " AND ".join(clauses)) if clauses else ""
        sql = _LIST_FILLS_BASE + where + " ORDER BY trade_date ASC"

        rows = self._client.fetchall(sql, params)
        return [self._row_to_fill(row) for row in rows]

    # ------------------------------------------------------------------
    # Position CRUD
    # ------------------------------------------------------------------

    def save_position(self, record: ActualPositionSnapshotRecord) -> None:
        """
        保存实际持仓快照.

        Args:
            record: ActualPositionSnapshotRecord 实例.

        """
        self._client.execute(
            _INSERT_POSITION,
            (
                record.snapshot_id,
                record.strategy_id,
                record.snapshot_date,
                record.instrument_id,
                record.quantity,
                record.available_quantity,
                record.average_cost,
                record.market_value,
                record.unrealized_pnl,
                record.realized_pnl,
                record.total_fees,
                record.created_at,
            ),
        )
        self._client.commit()

    def get_latest_position(
        self, strategy_id: str, instrument_id: int
    ) -> ActualPositionSnapshotRecord | None:
        """
        查询指定策略/标的的最新持仓快照.

        Args:
            strategy_id: 策略 ID.
            instrument_id: 标的 ID.

        Returns:
            最新日期的 ActualPositionSnapshotRecord 或 None.

        """
        row = self._client.fetchone(_GET_LATEST_POSITION, (strategy_id, instrument_id))
        return self._row_to_position(row) if row else None

    def list_positions(
        self,
        strategy_id: str,
        snapshot_date: str | None = None,
    ) -> list[ActualPositionSnapshotRecord]:
        """
        按条件查询持仓快照列表.

        Args:
            strategy_id: 策略 ID（必填）.
            snapshot_date: 快照日期过滤.

        Returns:
            匹配的 ActualPositionSnapshotRecord 列表.

        """
        sql, params = _build_where_clause(
            _LIST_POSITIONS_BASE,
            strategy_id,
            {"snapshot_date": snapshot_date},
            "snapshot_date ASC",
        )
        rows = self._client.fetchall(sql, params)
        return [self._row_to_position(row) for row in rows]

    # ------------------------------------------------------------------
    # Internal: row -> record converters
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_intent(row: dict[str, Any]) -> TradeIntentRecord:
        """将数据库行字典转换为 TradeIntentRecord."""
        return TradeIntentRecord(**row)

    @staticmethod
    def _row_to_fill(row: dict[str, Any]) -> ManualExecutionFillRecord:
        """将数据库行字典转换为 ManualExecutionFillRecord."""
        return ManualExecutionFillRecord(**row)

    @staticmethod
    def _row_to_position(row: dict[str, Any]) -> ActualPositionSnapshotRecord:
        """将数据库行字典转换为 ActualPositionSnapshotRecord."""
        return ActualPositionSnapshotRecord(**row)
