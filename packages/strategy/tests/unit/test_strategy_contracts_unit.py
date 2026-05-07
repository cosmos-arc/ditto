"""Strategy contracts type-checking tests."""

from typing import Protocol

from ditto_strategy.contracts import SignalProvider


def test_signal_provider_is_protocol() -> None:
    assert issubclass(SignalProvider, Protocol)


def test_signal_provider_is_runtime_checkable() -> None:
    assert isinstance(42, SignalProvider) is False
