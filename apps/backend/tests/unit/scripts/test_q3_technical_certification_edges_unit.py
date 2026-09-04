"""Isolated state-machine tests for Q3 technical certification composition."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import polars as pl
import pytest
from ditto_application.commands.data_product_certification import (
    DataProductCertificationCommands,
)
from ditto_application.commands.data_product_certification_builder import (
    CertificationBuildRequest,
    DataProductCertificationBuilder,
)
from ditto_apps.scripts import q3_live_discovery_support as subject
from ditto_data.catalog.certification import (
    CertificationGovernanceStore,
    DatasetCertificationReport,
)
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import ProviderSnapshot


def _snapshot() -> ProviderSnapshot:
    checksum = "a" * 32
    return ProviderSnapshot(
        snapshot_id="snapshot-1",
        dataset_id="stock_daily",
        source="tushare",
        request_start="2022-10-01",
        request_end="2024-03-29",
        schema_version="1",
        checksum=checksum,
        canonical_asset=DataAssetRef(
            dataset_id="stock_daily",
            namespace="market/daily",
        ),
        request_parameters_hash="request-1",
        response_metadata=(),
        license_record_id="license:tushare",
        row_count=2,
        payload_uri=f"provider_payloads/tushare/stock_daily/{checksum}.parquet",
        payload_retained=True,
        created_at=datetime(2024, 3, 29, tzinfo=UTC),
    )


def _report(
    report_id: str,
    *,
    snapshot_ids: tuple[str, ...] = ("snapshot-1",),
) -> DatasetCertificationReport:
    return cast(
        DatasetCertificationReport,
        SimpleNamespace(
            report_id=report_id,
            evidence=SimpleNamespace(snapshot_ids=snapshot_ids),
        ),
    )


class _Store:
    def __init__(
        self,
        reports: tuple[DatasetCertificationReport | None, ...],
    ) -> None:
        self._reports = iter(reports)

    def get_active_report(
        self,
        dataset_id: str,
        profile: str,
    ) -> DatasetCertificationReport | None:
        assert dataset_id == "stock_daily"
        assert profile == "technical_daily"
        return next(self._reports)


class _Builder:
    def __init__(self, report: DatasetCertificationReport) -> None:
        self.report = report
        self.request: CertificationBuildRequest | None = None

    def build(self, request: CertificationBuildRequest) -> DatasetCertificationReport:
        self.request = request
        return self.report


class _Commands:
    def __init__(self, frozen: DatasetCertificationReport) -> None:
        self.frozen = frozen
        self.reviewed: tuple[str, str, datetime] | None = None

    def freeze(
        self,
        report: DatasetCertificationReport,
    ) -> DatasetCertificationReport:
        assert report is self.frozen
        return self.frozen

    def review(
        self,
        report_id: str,
        *,
        reviewer: str,
        reviewed_at: datetime,
    ) -> object:
        self.reviewed = (report_id, reviewer, reviewed_at)
        return object()


def _probe(data_root: Path, dataset_id: str) -> dict[str, object]:
    assert data_root.is_dir()
    assert dataset_id == "stock_daily"
    return {"status": "ok"}


def _context(
    root: Path,
    *,
    reports: tuple[DatasetCertificationReport | None, ...],
    frozen: DatasetCertificationReport,
) -> tuple[
    subject._TechnicalCertificationContext,
    _Builder,
    _Commands,
]:
    root.mkdir(parents=True, exist_ok=True)
    recovery = root / "recovery.json"
    recovery.write_text("recovered", encoding="utf-8")
    builder = _Builder(frozen)
    commands = _Commands(frozen)
    return (
        subject._TechnicalCertificationContext(
            evidence_root=root / "evidence",
            recovery_evidence=recovery,
            generated_at=datetime(2024, 3, 29, tzinfo=UTC),
            actor="reviewer",
            data_root=root,
            builder=cast(DataProductCertificationBuilder, builder),
            commands=cast(DataProductCertificationCommands, commands),
            store=cast(CertificationGovernanceStore, _Store(reports)),
        ),
        builder,
        commands,
    )


def _certify(
    context: subject._TechnicalCertificationContext,
) -> DatasetCertificationReport:
    return subject._technical_certification(
        dataset_id="stock_daily",
        instrument_code="600000.SH",
        snapshot=_snapshot(),
        payload=pl.DataFrame({"trade_date": [date(2024, 3, 28), date(2024, 3, 29)]}),
        context=context,
    )


def test_existing_active_report_must_match_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "probe_consumer_payload", _probe)
    matching = _report("report-active")
    context, _, _ = _context(
        tmp_path / "matching",
        reports=(matching,),
        frozen=matching,
    )
    assert _certify(context) is matching

    conflicting = _report("report-conflict", snapshot_ids=("snapshot-other",))
    context, _, _ = _context(
        tmp_path / "conflicting",
        reports=(conflicting,),
        frozen=conflicting,
    )
    with pytest.raises(ValueError, match="conflicts with active facts"):
        _certify(context)


def test_new_report_is_built_reviewed_and_reloaded_as_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "probe_consumer_payload", _probe)
    frozen = _report("report-new")
    context, builder, commands = _context(
        tmp_path,
        reports=(None, frozen),
        frozen=frozen,
    )

    assert _certify(context) is frozen
    assert builder.request is not None
    assert builder.request.snapshot_ids == ("snapshot-1",)
    assert builder.request.expected_dates == (date(2024, 3, 28), date(2024, 3, 29))
    assert commands.reviewed == (
        "report-new",
        "reviewer",
        datetime(2024, 3, 29, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    "final_report",
    [None, _report("report-other")],
)
def test_new_report_must_become_the_matching_active_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_report: DatasetCertificationReport | None,
) -> None:
    monkeypatch.setattr(subject, "probe_consumer_payload", _probe)
    frozen = _report("report-new")
    context, _, _ = _context(
        tmp_path,
        reports=(None, final_report),
        frozen=frozen,
    )

    with pytest.raises(ValueError, match="did not become active"):
        _certify(context)
