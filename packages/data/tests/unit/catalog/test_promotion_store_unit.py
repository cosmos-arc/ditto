"""Unit tests for persistent dataset promotion evidence storage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
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
            ).upsert_dataset_maturity_promotion(
                promotion,
                assessed_event_sequence=0,
            )
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
            store.upsert_dataset_maturity_promotion(
                promotion,
                assessed_event_sequence=0,
            )
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
                sequence=2,
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
                    sequence=1,
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

    def test_upsert_rejects_promotion_predating_latest_revocation(
        self,
        tmp_path: Path,
    ) -> None:
        """#380:并发窗口内不得复活已被更新撤销压过的晋级 override。"""
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteDatasetMaturityPromotionStore(client)
        promoted_at = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
        revoked_at = datetime(2026, 6, 2, 9, 0, tzinfo=UTC)
        stale_promotion = DatasetMaturityPromotion(
            dataset_id="stock_daily",
            previous_maturity="experimental",
            promoted_maturity="initial-focus",
            promoted_by="architecture-review",
            promoted_at=promoted_at,
        )
        re_promotion = DatasetMaturityPromotion(
            dataset_id="stock_daily",
            previous_maturity="experimental",
            promoted_maturity="initial-focus",
            promoted_by="architecture-review",
            promoted_at=revoked_at + timedelta(minutes=1),
        )

        try:
            store.upsert_dataset_maturity_promotion(
                stale_promotion,
                assessed_event_sequence=0,
            )
            store.revoke_dataset_maturity_promotion(
                "stock_daily",
                revoked_by="data-governance",
                revoked_at=revoked_at,
                revocation_reason="evidence_invalidated",
            )

            with pytest.raises(ValueError, match="newer revocation"):
                store.upsert_dataset_maturity_promotion(
                    stale_promotion,
                    assessed_event_sequence=0,
                )
            assert store.get_dataset_maturity_promotion("stock_daily") is None

            store.upsert_dataset_maturity_promotion(
                re_promotion, assessed_event_sequence=2
            )
            current = store.get_dataset_maturity_promotion("stock_daily")
            assert current is not None
            assert current.promoted_at == re_promotion.promoted_at
        finally:
            pool.close()

    def test_upsert_rejects_naive_promoted_at(
        self,
        tmp_path: Path,
    ) -> None:
        """#380:无时区 promoted_at 无法与撤销排序,写入即拒。"""
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteDatasetMaturityPromotionStore(client)
        naive_promotion = DatasetMaturityPromotion(
            dataset_id="stock_daily",
            previous_maturity="experimental",
            promoted_maturity="initial-focus",
            promoted_by="architecture-review",
            promoted_at=datetime(2026, 6, 1, 13, 0),
        )

        try:
            with pytest.raises(ValueError, match="timezone-aware"):
                store.upsert_dataset_maturity_promotion(
                    naive_promotion,
                    assessed_event_sequence=0,
                )
        finally:
            pool.close()

    def test_upsert_orders_revocation_as_instant_across_offsets(
        self,
        tmp_path: Path,
    ) -> None:
        """#380:不同时区偏移按时刻比较,不受 ISO 字典序影响。"""
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteDatasetMaturityPromotionStore(client)
        # 08:00+08:00 == 00:00Z;晋级时刻 01:00Z 晚于撤销,应当成功
        store.upsert_dataset_maturity_promotion(
            DatasetMaturityPromotion(
                dataset_id="stock_daily",
                previous_maturity="experimental",
                promoted_maturity="initial-focus",
                promoted_by="architecture-review",
                promoted_at=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
            ),
            assessed_event_sequence=0,
        )
        store.revoke_dataset_maturity_promotion(
            "stock_daily",
            revoked_by="data-governance",
            revoked_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone(timedelta(hours=8))),
            revocation_reason="evidence_invalidated",
        )
        store.upsert_dataset_maturity_promotion(
            DatasetMaturityPromotion(
                dataset_id="stock_daily",
                previous_maturity="experimental",
                promoted_maturity="initial-focus",
                promoted_by="architecture-review",
                promoted_at=datetime(2026, 6, 1, 1, 0, tzinfo=UTC),
            ),
            # 评估已见到该撤销(00:00Z),快照不得早于它
            assessed_event_sequence=2,
        )
        current = store.get_dataset_maturity_promotion("stock_daily")
        assert current is not None
        assert current.promoted_at == datetime(2026, 6, 1, 1, 0, tzinfo=UTC)
        pool.close()

    def test_upsert_rejects_promotion_tied_with_revocation(
        self,
        tmp_path: Path,
    ) -> None:
        """#380:与撤销同刻的晋级不可排序,一律拒绝(与纯函数严格序一致)。"""
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteDatasetMaturityPromotionStore(client)
        moment = datetime(2026, 6, 2, 9, 0, tzinfo=UTC)
        store.upsert_dataset_maturity_promotion(
            DatasetMaturityPromotion(
                dataset_id="stock_daily",
                previous_maturity="experimental",
                promoted_maturity="initial-focus",
                promoted_by="architecture-review",
                promoted_at=datetime(2026, 6, 1, tzinfo=UTC),
            ),
            assessed_event_sequence=0,
        )
        store.revoke_dataset_maturity_promotion(
            "stock_daily",
            revoked_by="data-governance",
            revoked_at=moment,
            revocation_reason="evidence_invalidated",
        )
        tied = DatasetMaturityPromotion(
            dataset_id="stock_daily",
            previous_maturity="experimental",
            promoted_maturity="initial-focus",
            promoted_by="architecture-review",
            promoted_at=moment,
        )

        try:
            with pytest.raises(ValueError, match="newer revocation"):
                store.upsert_dataset_maturity_promotion(tied, assessed_event_sequence=0)
        finally:
            pool.close()

    def test_upsert_rejects_revocation_unseen_by_assessment_snapshot(
        self,
        tmp_path: Path,
    ) -> None:
        """#380:评估快照之后落地的撤销(如暂停的 revoker)不得被穿透。"""
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteDatasetMaturityPromotionStore(client)
        snapshot = 1  # 评估者只见到事件 1(首次晋级),未见到事件 2(撤销)
        # revoker 在 t=11:00 已捕获时刻但尚未写事件;评估者读到空历史
        store.upsert_dataset_maturity_promotion(
            DatasetMaturityPromotion(
                dataset_id="stock_daily",
                previous_maturity="experimental",
                promoted_maturity="initial-focus",
                promoted_by="architecture-review",
                promoted_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            ),
            assessed_event_sequence=0,
        )
        store.revoke_dataset_maturity_promotion(
            "stock_daily",
            revoked_by="data-governance",
            revoked_at=datetime(2026, 6, 1, 11, 0, tzinfo=UTC),
            revocation_reason="evidence_invalidated",
        )
        stale_write = DatasetMaturityPromotion(
            dataset_id="stock_daily",
            previous_maturity="experimental",
            promoted_maturity="initial-focus",
            promoted_by="architecture-review",
            promoted_at=datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
        )

        try:
            with pytest.raises(ValueError, match="newer revocation"):
                store.upsert_dataset_maturity_promotion(
                    stale_write, assessed_event_sequence=snapshot
                )
            assert store.get_dataset_maturity_promotion("stock_daily") is None
        finally:
            pool.close()

    def test_upsert_orders_subsecond_revocation_and_promotion(
        self,
        tmp_path: Path,
    ) -> None:
        """#380:同秒内的亚秒级撤销/晋级按全精度时刻比较。"""
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteDatasetMaturityPromotionStore(client)
        store.upsert_dataset_maturity_promotion(
            DatasetMaturityPromotion(
                dataset_id="stock_daily",
                previous_maturity="experimental",
                promoted_maturity="initial-focus",
                promoted_by="architecture-review",
                promoted_at=datetime(2026, 6, 1, tzinfo=UTC),
            ),
            assessed_event_sequence=0,
        )
        store.revoke_dataset_maturity_promotion(
            "stock_daily",
            revoked_by="data-governance",
            revoked_at=datetime(2026, 6, 2, 9, 0, 0, 100000, tzinfo=UTC),
            revocation_reason="evidence_invalidated",
        )
        # 晚 800ms 的重晋级应成功(datetime() 截断会误判为同秒拒绝)
        store.upsert_dataset_maturity_promotion(
            DatasetMaturityPromotion(
                dataset_id="stock_daily",
                previous_maturity="experimental",
                promoted_maturity="initial-focus",
                promoted_by="architecture-review",
                promoted_at=datetime(2026, 6, 2, 9, 0, 0, 900000, tzinfo=UTC),
            ),
            assessed_event_sequence=2,
        )
        current = store.get_dataset_maturity_promotion("stock_daily")
        assert current is not None
        assert current.promoted_at == datetime(2026, 6, 2, 9, 0, 0, 900000, tzinfo=UTC)
        pool.close()

    def test_revoke_rejects_naive_timestamp_before_deleting_override(
        self,
        tmp_path: Path,
    ) -> None:
        """#380:naive revoked_at 在删除 override 之前即拒,不留半撤销状态。"""
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteDatasetMaturityPromotionStore(client)
        store.upsert_dataset_maturity_promotion(
            DatasetMaturityPromotion(
                dataset_id="stock_daily",
                previous_maturity="experimental",
                promoted_maturity="initial-focus",
                promoted_by="architecture-review",
                promoted_at=datetime(2026, 6, 1, tzinfo=UTC),
            ),
            assessed_event_sequence=0,
        )

        try:
            with pytest.raises(ValueError, match="timezone-aware"):
                store.revoke_dataset_maturity_promotion(
                    "stock_daily",
                    revoked_by="data-governance",
                    revoked_at=datetime(2026, 6, 2, 9, 0),
                    revocation_reason="evidence_invalidated",
                )
            assert store.get_dataset_maturity_promotion("stock_daily") is not None
        finally:
            pool.close()

    def test_evidence_log_is_append_only_with_latest_projection(
        self,
        tmp_path: Path,
    ) -> None:
        """#383:重审同准则追加新行,读侧取最新,审计轨迹全量保留。"""
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteDatasetPromotionEvidenceStore(client)

        try:
            store.upsert_dataset_evidence(
                "stock_daily",
                DatasetPromotionEvidence(
                    criterion="complete PIT/replay coverage for the dataset",
                    evidence_uri="ditto://evidence/old",
                    approved_by="architecture-review",
                    passed=True,
                    reviewed_at=datetime(2026, 6, 1, tzinfo=UTC),
                    assessed_event_sequence=0,
                ),
            )
            store.upsert_dataset_evidence(
                "stock_daily",
                DatasetPromotionEvidence(
                    criterion="complete PIT/replay coverage for the dataset",
                    evidence_uri="ditto://evidence/new",
                    approved_by="data-governance",
                    passed=False,
                    reviewed_at=datetime(2026, 6, 3, tzinfo=UTC),
                    assessed_event_sequence=4,
                ),
            )

            current = store.list_dataset_evidence("stock_daily")
            assert len(current) == 1
            assert current[0].evidence_uri == "ditto://evidence/new"
            assert current[0].passed is False
            assert current[0].assessed_event_sequence == 4

            history = store.list_dataset_evidence_history("stock_daily")
            assert [row.evidence_uri for row in history] == [
                "ditto://evidence/old",
                "ditto://evidence/new",
            ]
        finally:
            pool.close()

    def test_legacy_evidence_table_migrates_into_log_once(
        self,
        tmp_path: Path,
    ) -> None:
        """#383:存量 last-write-wins 行一次性入日志(sequence 0),旧表退役。"""
        client, pool = _client(tmp_path / "catalog.sqlite")
        client.executescript(
            """
            CREATE TABLE dataset_promotion_evidence (
                dataset_id TEXT NOT NULL,
                criterion TEXT NOT NULL,
                evidence_uri TEXT NOT NULL,
                approved_by TEXT NOT NULL,
                passed INTEGER NOT NULL,
                notes TEXT,
                reviewed_at TEXT,
                PRIMARY KEY (dataset_id, criterion)
            );
            INSERT INTO dataset_promotion_evidence VALUES (
                'stock_daily', 'c1', 'ditto://evidence/legacy',
                'architecture-review', 1, NULL, '2026-05-01T00:00:00+00:00'
            );
            """
        )
        client.commit()

        store = SQLiteDatasetPromotionEvidenceStore(client)
        try:
            migrated = store.list_dataset_evidence("stock_daily")
            assert len(migrated) == 1
            assert migrated[0].evidence_uri == "ditto://evidence/legacy"
            assert migrated[0].assessed_event_sequence == 0

            legacy = client.fetchone(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name = 'dataset_promotion_evidence'
                """
            )
            assert legacy is None

            # 再实例化不重复迁移
            SQLiteDatasetPromotionEvidenceStore(client)
            history = store.list_dataset_evidence_history("stock_daily")
            assert len(history) == 1
        finally:
            pool.close()
