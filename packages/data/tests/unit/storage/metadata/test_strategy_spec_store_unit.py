"""Unit tests for SQLiteStrategySpecReader / SQLiteStrategySpecWriter."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_platform.foundation import SQLitePool
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.strategy_spec_store import (
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)


@pytest.fixture
def pool(tmp_path: Path) -> SQLitePool:
    """Create a SQLitePool backed by a temporary file."""
    p = SQLitePool(str(tmp_path / "test.db"))
    yield p
    p.close()


@pytest.fixture
def writer(pool: SQLitePool) -> SQLiteStrategySpecWriter:
    return SQLiteStrategySpecWriter(pool)


@pytest.fixture
def reader(pool: SQLitePool) -> SQLiteStrategySpecReader:
    return SQLiteStrategySpecReader(pool)


def _make_spec(
    strategy_id: str = "strat-001",
    name: str = "Test Strategy",
    spec_json: dict[str, object] | None = None,
    version: int = 1,
    status: str = "draft",
    created_at: str = "2026-03-24T10:00:00+08:00",
    updated_at: str = "2026-03-24T10:00:00+08:00",
    tags: tuple[str, ...] = (),
) -> StrategySpecRecord:
    return StrategySpecRecord(
        strategy_id=strategy_id,
        name=name,
        spec_json=spec_json or {"type": "etf_momentum", "params": {"lookback": 20}},
        version=version,
        status=status,
        created_at=created_at,
        updated_at=updated_at,
        tags=tags,
    )


class TestSQLiteStrategySpecWriter:
    """Tests for SQLiteStrategySpecWriter."""

    def test_init_schema_is_idempotent(self, writer: SQLiteStrategySpecWriter) -> None:
        """Calling init_schema twice should not raise."""
        writer.init_schema()
        writer.init_schema()  # second call should be safe

    def test_save_inserts_record(self, writer: SQLiteStrategySpecWriter) -> None:
        """save() should persist a new record."""
        writer.init_schema()
        record = _make_spec()
        writer.save(record)

    def test_save_upsert_replaces_same_key(
        self,
        writer: SQLiteStrategySpecWriter,
        reader: SQLiteStrategySpecReader,
    ) -> None:
        """INSERT OR REPLACE should overwrite existing (strategy_id, version)."""
        writer.init_schema()
        writer.save(_make_spec(name="Original"))

        updated = _make_spec(name="Updated")
        writer.save(updated)

        result = reader.get_spec("strat-001", version=1)
        assert result is not None
        assert result.name == "Updated"


class TestSQLiteStrategySpecReader:
    """Tests for SQLiteStrategySpecReader."""

    def test_get_spec_returns_none_for_missing(
        self, writer: SQLiteStrategySpecWriter, reader: SQLiteStrategySpecReader
    ) -> None:
        """get_spec() returns None when no matching record exists."""
        writer.init_schema()
        assert reader.get_spec("nonexistent") is None
        assert reader.get_spec("nonexistent", version=1) is None

    def test_get_spec_by_exact_version(
        self, writer: SQLiteStrategySpecWriter, reader: SQLiteStrategySpecReader
    ) -> None:
        """get_spec() with explicit version returns that version."""
        writer.init_schema()
        writer.save(_make_spec(version=1))
        writer.save(_make_spec(version=2, name="V2"))

        result = reader.get_spec("strat-001", version=1)
        assert result is not None
        assert result.version == 1
        assert result.name == "Test Strategy"

        result_v2 = reader.get_spec("strat-001", version=2)
        assert result_v2 is not None
        assert result_v2.version == 2
        assert result_v2.name == "V2"

    def test_get_spec_without_version_returns_latest(
        self, writer: SQLiteStrategySpecWriter, reader: SQLiteStrategySpecReader
    ) -> None:
        """get_spec() with version=None returns the record with MAX(version)."""
        writer.init_schema()
        writer.save(_make_spec(version=1, name="V1"))
        writer.save(_make_spec(version=2, name="V2"))
        writer.save(_make_spec(version=3, name="V3"))

        result = reader.get_spec("strat-001")
        assert result is not None
        assert result.version == 3
        assert result.name == "V3"

    def test_get_spec_preserves_spec_json(
        self, writer: SQLiteStrategySpecWriter, reader: SQLiteStrategySpecReader
    ) -> None:
        """spec_json should roundtrip through serialization."""
        writer.init_schema()
        spec = _make_spec(
            spec_json={
                "type": "etf_momentum",
                "params": {"lookback": 20, "threshold": 0.5},
            }
        )
        writer.save(spec)

        result = reader.get_spec("strat-001")
        assert result is not None
        assert result.spec_json == spec.spec_json

    def test_get_spec_preserves_tags(
        self, writer: SQLiteStrategySpecWriter, reader: SQLiteStrategySpecReader
    ) -> None:
        """tags tuple should roundtrip as a tuple."""
        writer.init_schema()
        writer.save(_make_spec(tags=("momentum", "etf")))

        result = reader.get_spec("strat-001")
        assert result is not None
        assert result.tags == ("momentum", "etf")

    def test_list_specs_returns_latest_version_per_strategy(
        self, writer: SQLiteStrategySpecWriter, reader: SQLiteStrategySpecReader
    ) -> None:
        """list_specs() should return one record per strategy_id (latest version)."""
        writer.init_schema()
        writer.save(_make_spec(strategy_id="strat-a", version=1))
        writer.save(_make_spec(strategy_id="strat-a", version=2))
        writer.save(_make_spec(strategy_id="strat-b", version=1))

        result = reader.list_specs()
        assert len(result) == 2
        ids = {r.strategy_id for r in result}
        assert ids == {"strat-a", "strat-b"}
        for r in result:
            if r.strategy_id == "strat-a":
                assert r.version == 2

    def test_list_specs_empty(
        self,
        writer: SQLiteStrategySpecWriter,
        reader: SQLiteStrategySpecReader,
    ) -> None:
        """list_specs() returns empty list when no records exist."""
        writer.init_schema()
        assert reader.list_specs() == []

    def test_list_versions_returns_all_for_strategy(
        self, writer: SQLiteStrategySpecWriter, reader: SQLiteStrategySpecReader
    ) -> None:
        """list_versions() returns all versions, ordered by version DESC."""
        writer.init_schema()
        writer.save(_make_spec(strategy_id="strat-x", version=1, name="V1"))
        writer.save(_make_spec(strategy_id="strat-x", version=2, name="V2"))
        writer.save(_make_spec(strategy_id="strat-x", version=3, name="V3"))

        result = reader.list_versions("strat-x")
        assert len(result) == 3
        assert [r.version for r in result] == [3, 2, 1]

    def test_list_versions_empty_for_missing(
        self, writer: SQLiteStrategySpecWriter, reader: SQLiteStrategySpecReader
    ) -> None:
        """list_versions() returns empty list for unknown strategy_id."""
        writer.init_schema()
        assert reader.list_versions("nonexistent") == []

    def test_list_versions_ignores_other_strategies(
        self, writer: SQLiteStrategySpecWriter, reader: SQLiteStrategySpecReader
    ) -> None:
        """list_versions() only returns versions for the requested strategy."""
        writer.init_schema()
        writer.save(_make_spec(strategy_id="strat-a", version=1))
        writer.save(_make_spec(strategy_id="strat-b", version=1))

        result = reader.list_versions("strat-a")
        assert len(result) == 1
        assert result[0].strategy_id == "strat-a"


class TestSQLiteStrategySpecWriterUpdateStatus:
    """Tests for update_status()."""

    def test_update_status_success(
        self, writer: SQLiteStrategySpecWriter, reader: SQLiteStrategySpecReader
    ) -> None:
        """update_status() should change the status field."""
        writer.init_schema()
        writer.save(_make_spec())

        ok = writer.update_status("strat-001", 1, "published")
        assert ok is True

        result = reader.get_spec("strat-001")
        assert result is not None
        assert result.status == "published"

    def test_update_status_missing_returns_false(
        self,
        writer: SQLiteStrategySpecWriter,
    ) -> None:
        """update_status() returns False when no matching row exists."""
        writer.init_schema()
        ok = writer.update_status("nonexistent", 99, "published")
        assert ok is False
