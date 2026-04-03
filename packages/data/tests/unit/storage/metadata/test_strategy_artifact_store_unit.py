"""Unit tests for SQLiteStrategyArtifactReader / SQLiteStrategyArtifactWriter."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_data.models.strategy import ArtifactKind, StrategyArtifactRecord
from ditto_data.storage.metadata.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)
from ditto_infra.foundation import SQLitePool


@pytest.fixture
def pool(tmp_path: Path) -> SQLitePool:
    """Create a SQLitePool backed by a temporary file."""
    p = SQLitePool(str(tmp_path / "test.db"))
    yield p
    p.close()


@pytest.fixture
def writer(pool: SQLitePool) -> SQLiteStrategyArtifactWriter:
    return SQLiteStrategyArtifactWriter(pool)


@pytest.fixture
def reader(pool: SQLitePool) -> SQLiteStrategyArtifactReader:
    return SQLiteStrategyArtifactReader(pool)


def _make_artifact(
    artifact_id: str = "art-001",
    strategy_id: str = "strat-001",
    run_id: str = "run-001",
    artifact_type: ArtifactKind = ArtifactKind.BACKTEST_REPORT,
    file_path: str = "reports/run-001/report.parquet",
    metadata: dict[str, object] | None = None,
    status: str = "active",
    created_at: str = "2026-03-24T10:00:00+08:00",
) -> StrategyArtifactRecord:
    return StrategyArtifactRecord(
        artifact_id=artifact_id,
        strategy_id=strategy_id,
        run_id=run_id,
        artifact_type=artifact_type,
        file_path=file_path,
        metadata=metadata or {"rows": 100},
        status=status,
        created_at=created_at,
    )


class TestSQLiteStrategyArtifactWriter:
    """Tests for SQLiteStrategyArtifactWriter."""

    def test_init_schema_is_idempotent(
        self,
        writer: SQLiteStrategyArtifactWriter,
    ) -> None:
        """Calling init_schema twice should not raise."""
        writer.init_schema()
        writer.init_schema()

    def test_save_inserts_record(self, writer: SQLiteStrategyArtifactWriter) -> None:
        """save() should persist a new record."""
        writer.init_schema()
        record = _make_artifact()
        writer.save(record)

    def test_save_upsert_replaces_same_key(
        self,
        writer: SQLiteStrategyArtifactWriter,
        reader: SQLiteStrategyArtifactReader,
    ) -> None:
        """INSERT OR REPLACE should overwrite existing artifact_id."""
        writer.init_schema()
        writer.save(_make_artifact(file_path="old/path.parquet"))

        updated = _make_artifact(file_path="new/path.parquet")
        writer.save(updated)

        result = reader.get("art-001")
        assert result is not None
        assert result.file_path == "new/path.parquet"


class TestSQLiteStrategyArtifactReader:
    """Tests for SQLiteStrategyArtifactReader."""

    def test_get_returns_none_for_missing(
        self,
        writer: SQLiteStrategyArtifactWriter,
        reader: SQLiteStrategyArtifactReader,
    ) -> None:
        """get() returns None when no matching record exists."""
        writer.init_schema()
        assert reader.get("nonexistent") is None

    def test_get_returns_saved_record(
        self,
        writer: SQLiteStrategyArtifactWriter,
        reader: SQLiteStrategyArtifactReader,
    ) -> None:
        """get() returns the saved record with correct fields."""
        writer.init_schema()
        record = _make_artifact(
            artifact_type=ArtifactKind.NAV,
            file_path="nav/run-001.nav",
            metadata={"points": 252},
            created_at="2026-03-24T12:00:00+08:00",
        )
        writer.save(record)

        result = reader.get("art-001")
        assert result is not None
        assert result == record
        assert result.artifact_type is ArtifactKind.NAV
        assert result.file_path == "nav/run-001.nav"
        assert result.metadata == {"points": 252}

    def test_get_preserves_artifact_type(
        self,
        writer: SQLiteStrategyArtifactWriter,
        reader: SQLiteStrategyArtifactReader,
    ) -> None:
        """artifact_type StrEnum should roundtrip correctly."""
        writer.init_schema()
        for kind in ArtifactKind:
            writer.save(
                _make_artifact(
                    artifact_id=f"art-{kind.value}",
                    artifact_type=kind,
                )
            )

        for kind in ArtifactKind:
            result = reader.get(f"art-{kind.value}")
            assert result is not None
            assert result.artifact_type is kind

    def test_list_all_returns_all_records(
        self,
        writer: SQLiteStrategyArtifactWriter,
        reader: SQLiteStrategyArtifactReader,
    ) -> None:
        """list_all() returns all saved records ordered by created_at DESC."""
        writer.init_schema()
        writer.save(
            _make_artifact(artifact_id="art-001", created_at="t1"),
        )
        writer.save(
            _make_artifact(artifact_id="art-002", created_at="t2"),
        )
        writer.save(
            _make_artifact(artifact_id="art-003", created_at="t0"),
        )

        result = reader.list_all()
        assert len(result) == 3
        assert [r.artifact_id for r in result] == ["art-002", "art-001", "art-003"]

    def test_list_all_empty(
        self,
        writer: SQLiteStrategyArtifactWriter,
        reader: SQLiteStrategyArtifactReader,
    ) -> None:
        """list_all() returns empty list when no records exist."""
        writer.init_schema()
        assert reader.list_all() == []

    def test_list_by_strategy_filters_correctly(
        self,
        writer: SQLiteStrategyArtifactWriter,
        reader: SQLiteStrategyArtifactReader,
    ) -> None:
        """list_by_strategy() returns only records for the given strategy_id."""
        writer.init_schema()
        writer.save(
            _make_artifact(
                artifact_id="art-a1",
                strategy_id="strat-a",
                created_at="t1",
            ),
        )
        writer.save(
            _make_artifact(
                artifact_id="art-a2",
                strategy_id="strat-a",
                created_at="t2",
            ),
        )
        writer.save(
            _make_artifact(
                artifact_id="art-b1",
                strategy_id="strat-b",
                created_at="t3",
            ),
        )

        result = reader.list_by_strategy("strat-a")
        assert len(result) == 2
        assert all(r.strategy_id == "strat-a" for r in result)
        assert [r.artifact_id for r in result] == ["art-a2", "art-a1"]

    def test_list_by_strategy_empty_for_missing(
        self,
        writer: SQLiteStrategyArtifactWriter,
        reader: SQLiteStrategyArtifactReader,
    ) -> None:
        """list_by_strategy() returns empty list for unknown strategy_id."""
        writer.init_schema()
        assert reader.list_by_strategy("nonexistent") == []

    def test_list_by_strategy_ordered_by_created_at_desc(
        self,
        writer: SQLiteStrategyArtifactWriter,
        reader: SQLiteStrategyArtifactReader,
    ) -> None:
        """list_by_strategy() should order results by created_at DESC."""
        writer.init_schema()
        writer.save(
            _make_artifact(
                artifact_id="art-1",
                strategy_id="s1",
                created_at="t1",
            ),
        )
        writer.save(
            _make_artifact(
                artifact_id="art-2",
                strategy_id="s1",
                created_at="t3",
            ),
        )
        writer.save(
            _make_artifact(
                artifact_id="art-3",
                strategy_id="s1",
                created_at="t2",
            ),
        )

        result = reader.list_by_strategy("s1")
        assert [r.artifact_id for r in result] == ["art-2", "art-3", "art-1"]


class TestSQLiteStrategyArtifactWriterUpdateStatus:
    """Tests for update_status()."""

    def test_update_status_success(
        self,
        writer: SQLiteStrategyArtifactWriter,
        reader: SQLiteStrategyArtifactReader,
    ) -> None:
        """update_status() should change the status field."""
        writer.init_schema()
        writer.save(_make_artifact())

        ok = writer.update_status("art-001", "archived")
        assert ok is True

        result = reader.get("art-001")
        assert result is not None
        assert result.status == "archived"

    def test_update_status_missing_returns_false(
        self,
        writer: SQLiteStrategyArtifactWriter,
    ) -> None:
        """update_status() returns False when no matching row exists."""
        writer.init_schema()
        ok = writer.update_status("nonexistent", "archived")
        assert ok is False
