"""Fail-closed edge contracts for the R3 live snapshot builder."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast

import polars as pl
import pytest
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
)
from ditto_apps.registry.live import r3_live_snapshot_builder as subject
from ditto_data.catalog.certification import CertificationReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader


class _Certification:
    def __init__(self, report: object | None) -> None:
        self.report = report

    def get_active_report(self, _dataset_id: str, _profile: str) -> object | None:
        return self.report


class _Snapshots:
    def __init__(self, snapshot: object | None) -> None:
        self.snapshot = snapshot

    def get_snapshot(self, _snapshot_id: str) -> object | None:
        return self.snapshot


def _report(
    *,
    complete_from: date | None = date(2015, 1, 1),
    target_to: date = date(2026, 8, 1),
    snapshot_ids: tuple[str, ...] = ("snapshot-1",),
) -> SimpleNamespace:
    return SimpleNamespace(
        report_id="report-1",
        generated_at=datetime(2026, 8, 1, tzinfo=UTC),
        coverage=SimpleNamespace(
            complete_from=complete_from,
            target_to=target_to,
        ),
        evidence=SimpleNamespace(snapshot_ids=snapshot_ids),
    )


def _snapshot(
    *,
    dataset_id: str = "stock_daily",
    retained: bool = True,
    payload_uri: str | None = "artifact://snapshot-1",
    request_end: str = "2026-07-31",
) -> SimpleNamespace:
    return SimpleNamespace(
        snapshot_id="snapshot-1",
        dataset_id=dataset_id,
        request_start="2015-01-01",
        request_end=request_end,
        payload_retained=retained,
        payload_uri=payload_uri,
    )


@pytest.mark.parametrize(
    "condition",
    [
        "missing_report",
        "late_start",
        "early_end",
        "missing_snapshot",
        "dataset",
        "retention",
        "empty",
    ],
)
def test_certified_binding_rejects_incomplete_authority(condition: str) -> None:
    report: object | None = _report()
    snapshot: object | None = _snapshot()
    if condition == "missing_report":
        report = None
    elif condition == "late_start":
        report = _report(complete_from=date(2026, 1, 1))
    elif condition == "early_end":
        report = _report(target_to=date(2020, 1, 1))
    elif condition == "missing_snapshot":
        snapshot = None
    elif condition == "dataset":
        snapshot = _snapshot(dataset_id="other")
    elif condition == "retention":
        snapshot = _snapshot(retained=False, payload_uri=None)
    else:
        report = _report(snapshot_ids=())

    with pytest.raises(ValueError):
        subject._certified_dataset_binding(
            certification_reader=cast(CertificationReader, _Certification(report)),
            snapshot_reader=cast(ProviderSnapshotReader, _Snapshots(snapshot)),
            dataset_id="stock_daily",
        )


def test_primary_certification_must_cover_live_snapshot_end() -> None:
    ids = {
        "calendar": "calendar-1",
        "etf_basic": "etf-basic-1",
        "etf_daily": "etf-daily-1",
        "index_daily": "index-daily-1",
    }

    class _Certifications:
        def get_active_report(self, dataset_id: str, _profile: str) -> object:
            return _report(snapshot_ids=(ids[dataset_id],))

    class _SnapshotSet:
        def get_snapshot(self, snapshot_id: str) -> object:
            dataset_id = next(key for key, value in ids.items() if value == snapshot_id)
            values = vars(
                _snapshot(
                    dataset_id=dataset_id,
                    request_end=(
                        "2020-01-01" if dataset_id == "etf_daily" else "2026-07-31"
                    ),
                )
            )
            values["snapshot_id"] = snapshot_id
            return SimpleNamespace(**values)

    with pytest.raises(ValueError, match="primary live provider evidence is stale"):
        subject._certified_source_snapshots(
            certification_reader=cast(CertificationReader, _Certifications()),
            snapshot_reader=cast(ProviderSnapshotReader, _SnapshotSet()),
            lane="etf",
        )


def test_instrument_rules_require_every_member_and_benchmark() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE instrument (
            instrument_id INTEGER,
            ticker TEXT,
            exchange TEXT,
            asset_class TEXT,
            list_date TEXT,
            delist_date TEXT,
            board TEXT
        )
        """
    )

    with pytest.raises(ValueError, match="instrument rules are incomplete"):
        subject._instrument_rules(
            connection,
            (1,),
            authority_snapshot_id="snapshot-1",
        )
    connection.close()


