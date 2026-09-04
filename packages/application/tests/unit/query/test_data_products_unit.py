"""Data product read-model tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from ditto_application.queries.data_products import (
    DataProductsQueryFacade,
    DataProductView,
)
from ditto_data.catalog.coverage import DatasetCoverage


def test_overview_lists_the_22_r2_hard_scope_products_independently() -> None:
    facade = DataProductsQueryFacade(certification_reader=MagicMock())

    products = facade.list_products(profile="r2-modern-a-share-v1")

    assert len(products) == 22
    assert len({product.dataset_id for product in products}) == 22
    assert all(isinstance(product, DataProductView) for product in products)
    assert all(product.r2_scope == "hard" for product in products)
    assert all(product.schema_version for product in products)
    assert all(product.frequency for product in products)
    assert all(product.timezone for product in products)


def test_coverage_view_exposes_raw_complete_and_certified_starts() -> None:
    active = MagicMock()
    active.coverage.complete_from = date(2016, 1, 4)
    reader = MagicMock()
    reader.get_active_report.return_value = active
    facade = DataProductsQueryFacade(certification_reader=reader)
    coverage = DatasetCoverage(
        dataset_id="stock_status",
        schedule="trading_days",
        target_from=date(2016, 1, 1),
        target_to=date(2016, 1, 6),
        native_from=date(2016, 1, 1),
        native_to=date(2016, 1, 6),
        actual_from=date(2016, 1, 4),
        actual_to=date(2016, 1, 6),
        raw_from=date(2016, 1, 4),
        complete_from=date(2016, 1, 4),
        expected_partitions=3,
        actual_partitions=3,
        gaps=(),
        exceptions=(),
        collected_at=datetime(2026, 7, 18, tzinfo=UTC),
    )

    view = facade.coverage_view(
        coverage,
        profile="r2-modern-a-share-v1",
    )

    assert view.raw_from == date(2016, 1, 4)
    assert view.complete_from == date(2016, 1, 4)
    assert view.certified_from == date(2016, 1, 4)


def test_product_evidence_is_bound_to_active_report_not_newer_pending_report() -> None:
    active = SimpleNamespace(
        report_id="report-approved",
        content_hash="a" * 64,
        evidence=SimpleNamespace(
            source_ids=("tushare",),
            schema_versions=("stock_daily.v1",),
            snapshot_ids=("snapshot-approved",),
            fallback_history=(),
            override_history=(),
        ),
    )
    pending = SimpleNamespace(
        report_id="report-pending",
        content_hash="b" * 64,
        evidence=SimpleNamespace(
            source_ids=("tushare",),
            schema_versions=("stock_daily.v1",),
            snapshot_ids=("snapshot-pending",),
            fallback_history=(),
            override_history=(),
        ),
    )
    reader = MagicMock()
    reader.get_active_report.return_value = active
    reader.list_reports.return_value = (active, pending)

    evidence = DataProductsQueryFacade(
        certification_reader=reader
    ).evidence_for_product("stock_daily", profile="research_daily")

    assert evidence is not None
    assert evidence.report_id == "report-approved"
    assert evidence.snapshot_ids == ("snapshot-approved",)
