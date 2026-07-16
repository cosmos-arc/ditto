"""Sparse PIT full-history re-attestation workflow tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import MagicMock, call

import pytest
from ditto_application.catalog_freshness import (
    catalog_asof_snapshot,
    catalog_source_snapshot_id,
)
from ditto_application.processes.ingestion.sparse_recovery import (
    SparsePITReattestationProcess,
)
from ditto_application.processes.ingestion.sparse_recovery_models import (
    SparsePITReattestationRequest,
)
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
    InMemoryDataCatalog,
)
from ditto_data.models.ingestion import IngestionQualityEvidence, IngestionResult


def _entry(
    trade_date: str,
    checksum: str,
    *,
    attested: bool,
) -> DataCatalogEntry:
    return DataCatalogEntry(
        asset=DataAssetRef(
            dataset_id="balance_sheet",
            namespace="fundamental",
            partition_keys=(f"trade_date={trade_date}",),
        ),
        storage_uri=f"balance_sheet/{trade_date}.parquet",
        schema=DataSchemaFingerprint(schema_hash="v1", row_count=1),
        source="tushare",
        freshness_at=datetime(2026, 7, 16, tzinfo=UTC),
        source_snapshot_id=catalog_source_snapshot_id(
            dataset="balance_sheet",
            trade_date=trade_date,
            source="tushare",
            checksum=checksum,
            l1_l2_attested=attested,
        ),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "partition_keys",
    [
        ("trade_date=malformed",),
        ("trade_date=2026-07-01", "ticker=000001.SZ"),
        ("year=2026",),
    ],
)
def test_recovery_fails_closed_for_invalid_catalog_component_partition(
    partition_keys: tuple[str, ...],
) -> None:
    catalog = InMemoryDataCatalog()
    catalog.upsert_asset(_entry("2026-07-01", "sha256:valid", attested=True))
    invalid_entry = replace(
        _entry("2026-06-15", "sha256:invalid", attested=True),
        asset=DataAssetRef(
            dataset_id="balance_sheet",
            namespace="fundamental",
            partition_keys=partition_keys,
        ),
    )
    catalog.upsert_asset(invalid_entry)
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
            checksum="sha256:valid",
        ),
    )
    verifier = MagicMock()
    verifier.verify_exact_date.return_value = True
    verifier.verify_asof_snapshot.return_value = True
    process = SparsePITReattestationProcess(
        ingestion=runner,
        catalog=catalog,
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
    catalog = InMemoryDataCatalog()
    checksums = {
        "2026-06-15": "sha256:legacy",
        "2026-07-01": "sha256:attested",
    }
    catalog.upsert_asset(_entry("2026-06-15", checksums["2026-06-15"], attested=False))
    catalog.upsert_asset(_entry("2026-07-01", checksums["2026-07-01"], attested=True))
    assert (
        catalog_asof_snapshot(
            reader=catalog,
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-16",
        )
        is None
    )
    runner = MagicMock()

    def reingest(dataset: str, trade_date: str, force: bool = False) -> IngestionResult:
        assert force is True
        checksum = checksums[trade_date]
        current = catalog.get_asset(
            DataAssetRef(
                dataset_id=dataset,
                namespace="fundamental",
                partition_keys=(f"trade_date={trade_date}",),
            )
        )
        assert current is not None
        catalog.upsert_asset(
            replace(
                current,
                source_snapshot_id=catalog_source_snapshot_id(
                    dataset=dataset,
                    trade_date=trade_date,
                    source="tushare",
                    checksum=checksum,
                    l1_l2_attested=True,
                ),
            )
        )
        return IngestionResult(
            dataset=dataset,
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
                checksum=checksum,
            ),
        )

    runner.ingest_date.side_effect = reingest
    verifier = MagicMock()
    verifier.verify_exact_date.return_value = True
    verifier.verify_asof_snapshot.return_value = True
    process = SparsePITReattestationProcess(
        ingestion=runner,
        catalog=catalog,
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
def test_recovery_requires_a_concrete_source() -> None:
    runner = MagicMock()
    process = SparsePITReattestationProcess(
        ingestion=runner,
        catalog=InMemoryDataCatalog(),
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
    catalog = InMemoryDataCatalog()
    catalog.upsert_asset(_entry("2026-07-01", "sha256:sheet", attested=True))
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
            checksum="sha256:sheet",
        ),
    )
    verifier = MagicMock()
    verifier.verify_exact_date.side_effect = RuntimeError("sqlite unavailable")
    process = SparsePITReattestationProcess(
        ingestion=runner,
        catalog=catalog,
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
