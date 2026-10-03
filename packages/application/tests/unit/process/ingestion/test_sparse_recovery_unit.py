"""Sparse PIT full-history re-attestation workflow tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, call

import pytest
from ditto_application.processes.ingestion.sparse_recovery import (
    SparsePITReattestationProcess,
)
from ditto_application.processes.ingestion.sparse_recovery_models import (
    SparsePITReattestationRequest,
)
from ditto_data.models.ingestion import IngestionQualityEvidence, IngestionResult
from packages.application.tests.unit.process.ingestion import (
    snapshot_evidence_support as _evidence_support,
)

_SCHEMA = "fundamental.balance_sheet.v1"


def _seed(stores, *, day: str, checksum: str, rows: int) -> None:
    _evidence_support.commit_snapshot(
        stores,
        dataset="balance_sheet",
        request_start=day,
        request_end=day,
        checksum=checksum,
        row_count=rows,
        schema_version=_SCHEMA,
        namespace="fundamental",
        observed_at=datetime(2026, 7, int(day[-2:]), 9, tzinfo=UTC),
    )
    _evidence_support.record_success(
        stores,
        dataset="balance_sheet",
        trade_date=day,
        checksum=checksum,
        rows=rows,
    )


@pytest.mark.unit
def test_recovery_fails_closed_for_invalid_snapshot_request_interval() -> None:
    """快照请求区间非法时发现阶段 fail closed,不得触碰 provider。"""
    from ditto_data.catalog.contracts import DataAssetRef
    from ditto_data.catalog.source_snapshot import (
        ProviderSnapshot,
        ProviderSnapshotDraft,
    )

    with _evidence_support.evidence_stores() as stores:
        stores.snapshots.append_snapshot(
            ProviderSnapshot.create(
                ProviderSnapshotDraft(
                    dataset_id="balance_sheet",
                    source="tushare",
                    request_start="2026-07-01",
                    request_end="2026-07-01",
                    schema_version=_SCHEMA,
                    checksum="a" * 32,
                    canonical_asset=DataAssetRef(
                        dataset_id="balance_sheet", namespace="fundamental"
                    ),
                    request_parameters_hash="sha256:test",
                    response_metadata=(),
                    row_count=1,
                    payload_uri="provider_payloads/tushare/balance_sheet/a.parquet",
                    payload_retained=True,
                    created_at=datetime(2026, 7, 1, 9, tzinfo=UTC),
                )
            )
        )
        # 直接改写持久化行,制造非法区间。
        from ditto_platform.foundation import SQLiteClient

        client = SQLiteClient(stores.pool)
        client.execute(
            "UPDATE provider_snapshots SET request_start = 'not-a-date' "
            "WHERE dataset_id = 'balance_sheet'"
        )
        client.commit()
        runner = MagicMock()
        verifier = MagicMock()
        process = SparsePITReattestationProcess(
            ingestion=runner,
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            verifier=verifier,
        )

        result = process.run(
            SparsePITReattestationRequest(
                dataset="balance_sheet",
                source="tushare",
                signal_date="2026-07-16",
            )
        )

        assert result.passed is False
        assert result.error == "SPARSE_REATTEST_COMPONENT_DISCOVERY_FAILED"
        runner.ingest_date.assert_not_called()
        verifier.verify_exact_date.assert_not_called()
        verifier.verify_asof_snapshot.assert_not_called()


@pytest.mark.unit
def test_recovery_reingests_every_component_and_is_idempotent() -> None:
    with _evidence_support.evidence_stores() as stores:
        _seed(stores, day="2026-06-15", checksum="1" * 32, rows=1)
        _seed(stores, day="2026-07-01", checksum="2" * 32, rows=2)
        runner = MagicMock()

        def reingest(_dataset: str, trade_date: str, force: bool = False):
            _ = force
            return IngestionResult(
                dataset="balance_sheet",
                trade_date=trade_date,
                status="success",
                row_count=1,
                quality_evidence=IngestionQualityEvidence(
                    kind="write_time_l1_l2",
                    status="passed",
                    source="tushare",
                    trade_date=trade_date,
                    levels=("l1", "l2"),
                    row_count=1,
                    checksum="2" * 32,
                ),
            )

        runner.ingest_date.side_effect = reingest
        verifier = MagicMock()
        verifier.verify_exact_date.return_value = True
        verifier.verify_asof_snapshot.return_value = True
        process = SparsePITReattestationProcess(
            ingestion=runner,
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            verifier=verifier,
        )
        request = SparsePITReattestationRequest(
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-16",
        )

        first = process.run(request)
        second = process.run(request)

        assert first.passed is True
        assert second.passed is True
        assert first.component_dates == ("2026-06-15", "2026-07-01")
        assert second.source_snapshot_id == first.source_snapshot_id
        assert runner.ingest_date.call_args_list == [
            call("balance_sheet", "2026-06-15", force=True),
            call("balance_sheet", "2026-07-01", force=True),
            call("balance_sheet", "2026-06-15", force=True),
            call("balance_sheet", "2026-07-01", force=True),
        ]


@pytest.mark.unit
def test_recovery_expands_range_snapshots_into_component_dates() -> None:
    """区间快照的每个日历日都是一个待重放组件(非交易日由摄取自行跳过)。"""
    with _evidence_support.evidence_stores() as stores:
        _evidence_support.commit_snapshot(
            stores,
            dataset="balance_sheet",
            request_start="2026-07-01",
            request_end="2026-07-03",
            checksum="3" * 32,
            row_count=3,
            schema_version=_SCHEMA,
            namespace="fundamental",
            observed_at=datetime(2026, 7, 3, 9, tzinfo=UTC),
        )
        runner = MagicMock()

        def reingest(_dataset: str, trade_date: str, force: bool = False):
            _ = force
            return IngestionResult(
                dataset="balance_sheet",
                trade_date=trade_date,
                status="success",
                row_count=1,
                quality_evidence=IngestionQualityEvidence(
                    kind="write_time_l1_l2",
                    status="passed",
                    source="tushare",
                    trade_date=trade_date,
                    levels=("l1", "l2"),
                    row_count=1,
                    checksum="3" * 32,
                ),
            )

        runner.ingest_date.side_effect = reingest
        verifier = MagicMock()
        verifier.verify_exact_date.return_value = True
        verifier.verify_asof_snapshot.return_value = True
        process = SparsePITReattestationProcess(
            ingestion=runner,
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            verifier=verifier,
        )

        result = process.run(
            SparsePITReattestationRequest(
                dataset="balance_sheet",
                source="tushare",
                signal_date="2026-07-16",
            )
        )

        assert result.passed is True
        assert result.component_dates == (
            "2026-07-01",
            "2026-07-02",
            "2026-07-03",
        )


@pytest.mark.unit
def test_recovery_requires_a_concrete_source() -> None:
    runner = MagicMock()
    with _evidence_support.evidence_stores() as stores:
        process = SparsePITReattestationProcess(
            ingestion=runner,
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            verifier=MagicMock(),
        )

        result = process.run(
            SparsePITReattestationRequest(
                dataset="balance_sheet",
                source="auto",
                signal_date="2026-07-16",
            )
        )

    assert result.passed is False
    assert result.error == "SPARSE_REATTEST_CONCRETE_SOURCE_REQUIRED"
    runner.ingest_date.assert_not_called()


@pytest.mark.unit
def test_recovery_contains_durable_component_verifier_exception() -> None:
    with _evidence_support.evidence_stores() as stores:
        _seed(stores, day="2026-07-01", checksum="4" * 32, rows=1)
        runner = MagicMock()
        runner.ingest_date.return_value = IngestionResult(
            dataset="balance_sheet",
            trade_date="2026-07-01",
            status="success",
            row_count=1,
            quality_evidence=IngestionQualityEvidence(
                kind="write_time_l1_l2",
                status="passed",
                source="tushare",
                trade_date="2026-07-01",
                levels=("l1", "l2"),
                row_count=1,
                checksum="4" * 32,
            ),
        )
        verifier = MagicMock()
        verifier.verify_exact_date.side_effect = RuntimeError("sqlite unavailable")
        process = SparsePITReattestationProcess(
            ingestion=runner,
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            verifier=verifier,
        )

        result = process.run(
            SparsePITReattestationRequest(
                dataset="balance_sheet",
                source="tushare",
                signal_date="2026-07-16",
            )
        )

        assert result.passed is False
        assert result.error == "SPARSE_REATTEST_COMPONENT_FAILED"
        assert result.components[0].error == (
            "SPARSE_REATTEST_COMPONENT_DURABLE_EVIDENCE_INVALID"
        )
