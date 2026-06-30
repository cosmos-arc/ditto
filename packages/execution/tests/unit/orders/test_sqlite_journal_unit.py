"""SqliteOrderEventJournal 单元测试 — 持久化 append-only 事件日志。"""

from __future__ import annotations

import pytest
from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.journal import OrderEventJournal
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.trigger import OrderTrigger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    client_id: ClientOrderId,
    trigger: OrderTrigger = OrderTrigger.SUBMIT,
    status: OrderStatus = OrderStatus.SUBMITTED,
    fill_price: float | None = None,
    fill_quantity: int = 0,
    fee: float = 0.0,
    message: str | None = None,
) -> OrderEvent:
    return OrderEvent(
        client_id=client_id,
        trigger=trigger,
        status=status,
        fill_price=fill_price,
        fill_quantity=fill_quantity,
        fee=fee,
        message=message,
    )


# ---------------------------------------------------------------------------
# Fixture — 使用 :memory: 避免文件 I/O
# ---------------------------------------------------------------------------


@pytest.fixture
def journal() -> OrderEventJournal:
    """创建内存 SQLite journal（通过 db_path=:memory:）。"""
    from ditto_execution.orders.sqlite_journal import SqliteOrderEventJournal

    return SqliteOrderEventJournal(db_path=":memory:")


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestSqliteJournalProtocolConformance:
    def test_isinstance_order_event_journal(self) -> None:
        from ditto_execution.orders.sqlite_journal import SqliteOrderEventJournal

        j = SqliteOrderEventJournal(db_path=":memory:")
        assert isinstance(j, OrderEventJournal)

    def test_implements_all_methods(self) -> None:
        from ditto_execution.orders.sqlite_journal import SqliteOrderEventJournal

        j = SqliteOrderEventJournal(db_path=":memory:")
        assert hasattr(j, "append")
        assert hasattr(j, "events_for")
        assert hasattr(j, "all_events")


# ---------------------------------------------------------------------------
# append + events_for
# ---------------------------------------------------------------------------


class TestSqliteJournalAppendAndQuery:
    def test_append_and_events_for(self, journal: OrderEventJournal) -> None:
        cid = ClientOrderId(value="test-001")
        event = _make_event(cid)

        journal.append(event)
        events = journal.events_for(cid)

        assert len(events) == 1
        assert events[0].client_id == cid
        assert events[0].trigger == OrderTrigger.SUBMIT
        assert events[0].status == OrderStatus.SUBMITTED

    def test_events_for_unknown_returns_empty(
        self,
        journal: OrderEventJournal,
    ) -> None:
        unknown = ClientOrderId(value="nonexistent")
        assert journal.events_for(unknown) == ()

    def test_multiple_events_same_order(self, journal: OrderEventJournal) -> None:
        cid = ClientOrderId(value="test-002")
        e1 = _make_event(cid, trigger=OrderTrigger.SUBMIT, status=OrderStatus.SUBMITTED)
        e2 = _make_event(
            cid,
            trigger=OrderTrigger.FILL,
            status=OrderStatus.FILLED,
            fill_price=10.5,
            fill_quantity=100,
            fee=1.5,
        )
        journal.append(e1)
        journal.append(e2)

        events = journal.events_for(cid)
        assert len(events) == 2
        assert events[0].trigger == OrderTrigger.SUBMIT
        assert events[1].trigger == OrderTrigger.FILL
        assert events[1].fill_price == 10.5
        assert events[1].fill_quantity == 100
        assert events[1].fee == 1.5

    def test_multiple_orders(self, journal: OrderEventJournal) -> None:
        id_a = ClientOrderId(value="order-a")
        id_b = ClientOrderId(value="order-b")
        ea = _make_event(id_a)
        eb = _make_event(id_b)

        journal.append(ea)
        journal.append(eb)

        assert len(journal.events_for(id_a)) == 1
        assert len(journal.events_for(id_b)) == 1
        assert journal.events_for(id_a)[0].client_id == id_a
        assert journal.events_for(id_b)[0].client_id == id_b


# ---------------------------------------------------------------------------
# all_events
# ---------------------------------------------------------------------------


class TestSqliteJournalAllEvents:
    def test_all_events_empty(self, journal: OrderEventJournal) -> None:
        assert journal.all_events() == ()

    def test_all_events_returns_all(self, journal: OrderEventJournal) -> None:
        id_a = ClientOrderId(value="a")
        id_b = ClientOrderId(value="b")
        e1 = _make_event(id_a)
        e2 = _make_event(id_b)
        e3 = _make_event(id_a, trigger=OrderTrigger.FILL, status=OrderStatus.FILLED)

        journal.append(e1)
        journal.append(e2)
        journal.append(e3)

        all_evts = journal.all_events()
        assert len(all_evts) == 3
        # 按 event_seq 排序
        assert all_evts[0].client_id == id_a
        assert all_evts[0].trigger == OrderTrigger.SUBMIT
        assert all_evts[1].client_id == id_b
        assert all_evts[2].client_id == id_a
        assert all_evts[2].trigger == OrderTrigger.FILL


