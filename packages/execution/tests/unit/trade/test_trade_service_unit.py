"""Tests for TradeService — 交易意图/人工成交/实际持仓的 CRUD 服务.

使用 Data 本地 DTO (SignalRecord / FillRecord /
PositionRecord)，不依赖 app/engine 包。
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from ditto_execution.models import (
    AccountSnapshotRecord,
    BrokerEventRecord,
    FillRecord,
    PositionRecord,
    SignalRecord,
)
from ditto_execution.storage.deps import ExecutionReaders, ExecutionWriters
from ditto_execution.storage.sqlite.trade import (
    ACCOUNT_SNAPSHOTS_DDL,
    BROKER_EVENTS_DDL,
    FILLS_DDL,
    INTENTS_DDL,
    POSITIONS_DDL,
    AccountSnapshotReader,
    AccountSnapshotWriter,
    BrokerEventReader,
    BrokerEventWriter,
    FillReader,
    FillWriter,
    IntentReader,
    IntentWriter,
    PositionReader,
    PositionWriter,
    ensure_position_schema,
)
from ditto_execution.storage.sqlite.trade.service import (
    TradeService,
)
from ditto_platform.foundation import SQLiteClient


def _init_db(client: SQLiteClient) -> None:
    """Initialize trade tables (moved from TradeService.init_schema to DI)."""
    client.executescript(
        INTENTS_DDL
        + FILLS_DDL
        + POSITIONS_DDL
        + ACCOUNT_SNAPSHOTS_DDL
        + BROKER_EVENTS_DDL
    )
    ensure_position_schema(client)
    client.commit()


def _make_service(client: SQLiteClient) -> TradeService:
    """Create TradeService with real Reader/Writer instances."""
    _init_db(client)
    readers = ExecutionReaders(
        intent=IntentReader(client),
        fill=FillReader(client),
        position=PositionReader(client),
        account=AccountSnapshotReader(client),
        broker_event=BrokerEventReader(client),
    )
    writers = ExecutionWriters(
        intent=IntentWriter(client),
        fill=FillWriter(client),
        position=PositionWriter(client),
        account=AccountSnapshotWriter(client),
        broker_event=BrokerEventWriter(client),
    )
    return TradeService(readers=readers, writers=writers)


# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _make_intent(
    intent_id: str = "INT-001",
    strategy_id: str = "STRAT-A",
    signal_date: str = "2026-04-10",
    instrument_id: int = 510300,
    direction: str = "buy",
    target_weight: float = 0.30,
    current_weight: float = 0.10,
    delta_weight: float = 0.20,
    quantity: int | None = 1000,
    status: str = "pending",
) -> SignalRecord:
    """创建测试用 SignalRecord."""
    return SignalRecord(
        intent_id=intent_id,
        strategy_id=strategy_id,
        signal_date=signal_date,
        instrument_id=instrument_id,
        direction=direction,
        target_weight=target_weight,
        current_weight=current_weight,
        delta_weight=delta_weight,
        quantity=quantity,
        status=status,
        created_at="2026-04-10T09:30:00Z",
    )


def _make_fill(
    fill_id: str = "FILL-001",
    intent_id: str = "INT-001",
    strategy_id: str = "STRAT-A",
    trade_date: str = "2026-04-11",
    instrument_id: int = 510300,
    direction: str = "buy",
    quantity: int = 1000,
    fill_price: float = 4.123,
    fee: float = 5.0,
    slippage: float = 0.002,
) -> FillRecord:
    """创建测试用 FillRecord."""
    return FillRecord(
        fill_id=fill_id,
        intent_id=intent_id,
        strategy_id=strategy_id,
        trade_date=trade_date,
        instrument_id=instrument_id,
        direction=direction,
        quantity=quantity,
        fill_price=fill_price,
        fee=fee,
        slippage=slippage,
        notes="",
        settlement_date="2026-04-14",
        created_at="2026-04-11T10:00:00Z",
    )


def _make_position(
    snapshot_id: str = "POS-001",
    run_id: str = "RUN-001",
    strategy_id: str = "STRAT-A",
    snapshot_date: str = "2026-04-11",
    instrument_id: int = 510300,
    quantity: int = 1000,
    available_quantity: int = 1000,
    average_cost: float = 4.123,
    market_value: float = 4123.0,
    unrealized_pnl: float = 50.0,
    realized_pnl: float = 0.0,
    total_fees: float = 5.0,
) -> PositionRecord:
    """创建测试用 PositionRecord."""
    return PositionRecord(
        snapshot_id=snapshot_id,
        run_id=run_id,
        strategy_id=strategy_id,
        snapshot_date=snapshot_date,
        instrument_id=instrument_id,
        quantity=quantity,
        available_quantity=available_quantity,
        average_cost=average_cost,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        total_fees=total_fees,
        created_at="2026-04-11T15:00:00Z",
    )


def _make_account_snapshot(
    snapshot_id: str = "ACCT-001",
    run_id: str = "RUN-001",
    strategy_id: str = "STRAT-A",
    account_id: str = "ACCT-A",
    snapshot_date: str = "2026-04-11",
    cash_available: float = 95_000.0,
    cash_settled: float = 95_000.0,
    cash_frozen: float = 0.0,
    total_value: float = 100_000.0,
    nav: float = 100_000.0,
    exposure: float = 5_000.0,
) -> AccountSnapshotRecord:
    """创建测试用 AccountSnapshotRecord."""
    return AccountSnapshotRecord(
        snapshot_id=snapshot_id,
        run_id=run_id,
        strategy_id=strategy_id,
        account_id=account_id,
        snapshot_date=snapshot_date,
        cash_available=cash_available,
        cash_settled=cash_settled,
        cash_frozen=cash_frozen,
        total_value=total_value,
        nav=nav,
        exposure=exposure,
        created_at="2026-04-11T15:00:00Z",
    )


def _make_broker_event(
    event_id: str = "BE-001",
    run_id: str = "RUN-001",
    broker: str = "paper",
    event_type: str = "order_ack",
    event_time: str = "2026-04-11T09:31:00Z",
    order_id: str | None = "INT-001",
    broker_order_id: str | None = "BRK-001",
    fill_id: str | None = None,
    instrument_id: int | None = 510300,
    status: str | None = "accepted",
    correlation_id: str | None = "INT-001",
    payload: dict[str, object] | None = None,
) -> BrokerEventRecord:
    """创建测试用 BrokerEventRecord."""
    return BrokerEventRecord(
        event_id=event_id,
        run_id=run_id,
        broker=broker,
        event_type=event_type,
        event_time=event_time,
        order_id=order_id,
        broker_order_id=broker_order_id,
        fill_id=fill_id,
        instrument_id=instrument_id,
        status=status,
        correlation_id=correlation_id,
        payload=payload if payload is not None else {"raw_status": "Accepted"},
        created_at="2026-04-11T09:31:01Z",
    )


# ===========================================================================
# Test: init_schema
# ===========================================================================


class TestInitSchema:
    """建表与索引测试."""

    def test_creates_trade_intents_table(self, sqlite_client: SQLiteClient) -> None:
        """_init_db 应创建 trade_intents 表."""
        _init_db(sqlite_client)

        row = sqlite_client.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trade_intents'"
        )
        assert row is not None
        assert row["name"] == "trade_intents"

    def test_creates_execution_fills_table(self, sqlite_client: SQLiteClient) -> None:
        """_init_db 应创建 execution_fills 表."""
        _init_db(sqlite_client)

        row = sqlite_client.fetchone(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='execution_fills'"
        )
        assert row is not None
        assert row["name"] == "execution_fills"

    def test_creates_actual_positions_table(self, sqlite_client: SQLiteClient) -> None:
        """_init_db 应创建 actual_positions 表."""
        _init_db(sqlite_client)

        row = sqlite_client.fetchone(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='actual_positions'"
        )
        assert row is not None
        assert row["name"] == "actual_positions"

    def test_creates_account_snapshots_table(self, sqlite_client: SQLiteClient) -> None:
        """_init_db 应创建 account_snapshots 表."""
        _init_db(sqlite_client)

        row = sqlite_client.fetchone(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='account_snapshots'"
        )
        assert row is not None
        assert row["name"] == "account_snapshots"

    def test_creates_broker_events_table(self, sqlite_client: SQLiteClient) -> None:
        """_init_db 应创建 broker_events 表."""
        _init_db(sqlite_client)

        row = sqlite_client.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='broker_events'"
        )
        assert row is not None
        assert row["name"] == "broker_events"

    def test_creates_indexes(self, sqlite_client: SQLiteClient) -> None:
        """_init_db 应创建所有索引."""
        _init_db(sqlite_client)

        rows = sqlite_client.fetchall(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name LIKE 'idx_trade_%' OR name LIKE 'idx_execution_%' "
            "OR name LIKE 'idx_actual_%' OR name LIKE 'idx_account_%' "
            "OR name LIKE 'idx_broker_%'"
        )
        index_names = {r["name"] for r in rows}
        assert "idx_trade_intents_strategy_date" in index_names
        assert "idx_trade_intents_status" in index_names
        assert "idx_execution_fills_strategy_date" in index_names
        assert "idx_execution_fills_intent" in index_names
        assert "idx_actual_positions_strategy_date" in index_names
        assert "idx_actual_positions_run_date" in index_names
        assert "idx_actual_positions_run_strategy_instrument_date" in index_names
        assert "idx_account_snapshots_run_date" in index_names
        assert "idx_account_snapshots_strategy_account_date" in index_names
        assert "idx_broker_events_run_time" in index_names
        assert "idx_broker_events_run_order" in index_names

    def test_idempotent(self, sqlite_client: SQLiteClient) -> None:
        """重复调用 _init_db 不应报错."""
        _init_db(sqlite_client)
        _init_db(sqlite_client)  # second call

        count = sqlite_client.fetchval("SELECT COUNT(*) FROM trade_intents")
        assert count == 0

    def test_migrates_legacy_positions_without_run_id(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """旧 actual_positions 表应迁移到 run-scoped 唯一键."""
        sqlite_client.executescript(
            """
            CREATE TABLE actual_positions (
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
            CREATE UNIQUE INDEX idx_actual_positions_strategy_instrument_date
            ON actual_positions(strategy_id, instrument_id, snapshot_date);
            """
        )
        sqlite_client.commit()

        _init_db(sqlite_client)

        columns = {
            row["name"]
            for row in sqlite_client.fetchall("PRAGMA table_info(actual_positions)")
        }
        index_names = {
            row["name"]
            for row in sqlite_client.fetchall(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        assert "run_id" in columns
        assert "idx_actual_positions_strategy_instrument_date" not in index_names
        assert "idx_actual_positions_run_strategy_instrument_date" in index_names


# ===========================================================================
# Test: Intent CRUD
# ===========================================================================


class TestSaveIntent:
    """save_intent 测试."""

    def test_saves_and_retrieves_intent(self, sqlite_client: SQLiteClient) -> None:
        """保存后应能按 intent_id 查回完整记录."""
        svc = _make_service(sqlite_client)

        intent = _make_intent()
        svc.save_intent(intent)

        result = svc.get_intent("INT-001")
        assert result is not None
        assert result.intent_id == "INT-001"
        assert result.strategy_id == "STRAT-A"
        assert result.signal_date == "2026-04-10"
        assert result.instrument_id == 510300
        assert result.direction == "buy"
        assert result.target_weight == pytest.approx(0.30)
        assert result.current_weight == pytest.approx(0.10)
        assert result.delta_weight == pytest.approx(0.20)
        assert result.quantity == 1000
        assert result.status == "pending"
        assert result.created_at == "2026-04-10T09:30:00Z"

    def test_saves_intent_with_null_quantity(self, sqlite_client: SQLiteClient) -> None:
        """quantity=None 应能正常保存和查回."""
        svc = _make_service(sqlite_client)

        intent = _make_intent(quantity=None)
        svc.save_intent(intent)

        result = svc.get_intent("INT-001")
        assert result is not None
        assert result.quantity is None

    def test_get_intent_nonexistent(self, sqlite_client: SQLiteClient) -> None:
        """查询不存在的 intent_id 应返回 None."""
        svc = _make_service(sqlite_client)

        assert svc.get_intent("NONEXISTENT") is None


class TestListIntents:
    """list_intents 测试."""

    def _seed_intents(self, svc: TradeService) -> None:
        """插入多条测试数据."""
        svc.save_intent(
            _make_intent(
                intent_id="INT-001",
                strategy_id="STRAT-A",
                signal_date="2026-04-10",
                status="pending",
            )
        )
        svc.save_intent(
            _make_intent(
                intent_id="INT-002",
                strategy_id="STRAT-A",
                signal_date="2026-04-11",
                status="filled",
            )
        )
        svc.save_intent(
            _make_intent(
                intent_id="INT-003",
                strategy_id="STRAT-B",
                signal_date="2026-04-10",
                status="pending",
            )
        )

    def test_list_by_strategy_id(self, sqlite_client: SQLiteClient) -> None:
        """按 strategy_id 过滤."""
        svc = _make_service(sqlite_client)
        self._seed_intents(svc)

        results = svc.list_intents("STRAT-A")
        assert len(results) == 2
        assert all(r.strategy_id == "STRAT-A" for r in results)

    def test_list_by_strategy_and_signal_date(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """按 strategy_id + signal_date 过滤."""
        svc = _make_service(sqlite_client)
        self._seed_intents(svc)

        results = svc.list_intents("STRAT-A", signal_date="2026-04-10")
        assert len(results) == 1
        assert results[0].intent_id == "INT-001"

    def test_list_by_strategy_and_status(self, sqlite_client: SQLiteClient) -> None:
        """按 strategy_id + status 过滤."""
        svc = _make_service(sqlite_client)
        self._seed_intents(svc)

        results = svc.list_intents("STRAT-A", status="filled")
        assert len(results) == 1
        assert results[0].intent_id == "INT-002"

    def test_list_by_strategy_and_date_and_status(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """按 strategy_id + signal_date + status 过滤."""
        svc = _make_service(sqlite_client)
        self._seed_intents(svc)

        results = svc.list_intents("STRAT-A", signal_date="2026-04-11", status="filled")
        assert len(results) == 1
        assert results[0].intent_id == "INT-002"

    def test_list_no_match_returns_empty(self, sqlite_client: SQLiteClient) -> None:
        """无匹配返回空列表."""
        svc = _make_service(sqlite_client)
        self._seed_intents(svc)

        assert svc.list_intents("STRAT-NONE") == []

    def test_list_all_filters_none_returns_all_for_strategy(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """不附加过滤条件时返回该策略所有 intents."""
        svc = _make_service(sqlite_client)
        self._seed_intents(svc)

        results = svc.list_intents("STRAT-B")
        assert len(results) == 1
        assert results[0].intent_id == "INT-003"


class TestUpdateIntentStatus:
    """update_intent_status 测试."""

    def test_updates_status(self, sqlite_client: SQLiteClient) -> None:
        """应正确更新状态字段."""
        svc = _make_service(sqlite_client)

        svc.save_intent(_make_intent(status="pending"))
        svc.update_intent_status("INT-001", "filled", expected_current=("pending",))

        result = svc.get_intent("INT-001")
        assert result is not None
        assert result.status == "filled"

    def test_update_to_cancelled(self, sqlite_client: SQLiteClient) -> None:
        """应能更新为 cancelled 状态."""
        svc = _make_service(sqlite_client)

        svc.save_intent(_make_intent(status="pending"))
        svc.update_intent_status("INT-001", "cancelled", expected_current=("pending",))

        result = svc.get_intent("INT-001")
        assert result is not None
        assert result.status == "cancelled"

    def test_update_status_with_transition_guard(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """expected_current 匹配时应成功更新并返回 True."""
        svc = _make_service(sqlite_client)

        svc.save_intent(_make_intent(status="pending"))
        updated = svc.update_intent_status(
            "INT-001",
            "filled",
            expected_current=("pending", "partially_filled"),
        )

        assert updated is True
        result = svc.get_intent("INT-001")
        assert result is not None
        assert result.status == "filled"

    def test_update_status_conflicting_transition_skips(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """expected_current 不匹配时应跳过更新并返回 False."""
        svc = _make_service(sqlite_client)

        svc.save_intent(_make_intent(status="cancelled"))
        updated = svc.update_intent_status(
            "INT-001",
            "filled",
            expected_current=("pending", "partially_filled"),
        )

        assert updated is False
        result = svc.get_intent("INT-001")
        assert result is not None
        assert result.status == "cancelled"


class TestOrderStatusRepairPort:
    """Order status repair port backed by trade intents."""

    def test_get_order_status_reads_intent_status(
        self, sqlite_client: SQLiteClient
    ) -> None:
        svc = _make_service(sqlite_client)
        svc.save_intent(_make_intent(intent_id="ORD-001", status="submitted"))

        assert svc.get_order_status("ORD-001") == "submitted"

    def test_get_order_status_returns_none_when_missing(
        self, sqlite_client: SQLiteClient
    ) -> None:
        svc = _make_service(sqlite_client)

        assert svc.get_order_status("ORD-MISSING") is None

    def test_update_order_status_uses_transition_guard(
        self, sqlite_client: SQLiteClient
    ) -> None:
        svc = _make_service(sqlite_client)
        svc.save_intent(_make_intent(intent_id="ORD-001", status="submitted"))

        updated = svc.update_order_status(
            "ORD-001",
            "filled",
            expected_current=("submitted",),
        )

        assert updated is True
        assert svc.get_order_status("ORD-001") == "filled"

    def test_update_order_status_conflicting_transition_returns_false(
        self, sqlite_client: SQLiteClient
    ) -> None:
        svc = _make_service(sqlite_client)
        svc.save_intent(_make_intent(intent_id="ORD-001", status="cancelled"))

        updated = svc.update_order_status(
            "ORD-001",
            "filled",
            expected_current=("submitted", "partially_filled"),
        )

        assert updated is False
        assert svc.get_order_status("ORD-001") == "cancelled"

    def test_update_order_status_missing_returns_false(
        self, sqlite_client: SQLiteClient
    ) -> None:
        svc = _make_service(sqlite_client)

        updated = svc.update_order_status(
            "ORD-MISSING",
            "filled",
            expected_current=("submitted",),
        )

        assert updated is False


# ===========================================================================
# Test: Fill CRUD
# ===========================================================================


class TestSaveFill:
    """save_fill / get_fill 测试."""

    def test_saves_and_retrieves_fill(self, sqlite_client: SQLiteClient) -> None:
        """保存后应能按 fill_id 查回完整记录."""
        svc = _make_service(sqlite_client)

        fill = _make_fill()
        svc.save_fill(fill)

        result = svc.get_fill("FILL-001")
        assert result is not None
        assert result.fill_id == "FILL-001"
        assert result.intent_id == "INT-001"
        assert result.strategy_id == "STRAT-A"
        assert result.trade_date == "2026-04-11"
        assert result.instrument_id == 510300
        assert result.direction == "buy"
        assert result.quantity == 1000
        assert result.fill_price == pytest.approx(4.123)
        assert result.fee == pytest.approx(5.0)
        assert result.slippage == pytest.approx(0.002)
        assert result.notes == ""
        assert result.settlement_date == "2026-04-14"
        assert result.created_at == "2026-04-11T10:00:00Z"

    def test_get_fill_nonexistent(self, sqlite_client: SQLiteClient) -> None:
        """查询不存在的 fill_id 应返回 None."""
        svc = _make_service(sqlite_client)

        assert svc.get_fill("NONEXISTENT") is None


class TestFindFill:
    """find_fill — 按 intent_id + trade_date 查找成交记录（幂等去重用）。"""

    def test_finds_existing_fill(self, sqlite_client: SQLiteClient) -> None:
        """存在匹配的 fill 时应返回对应记录."""
        svc = _make_service(sqlite_client)

        fill = _make_fill(intent_id="INT-001", trade_date="2026-04-11")
        svc.save_fill(fill)

        result = svc.find_fill("INT-001", "2026-04-11")
        assert result is not None
        assert result.fill_id == "FILL-001"
        assert result.intent_id == "INT-001"
        assert result.trade_date == "2026-04-11"

    def test_returns_none_when_no_match(self, sqlite_client: SQLiteClient) -> None:
        """无匹配时返回 None."""
        svc = _make_service(sqlite_client)

        fill = _make_fill(intent_id="INT-001", trade_date="2026-04-11")
        svc.save_fill(fill)

        assert svc.find_fill("INT-001", "2026-04-12") is None
        assert svc.find_fill("INT-999", "2026-04-11") is None

    def test_returns_first_when_multiple_fills_same_key(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """同 intent_id + trade_date 存在多条时返回第一条（LIMIT 1）."""
        svc = _make_service(sqlite_client)

        svc.save_fill(
            _make_fill(
                fill_id="FILL-001",
                intent_id="INT-001",
                trade_date="2026-04-11",
            )
        )
        svc.save_fill(
            _make_fill(
                fill_id="FILL-002",
                intent_id="INT-001",
                trade_date="2026-04-11",
                quantity=500,
            )
        )

        result = svc.find_fill("INT-001", "2026-04-11")
        assert result is not None
        assert result.fill_id == "FILL-001"


class TestReplaceFill:
    """replace_fill 测试."""

    def test_replaces_existing_fill_by_id(self, sqlite_client: SQLiteClient) -> None:
        """替换已有 fill_id 时应覆盖可修正字段并保留主键."""
        svc = _make_service(sqlite_client)
        original = _make_fill()
        amended = replace(
            original,
            quantity=1200,
            fill_price=4.25,
            fee=6.0,
            notes="amended by reconciliation repair",
        )
        svc.save_fill(original)

        replaced = svc.replace_fill(amended)

        result = svc.get_fill("FILL-001")
        assert replaced is True
        assert result == amended

    def test_returns_false_when_fill_missing(self, sqlite_client: SQLiteClient) -> None:
        """缺失 fill_id 时不应插入新成交."""
        svc = _make_service(sqlite_client)

        replaced = svc.replace_fill(_make_fill())

        assert replaced is False
        assert svc.get_fill("FILL-001") is None


class TestListFills:
    """list_fills 测试."""

    def _seed_fills(self, svc: TradeService) -> None:
        """插入多条测试数据."""
        svc.save_fill(
            _make_fill(
                fill_id="FILL-001",
                intent_id="INT-001",
                strategy_id="STRAT-A",
                trade_date="2026-04-11",
            )
        )
        svc.save_fill(
            _make_fill(
                fill_id="FILL-002",
                intent_id="INT-002",
                strategy_id="STRAT-A",
                trade_date="2026-04-12",
            )
        )
        svc.save_fill(
            _make_fill(
                fill_id="FILL-003",
                intent_id="INT-003",
                strategy_id="STRAT-B",
                trade_date="2026-04-11",
            )
        )

    def test_list_by_strategy_id(self, sqlite_client: SQLiteClient) -> None:
        """按 strategy_id 过滤."""
        svc = _make_service(sqlite_client)
        self._seed_fills(svc)

        results = svc.list_fills("STRAT-A")
        assert len(results) == 2
        assert all(r.strategy_id == "STRAT-A" for r in results)

    def test_list_by_strategy_and_trade_date(self, sqlite_client: SQLiteClient) -> None:
        """按 strategy_id + trade_date 过滤."""
        svc = _make_service(sqlite_client)
        self._seed_fills(svc)

        results = svc.list_fills("STRAT-A", trade_date="2026-04-11")
        assert len(results) == 1
        assert results[0].fill_id == "FILL-001"

    def test_list_by_intent_id(self, sqlite_client: SQLiteClient) -> None:
        """按 intent_id 过滤."""
        svc = _make_service(sqlite_client)
        self._seed_fills(svc)

        results = svc.list_fills("STRAT-A", intent_id="INT-002")
        assert len(results) == 1
        assert results[0].fill_id == "FILL-002"

    def test_list_no_match_returns_empty(self, sqlite_client: SQLiteClient) -> None:
        """无匹配返回空列表."""
        svc = _make_service(sqlite_client)
        self._seed_fills(svc)

        assert svc.list_fills("STRAT-NONE") == []


# ===========================================================================
# Test: Position CRUD
# ===========================================================================


class TestSavePosition:
    """save_position 测试."""

    def test_saves_and_retrieves_position(self, sqlite_client: SQLiteClient) -> None:
        """保存后应能通过 get_latest_position 查回."""
        svc = _make_service(sqlite_client)

        pos = _make_position()
        svc.save_position(pos)

        result = svc.get_latest_position("STRAT-A", 510300)
        assert result is not None
        assert result.snapshot_id == "POS-001"
        assert result.run_id == "RUN-001"
        assert result.strategy_id == "STRAT-A"
        assert result.snapshot_date == "2026-04-11"
        assert result.instrument_id == 510300
        assert result.quantity == 1000
        assert result.available_quantity == 1000
        assert result.average_cost == pytest.approx(4.123)
        assert result.market_value == pytest.approx(4123.0)
        assert result.unrealized_pnl == pytest.approx(50.0)
        assert result.realized_pnl == pytest.approx(0.0)
        assert result.total_fees == pytest.approx(5.0)
        assert result.created_at == "2026-04-11T15:00:00Z"

    def test_get_latest_position_nonexistent(self, sqlite_client: SQLiteClient) -> None:
        """查询不存在的 strategy_id/instrument_id 应返回 None."""
        svc = _make_service(sqlite_client)

        assert svc.get_latest_position("STRAT-NONE", 999999) is None

    def test_get_latest_returns_newest_date(self, sqlite_client: SQLiteClient) -> None:
        """多天快照应返回最新日期."""
        svc = _make_service(sqlite_client)

        svc.save_position(
            _make_position(snapshot_id="POS-001", snapshot_date="2026-04-10")
        )
        svc.save_position(
            _make_position(snapshot_id="POS-002", snapshot_date="2026-04-12")
        )
        svc.save_position(
            _make_position(snapshot_id="POS-003", snapshot_date="2026-04-11")
        )

        result = svc.get_latest_position("STRAT-A", 510300)
        assert result is not None
        assert result.snapshot_date == "2026-04-12"
        assert result.snapshot_id == "POS-002"

    def test_save_position_upsert_same_snapshot_id(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """同一 snapshot_id 重复写入不报错，后写入覆盖先写入."""
        svc = _make_service(sqlite_client)

        svc.save_position(
            _make_position(snapshot_id="POS-001", quantity=1000, average_cost=4.0)
        )
        svc.save_position(
            _make_position(snapshot_id="POS-001", quantity=2000, average_cost=4.5)
        )

        result = svc.get_latest_position("STRAT-A", 510300)
        assert result is not None
        assert result.quantity == 2000
        assert result.average_cost == pytest.approx(4.5)

    def test_save_position_upsert_same_unique_key(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """同一 run-scoped 业务键不同 snapshot_id，后写入覆盖先写入."""
        svc = _make_service(sqlite_client)

        svc.save_position(
            _make_position(
                snapshot_id="POS-001",
                snapshot_date="2026-04-11",
                quantity=1000,
                average_cost=4.0,
            )
        )
        svc.save_position(
            _make_position(
                snapshot_id="POS-002",
                snapshot_date="2026-04-11",
                quantity=2000,
                average_cost=4.5,
            )
        )

        result = svc.get_latest_position("STRAT-A", 510300)
        assert result is not None
        assert result.quantity == 2000
        assert result.average_cost == pytest.approx(4.5)
        assert result.snapshot_id == "POS-002"

    def test_same_strategy_instrument_date_can_exist_in_different_runs(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """相同策略/标的/日期在不同 run 下应保留独立快照."""
        svc = _make_service(sqlite_client)

        svc.save_position(
            _make_position(
                snapshot_id="POS-RUN-001",
                run_id="RUN-001",
                snapshot_date="2026-04-11",
                quantity=1000,
            )
        )
        svc.save_position(
            _make_position(
                snapshot_id="POS-RUN-002",
                run_id="RUN-002",
                snapshot_date="2026-04-11",
                quantity=2000,
            )
        )

        run_1 = svc.get_latest_position("STRAT-A", 510300, run_id="RUN-001")
        run_2 = svc.get_latest_position("STRAT-A", 510300, run_id="RUN-002")

        assert run_1 is not None
        assert run_1.snapshot_id == "POS-RUN-001"
        assert run_1.quantity == 1000
        assert run_2 is not None
        assert run_2.snapshot_id == "POS-RUN-002"
        assert run_2.quantity == 2000


class TestListPositions:
    """list_positions 测试."""

    def _seed_positions(self, svc: TradeService) -> None:
        """插入多条测试数据."""
        svc.save_position(
            _make_position(
                snapshot_id="POS-001",
                strategy_id="STRAT-A",
                snapshot_date="2026-04-10",
                instrument_id=510300,
            )
        )
        svc.save_position(
            _make_position(
                snapshot_id="POS-002",
                strategy_id="STRAT-A",
                snapshot_date="2026-04-10",
                instrument_id=159915,
            )
        )
        svc.save_position(
            _make_position(
                snapshot_id="POS-003",
                strategy_id="STRAT-A",
                snapshot_date="2026-04-11",
                instrument_id=510300,
            )
        )
        svc.save_position(
            _make_position(
                snapshot_id="POS-004",
                run_id="RUN-002",
                strategy_id="STRAT-B",
                snapshot_date="2026-04-10",
                instrument_id=510300,
            )
        )

    def test_list_by_strategy_id(self, sqlite_client: SQLiteClient) -> None:
        """按 strategy_id 过滤."""
        svc = _make_service(sqlite_client)
        self._seed_positions(svc)

        results = svc.list_positions("STRAT-A")
        assert len(results) == 3
        assert all(r.strategy_id == "STRAT-A" for r in results)

    def test_list_by_strategy_and_date(self, sqlite_client: SQLiteClient) -> None:
        """按 strategy_id + snapshot_date 过滤."""
        svc = _make_service(sqlite_client)
        self._seed_positions(svc)

        results = svc.list_positions("STRAT-A", snapshot_date="2026-04-10")
        assert len(results) == 2
        assert all(r.snapshot_date == "2026-04-10" for r in results)

    def test_list_by_run_strategy_and_date(self, sqlite_client: SQLiteClient) -> None:
        """按 run_id + strategy_id + snapshot_date 过滤."""
        svc = _make_service(sqlite_client)
        self._seed_positions(svc)
        svc.save_position(
            _make_position(
                snapshot_id="POS-005",
                run_id="RUN-002",
                strategy_id="STRAT-A",
                snapshot_date="2026-04-10",
                instrument_id=510300,
                quantity=3000,
            )
        )

        results = svc.list_positions(
            "STRAT-A",
            snapshot_date="2026-04-10",
            run_id="RUN-001",
        )

        assert len(results) == 2
        assert {r.snapshot_id for r in results} == {"POS-001", "POS-002"}
        assert {r.run_id for r in results} == {"RUN-001"}

    def test_list_no_match_returns_empty(self, sqlite_client: SQLiteClient) -> None:
        """无匹配返回空列表."""
        svc = _make_service(sqlite_client)
        self._seed_positions(svc)

        assert svc.list_positions("STRAT-NONE") == []


# ===========================================================================
# Test: Account Snapshot CRUD
# ===========================================================================


class TestSaveAccountSnapshot:
    """save_account_snapshot 测试."""

    def test_saves_and_retrieves_latest_account_snapshot(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """保存后应能按 run_id/account_id 查回最新账户快照."""
        svc = _make_service(sqlite_client)

        svc.save_account_snapshot(_make_account_snapshot())

        result = svc.get_latest_account_snapshot("RUN-001", "ACCT-A")
        assert result is not None
        assert result.snapshot_id == "ACCT-001"
        assert result.run_id == "RUN-001"
        assert result.strategy_id == "STRAT-A"
        assert result.account_id == "ACCT-A"
        assert result.snapshot_date == "2026-04-11"
        assert result.cash_available == pytest.approx(95_000.0)
        assert result.total_value == pytest.approx(100_000.0)
        assert result.nav == pytest.approx(100_000.0)
        assert result.exposure == pytest.approx(5_000.0)

    def test_get_latest_account_snapshot_returns_newest_date(
        self, sqlite_client: SQLiteClient
    ) -> None:
        """多天账户快照应返回最新日期."""
        svc = _make_service(sqlite_client)

        svc.save_account_snapshot(
            _make_account_snapshot(snapshot_id="ACCT-001", snapshot_date="2026-04-10")
        )
        svc.save_account_snapshot(
            _make_account_snapshot(snapshot_id="ACCT-002", snapshot_date="2026-04-12")
        )
        svc.save_account_snapshot(
            _make_account_snapshot(snapshot_id="ACCT-003", snapshot_date="2026-04-11")
        )

        result = svc.get_latest_account_snapshot("RUN-001", "ACCT-A")
        assert result is not None
        assert result.snapshot_id == "ACCT-002"
        assert result.snapshot_date == "2026-04-12"


class TestListAccountSnapshots:
    """list_account_snapshots 测试."""

    def test_lists_by_run_and_strategy(self, sqlite_client: SQLiteClient) -> None:
        """按 run_id + strategy_id 过滤账户快照."""
        svc = _make_service(sqlite_client)
        svc.save_account_snapshot(_make_account_snapshot(snapshot_id="ACCT-001"))
        svc.save_account_snapshot(
            _make_account_snapshot(snapshot_id="ACCT-002", account_id="ACCT-B")
        )
        svc.save_account_snapshot(
            _make_account_snapshot(
                snapshot_id="ACCT-003",
                run_id="RUN-002",
                account_id="ACCT-C",
            )
        )

        results = svc.list_account_snapshots("RUN-001", strategy_id="STRAT-A")

        assert [r.snapshot_id for r in results] == ["ACCT-001", "ACCT-002"]
        assert {r.run_id for r in results} == {"RUN-001"}
        assert {r.strategy_id for r in results} == {"STRAT-A"}


# ===========================================================================
# Test: Broker Event CRUD
# ===========================================================================


class TestSaveBrokerEvent:
    """save_broker_event 测试."""

    def test_saves_single_event_with_payload(self, sqlite_client: SQLiteClient) -> None:
        """save_broker_event 应持久化 live/paper broker 标准事件."""
        svc = _make_service(sqlite_client)
        event = _make_broker_event(payload={"venue_status": "Accepted", "seq": 42})

        svc.save_broker_event(event)

        result = svc.get_broker_event("BE-001")
        assert result is not None
        assert result.run_id == "RUN-001"
        assert result.order_id == "INT-001"
        assert result.broker_order_id == "BRK-001"
        assert result.payload == {"venue_status": "Accepted", "seq": 42}

    def test_duplicate_event_id_preserves_first_callback(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        """重复 broker callback 应按 event_id 幂等，不覆盖首次观测事件."""
        svc = _make_service(sqlite_client)
        first = _make_broker_event(
            event_id="BE-DUP",
            event_time="2026-04-11T09:31:00Z",
            status="partially_filled",
            payload={"venue_status": "PartiallyFilled", "seq": 1},
        )
        duplicate = _make_broker_event(
            event_id="BE-DUP",
            event_time="2026-04-11T09:40:00Z",
            status="filled",
            payload={"venue_status": "Filled", "seq": 2},
        )

        svc.save_broker_event(first)
        svc.save_broker_event(duplicate)

        result = svc.get_broker_event("BE-DUP")
        assert result is not None
        assert result.event_time == "2026-04-11T09:31:00Z"
        assert result.status == "partially_filled"
        assert result.payload == {"venue_status": "PartiallyFilled", "seq": 1}

    def test_duplicate_event_id_backfills_missing_broker_order_link(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        """乱序 callback 后到的 broker_order_id 应补齐查询 link key."""
        svc = _make_service(sqlite_client)
        out_of_order_fill = _make_broker_event(
            event_id="BE-LATE-LINK",
            event_type="fill",
            event_time="2026-04-11T09:31:00Z",
            broker_order_id=None,
            fill_id="FILL-001",
            status="partially_filled",
            payload={"venue_status": "PartiallyFilled", "seq": 1},
        )
        replayed_fill_after_ack = _make_broker_event(
            event_id="BE-LATE-LINK",
            event_type="fill",
            event_time="2026-04-11T09:40:00Z",
            broker_order_id="BRK-001",
            fill_id="FILL-001",
            status="filled",
            payload={"venue_status": "Filled", "seq": 2},
        )

        svc.save_broker_event(out_of_order_fill)
        svc.save_broker_event(replayed_fill_after_ack)

        result = svc.get_broker_event("BE-LATE-LINK")
        assert result is not None
        assert result.broker_order_id == "BRK-001"
        assert result.event_time == "2026-04-11T09:31:00Z"
        assert result.status == "partially_filled"
        assert result.payload == {"venue_status": "PartiallyFilled", "seq": 1}
        by_broker_order = svc.list_broker_events(
            "RUN-001",
            broker_order_id="BRK-001",
        )
        assert [event.event_id for event in by_broker_order] == ["BE-LATE-LINK"]

    def test_duplicate_event_id_backfills_blank_broker_order_link(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        """历史 blank broker_order_id 也应被后续有效 replay 补齐."""
        svc = _make_service(sqlite_client)
        out_of_order_fill = _make_broker_event(
            event_id="BE-BLANK-LATE-LINK",
            event_type="fill",
            event_time="2026-04-11T09:31:00Z",
            broker_order_id="   ",
            fill_id="FILL-001",
            status="partially_filled",
            payload={"venue_status": "PartiallyFilled", "seq": 1},
        )
        replayed_fill_after_ack = _make_broker_event(
            event_id="BE-BLANK-LATE-LINK",
            event_type="fill",
            event_time="2026-04-11T09:40:00Z",
            broker_order_id="BRK-001",
            fill_id="FILL-001",
            status="filled",
            payload={"venue_status": "Filled", "seq": 2},
        )

        svc.save_broker_event(out_of_order_fill)
        svc.save_broker_event(replayed_fill_after_ack)

        result = svc.get_broker_event("BE-BLANK-LATE-LINK")
        assert result is not None
        assert result.broker_order_id == "BRK-001"
        assert result.event_time == "2026-04-11T09:31:00Z"
        assert result.status == "partially_filled"
        assert result.payload == {"venue_status": "PartiallyFilled", "seq": 1}
        by_broker_order = svc.list_broker_events(
            "RUN-001",
            broker_order_id="BRK-001",
        )
        assert [event.event_id for event in by_broker_order] == ["BE-BLANK-LATE-LINK"]


class TestListBrokerEvents:
    """list_broker_events 测试."""

    def test_list_by_run_order_and_date(self, sqlite_client: SQLiteClient) -> None:
        """broker_events 应按 run/order/date 过滤，避免跨运行串线."""
        svc = _make_service(sqlite_client)
        svc.save_broker_event(_make_broker_event(event_id="BE-001"))
        svc.save_broker_event(
            _make_broker_event(
                event_id="BE-002",
                run_id="RUN-002",
                event_time="2026-04-11T09:32:00Z",
            )
        )
        svc.save_broker_event(
            _make_broker_event(
                event_id="BE-003",
                order_id="INT-002",
                correlation_id="INT-002",
            )
        )

        result = svc.list_broker_events(
            "RUN-001",
            order_id="INT-001",
            start_date="2026-04-11",
            end_date="2026-04-11",
        )

        assert [event.event_id for event in result] == ["BE-001"]


# ===========================================================================
# Test: _build_where_clause whitelist validation
# ===========================================================================


class TestBuildWhereClauseWhitelist:
    """_build_where_clause 白名单校验测试 — 防止 SQL 注入."""

    def test_valid_order_by_signal_date_asc(self) -> None:
        """合法 order_by 'signal_date ASC' 应正常构建 SQL."""
        from ditto_execution.storage.sqlite.trade._sql import (
            build_where_clause as _build_where_clause,
        )

        sql, params = _build_where_clause(
            "SELECT * FROM trade_intents WHERE strategy_id = ?",
            "STRAT-A",
            {"signal_date": "2026-04-10"},
            "signal_date ASC",
        )
        assert "ORDER BY signal_date ASC" in sql
        assert params == ["STRAT-A", "2026-04-10"]

    def test_valid_order_by_signal_date_desc(self) -> None:
        """合法 order_by 'signal_date DESC' 应正常构建 SQL."""
        from ditto_execution.storage.sqlite.trade._sql import (
            build_where_clause as _build_where_clause,
        )

        sql, _params = _build_where_clause(
            "SELECT * FROM trade_intents WHERE strategy_id = ?",
            "STRAT-A",
            {},
            "signal_date DESC",
        )
        assert "ORDER BY signal_date DESC" in sql

    def test_valid_order_by_snapshot_date_asc(self) -> None:
        """合法 order_by 'snapshot_date ASC' 应正常构建 SQL."""
        from ditto_execution.storage.sqlite.trade._sql import (
            build_where_clause as _build_where_clause,
        )

        sql, _params = _build_where_clause(
            "SELECT * FROM actual_positions WHERE strategy_id = ?",
            "STRAT-A",
            {"snapshot_date": "2026-04-10"},
            "snapshot_date ASC",
        )
        assert "ORDER BY snapshot_date ASC" in sql

    def test_valid_order_by_snapshot_date_desc(self) -> None:
        """合法 order_by 'snapshot_date DESC' 应正常构建 SQL."""
        from ditto_execution.storage.sqlite.trade._sql import (
            build_where_clause as _build_where_clause,
        )

        sql, _params = _build_where_clause(
            "SELECT * FROM actual_positions WHERE strategy_id = ?",
            "STRAT-A",
            {},
            "snapshot_date DESC",
        )
        assert "ORDER BY snapshot_date DESC" in sql

    def test_valid_filter_columns(self) -> None:
        """合法过滤列应正常构建 SQL."""
        from ditto_execution.storage.sqlite.trade._sql import (
            build_where_clause as _build_where_clause,
        )

        # signal_date
        sql, _params = _build_where_clause(
            "SELECT * FROM trade_intents WHERE strategy_id = ?",
            "STRAT-A",
            {"signal_date": "2026-04-10"},
            "signal_date ASC",
        )
        assert "signal_date = ?" in sql

        # status
        sql, _params = _build_where_clause(
            "SELECT * FROM trade_intents WHERE strategy_id = ?",
            "STRAT-A",
            {"status": "pending"},
            "signal_date ASC",
        )
        assert "status = ?" in sql

        # snapshot_date
        sql, _params = _build_where_clause(
            "SELECT * FROM actual_positions WHERE strategy_id = ?",
            "STRAT-A",
            {"snapshot_date": "2026-04-10"},
            "signal_date ASC",
        )
        assert "snapshot_date = ?" in sql

        # run_id
        sql, _params = _build_where_clause(
            "SELECT * FROM actual_positions WHERE strategy_id = ?",
            "STRAT-A",
            {"run_id": "RUN-001"},
            "snapshot_date ASC",
        )
        assert "run_id = ?" in sql

    def test_none_filter_values_skipped(self) -> None:
        """None 值过滤条件应被跳过，不触发白名单校验."""
        from ditto_execution.storage.sqlite.trade._sql import (
            build_where_clause as _build_where_clause,
        )

        sql, params = _build_where_clause(
            "SELECT * FROM trade_intents WHERE strategy_id = ?",
            "STRAT-A",
            {"signal_date": None, "status": None},
            "signal_date ASC",
        )
        assert "ORDER BY signal_date ASC" in sql
        assert params == ["STRAT-A"]

    def test_invalid_order_by_rejects(self) -> None:
        """非法 order_by（含 SQL 注入）应抛出 ValueError."""
        from ditto_execution.storage.sqlite.trade._sql import (
            build_where_clause as _build_where_clause,
        )

        with pytest.raises(ValueError, match="order_by"):
            _build_where_clause(
                "SELECT * FROM trade_intents WHERE strategy_id = ?",
                "STRAT-A",
                {},
                "1; DROP TABLE trade_intents; --",
            )

    def test_invalid_order_by_rejects_subtle_injection(self) -> None:
        """含子查询的 order_by 应被拒绝."""
        from ditto_execution.storage.sqlite.trade._sql import (
            build_where_clause as _build_where_clause,
        )

        with pytest.raises(ValueError, match="order_by"):
            _build_where_clause(
                "SELECT * FROM trade_intents WHERE strategy_id = ?",
                "STRAT-A",
                {},
                "signal_date ASC; SELECT * FROM trade_intents",
            )

    def test_invalid_filter_column_rejects(self) -> None:
        """非法过滤列名应抛出 ValueError."""
        from ditto_execution.storage.sqlite.trade._sql import (
            build_where_clause as _build_where_clause,
        )

        with pytest.raises(ValueError, match="不在白名单内"):
            _build_where_clause(
                "SELECT * FROM trade_intents WHERE strategy_id = ?",
                "STRAT-A",
                {"1; DROP TABLE trade_intents; --": "value"},
                "signal_date ASC",
            )

    def test_invalid_filter_column_rejects_subtle(self) -> None:
        """非法列名（含 SQL 片段）应被拒绝."""
        from ditto_execution.storage.sqlite.trade._sql import (
            build_where_clause as _build_where_clause,
        )

        with pytest.raises(ValueError, match="不在白名单内"):
            _build_where_clause(
                "SELECT * FROM trade_intents WHERE strategy_id = ?",
                "STRAT-A",
                {"status = 'filled' OR 1=1": "value"},
                "signal_date ASC",
            )

    def test_empty_order_by_rejects(self) -> None:
        """空字符串 order_by 应被拒绝."""
        from ditto_execution.storage.sqlite.trade._sql import (
            build_where_clause as _build_where_clause,
        )

        with pytest.raises(ValueError, match="order_by"):
            _build_where_clause(
                "SELECT * FROM trade_intents WHERE strategy_id = ?",
                "STRAT-A",
                {},
                "",
            )

    def test_allowed_order_by_constants_cover_current_usage(self) -> None:
        """_ALLOWED_ORDER_BY 应覆盖当前所有调用点的 order_by 值."""
        from ditto_execution.storage.sqlite.trade._sql import (
            ALLOWED_ORDER_BY as _ALLOWED_ORDER_BY,
        )

        assert "signal_date ASC" in _ALLOWED_ORDER_BY
        assert "snapshot_date ASC" in _ALLOWED_ORDER_BY

    def test_allowed_columns_constants_cover_current_usage(self) -> None:
        """_ALLOWED_COLUMNS 应覆盖当前所有调用点的过滤列名."""
        from ditto_execution.storage.sqlite.trade._sql import (
            ALLOWED_COLUMNS as _ALLOWED_COLUMNS,
        )

        assert "signal_date" in _ALLOWED_COLUMNS
        assert "status" in _ALLOWED_COLUMNS
        assert "snapshot_date" in _ALLOWED_COLUMNS
