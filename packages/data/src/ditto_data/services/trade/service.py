"""
TradeService — 交易意图/人工成交/实际持仓 CRUD 服务.

使用 SQLite 持久化交易闭环的本地数据记录（TradeIntentRecord、
ManualExecutionFillRecord、ActualPositionSnapshotRecord），
提供幂等建表、按条件查询、状态更新等操作。

注意：本服务仅操作 *Record 数据类，不依赖 app/engine 包。
"""

from __future__ import annotations

from ditto_data.models.trade import (
    ActualPositionSnapshotRecord,
    ManualExecutionFillRecord,
    TradeIntentRecord,
)
from ditto_data.services.trade.fills import FILLS_DDL, FillWriter
from ditto_data.services.trade.intents import INTENTS_DDL, TradeIntentWriter
from ditto_data.services.trade.positions import POSITIONS_DDL, PositionWriter
from ditto_data.storage.sqlite_client import SQLiteClient

__all__ = [
    "TradeService",
]


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
        self._intents = TradeIntentWriter(client)
        self._fills = FillWriter(client)
        self._positions = PositionWriter(client)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def init_schema(self) -> None:
        """创建三张表及索引（幂等操作）。"""
        self._client.executescript(INTENTS_DDL + FILLS_DDL + POSITIONS_DDL)
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
        self._intents.save(record)

    def get_intent(self, intent_id: str) -> TradeIntentRecord | None:
        """
        按 intent_id 查询单条交易意图.

        Args:
            intent_id: 意图唯一标识.

        Returns:
            TradeIntentRecord 或 None.

        """
        return self._intents.get(intent_id)

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
        return self._intents.list(strategy_id, signal_date=signal_date, status=status)

    def update_intent_status(
        self,
        intent_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...] | None = None,
    ) -> bool:
        """
        更新交易意图状态.

        Args:
            intent_id: 意图唯一标识.
            status: 新状态.
            expected_current: 期望的当前状态集合。传入时使用带状态前置
                条件的 SQL 防止 TOCTOU 竞态，仅当当前状态在集合内时
                才执行更新。

        Returns:
            True 表示更新成功，False 表示因状态前置条件不满足而跳过。

        """
        return self._intents.update_status(
            intent_id, status, expected_current=expected_current
        )

    # ------------------------------------------------------------------
    # Fill CRUD
    # ------------------------------------------------------------------

    def save_fill(self, record: ManualExecutionFillRecord) -> None:
        """
        保存人工成交记录.

        Args:
            record: ManualExecutionFillRecord 实例.

        """
        self._fills.save(record)

    def get_fill(self, fill_id: str) -> ManualExecutionFillRecord | None:
        """
        按 fill_id 查询单条成交记录.

        Args:
            fill_id: 成交唯一标识.

        Returns:
            ManualExecutionFillRecord 或 None.

        """
        return self._fills.get(fill_id)

    def find_fill(
        self, intent_id: str, trade_date: str
    ) -> ManualExecutionFillRecord | None:
        """
        按 intent_id + trade_date 查找成交记录（幂等去重用）.

        Args:
            intent_id: 关联交易意图 ID.
            trade_date: 成交日期.

        Returns:
            ManualExecutionFillRecord 或 None.

        """
        return self._fills.find(intent_id, trade_date)

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
        return self._fills.list(
            strategy_id, trade_date=trade_date, intent_id=intent_id, end_date=end_date
        )

    # ------------------------------------------------------------------
    # Position CRUD
    # ------------------------------------------------------------------

    def save_position(self, record: ActualPositionSnapshotRecord) -> None:
        """
        保存实际持仓快照.

        Args:
            record: ActualPositionSnapshotRecord 实例.

        """
        self._positions.save(record)

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
        return self._positions.get_latest(strategy_id, instrument_id)

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
        return self._positions.list(strategy_id, snapshot_date=snapshot_date)
