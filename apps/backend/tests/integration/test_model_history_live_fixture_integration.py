"""MODEL history live-fixture acceptance: real DI, saved targets, pin replay."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest
from ditto_application.queries.model_history import (
    GetModelHistoryQuery,
    ModelHistoryRequest,
)
from ditto_application.signal_package_contract import compute_signal_package_checksum
from ditto_apps.registry.container import make_app_container
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_platform.foundation import SQLiteClient, SQLitePool
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)

STRATEGY_ID = "live-model-history"
NOW = datetime(2026, 3, 1, 1, 0, tzinfo=UTC)
KNOWLEDGE = datetime(2026, 3, 5, 16, 0, tzinfo=UTC)

_BARS = (
    ("2026-03-02", 600519, 10.0),
    ("2026-03-03", 600519, 11.0),
    ("2026-03-04", 600519, 12.1),
    ("2026-03-02", 510300, 20.0),
    ("2026-03-03", 510300, 22.0),
    ("2026-03-04", 510300, 20.0),
)


def _package_record(
    artifact_id: str,
    signal_date: str,
    weights: dict[int, float],
    snapshot_id: str,
) -> StrategyArtifactRecord:
    payload: dict[str, object] = {
        "dataset_snapshot_ids": {"stock_daily": snapshot_id},
        "factor_ids": [],
        "factor_values": {},
        "intents": [],
        "risk_flags": [],
        "selection_reasons": {
            str(instrument): {"target_weight": weight}
            for instrument, weight in weights.items()
        },
        "signal_date": signal_date,
        "strategy_id": STRATEGY_ID,
        "strategy_version": "1",
    }
    return StrategyArtifactRecord(
        artifact_id=artifact_id,
        strategy_id=STRATEGY_ID,
        run_id=f"eod-{signal_date}-{STRATEGY_ID}-1",
        artifact_type=ArtifactKind.SIGNAL_PACKAGE,
        file_path=f"evidence/{artifact_id}.json",
        metadata={
            **payload,
            "schema_version": "1.0",
            "business_payload": payload,
            "batch_key": f"eod-{signal_date}-{STRATEGY_ID}-1",
            "checksum": compute_signal_package_checksum(payload),
            "no_rebalance": True,
            "outcome": "no_rebalance",
        },
        status="active",
        created_at=NOW.isoformat(),
    )


def _seed(root: Path) -> str:
    """Retain prices and save two real signal packages."""
    metadata = root / "metadata" / "metadata.sqlite"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    pool = SQLitePool(str(metadata))
    client = SQLiteClient(pool)
    try:
        payload = pl.DataFrame(
            {
                "instrument_id": [row[1] for row in _BARS],
                "trade_date": [row[0] for row in _BARS],
                "open": [row[2] for row in _BARS],
                "high": [row[2] for row in _BARS],
                "low": [row[2] for row in _BARS],
                "close": [row[2] for row in _BARS],
                "volume": [1000.0] * len(_BARS),
                "amount": [10000.0] * len(_BARS),
                "published_at": [
                    datetime.fromisoformat(f"{row[0]}T10:00:00+00:00") for row in _BARS
                ],
                "available_at": [
                    datetime.fromisoformat(f"{row[0]}T10:00:00+00:00") for row in _BARS
                ],
            }
        )
        artifact = FilesystemProviderPayloadStore(root).retain_payload(
            dataset_id="stock_daily",
            source="model_history_fixture",
            payload=payload,
        )
        snapshot = ProviderSnapshot.create(
            ProviderSnapshotDraft(
                dataset_id="stock_daily",
                source="model_history_fixture",
                request_start="2026-03-02",
                request_end="2026-03-04",
                schema_version="market.stock_daily.v1",
                checksum=artifact.checksum,
                canonical_asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2026-03-02",),
                ),
                request_parameters_hash="sha256:model-history-request-v1",
                response_metadata=(("fixture", "model-history-live"),),
                license_record_id="license:model-history:v1",
                row_count=artifact.row_count,
                payload_uri=artifact.uri,
                payload_retained=True,
                created_at=NOW,
            )
        )
        SQLiteProviderSnapshotStore(client).append_snapshot(snapshot)

        writer = SQLiteStrategyArtifactWriter(pool)
        writer.init_schema()
        service = StrategyArtifactService(
            reader=SQLiteStrategyArtifactReader(pool),
            writer=writer,
        )
        service.save_artifact(
            _package_record(
                "signal-package-live-a",
                "2026-03-02",
                {600519: 0.6, 510300: 0.4},
                snapshot.snapshot_id,
            )
        )
        service.save_artifact(
            _package_record(
                "signal-package-live-b",
                "2026-03-03",
                {600519: 1.0},
                snapshot.snapshot_id,
            )
        )
        client.close()
        return snapshot.snapshot_id
    finally:
        client.close()


def _request(
    *,
    artifact_ids: tuple[str, ...] = (),
    initial_capital: str = "100",
) -> ModelHistoryRequest:
    return ModelHistoryRequest(
        strategy_id=STRATEGY_ID,
        start_date="2026-03-02",
        end_date="2026-03-04",
        initial_capital=Decimal(initial_capital),
        knowledge_cutoff=KNOWLEDGE,
        publication_cutoff=KNOWLEDGE,
        artifact_ids=artifact_ids,
    )


@pytest.mark.integration
def test_model_history_live_fixture_replays_and_pins_saved_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix="ditto-model-history-") as temporary:
        root = Path(temporary)
        _seed(root)
        for name, path in {
            "DITTO_STATE_ROOT": root,
            "DITTO_CONFIG_ROOT": root / "config",
            "DITTO_CACHE_ROOT": root / "cache",
            "DITTO_LOG_DIR": root / "logs",
            "SQLITE_PATH": root / "metadata/metadata.sqlite",
        }.items():
            monkeypatch.setenv(name, str(path))
        monkeypatch.setenv("ENVIRONMENT", "testing")

        store_before = _store_state(root)
        container = make_app_container()
        try:
            query = container.get(GetModelHistoryQuery)
            view = query.history(_request())
            replay = query.history(_request())
        finally:
            container.close()
        # GET-style replays leave the artifact and payload stores untouched.
        assert _store_state(root) == store_before

        # 03-02: 60@10 + 40@20 = 100; 03-03 rebalance at 110 (all 600519);
        # 03-04 drift: 10 @ 12.1 = 121.
        assert [point.total_value for point in view.points] == [
            Decimal("100.00"),
            Decimal("110.00"),
            Decimal("121.00"),
        ]
        assert view.points[1].period_return == Decimal("0.1")
        assert view.points[2].period_return == Decimal("121") / Decimal(
            "110"
        ) - Decimal("1")
        assert view.segments[0].linked_return == Decimal("1.1") * (
            Decimal("121") / Decimal("110")
        ) - Decimal("1")
        assert [target.artifact_id for target in view.targets] == [
            "signal-package-live-a",
            "signal-package-live-b",
        ]
        assert all(point.external_flow == Decimal("0") for point in view.points)
        assert view.method == "twr-linked-v1"
        assert view.result_id.startswith("model-history:sha256:")
        assert replay.result_id == view.result_id

        # A later publish supersedes the 03-03 target through the real store;
        # the pinned replay of the old identity must stay byte-identical.
        pool = SQLitePool(str(root / "metadata/metadata.sqlite"))
        client = SQLiteClient(pool)
        try:
            service = StrategyArtifactService(
                reader=SQLiteStrategyArtifactReader(pool),
                writer=SQLiteStrategyArtifactWriter(pool),
            )
            assert service.archive_artifact("signal-package-live-b") is True
            superseding = service.save_artifact(
                _package_record(
                    "signal-package-live-c",
                    "2026-03-03",
                    {600519: 0.5, 510300: 0.5},
                    _snapshot_id_of(root),
                )
            )
            assert superseding.status == "active"
            client.close()
        finally:
            client.close()

        container = make_app_container()
        try:
            query = container.get(GetModelHistoryQuery)
            pinned = query.history(
                _request(
                    artifact_ids=(
                        "signal-package-live-a",
                        "signal-package-live-b",
                    )
                )
            )
            fresh = query.history(_request())
        finally:
            container.close()

        assert pinned.result_id == view.result_id
        assert pinned.points[2].total_value == Decimal("121.00")
        assert [target.artifact_id for target in fresh.targets] == [
            "signal-package-live-a",
            "signal-package-live-c",
        ]
        # 03-03: 55@11 + 55@22 = 110; 03-04: 5@12.1 + 2.5@20 = 110.50.
        assert fresh.points[2].total_value == Decimal("110.50")
        assert fresh.result_id != view.result_id


def _snapshot_id_of(root: Path) -> str:
    client = SQLiteClient(SQLitePool(str(root / "metadata/metadata.sqlite")))
    try:
        store = SQLiteProviderSnapshotStore(client)
        snapshots = store.list_snapshots(dataset_id="stock_daily")
        if not snapshots:
            raise AssertionError("fixture snapshot is missing")
        return snapshots[0].snapshot_id
    finally:
        client.close()


def _store_state(root: Path) -> tuple[tuple[str, str] | str, ...]:
    """Artifact ids with statuses plus the retained payload file names."""
    pool = SQLitePool(str(root / "metadata/metadata.sqlite"))
    service = StrategyArtifactService(
        reader=SQLiteStrategyArtifactReader(pool),
        writer=SQLiteStrategyArtifactWriter(pool),
    )
    artifacts = tuple(
        (record.artifact_id, record.status)
        for record in sorted(
            service.list_by_strategy(STRATEGY_ID), key=lambda r: r.artifact_id
        )
    )
    payloads_dir = root / "payloads"
    payloads = (
        tuple(sorted(path.name for path in payloads_dir.rglob("*") if path.is_file()))
        if payloads_dir.exists()
        else ()
    )
    return (*artifacts, *payloads)
