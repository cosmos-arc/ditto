"""Execution sqlite trade storage ownership tests."""

from __future__ import annotations

import importlib

import pytest


def test_trade_package_owns_sqlite_readers_and_writers() -> None:
    from ditto_execution.storage.sqlite.trade import (
        FillReader,
        FillWriter,
        IntentReader,
        IntentWriter,
        PositionReader,
        PositionWriter,
    )

    assert IntentReader.__module__ == "ditto_execution.storage.sqlite.trade.intents"
    assert IntentWriter.__module__ == "ditto_execution.storage.sqlite.trade.intents"
    assert FillReader.__module__ == "ditto_execution.storage.sqlite.trade.fills"
    assert FillWriter.__module__ == "ditto_execution.storage.sqlite.trade.fills"
    assert PositionReader.__module__ == "ditto_execution.storage.sqlite.trade.positions"
    assert PositionWriter.__module__ == "ditto_execution.storage.sqlite.trade.positions"


def test_legacy_sqlite_storage_package_is_not_importable() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ditto_execution.storage.sqlite.legacy")
