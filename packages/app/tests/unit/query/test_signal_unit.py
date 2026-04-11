"""Tests for SignalQueryFacade — 信号查询门面."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_app.query.signal import SignalQueryFacade
from ditto_data.models.trade import TradeIntentRecord


def _make_intent_record(
    intent_id: str = "intent-1",
    strategy_id: str = "s-1",
    signal_date: str = "2024-01-15",
    instrument_id: int = 510300,
    direction: str = "buy",
    target_weight: float = 0.3,
    current_weight: float = 0.1,
    delta_weight: float = 0.2,
    quantity: int | None = 1000,
    status: str = "pending",
) -> TradeIntentRecord:
    return TradeIntentRecord(
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
    )


class TestGetLatestIntents:
    """SignalQueryFacade.get_latest_intents — 返回最新信号日期的 intents."""

    def test_returns_intents_for_latest_date(self) -> None:
        service = MagicMock(spec=["list_intents"])
        records = [
            _make_intent_record("i-1", signal_date="2024-01-14"),
            _make_intent_record("i-2", signal_date="2024-01-15"),
            _make_intent_record("i-3", signal_date="2024-01-15"),
        ]
        service.list_intents.return_value = records
        facade = SignalQueryFacade(trade_service=service)

        result = facade.get_latest_intents("s-1")

        assert len(result) == 2
        assert all(r.signal_date == "2024-01-15" for r in result)
        service.list_intents.assert_called_once_with(
            strategy_id="s-1",
            signal_date=None,
            status=None,
        )

    def test_returns_empty_when_no_intents(self) -> None:
        service = MagicMock(spec=["list_intents"])
        service.list_intents.return_value = []
        facade = SignalQueryFacade(trade_service=service)

        result = facade.get_latest_intents("s-1")

        assert result == []

    def test_maps_records_to_dto(self) -> None:
        service = MagicMock(spec=["list_intents"])
        records = [_make_intent_record("i-1", signal_date="2024-01-15")]
        service.list_intents.return_value = records
        facade = SignalQueryFacade(trade_service=service)

        result = facade.get_latest_intents("s-1")

        assert len(result) == 1
        assert result[0].intent_id == "i-1"
        assert result[0].strategy_id == "s-1"
        assert result[0].instrument_id == 510300

    def test_single_date_returns_all(self) -> None:
        service = MagicMock(spec=["list_intents"])
        records = [
            _make_intent_record("i-1", signal_date="2024-01-10"),
        ]
        service.list_intents.return_value = records
        facade = SignalQueryFacade(trade_service=service)

        result = facade.get_latest_intents("s-1")

        assert len(result) == 1
        assert result[0].signal_date == "2024-01-10"


class TestGetIntentsByDate:
    """SignalQueryFacade.get_intents_by_date — 返回指定日期的 intents."""

    def test_returns_intents_for_given_date(self) -> None:
        service = MagicMock(spec=["list_intents"])
        records = [
            _make_intent_record("i-1", signal_date="2024-01-15"),
            _make_intent_record("i-2", signal_date="2024-01-15"),
        ]
        service.list_intents.return_value = records
        facade = SignalQueryFacade(trade_service=service)

        result = facade.get_intents_by_date("s-1", "2024-01-15")

        assert len(result) == 2
        service.list_intents.assert_called_once_with(
            strategy_id="s-1",
            signal_date="2024-01-15",
            status=None,
        )

    def test_returns_empty_when_no_intents(self) -> None:
        service = MagicMock(spec=["list_intents"])
        service.list_intents.return_value = []
        facade = SignalQueryFacade(trade_service=service)

        result = facade.get_intents_by_date("s-1", "2024-01-15")

        assert result == []

    def test_maps_records_to_dto(self) -> None:
        service = MagicMock(spec=["list_intents"])
        record = _make_intent_record(
            "i-1",
            direction="sell",
            target_weight=0.0,
            current_weight=0.2,
            delta_weight=-0.2,
        )
        service.list_intents.return_value = [record]
        facade = SignalQueryFacade(trade_service=service)

        result = facade.get_intents_by_date("s-1", "2024-01-15")

        assert len(result) == 1
        dto = result[0]
        assert dto.intent_id == "i-1"
        assert dto.direction == "sell"
        assert dto.target_weight == 0.0
        assert dto.delta_weight == -0.2
