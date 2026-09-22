"""Data specimen evidence persistence tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import orjson
import pytest
from ditto_data.catalog.specimen import (
    DataSpecimen,
    SpecimenReader,
    SpecimenSource,
    SpecimenWriter,
)
from ditto_data.catalog.specimen_store import SQLiteSpecimenStore
from ditto_platform.foundation import SQLiteClient, SQLitePool


def _client(db_path: Path) -> tuple[SQLiteClient, SQLitePool]:
    pool = SQLitePool(str(db_path))
    return SQLiteClient(pool), pool


def _verified(anchor: str, adjudicated_at: datetime) -> DataSpecimen:
    return DataSpecimen(
        category="index_rebalance",
        dataset_id="index_weight",
        anchor=anchor,
        sources=(
            SpecimenSource(
                source="tushare",
                provider_snapshot_id="snapshot:tushare:index_weight:sha256:a",
            ),
        ),
        coverage_from=date(2026, 1, 1),
        coverage_to=date(2026, 6, 30),
        knowable_from=datetime(2026, 7, 1, tzinfo=UTC),
        time_precision="date",
        as_of_counterexample="cutoff before effective date keeps prior constituents",
        license_record_ids=("license:tushare:index_weight:sha256:x",),
        allowed_uses=("display", "exploration", "formal_research"),
        verification_status="verified",
        adjudicated_by="chevy",
        adjudicated_at=adjudicated_at,
    )


class TestSQLiteSpecimenStore:
    def test_append_only_record_survives_reopen(self, tmp_path: Path) -> None:
        db_path = tmp_path / "catalog.sqlite"
        specimen = _verified("000300.SH", datetime(2026, 9, 20, 12, tzinfo=UTC))
        writer_client, writer_pool = _client(db_path)
        try:
            store = SQLiteSpecimenStore(writer_client)
            store.append_specimen(specimen)
            store.append_specimen(specimen)
        finally:
            writer_pool.close()

        reader_client, reader_pool = _client(db_path)
        try:
            store = SQLiteSpecimenStore(reader_client)
            assert store.get_specimen(specimen.specimen_id) == specimen
            assert store.list_specimens(category="index_rebalance") == (specimen,)
            assert store.list_specimens(dataset_id="index_weight") == (specimen,)
            assert isinstance(store, SpecimenReader)
            assert isinstance(store, SpecimenWriter)
        finally:
            reader_pool.close()

    def test_tampered_persisted_payload_conflicts_on_reappend(
        self, tmp_path: Path
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteSpecimenStore(client)
        specimen = _verified("000300.SH", datetime(2026, 9, 20, 12, tzinfo=UTC))
        try:
            store.append_specimen(specimen)
            # Content addressing makes a live conflict impossible; rewrite the
            # persisted payload to different valid content under the same row
            # identity to exercise the fail-closed guard.
            tampered = specimen.to_payload()
            tampered["anchor"] = "000905.SH"
            client.execute(
                "UPDATE data_specimen_records SET payload = ? WHERE specimen_id = ?",
                [orjson.dumps(tampered).decode(), specimen.specimen_id],
            )
            client.commit()
            with pytest.raises(ValueError, match="immutable specimen record"):
                store.append_specimen(specimen)
        finally:
            pool.close()

    def test_latest_adjudication_lists_first(self, tmp_path: Path) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteSpecimenStore(client)
        older = _verified("000300.SH", datetime(2026, 9, 1, tzinfo=UTC))
        newer = _verified("000905.SH", datetime(2026, 9, 20, tzinfo=UTC))
        try:
            store.append_specimen(older)
            store.append_specimen(newer)
            assert store.list_specimens(category="index_rebalance") == (
                newer,
                older,
            )
        finally:
            pool.close()