@pytest.mark.parametrize("lane", ["stock", "etf-default", "etf-explicit"])
def test_live_membership_dispatches_only_to_the_selected_lane(
    monkeypatch: pytest.MonkeyPatch,
    lane: str,
) -> None:
    calls: list[tuple[str, object]] = []
    frame = pl.DataFrame({"instrument_id": [1]})

    def stock(*_args: object, **_kwargs: object) -> pl.DataFrame:
        calls.append(("stock", None))
        return frame

    def etf(*_args: object, **kwargs: object) -> pl.DataFrame:
        calls.append(("etf", kwargs.get("tickers")))
        return frame

    monkeypatch.setattr(subject, "_stock_membership", stock)
    monkeypatch.setattr(subject, "_etf_membership", etf)
    selected_lane: subject.LiveLane = "stock" if lane == "stock" else "etf"
    tickers = ("510300.SH",) if lane == "etf-explicit" else None

    result = subject._live_membership(
        cast(sqlite3.Connection, object()),
        lane=selected_lane,
        sessions=(date(2026, 8, 1),),
        authority_snapshot_id="snapshot-1",
        options=subject.LiveResearchSnapshotOptions(etf_tickers=tickers),
    )

    assert result.equals(frame)
    assert calls == [("stock", None) if lane == "stock" else ("etf", tickers)]


@dataclass
class _ArtifactService:
    drift: bool = False
    calls: list[str] = field(default_factory=list)

    def publish_frozen_research_input(self, input_id: str, _payload: bytes) -> str:
        self.calls.append(input_id)
        return "b" * 64 if self.drift else "a" * 64


def _input(input_id: str) -> tuple[ContentAddressedResearchInput, bytes]:
    return (
        ContentAddressedResearchInput(
            input_id=input_id,
            artifact_kind="dependency_test",
            content_hash="a" * 64,
            schema_hash="b" * 64,
        ),
        b"payload",
    )


def test_input_publication_is_hash_verified_and_sorted() -> None:
    service = _ArtifactService()
    published = subject._publish_inputs(
        cast(subject.ResearchArtifactService, service),
        (_input("z-input"), _input("a-input")),
    )

    assert tuple(item.input_id for item in published) == ("a-input", "z-input")
    assert service.calls == ["z-input", "a-input"]

    with pytest.raises(ValueError, match="publication hash drift"):
        subject._publish_inputs(
            cast(subject.ResearchArtifactService, _ArtifactService(drift=True)),
            (_input("input"),),
        )


class _Catalog:
    def __init__(self, drift: str) -> None:
        self.drift = drift

    def get_spine_spec(self, _identity: str) -> object | None:
        return object() if self.drift == "spine" else None

    def save_spine_spec(self, _value: object) -> None:
        return None

    def get_dataset_spec(self, _identity: str) -> object | None:
        return object() if self.drift == "dataset" else None

    def save_dataset_spec(self, _value: object) -> None:
        return None

    def get_spine_snapshot(self, _identity: str) -> object | None:
        return object() if self.drift == "snapshot" else None

    def save_spine_snapshot(self, _value: object) -> None:
        return None


@pytest.mark.parametrize("drift", ["spine", "dataset", "snapshot"])
def test_catalog_parent_replay_rejects_any_identity_drift(drift: str) -> None:
    with pytest.raises(ValueError, match="replay drift"):
        subject._ensure_live_catalog_parents(
            cast(ResearchCatalogService, _Catalog(drift)),
            lane="stock",
            calendar_input=_input("calendar")[0],
            calendar_row_count=1,
            created_at="2026-08-01T00:00:00Z",
        )
