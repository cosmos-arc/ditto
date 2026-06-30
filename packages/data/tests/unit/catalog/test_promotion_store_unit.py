"""Unit tests for persistent dataset promotion evidence storage."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ditto_data.catalog.promotion import (
    DatasetMaturityPromotion,
    DatasetMaturityPromotionEvent,
    DatasetMaturityPromotionHistoryReader,
    DatasetMaturityPromotionReader,
    DatasetMaturityPromotionRevoker,
    DatasetMaturityPromotionWriter,
    DatasetPromotionEvidence,
    DatasetPromotionEvidenceReader,
    DatasetPromotionEvidenceWriter,
)
from ditto_data.catalog.promotion_store import (
    SQLiteDatasetMaturityPromotionStore,
    SQLiteDatasetPromotionEvidenceStore,
)
from ditto_platform.foundation import SQLiteClient, SQLitePool


def _client(db_path: Path) -> tuple[SQLiteClient, SQLitePool]:
    pool = SQLitePool(str(db_path))
    return SQLiteClient(pool), pool


def _evidence(
    criterion: str = "complete PIT/replay coverage for the dataset",
    *,
    evidence_uri: str = "ditto://evidence/stock_daily/pit-replay",
    passed: bool = True,
) -> DatasetPromotionEvidence:
    return DatasetPromotionEvidence(
        criterion=criterion,
        evidence_uri=evidence_uri,
        approved_by="architecture-review",
        passed=passed,
        notes="reviewed during maturity promotion audit",
        reviewed_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )


class TestSQLiteDatasetPromotionEvidenceStore:
    """Promotion evidence must be durable and scoped by dataset."""

    def test_evidence_survives_reopened_sqlite_connection(self, tmp_path: Path) -> None:
        db_path = tmp_path / "catalog.sqlite"
        evidence = _evidence()

        writer_client, writer_pool = _client(db_path)
        try:
            SQLiteDatasetPromotionEvidenceStore(writer_client).upsert_dataset_evidence(
                "stock_daily", evidence
            )
        finally:
            writer_pool.close()

        reader_client, reader_pool = _client(db_path)
        try:
            store = SQLiteDatasetPromotionEvidenceStore(reader_client)

            assert store.list_dataset_evidence("stock_daily") == (evidence,)
            assert store.list_dataset_evidence("etf_daily") == ()
        finally:
            reader_pool.close()

    def test_upsert_replaces_existing_evidence_for_same_dataset_and_criterion(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteDatasetPromotionEvidenceStore(client)
        criterion = "document runtime owner, freshness SLA, and source failover policy"
        rejected = _evidence(
            criterion,
            evidence_uri="ditto://evidence/stock_daily/source-policy/rejected",
            passed=False,
        )
        approved = _evidence(
            criterion,
            evidence_uri="ditto://evidence/stock_daily/source-policy/approved",
            passed=True,
        )

        try:
            store.upsert_dataset_evidence("stock_daily", rejected)
            store.upsert_dataset_evidence("stock_daily", approved)

            assert store.list_dataset_evidence("stock_daily") == (approved,)
        finally:
            pool.close()

    def test_satisfies_promotion_evidence_reader_and_writer_protocols(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        try:
            store = SQLiteDatasetPromotionEvidenceStore(client)

            assert isinstance(store, DatasetPromotionEvidenceReader)
            assert isinstance(store, DatasetPromotionEvidenceWriter)
        finally:
            pool.close()


class TestSQLiteDatasetMaturityPromotionStore:
    """Maturity promotion overrides must be durable and dataset-scoped."""

    def test_promotion_survives_reopened_sqlite_connection(
        self,
        tmp_path: Path,
    ) -> None:
        db_path = tmp_path / "catalog.sqlite"
        promotion = DatasetMaturityPromotion(
            dataset_id="stock_daily",
            previous_maturity="experimental",
            promoted_maturity="initial-focus",
            promoted_by="architecture-review",
            promoted_at=datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
            evidence_uri="ditto://evidence/stock_daily/runtime-tests",
            notes="all criteria approved",
        )

        writer_client, writer_pool = _client(db_path)
        try:
            SQLiteDatasetMaturityPromotionStore(
                writer_client
            ).upsert_dataset_maturity_promotion(promotion)
        finally:
            writer_pool.close()

        reader_client, reader_pool = _client(db_path)
        try:
            store = SQLiteDatasetMaturityPromotionStore(reader_client)

            assert store.get_dataset_maturity_promotion("stock_daily") == promotion
            assert store.get_dataset_maturity_promotion("etf_daily") is None
        finally:
            reader_pool.close()

    def test_satisfies_maturity_promotion_reader_and_writer_protocols(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        try:
            store = SQLiteDatasetMaturityPromotionStore(client)

            assert isinstance(store, DatasetMaturityPromotionReader)
            assert isinstance(store, DatasetMaturityPromotionWriter)
        finally:
            pool.close()

    def test_promotion_and_reversal_are_recorded_in_history(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteDatasetMaturityPromotionStore(client)
        promoted_at = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
        revoked_at = datetime(2026, 6, 2, 9, 0, tzinfo=UTC)
        promotion = DatasetMaturityPromotion(
            dataset_id="stock_daily",
            previous_maturity="experimental",
            promoted_maturity="initial-focus",
            promoted_by="architecture-review",
            promoted_at=promoted_at,
            evidence_uri="ditto://evidence/stock_daily/runtime-tests",
            notes="all criteria approved",
        )

        try:
            store.upsert_dataset_maturity_promotion(promotion)
            revoked = store.revoke_dataset_maturity_promotion(
                "stock_daily",
                revoked_by="architecture-review",
                revoked_at=revoked_at,
                revocation_reason="failed_revalidation",
                notes="production incident found missing PIT fixture",
            )

            assert store.get_dataset_maturity_promotion("stock_daily") is None
            assert revoked == DatasetMaturityPromotionEvent(
                dataset_id="stock_daily",
                action="revoked",
                previous_maturity="initial-focus",
                next_maturity="experimental",
                actor="architecture-review",
                action_at=revoked_at,
                evidence_uri="ditto://evidence/stock_daily/runtime-tests",
                revocation_reason="failed_revalidation",
                notes="production incident found missing PIT fixture",
            )
            assert store.list_dataset_maturity_promotion_events("stock_daily") == (
                DatasetMaturityPromotionEvent(
                    dataset_id="stock_daily",
                    action="promoted",
                    previous_maturity="experimental",
                    next_maturity="initial-focus",
                    actor="architecture-review",
                    action_at=promoted_at,
                    evidence_uri="ditto://evidence/stock_daily/runtime-tests",
                    notes="all criteria approved",
                ),
                revoked,
            )
        finally:
            pool.close()

    def test_satisfies_maturity_promotion_history_and_revoker_protocols(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        try:
            store = SQLiteDatasetMaturityPromotionStore(client)

            assert isinstance(store, DatasetMaturityPromotionHistoryReader)
            assert isinstance(store, DatasetMaturityPromotionRevoker)
        finally:
            pool.close()
