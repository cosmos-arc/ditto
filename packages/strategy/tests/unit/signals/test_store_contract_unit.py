from typing import Protocol

from ditto_strategy.signals.store import SignalStore


def test_signal_store_is_protocol() -> None:
    assert issubclass(SignalStore, Protocol)
