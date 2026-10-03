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
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleEvent,
    PartitionLifecycleReader,
    PartitionLifecycleStatus,
)

_CUTOFF = datetime(2026, 8, 1, tzinfo=UTC)


def _snapshot(
    *,
    snapshot_id: str = "snapshot-1",
    dataset_id: str = "stock_daily",
    retained: bool = True,
    payload_uri: str | None = "artifact://snapshot-1",
    request_start: str = "2015-01-01",
    request_end: str = "2026-07-31",
    created_at: datetime = _CUTOFF,
) -> SimpleNamespace:
    return SimpleNamespace(
        snapshot_id=snapshot_id,
        dataset_id=dataset_id,
        source="tushare",
        request_start=request_start,
        request_end=request_end,
        checksum=f"checksum-{snapshot_id}",
        payload_retained=retained,
        payload_uri=payload_uri,
        created_at=created_at,
    )


class _Snapshots:
    def __init__(
        self,
        snapshots: tuple[SimpleNamespace, ...],
        *,
        hide: frozenset[str] = frozenset(),
    ) -> None:
        self._snapshots = snapshots
        self._hide = hide

    def list_snapshots(self, *, dataset_id: str) -> tuple[SimpleNamespace, ...]:
        return tuple(item for item in self._snapshots if item.dataset_id == dataset_id)

    def get_snapshot(self, snapshot_id: str) -> SimpleNamespace | None:
        if snapshot_id in self._hide:
            return None
        return next(
            (item for item in self._snapshots if item.snapshot_id == snapshot_id),
            None,
        )


class _Lifecycle:
    """Mark exactly the addressed snapshots as durably completed."""

    def __init__(self, snapshots: tuple[SimpleNamespace, ...]) -> None:
        self._snapshots = snapshots

    def list_complete(self, *, dataset_id: str) -> tuple[PartitionCheckpoint, ...]:
        return tuple(
            PartitionCheckpoint(
                chunk_id=f"chunk-{snapshot.snapshot_id}",
                dataset_id=snapshot.dataset_id,
                source="tushare",
                request_start=snapshot.request_start,
                request_end=snapshot.request_end,
                status=PartitionLifecycleStatus.COMPLETE,
                last_successful_stage=PartitionLifecycleStatus.COMPLETE,
                attempt=1,
                retry_budget=3,
                payload_id=(
                    f"payload:{snapshot.checksum}:synthetic:{snapshot.snapshot_id}"
                ),
                catalog_asset_id=None,
                lineage_run_id=None,
                ingestion_log_id=None,
                error_code=None,
                updated_at=_CUTOFF,
            )
            for snapshot in self._snapshots
            if snapshot.dataset_id == dataset_id
        )

    def list_events(self, chunk_id: str) -> tuple[PartitionLifecycleEvent, ...]:
        snapshot = next(
            (
                item
                for item in self._snapshots
                if f"chunk-{item.snapshot_id}" == chunk_id
            ),
            None,
        )
        if snapshot is None:
            return ()
        return (
            PartitionLifecycleEvent(
                event_id=1,
                chunk_id=chunk_id,
                from_status=PartitionLifecycleStatus.SUCCESS_RECORDED,
                to_status=PartitionLifecycleStatus.COMPLETE,
                attempt=1,
                evidence_id=snapshot.snapshot_id,
                error_code=None,
                occurred_at=_CUTOFF,
            ),
        )


@pytest.mark.parametrize(
    "condition",
    [
        "late_start",
        "early_end",
        "missing_snapshot",
        "dataset",
        "retention",
        "empty",
    ],
)
def test_observed_binding_rejects_incomplete_history(condition: str) -> None:
    snapshot = _snapshot()
    hide: frozenset[str] = frozenset()
    if condition == "late_start":
        snapshot = _snapshot(request_start="2026-01-01")
    elif condition == "early_end":
        snapshot = _snapshot(request_end="2020-01-01")
    elif condition == "missing_snapshot":
        hide = frozenset({"snapshot-1"})
    elif condition == "dataset":
        snapshot = _snapshot(dataset_id="other")
    elif condition == "retention":
        snapshot = _snapshot(retained=False, payload_uri=None)
    else:
        snapshot = None

    snapshots = () if snapshot is None else (snapshot,)
    with pytest.raises(ValueError):
        subject._observed_dataset_binding(
            snapshot_reader=cast(
                ProviderSnapshotReader, _Snapshots(snapshots, hide=hide)
            ),
            lifecycle_reader=cast(PartitionLifecycleReader, _Lifecycle(snapshots)),
            dataset_id="stock_daily",
            observed_cutoff=_CUTOFF,
        )


def test_primary_observed_snapshot_is_the_latest_covering_live_end() -> None:
    snapshots = tuple(
        _snapshot(
            snapshot_id=snapshot_id,
            dataset_id=dataset_id,
        )
        for dataset_id, snapshot_id in (
            ("calendar", "calendar-1"),
            ("etf_basic", "etf-basic-1"),
            ("etf_daily", "etf-daily-1"),
            ("etf_daily", "etf-daily-older"),
            ("index_daily", "index-daily-1"),
        )
    )
    older = snapshots[3]
    snapshots = (
        *snapshots[:3],
        _snapshot(
            snapshot_id=older.snapshot_id,
            dataset_id=older.dataset_id,
            request_end="2026-06-30",
        ),
        snapshots[4],
    )

    sources, authority, _by_dataset, bindings = subject._observed_source_snapshots(
        snapshot_reader=cast(ProviderSnapshotReader, _Snapshots(snapshots)),
        lifecycle_reader=cast(PartitionLifecycleReader, _Lifecycle(snapshots)),
        lane="etf",
        observed_cutoff=_CUTOFF,
    )

    assert authority == "etf-daily-1"
    assert tuple(binding.dataset_id for binding in bindings) == (
        "calendar",
        "etf_basic",
        "etf_daily",
        "index_daily",
    )
    assert sources == tuple(sorted(item.snapshot_id for item in snapshots))


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
