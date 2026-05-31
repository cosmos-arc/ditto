"""Tests for SQLite-backed derived catalog readers."""

from pathlib import Path

import pytest
from ditto_features.models.derived import DerivedRunRecord
from ditto_features.storage.sqlite.derived import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)
from ditto_platform.foundation import SQLiteClient, SQLitePool


@pytest.fixture
def sqlite_client(tmp_path: Path):
    """Provide a SQLite client initialized with the production schema."""
    schema_path = (
        Path(__file__).resolve().parents[7]
        / "packages"
        / "data"
        / "src"
        / "ditto_data"
        / "scripts"
        / "schema.sql"
    )
    pool = SQLitePool(str(tmp_path / "derived.sqlite"), schema_path=schema_path)
    pool.init_schema()
    yield SQLiteClient(pool)
    pool.close()


def _run_record(
    *,
    run_id: str,
    trigger: str,
    created_at: str = "2026-03-14T12:00:00+08:00",
) -> DerivedRunRecord:
    return DerivedRunRecord(
        run_id=run_id,
        derived_id="factor.alpha_repair",
        version=3,
        mode="full",
        trigger=trigger,
        request_start="2026-03-11",
        request_end="2026-03-11",
        compute_start="2026-03-11",
        compute_end="2026-03-11",
        source_snapshot_id=None,
        status="SUCCESS",
        rows_written=1,
        partitions_written=("2026-03-11",),
        error_message=None,
        created_at=created_at,
        started_at=created_at,
        finished_at=created_at,
    )


class TestSQLiteDerivedCatalogReader:
    """Tests for derived catalog read ordering."""

    def test_latest_run_uses_last_persisted_row_when_timestamps_tie(
        self,
        sqlite_client,
    ) -> None:
        """Random run ids must not decide latest-run semantics."""
        writer = SQLiteDerivedCatalogWriter(sqlite_client)
        reader = SQLiteDerivedCatalogReader(sqlite_client)

        writer.write_run(_run_record(run_id="drv-z-scheduled", trigger="scheduled"))
        writer.write_run(_run_record(run_id="drv-a-cascade", trigger="cascade"))

        latest = reader.get_latest_run("factor.alpha_repair", 3)

        assert latest is not None
        assert latest.run_id == "drv-a-cascade"
        assert latest.trigger == "cascade"
