"""Unit tests for PromotionEvidenceCollector."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.promotion_evidence import (
    CriterionEvidence,
    PromotionEvidenceCollector,
    PromotionEvidenceReport,
)
from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
)
from ditto_data.catalog.metadata import (
    DatasetIngestionGranularity,
    DatasetMetadata,
)

_EXPERIMENTAL_CRITERIA = (
    "complete PIT/replay coverage for the dataset",
    "document runtime owner, freshness SLA, and source failover policy",
    "pass catalog-backed runtime/read-model tests without research opt-in",
)


def _make_metadata(
    *,
    default_source: str | None = "tushare",
    freshness_sla_hours: int | None = 36,
    supported_sources: tuple[str, ...] = ("tushare",),
    ingestion_granularities: tuple[DatasetIngestionGranularity, ...] = ("date",),
    promotion_criteria: tuple[str, ...] = _EXPERIMENTAL_CRITERIA,
) -> DatasetMetadata:
    """Build a stock_daily-shaped experimental metadata for deterministic tests."""
    return DatasetMetadata(
        dataset_id="stock_daily",
        domain="market",
        maturity="experimental",
        schedule="trading_days",
        default_source=default_source,
        supported_sources=supported_sources,
        ingestion_granularities=ingestion_granularities,
        freshness_sla_hours=freshness_sla_hours,
        schema_version="market.stock_daily.v1" if ingestion_granularities else None,
        promotion_criteria=promotion_criteria,
    )


def _make_catalog_entry(dataset_id: str = "stock_daily") -> DataCatalogEntry:
    return DataCatalogEntry(
        asset=DataAssetRef(dataset_id=dataset_id, namespace="market"),
        storage_uri=f"lake://market/{dataset_id}",
        schema=DataSchemaFingerprint(schema_hash="abc", row_count=100),
        source="tushare",
        freshness_at=datetime(2024, 1, 15, tzinfo=UTC),
    )


class TestPromotionEvidenceCollector:
    """Collector gathers objective evidence without deciding promotion readiness."""

    def test_collect_returns_report_with_all_criteria(self) -> None:
        collector = PromotionEvidenceCollector(catalog_reader=None)
        report = collector.collect("stock_daily", metadata=_make_metadata())
        assert isinstance(report, PromotionEvidenceReport)
        assert report.dataset_id == "stock_daily"
        assert report.maturity == "experimental"
        assert len(report.criteria) == 3
        assert all(isinstance(c, CriterionEvidence) for c in report.criteria)

    def test_documentation_measured_when_metadata_complete(self) -> None:
        collector = PromotionEvidenceCollector(catalog_reader=None)
        report = collector.collect("stock_daily", metadata=_make_metadata())
        doc = next(c for c in report.criteria if "runtime owner" in c.criterion)
        assert doc.status == "measured"
        assert doc.materials  # carries objective material

    def test_documentation_needs_review_when_declaration_missing(self) -> None:
        metadata = _make_metadata(
            default_source=None,
            freshness_sla_hours=None,
            supported_sources=(),
            ingestion_granularities=(),
        )
        collector = PromotionEvidenceCollector(catalog_reader=None)
        report = collector.collect("stock_daily", metadata=metadata)
        doc = next(c for c in report.criteria if "runtime owner" in c.criterion)
        assert doc.status == "needs_review"

    def test_coverage_needs_review_without_reader(self) -> None:
        collector = PromotionEvidenceCollector(catalog_reader=None)
        report = collector.collect("stock_daily", metadata=_make_metadata())
        coverage = next(c for c in report.criteria if "coverage" in c.criterion)
        assert coverage.status == "needs_review"

    def test_coverage_measured_when_assets_registered(self) -> None:
        reader = MagicMock()
        reader.list_assets.return_value = (_make_catalog_entry(),)
        collector = PromotionEvidenceCollector(catalog_reader=reader)
        report = collector.collect("stock_daily", metadata=_make_metadata())
        coverage = next(c for c in report.criteria if "coverage" in c.criterion)
        assert coverage.status == "measured"
        assert any("1 catalog asset" in material for material in coverage.materials)

    def test_coverage_needs_review_when_no_assets(self) -> None:
        reader = MagicMock()
        reader.list_assets.return_value = ()
        collector = PromotionEvidenceCollector(catalog_reader=reader)
        report = collector.collect("stock_daily", metadata=_make_metadata())
        coverage = next(c for c in report.criteria if "coverage" in c.criterion)
        assert coverage.status == "needs_review"

    def test_test_pass_criterion_always_needs_review(self) -> None:
        """Tool must not auto-decide test pass; reviewer owns this criterion."""
        collector = PromotionEvidenceCollector(catalog_reader=None)
        report = collector.collect("stock_daily", metadata=_make_metadata())
        test_criterion = next(
            c for c in report.criteria if "catalog-backed" in c.criterion
        )
        assert test_criterion.status == "needs_review"
        assert test_criterion.suggestion is not None

    def test_unknown_dataset_without_metadata_raises(self) -> None:
        collector = PromotionEvidenceCollector(catalog_reader=None)
        with pytest.raises(AppQueryError, match="Unknown dataset"):
            collector.collect("nonexistent_dataset")
