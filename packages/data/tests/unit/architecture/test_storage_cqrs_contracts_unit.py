"""Architecture tests for storage CQRS method ownership."""

from __future__ import annotations

import inspect

from ditto_data.storage.metadata.fee_schedule_reader import (
    SQLiteFeeScheduleReader,
)
from ditto_data.storage.metadata.fee_schedule_writer import (
    SQLiteFeeScheduleWriter,
)
from ditto_data.storage.metadata.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)
from ditto_data.storage.metadata.strategy_run_store import (
    SQLiteStrategyRunReader,
    SQLiteStrategyRunWriter,
)
from ditto_data.storage.metadata.strategy_spec_store import (
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)
from ditto_data.storage.metadata.trading_rule_reader import SQLiteTradingRuleReader
from ditto_data.storage.metadata.trading_rule_writer import SQLiteTradingRuleWriter

_READER_METHOD_PREFIXES = ("get", "list", "read", "count")

_WRITE_PREFIXES = ("write", "save", "delete", "update", "load")

_READER_CLASSES = (
    SQLiteStrategySpecReader,
    SQLiteFeeScheduleReader,
    SQLiteTradingRuleReader,
    SQLiteStrategyArtifactReader,
    SQLiteStrategyRunReader,
)

_WRITER_CLASSES = (
    SQLiteStrategySpecWriter,
    SQLiteFeeScheduleWriter,
    SQLiteTradingRuleWriter,
    SQLiteStrategyArtifactWriter,
    SQLiteStrategyRunWriter,
)


def _public_methods(cls: type[object]) -> set[str]:
    return {
        name
        for name, _ in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_metadata_readers_do_not_expose_write_or_schema_methods() -> None:
    for cls in _READER_CLASSES:
        methods = _public_methods(cls)
        forbidden = {
            name
            for name in methods
            if name == "init_schema" or name.startswith(_WRITE_PREFIXES)
        }
        msg = f"{cls.__name__} has forbidden write methods: {forbidden}"
        assert forbidden == set(), msg


def test_metadata_writers_do_not_expose_query_methods() -> None:
    for cls in _WRITER_CLASSES:
        methods = _public_methods(cls)
        forbidden = {
            name for name in methods if name.startswith(_READER_METHOD_PREFIXES)
        }
        msg = f"{cls.__name__} has forbidden query methods: {forbidden}"
        assert forbidden == set(), msg
