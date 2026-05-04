"""Execution domain dependency groups for DI assembly."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_execution.storage.sqlite.trade import (
    FillReader,
    FillWriter,
    IntentReader,
    IntentWriter,
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
