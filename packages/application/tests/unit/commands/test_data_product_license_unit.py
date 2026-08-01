"""Unit contract for explicit provider-license review commands."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime

import pytest
from ditto_application.commands.data_product_license import (
    DataProductLicenseCommands,
    ReviewDataProductLicense,
)
from ditto_application.exceptions import AppCommandError
from ditto_data.catalog.license import DatasetLicenseRecord


@dataclass
class _Writer:
    records: list[DatasetLicenseRecord] = field(default_factory=list)

    def append_license(self, record: DatasetLicenseRecord) -> None:
        self.records.append(record)


def _review() -> ReviewDataProductLicense:
    return ReviewDataProductLicense(
        dataset_id="stock_daily",
        source="tushare",
        terms_version="terms-2026-08",
        effective_from=date(2026, 8, 1),
        effective_to=None,
        local_cache="allowed",
        derivative_compute="allowed",
        display="restricted",
        redistribution="prohibited",
        notes="Reviewed provider terms for local research use.",
        reviewed_by="data-owner",
        reviewed_at=datetime(2026, 8, 1, 4, 0, tzinfo=UTC),
    )


@pytest.mark.unit
def test_review_appends_one_content_addressed_record_for_declared_source() -> None:
    writer = _Writer()

    record = DataProductLicenseCommands(writer).review(_review())

    assert writer.records == [record]
    assert record.record_id.startswith("license:tushare:stock_daily:sha256:")
    assert record.reviewed_by == "data-owner"


@pytest.mark.unit
def test_review_rejects_source_outside_product_contract_without_write() -> None:
    writer = _Writer()

    with pytest.raises(AppCommandError, match="not declared"):
        DataProductLicenseCommands(writer).review(replace(_review(), source="fred"))

    assert writer.records == []
