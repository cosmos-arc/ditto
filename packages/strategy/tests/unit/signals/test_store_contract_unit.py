from typing import Protocol

from ditto_strategy.signals.models import SignalRecord
from ditto_strategy.signals.store import SignalStore


def test_signal_store_is_protocol() -> None:
    assert issubclass(SignalStore, Protocol)


def test_signal_record_captures_strategy_output() -> None:
    record = SignalRecord(
        signal_id="sig-1",
        strategy_id="trend",
        run_id="run-1",
        trade_date="2026-05-05",
        instrument_id=510300,
        direction="buy",
        strength=0.75,
        score=0.61,
    )

    assert record.instrument_id == 510300
    assert record.metadata == {}


def test_signal_store_contract_is_actionable() -> None:
    assert hasattr(SignalStore, "save_signal")
    assert hasattr(SignalStore, "list_signals")
