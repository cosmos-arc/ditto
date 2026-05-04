"""SQLite storage for execution trade intents, fills, and positions."""

from importlib import import_module
from typing import TYPE_CHECKING

from ditto_execution.storage.sqlite.trade.fills import FILLS_DDL, FillReader, FillWriter
from ditto_execution.storage.sqlite.trade.intents import (
    INTENTS_DDL,
    IntentReader,
    IntentWriter,
)
from ditto_execution.storage.sqlite.trade.positions import (
    POSITIONS_DDL,
    PositionReader,
    PositionWriter,
)

if TYPE_CHECKING:
    from ditto_execution.storage.sqlite.trade.service import TradeService

__all__ = [
    "FILLS_DDL",
    "INTENTS_DDL",
    "POSITIONS_DDL",
    "FillReader",
    "FillWriter",
    "IntentReader",
    "IntentWriter",
    "PositionReader",
    "PositionWriter",
    "TradeService",
]


def __getattr__(name: str) -> object:
    """Lazily expose TradeService without creating a deps import cycle."""
    if name == "TradeService":
        module = import_module("ditto_execution.storage.sqlite.trade.service")
        return module.__dict__["TradeService"]
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
