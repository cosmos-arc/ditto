"""Execution domain dependency groups for DI assembly."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_execution.storage.sqlite.trade.fills import FillReader, FillWriter
from ditto_execution.storage.sqlite.trade.intents import IntentReader, IntentWriter
from ditto_execution.storage.sqlite.trade.positions import (
    PositionReader,
    PositionWriter,
)


@dataclass(frozen=True)
class ExecutionReaders:
    """Execution domain read dependencies."""

    intent: IntentReader
    fill: FillReader
    position: PositionReader


@dataclass(frozen=True)
class ExecutionWriters:
    """Execution domain write dependencies."""

    intent: IntentWriter
    fill: FillWriter
    position: PositionWriter


__all__ = ["ExecutionReaders", "ExecutionWriters"]
