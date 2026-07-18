"""Certified fixed-seed deterministic materialization smoke tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.materialization.r2_seed_smoke import (
    R2SeedDatasetSnapshots,
    R2SeedSmokeRequest,
    R2SeedSmokeRunner,
)
from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
)
from ditto_data.catalog.store import InMemoryDataCatalog


def _catalog() -> InMemoryDataCatalog:
    catalog = InMemoryDataCatalog()
    for dataset_id in (
        "stock_daily",
        "adj_factor",
        "balance_sheet",
        "income_statement",
    ):
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id=dataset_id,
                    namespace="market" if dataset_id.endswith("daily") else "data",
                    partition_keys=("trade_date=2026-07-18",),
                ),
                storage_uri=f"{dataset_id}/2026",
                schema=DataSchemaFingerprint(
                    schema_hash=f"{dataset_id}.v1",
                    row_count=1,
                    schema_version=f"r2.{dataset_id}.v1",
                    columns=("instrument_id", "trade_date"),
                ),
                source="tushare",
                freshness_at=datetime(2026, 7, 18, tzinfo=UTC),
                source_snapshot_id=f"snapshot:{dataset_id}:2026-07-18",
            )
        )
    return catalog


def _request() -> R2SeedSmokeRequest:
    datasets = (
        "stock_daily",
        "adj_factor",
        "balance_sheet",
        "income_statement",
    )
    return R2SeedSmokeRequest(
        factor_ids=("quality_roe", "value_pe", "momentum_1m"),
        input_dataset_ids=datasets,
        max_lookback=20,
        knowledge_date=date(2026, 7, 18),
        certification_profile="r2-modern-a-share-v1",
        dataset_snapshots=tuple(
            R2SeedDatasetSnapshots(
                dataset_id=dataset_id,
                snapshot_ids=(f"snapshot:{dataset_id}:2026-07-18",),
            )
            for dataset_id in datasets
        ),
    )


def _certification_reader(request: R2SeedSmokeRequest) -> MagicMock:
    reports: dict[str, MagicMock] = {}
    for dataset in request.dataset_snapshots:
        report = MagicMock()
        report.report_id = f"certification:{dataset.dataset_id}:1"
        report.coverage.complete_from = date(2015, 1, 1)
        report.coverage.target_to = request.knowledge_date
        report.evidence.snapshot_ids = dataset.snapshot_ids
        reports[dataset.dataset_id] = report
    reader = MagicMock()
    reader.get_active_report.side_effect = lambda dataset_id, profile: reports.get(
        dataset_id
    )
    return reader


def test_seed_smoke_freezes_evidence_and_replays_to_identical_checksum() -> None:
    request = _request()
    materialize = MagicMock(return_value=b"canonical factor rows")
    runner = R2SeedSmokeRunner(
        catalog_reader=_catalog(),
        certification_reader=_certification_reader(request),
        materialize=materialize,
    )

    report = runner.run(request)

    assert report.status == "passed"
    assert report.factor_ids == request.factor_ids
    assert report.max_lookback == 20
    assert report.knowledge_date == date(2026, 7, 18)
    assert report.certification_profile == "r2-modern-a-share-v1"
    assert report.source_snapshot_ids == tuple(
        snapshot_id
        for dataset in request.dataset_snapshots
        for snapshot_id in dataset.snapshot_ids
    )
    assert report.first_checksum == report.replay_checksum
    assert materialize.call_count == 2
    materialize.assert_called_with(request)


def test_seed_smoke_fails_closed_when_materialization_replay_differs() -> None:
    request = _request()
    runner = R2SeedSmokeRunner(
        catalog_reader=_catalog(),
        certification_reader=_certification_reader(request),
        materialize=MagicMock(side_effect=(b"first", b"different")),
    )

    with pytest.raises(AppProcessError, match="deterministic materialization"):
        runner.run(request)


def test_seed_smoke_fails_closed_when_certification_snapshot_is_missing() -> None:
    request = _request()
    reader = _certification_reader(request)
    reader.get_active_report.return_value = None
    reader.get_active_report.side_effect = None
    runner = R2SeedSmokeRunner(
        catalog_reader=_catalog(),
        certification_reader=reader,
        materialize=MagicMock(return_value=b"rows"),
    )

    with pytest.raises(AppProcessError, match="certification"):
        runner.run(request)
