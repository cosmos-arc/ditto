"""Remaining fail-closed grammar edge for the generic SQLite client."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_platform.foundation.db import SQLitePool
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient


def test_count_rejects_whitespace_only_where_clause(tmp_path: Path) -> None:
    pool = SQLitePool(str(tmp_path / "state.sqlite"))
    client = SQLiteClient(pool)

    with pytest.raises(ValueError, match="empty clause"):
        client.count("events", "   ", ())

    pool.close_all()
