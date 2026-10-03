"""Fail-closed snapshot coverage and persisted PIT evidence tests (#394)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ditto_application.catalog_freshness import (
    PersistedIngestionEvidenceVerifier,
    SourceCoverageEvidence,
    aggregate_source_snapshot_ids,
    assess_catalog_freshness,
    dataset_namespace,
    latest_catalog_entry_for_dataset,
    observed_at,
    observed_snapshot_ids,
    select_ingestion_source,
    snapshot_asof_evidence,
    snapshot_repair_priority,
    source_coverage_evidence,
)
from ditto_data.catalog import DataAssetRef, DataCatalogEntry, DataSchemaFingerprint
from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from packages.application.tests.unit.process.ingestion import (
    snapshot_evidence_support as _evidence_support,
)

pytestmark = [pytest.mark.unit, pytest.mark.pit]

_BALANCE = "fundamental.balance_sheet.v1"


def _entry(
    dataset: str = "balance_sheet",
    *,
    namespace: str = "fundamental",
    partition_keys: tuple[str, ...] = (),
    freshness_at: datetime = datetime(2026, 7, 1, tzinfo=UTC),
) -> DataCatalogEntry:
    return DataCatalogEntry(
        asset=DataAssetRef(
            dataset_id=dataset,
            namespace=namespace,
            partition_keys=partition_keys,
        ),
        storage_uri=f"{dataset}/2026",
        schema=DataSchemaFingerprint(schema_hash="schema:v1", row_count=1),
        source="tushare",
        freshness_at=freshness_at,
    )


class _Catalog:
    def __init__(self, *entries: DataCatalogEntry) -> None:
        self._entries = entries

    def get_asset(self, asset: DataAssetRef) -> DataCatalogEntry | None:
        return next((entry for entry in self._entries if entry.asset == asset), None)

    def list_assets(self, namespace: str | None = None) -> tuple[DataCatalogEntry, ...]:
        if namespace is None:
            return self._entries
        return tuple(e for e in self._entries if e.asset.namespace == namespace)


def test_freshness_statuses_observe_sla_boundary_and_unknown_dataset() -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=UTC)
    at_boundary = _entry("stock_daily", freshness_at=datetime(2026, 7, 1, tzinfo=UTC))
    stale = _entry(
        "stock_daily",
        freshness_at=datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC),
    )

    assert (
        assess_catalog_freshness(
            dataset="stock_daily", catalog_entry=at_boundary, now=lambda: now
        ).status
        == "fresh"
    )
    assert (
        assess_catalog_freshness(
            dataset="stock_daily", catalog_entry=stale, now=lambda: now
        ).status
        == "stale"
    )
    assert (
        assess_catalog_freshness(dataset="stock_daily", catalog_entry=None).status
        == "missing"
    )
    unknown = assess_catalog_freshness(dataset="private_dataset", catalog_entry=stale)
    assert (unknown.status, unknown.sla_hours, unknown.entry) == (
        "not_applicable",
        None,
        stale,
    )


def test_latest_dataset_entry_ignores_partitioned_rows() -> None:
    partitioned = _entry(partition_keys=("trade_date=2026-06-01",))
    older = _entry(freshness_at=datetime(2026, 7, 1, tzinfo=UTC))
    newer = _entry(freshness_at=datetime(2026, 7, 2, tzinfo=UTC))
    catalog = _Catalog(partitioned, older, newer)

    assert latest_catalog_entry_for_dataset(catalog, "balance_sheet") is newer
    assert latest_catalog_entry_for_dataset(_Catalog(partitioned), "balance_sheet") is (
        None
    )


def test_observed_at_prefers_latest_observation_event() -> None:
    with _evidence_support.evidence_stores() as stores:
        first = _evidence_support.commit_snapshot(
            stores,
            dataset="balance_sheet",
            request_start="2026-06-01",
            request_end="2026-06-01",
            checksum="a" * 32,
            row_count=1,
            schema_version=_BALANCE,
            namespace="fundamental",
        )
        assert first.observations
        assert observed_at(first) == first.created_at
        assert observed_at(first) == first.observations[-1]


def test_source_coverage_evidence_uses_completed_snapshots_only() -> None:
    with _evidence_support.evidence_stores() as stores:
        # tushare: completed snapshot covering the date.
        _evidence_support.commit_snapshot(
            stores,
            dataset="stock_daily",
            request_start="2026-07-01",
            request_end="2026-07-01",
            checksum="b" * 32,
            row_count=5,
            schema_version="market.stock_daily.v1",
        )
        # akshare: snapshot present but never completed.
        _evidence_support.commit_snapshot(
            stores,
            dataset="stock_daily",
            source="akshare",
            request_start="2026-07-01",
            request_end="2026-07-01",
            checksum="c" * 32,
            row_count=5,
            schema_version="market.stock_daily.v1",
            complete=False,
        )

        tushare = source_coverage_evidence(
            stores.snapshots,
            stores.lifecycle,
            dataset="stock_daily",
            source="tushare",
            trade_date="2026-07-01",
        )
        akshare = source_coverage_evidence(
            stores.snapshots,
            stores.lifecycle,
            dataset="stock_daily",
            source="akshare",
            trade_date="2026-07-01",
        )
        fuyao = source_coverage_evidence(
            stores.snapshots,
            stores.lifecycle,
            dataset="stock_daily",
            source="fuyao",
            trade_date="2026-07-01",
        )
        unknown = source_coverage_evidence(
            stores.snapshots,
            stores.lifecycle,
            dataset="private_dataset",
            source="tushare",
            trade_date="2026-07-01",
        )

        assert tushare == SourceCoverageEvidence(
            source="tushare",
            status="fresh",
            sla_hours=36,
            snapshot=tushare.snapshot,
        )
        assert tushare.snapshot is not None
        assert tushare.snapshot.row_count == 5
        assert (akshare.status, akshare.snapshot) == ("stale", None)
        assert (fuyao.status, fuyao.snapshot) == ("missing", None)
        assert unknown.status == "not_applicable"


def test_select_ingestion_source_prefers_completed_coverage() -> None:
    with _evidence_support.evidence_stores() as stores:
        _evidence_support.commit_snapshot(
            stores,
            dataset="macro_indicators",
            source="fred",
            request_start="2026-07-01",
            request_end="2026-07-01",
            checksum="d" * 32,
            row_count=1,
            schema_version="macro.macro_indicators.v1",
            namespace="macro",
        )

        with pytest.raises(ValueError, match="available_sources must not be empty"):
            select_ingestion_source(
                dataset="macro_indicators",
                trade_date="2026-07-01",
                available_sources=(),
            )
        assert (
            select_ingestion_source(
                dataset="macro_indicators",
                trade_date="2026-07-01",
                available_sources=("FRED", "TUSHARE", "fred"),
                snapshots=stores.snapshots,
                lifecycle=stores.lifecycle,
            )
            == "fred"
        )
        # 无完成事实端口时保持默认源,不猜。
        assert (
            select_ingestion_source(
                dataset="macro_indicators",
                trade_date="2026-07-01",
                available_sources=("tushare", "fred"),
            )
            == "tushare"
        )
        assert (
            select_ingestion_source(
                dataset="stock_daily",
                trade_date="2026-07-01",
                available_sources=("local",),
            )
            == "local"
        )


def test_asof_snapshot_rejects_bad_cutoff_staleness_and_invisible_observations() -> (
    None
):
    with _evidence_support.evidence_stores() as stores:
        _evidence_support.commit_snapshot(
            stores,
            dataset="balance_sheet",
            request_start="2026-06-01",
            request_end="2026-06-01",
            checksum="e" * 32,
            row_count=1,
            schema_version=_BALANCE,
            namespace="fundamental",
            observed_at=datetime(2026, 7, 1, 9, tzinfo=UTC),
        )

        assert (
            snapshot_asof_evidence(
                snapshots=stores.snapshots,
                lifecycle=stores.lifecycle,
                dataset="balance_sheet",
                source="tushare",
                signal_date="invalid",
            )
            is None
        )
        assert (
            snapshot_asof_evidence(
                snapshots=stores.snapshots,
                lifecycle=stores.lifecycle,
                dataset="balance_sheet",
                source="tushare",
                signal_date="2026-05-31",
            )
            is None
        )
        # balance_sheet SLA=1080h:组件最晚 2026-06-01,信号日 2026-08-01
        # 超出 SLA,fail closed。
        assert (
            snapshot_asof_evidence(
                snapshots=stores.snapshots,
                lifecycle=stores.lifecycle,
                dataset="balance_sheet",
                source="tushare",
                signal_date="2026-08-01",
            )
            is None
        )
        snapshot = snapshot_asof_evidence(
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-01",
        )
        assert snapshot is not None
        assert snapshot.effective_partition_date == "2026-06-01"
        assert len(snapshot.source_snapshot_ids) == 1
        assert snapshot.row_count == 1


def test_asof_snapshot_aggregates_completed_visible_components() -> None:
    with _evidence_support.evidence_stores() as stores:
        first = _evidence_support.commit_snapshot(
            stores,
            dataset="balance_sheet",
            request_start="2026-06-01",
            request_end="2026-06-01",
            checksum="1" * 32,
            row_count=2,
            schema_version=_BALANCE,
            namespace="fundamental",
            observed_at=datetime(2026, 6, 1, 9, tzinfo=UTC),
        )
        second = _evidence_support.commit_snapshot(
            stores,
            dataset="balance_sheet",
            request_start="2026-06-15",
            request_end="2026-06-15",
            checksum="2" * 32,
            row_count=3,
            schema_version=_BALANCE,
            namespace="fundamental",
            observed_at=datetime(2026, 6, 15, 9, tzinfo=UTC),
        )
        # 未完成的组件不得进入聚合。
        _evidence_support.commit_snapshot(
            stores,
            dataset="balance_sheet",
            request_start="2026-06-20",
            request_end="2026-06-20",
            checksum="3" * 32,
            row_count=7,
            schema_version=_BALANCE,
            namespace="fundamental",
            complete=False,
        )

        snapshot = snapshot_asof_evidence(
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-06-20",
        )

        assert snapshot is not None
        assert snapshot.source_snapshot_ids == tuple(
            sorted({first.snapshot_id, second.snapshot_id})
        )
        assert snapshot.source_snapshot_id == aggregate_source_snapshot_ids(
            snapshot.source_snapshot_ids
        )
        assert snapshot.row_count == 5
        assert snapshot.effective_partition_date == "2026-06-15"


def test_asof_snapshot_requires_observation_event_visibility() -> None:
    """无观察事件的遗留快照行不得参与聚合(fail closed)。"""
    with _evidence_support.evidence_stores() as stores:
        _evidence_support.commit_snapshot(
            stores,
            dataset="balance_sheet",
            request_start="2026-06-01",
            request_end="2026-06-01",
            checksum="4" * 32,
            row_count=1,
            schema_version=_BALANCE,
            namespace="fundamental",
            observed_at=datetime(2026, 6, 10, 9, tzinfo=UTC),
        )
        assert (
            snapshot_asof_evidence(
                snapshots=stores.snapshots,
                lifecycle=stores.lifecycle,
                dataset="balance_sheet",
                source="tushare",
                signal_date="2026-07-01",
            )
            is not None
        )
        # 抹掉观察账本(模拟事件表之前的遗留行)后必须不可见。
        from ditto_platform.foundation import SQLiteClient

        client = SQLiteClient(stores.pool)
        client.execute("DELETE FROM provider_snapshot_observation_events")
        client.commit()

        assert (
            snapshot_asof_evidence(
                snapshots=stores.snapshots,
                lifecycle=stores.lifecycle,
                dataset="balance_sheet",
                source="tushare",
                signal_date="2026-07-01",
            )
            is None
        )


def test_aggregate_snapshot_identity_is_empty_singleton_or_order_invariant() -> None:
    assert aggregate_source_snapshot_ids(()) is None
    assert aggregate_source_snapshot_ids(("snapshot:a",)) == "snapshot:a"
    assert aggregate_source_snapshot_ids(("snapshot:b", "snapshot:a")) == (
        aggregate_source_snapshot_ids(("snapshot:a", "snapshot:b", "snapshot:a"))
    )


def test_observed_snapshot_ids_filters_retained_completed_and_cutoff() -> None:
    with _evidence_support.evidence_stores() as stores:
        kept = _evidence_support.commit_snapshot(
            stores,
            dataset="stock_daily",
            request_start="2026-06-01",
            request_end="2026-06-01",
            checksum="5" * 32,
            row_count=1,
            schema_version="market.stock_daily.v1",
            observed_at=datetime(2026, 6, 1, 9, tzinfo=UTC),
        )
        _evidence_support.commit_snapshot(
            stores,
            dataset="stock_daily",
            request_start="2026-06-02",
            request_end="2026-06-02",
            checksum="6" * 32,
            row_count=1,
            schema_version="market.stock_daily.v1",
            observed_at=datetime(2026, 6, 2, 9, tzinfo=UTC),
            payload_retained=False,
        )

        identities = observed_snapshot_ids(
            stores.snapshots,
            stores.lifecycle,
            dataset_ids=("stock_daily",),
            knowledge_cutoff=datetime(2026, 6, 1, 12, tzinfo=UTC),
        )

        assert identities == (kept.snapshot_id,)


def test_verify_exact_date_binds_log_to_completed_snapshot_content() -> None:
    with _evidence_support.evidence_stores() as stores:
        _evidence_support.commit_snapshot(
            stores,
            dataset="stock_daily",
            request_start="2026-07-01",
            request_end="2026-07-01",
            checksum="7" * 32,
            row_count=5,
            schema_version="market.stock_daily.v1",
        )
        _evidence_support.record_success(
            stores,
            dataset="stock_daily",
            trade_date="2026-07-01",
            checksum="7" * 32,
            rows=5,
        )
        verifier = PersistedIngestionEvidenceVerifier(
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            ingestion_logs=stores.logs,
        )

        assert verifier.verify_exact_date(
            dataset="stock_daily",
            source="tushare",
            trade_date="2026-07-01",
            checksum="7" * 32,
            row_count=5,
        )
        # 同 run 不同内容:log 内容与快照内容漂移必须拒绝。
        assert not verifier.verify_exact_date(
            dataset="stock_daily",
            source="tushare",
            trade_date="2026-07-01",
            checksum="7" * 32,
            row_count=6,
        )
        assert not verifier.verify_exact_date(
            dataset="stock_daily",
            source="tushare",
            trade_date="2026-07-01",
            checksum="8" * 32,
            row_count=5,
        )
        # 覆盖同一日期但未完成的快照不能作证。
        _evidence_support.commit_snapshot(
            stores,
            dataset="stock_daily",
            request_start="2026-07-01",
            request_end="2026-07-01",
            checksum="9" * 32,
            row_count=9,
            schema_version="market.stock_daily.v1",
            complete=False,
        )
        _evidence_support.record_success(
            stores,
            dataset="stock_daily",
            trade_date="2026-07-02",
            checksum="9" * 32,
            rows=9,
        )
        assert not verifier.verify_exact_date(
            dataset="stock_daily",
            source="tushare",
            trade_date="2026-07-02",
            checksum="9" * 32,
            row_count=9,
        )


def test_verify_asof_snapshot_cross_checks_log_snapshot_and_completion() -> None:
    with _evidence_support.evidence_stores() as stores:
        first = _evidence_support.commit_snapshot(
            stores,
            dataset="balance_sheet",
            request_start="2026-06-01",
            request_end="2026-06-01",
            checksum="a" * 32,
            row_count=2,
            schema_version=_BALANCE,
            namespace="fundamental",
        )
        second = _evidence_support.commit_snapshot(
            stores,
            dataset="balance_sheet",
            request_start="2026-06-15",
            request_end="2026-06-15",
            checksum="b" * 32,
            row_count=3,
            schema_version=_BALANCE,
            namespace="fundamental",
        )
        _evidence_support.record_success(
            stores,
            dataset="balance_sheet",
            trade_date="2026-06-01",
            checksum="a" * 32,
            rows=2,
        )
        _evidence_support.record_success(
            stores,
            dataset="balance_sheet",
            trade_date="2026-06-15",
            checksum="b" * 32,
            rows=3,
        )
        verifier = PersistedIngestionEvidenceVerifier(
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            ingestion_logs=stores.logs,
        )
        ids = tuple(sorted({first.snapshot_id, second.snapshot_id}))

        assert verifier.verify_asof_snapshot(
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-01",
            expected_snapshot_ids=ids,
            expected_row_count=5,
        )
        assert not verifier.verify_asof_snapshot(
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-01",
            expected_snapshot_ids=("snapshot:unexpected",),
            expected_row_count=5,
        )
        assert not verifier.verify_asof_snapshot(
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-01",
            expected_snapshot_ids=ids,
            expected_row_count=6,
        )
        # 组件缺 success log 佐证时拒绝。
        stores.logs._logs.pop(("balance_sheet", "tushare", "2026-06-15"))
        assert not verifier.verify_asof_snapshot(
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-01",
            expected_snapshot_ids=ids,
            expected_row_count=5,
        )


def test_snapshot_repair_priority_orders_by_log_attempts_then_time() -> None:
    logs = {
        ("stock_daily", "tushare", "2026-07-03"): IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2026-07-03",
            status=IngestionStatus.FAIL,
            attempts=1,
            last_attempt_at="2026-07-03T08:00:00+00:00",
        ),
        ("stock_daily", "tushare", "2026-07-01"): IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2026-07-01",
            status=IngestionStatus.FAIL,
            attempts=3,
            last_attempt_at="2026-07-01T08:00:00+00:00",
        ),
    }

    class _Logs:
        def get_log(
            self, dataset: str, source: str, trade_date: str
        ) -> IngestionLog | None:
            return logs.get((dataset, source, trade_date))

    assert snapshot_repair_priority(
        logs=_Logs(),
        dataset="stock_daily",
        source="tushare",
        trade_date="2026-07-02",
    ) == (0, "", "2026-07-02")
    assert snapshot_repair_priority(
        logs=_Logs(),
        dataset="stock_daily",
        source="tushare",
        trade_date="2026-07-01",
    ) > snapshot_repair_priority(
        logs=_Logs(),
        dataset="stock_daily",
        source="tushare",
        trade_date="2026-07-03",
    )
    assert dataset_namespace("balance_sheet") == "fundamental"
    assert dataset_namespace("private_dataset") == "data"
