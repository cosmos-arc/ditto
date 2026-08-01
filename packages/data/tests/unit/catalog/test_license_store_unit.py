"""Dataset/provider license ledger persistence tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ditto_data.catalog.license import (
    DatasetLicenseDraft,
    DatasetLicenseReader,
    DatasetLicenseRecord,
    DatasetLicenseWriter,
)
from ditto_data.catalog.license_store import SQLiteDatasetLicenseStore
from ditto_platform.foundation import SQLiteClient, SQLitePool


def _client(db_path: Path) -> tuple[SQLiteClient, SQLitePool]:
    pool = SQLitePool(str(db_path))
    return SQLiteClient(pool), pool


def _record() -> DatasetLicenseRecord:
    return DatasetLicenseRecord.create(
        DatasetLicenseDraft(
            dataset_id="stock_daily",
            source="tushare",
            terms_version="2026-07",
            effective_from=date(2026, 7, 1),
            effective_to=None,
            local_cache="allowed",
            derivative_compute="allowed",
            display="restricted",
            redistribution="prohibited",
            notes="Internal single-operator use only.",
            reviewed_by="data-owner",
            reviewed_at=datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
        )
    )


class TestSQLiteDatasetLicenseStore:
    def test_append_only_record_survives_reopen(self, tmp_path: Path) -> None:
        db_path = tmp_path / "catalog.sqlite"
        record = _record()
        writer_client, writer_pool = _client(db_path)
        try:
            store = SQLiteDatasetLicenseStore(writer_client)
            store.append_license(record)
            store.append_license(record)
        finally:
            writer_pool.close()

        reader_client, reader_pool = _client(db_path)
        try:
            store = SQLiteDatasetLicenseStore(reader_client)
            assert store.get_license(record.record_id) == record
            assert store.list_licenses(dataset_id="stock_daily", source="tushare") == (
                record,
            )
            assert isinstance(store, DatasetLicenseReader)
            assert isinstance(store, DatasetLicenseWriter)
        finally:
            reader_pool.close()

    def test_rejects_mutation_of_existing_record(self, tmp_path: Path) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteDatasetLicenseStore(client)
        record = _record()
        mutated = replace(record, notes="Changed after review")

        try:
            store.append_license(record)

            with pytest.raises(ValueError, match="immutable license record"):
                store.append_license(mutated)
        finally:
            pool.close()

    def test_semantic_retry_preserves_original_review_timestamp(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteDatasetLicenseStore(client)
        record = _record()
        retry = replace(
            record,
            reviewed_at=datetime(2026, 7, 18, 10, 0, tzinfo=UTC),
        )

        try:
            store.append_license(record)
            store.append_license(retry)

            assert store.get_license(record.record_id) == record
            assert store.list_licenses() == (record,)
        finally:
            pool.close()


class TestDatasetLicenseRecordValidation:
    @pytest.mark.parametrize(
        "notes",
        [
            "token=abc123",
            "api_key: abc123",
            "client_secret is abc123",
            "password=abc123",
        ],
    )
    def test_rejects_secret_like_notes(self, notes: str) -> None:
        with pytest.raises(ValueError, match="secret"):
            DatasetLicenseRecord.create(
                DatasetLicenseDraft(
                    dataset_id="stock_daily",
                    source="tushare",
                    terms_version="2026-07",
                    effective_from=date(2026, 7, 1),
                    effective_to=None,
                    local_cache="allowed",
                    derivative_compute="allowed",
                    display="restricted",
                    redistribution="prohibited",
                    notes=notes,
                    reviewed_by="data-owner",
                    reviewed_at=datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
                )
            )

    def test_rejects_invalid_effective_interval(self) -> None:
        with pytest.raises(ValueError, match="effective_to"):
            DatasetLicenseRecord.create(
                DatasetLicenseDraft(
                    dataset_id="stock_daily",
                    source="tushare",
                    terms_version="2026-07",
                    effective_from=date(2026, 7, 2),
                    effective_to=date(2026, 7, 1),
                    local_cache="allowed",
                    derivative_compute="allowed",
                    display="restricted",
                    redistribution="prohibited",
                    notes="Internal use.",
                    reviewed_by="data-owner",
                    reviewed_at=datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
                )
            )
