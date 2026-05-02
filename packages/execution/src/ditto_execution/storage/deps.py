"""Execution domain dependency groups for DI assembly."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_execution.storage.sqlite.legacy import (
    FillReader,
    FillWriter,
    PositionReader,
    PositionWriter,
    SignalReader,
    SignalWriter,
)


@dataclass(frozen=True)
class ExecutionReaders:
    """Execution domain read dependencies."""

    signal: SignalReader
    fill: FillReader
    position: PositionReader


@dataclass(frozen=True)
class ExecutionWriters:
    """Execution domain write dependencies."""

    signal: SignalWriter
    fill: FillWriter
    position: PositionWriter


__all__ = ["ExecutionReaders", "ExecutionWriters"]
