"""Reachable recovery and schema-guard edges for the SQLite pool."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import ditto_platform.foundation.db.sqlite_pool as sqlite_pool_module
import pytest
from ditto_platform.foundation.db import SQLitePool


class _LowWarningThresholdPool(SQLitePool):
    WARN_CONNECTION_COUNT = 1


def test_pool_replaces_a_thread_local_connection_closed_out_of_band(
    tmp_path: Path,
) -> None:
    pool = SQLitePool(str(tmp_path / "state.sqlite"))
    first = pool.get_connection()
    first.close()

    second = pool.get_connection()

    assert second is not first
    assert second.execute("SELECT 1").fetchone() is not None
    pool.close_all()


def test_pool_warns_when_connection_count_reaches_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = MagicMock()
    monkeypatch.setattr(sqlite_pool_module, "logger", log)
    pool = _LowWarningThresholdPool(str(tmp_path / "state.sqlite"))

    pool.get_connection()

    assert log.warning.call_args.kwargs["event"] == "connection_count_warning"
    pool.close_all()


def test_get_schema_fails_closed_without_a_schema_path(tmp_path: Path) -> None:
    pool = SQLitePool(str(tmp_path / "state.sqlite"))

    with pytest.raises(ValueError, match="schema_path is not set"):
        pool._get_schema()
