"""Data product read-model tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from ditto_application.queries.data_products import DataProductsQueryFacade
from ditto_data.catalog.coverage import DatasetCoverage


def test_overview_lists_the_19_r2_hard_scope_products_independently() -> None:
    facade = DataProductsQueryFacade(certification_reader=MagicMock())

    products = facade.list_products(profile="r2-modern-a-share-v1")

    assert len(products) == 19
    assert len({product.dataset_id for product in products}) == 19
    assert all(product.r2_scope == "hard" for product in products)


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