# ---------------------------------------------------------------------------
# 事件字段完整性
# ---------------------------------------------------------------------------


class TestSqliteJournalEventFields:
    def test_event_with_optional_fields(self, journal: OrderEventJournal) -> None:
        cid = ClientOrderId(value="full-event")
        event = _make_event(
            cid,
            trigger=OrderTrigger.FILL,
            status=OrderStatus.FILLED,
            fill_price=99.9,
            fill_quantity=500,
            fee=3.75,
            message="test fill",
        )

        journal.append(event)
        result = journal.events_for(cid)

        assert len(result) == 1
        r = result[0]
        assert r.client_id == cid
        assert r.trigger == OrderTrigger.FILL
        assert r.status == OrderStatus.FILLED
        assert r.fill_price == 99.9
        assert r.fill_quantity == 500
        assert r.fee == 3.75
        assert r.message == "test fill"
        assert r.timestamp is not None

    def test_event_with_none_fields(self, journal: OrderEventJournal) -> None:
        cid = ClientOrderId(value="minimal-event")
        event = _make_event(cid)

        journal.append(event)
        result = journal.events_for(cid)

        assert len(result) == 1
        r = result[0]
        assert r.fill_price is None
        assert r.fill_quantity == 0
        assert r.fee == 0.0
        assert r.message is None


# ---------------------------------------------------------------------------
# 持久化 — close → reopen 数据不丢失
# ---------------------------------------------------------------------------


class TestSqliteJournalPersistence:
    def test_data_survives_close_reopen(self, tmp_path: object) -> None:
        import pathlib

        from ditto_execution.orders.sqlite_journal import SqliteOrderEventJournal

        db_file = pathlib.Path(str(tmp_path)) / "test_journal.db"  # type: ignore[arg-type]
        cid = ClientOrderId(value="persist-test")
        event = _make_event(
            cid,
            trigger=OrderTrigger.FILL,
            status=OrderStatus.FILLED,
            fill_price=42.0,
            fill_quantity=200,
        )

        # 写入 → 关闭
        j1 = SqliteOrderEventJournal(db_path=str(db_file))
        j1.append(event)
        j1.close()

        # 重新打开 → 数据仍在
        j2 = SqliteOrderEventJournal(db_path=str(db_file))
        events = j2.events_for(cid)
        assert len(events) == 1
        assert events[0].client_id == cid
        assert events[0].fill_price == 42.0
        assert events[0].fill_quantity == 200
        j2.close()

    def test_all_events_survives_close_reopen(self, tmp_path: object) -> None:
        import pathlib

        from ditto_execution.orders.sqlite_journal import SqliteOrderEventJournal

        db_file = pathlib.Path(str(tmp_path)) / "test_journal2.db"  # type: ignore[arg-type]
        id_a = ClientOrderId(value="pa")
        id_b = ClientOrderId(value="pb")
        e1 = _make_event(id_a)
        e2 = _make_event(id_b)

        j1 = SqliteOrderEventJournal(db_path=str(db_file))
        j1.append(e1)
        j1.append(e2)
        j1.close()

        j2 = SqliteOrderEventJournal(db_path=str(db_file))
        all_evts = j2.all_events()
        assert len(all_evts) == 2
        assert all_evts[0].client_id == id_a
        assert all_evts[1].client_id == id_b
        j2.close()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestSqliteJournalContextManager:
    def test_context_manager(self) -> None:
        from ditto_execution.orders.sqlite_journal import SqliteOrderEventJournal

        with SqliteOrderEventJournal(db_path=":memory:") as j:
            cid = ClientOrderId(value="ctx-test")
            j.append(_make_event(cid))
            assert len(j.events_for(cid)) == 1


# ---------------------------------------------------------------------------
# Schema 初始化幂等性
# ---------------------------------------------------------------------------


class TestSqliteJournalSchemaIdempotent:
    def test_reopen_same_db_no_error(self, tmp_path: object) -> None:
        import pathlib

        from ditto_execution.orders.sqlite_journal import SqliteOrderEventJournal

        db_file = pathlib.Path(str(tmp_path)) / "idempotent.db"  # type: ignore[arg-type]

        SqliteOrderEventJournal(db_path=str(db_file)).close()
        SqliteOrderEventJournal(db_path=str(db_file)).close()
