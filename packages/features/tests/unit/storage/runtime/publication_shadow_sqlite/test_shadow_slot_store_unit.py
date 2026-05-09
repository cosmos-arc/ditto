"""Tests for SQLite-backed derived shadow slot stores."""

from pathlib import Path

import pytest
from ditto_features.publication_safety_records import DerivedShadowSlotRecord
from ditto_features.storage.runtime.publication_shadow_sqlite import (
    SQLiteDerivedShadowSlotReader,
    SQLiteDerivedShadowSlotWriter,
)
from ditto_platform.foundation import SQLiteClient, SQLitePool


@pytest.fixture
def sqlite_client(tmp_path: Path):
    """Provide a SQLite client with the minimal shadow slot schema."""
    pool = SQLitePool(str(tmp_path / "test.sqlite"))
    client = SQLiteClient(pool)
    client.execute(
        """
        CREATE TABLE derived_shadow_slot (
            derived_id TEXT PRIMARY KEY,
            candidate_version INTEGER NOT NULL,
            baseline_version INTEGER,
            activated_at TEXT NOT NULL,
            disabled_at TEXT
        )
        """
    )
    client.commit()
    yield client
    pool.close()


class TestSQLiteDerivedShadowSlotStore:
    """Tests for shadow slot SQLite reader/writer."""

    def test_roundtrip_and_disable_active_slot(self, sqlite_client) -> None:
        """Active slots should be readable until they are explicitly disabled."""
        reader = SQLiteDerivedShadowSlotReader(sqlite_client)
        writer = SQLiteDerivedShadowSlotWriter(sqlite_client)
        record = DerivedShadowSlotRecord(
            derived_id="factor.alpha_simple",
            candidate_version=3,
            baseline_version=2,
            activated_at="2026-03-14T12:00:00+08:00",
            disabled_at=None,
        )

        writer.write_slot(record)

        assert reader.read_slot("factor.alpha_simple") == record
        assert reader.read_active_slot("factor.alpha_simple") == record

        writer.disable_slot(
            derived_id="factor.alpha_simple",
            disabled_at="2026-03-14T12:30:00+08:00",
        )

        disabled = reader.read_slot("factor.alpha_simple")
        assert disabled is not None
        assert disabled.disabled_at == "2026-03-14T12:30:00+08:00"
        assert reader.read_active_slot("factor.alpha_simple") is None

    def test_write_slot_replaces_existing_candidate_for_same_derived_id(
        self,
        sqlite_client,
    ) -> None:
        """Each derived id should keep at most one active candidate slot."""
        reader = SQLiteDerivedShadowSlotReader(sqlite_client)
        writer = SQLiteDerivedShadowSlotWriter(sqlite_client)
        writer.write_slot(
            DerivedShadowSlotRecord(
                derived_id="factor.alpha_simple",
                candidate_version=3,
                baseline_version=2,
                activated_at="2026-03-14T12:00:00+08:00",
                disabled_at=None,
            )
        )

        writer.write_slot(
            DerivedShadowSlotRecord(
                derived_id="factor.alpha_simple",
                candidate_version=4,
                baseline_version=3,
                activated_at="2026-03-14T13:00:00+08:00",
                disabled_at=None,
            )
        )

        assert reader.read_active_slot(
            "factor.alpha_simple"
        ) == DerivedShadowSlotRecord(
            derived_id="factor.alpha_simple",
            candidate_version=4,
            baseline_version=3,
            activated_at="2026-03-14T13:00:00+08:00",
            disabled_at=None,
        )
