"""Production ETF/Paper app over isolated, admitted recorded evidence."""

from __future__ import annotations

import importlib
import os
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import polars as pl
from ditto_application.commands.paper_account import (
    CreatePaperAccountCommand,
    CreatePaperAccountHandler,
)
from ditto_apps.registry.fresh_runtime import create_fresh_runtime
from ditto_data.catalog.certification import (
    CertificationEvidence,
    DatasetCertificationReport,
    EvidenceCheck,
)
from ditto_data.catalog.certification_store import SQLiteCertificationStore
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.coverage import DatasetCoverage
from ditto_data.catalog.field_evidence import CertifiedField
from ditto_data.catalog.license import DatasetLicenseDraft, DatasetLicenseRecord
from ditto_data.catalog.license_store import SQLiteDatasetLicenseStore
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleStatus,
)
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_data.models.metadata import InstrumentRegistration
from ditto_data.storage.metadata.instrument.instrument_writer import InstrumentWriter
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_platform.foundation import SQLiteClient, SQLitePool

if os.environ.get("DITTO_ENVIRONMENT") != "testing":
    raise RuntimeError("ETF Paper fixture requires testing mode")
_root = Path(os.environ["DITTO_ACCEPTANCE_DATA_ROOT"]).resolve()
if not _root.is_relative_to(Path("/tmp").resolve()):
    raise RuntimeError("ETF Paper fixture requires isolated /tmp state")
_state = _root / "state"
os.environ.update(
    {
        "DITTO_STATE_ROOT": str(_state),
        "SQLITE_PATH": str(_state / "metadata/metadata.sqlite"),
        "DITTO_TRADING_SQLITE_PATH": str(_state / "trading/trading.sqlite"),
        "ENVIRONMENT": "testing",
    }
)

SIGNAL = date(2026, 9, 1)
TRADE = date(2026, 9, 2)
SIGNAL_VISIBLE = datetime(2026, 9, 1, 8, tzinfo=UTC)
EXECUTION_VISIBLE = datetime(2026, 9, 3, 7, tzinfo=UTC)
ETF_ID = 2_000_101
BLOCKED_ID = 2_000_102
ACCOUNT_ID = "etf-paper-browser"
_SOURCE = "recorded"
_RULES = {
    "asset_class": "etf",
    "trading_currency": "CNY",
    "lot_size": "100",
    "tick_size": "0.001",
    "settlement_cycle": "1",
    "price_limit_pct": "0.1",
    "commission_rate": "0.0003",
    "min_commission": "5",
    "stamp_duty_rate": "0",
    "transfer_fee_rate": "0",
}
_BAR_FIELDS = ("open", "high", "low", "close", "pre_close", "volume", "amount")


def _license(client: SQLiteClient, dataset: str) -> DatasetLicenseRecord:
    record = DatasetLicenseRecord.create(
        DatasetLicenseDraft(
            dataset_id=dataset,
            source=_SOURCE,
            terms_version="isolated-test-v1",
            effective_from=date(2026, 1, 1),
            effective_to=None,
            local_cache="allowed",
            derivative_compute="allowed",
            display="allowed",
            redistribution="prohibited",
            notes="isolated recorded acceptance data",
            reviewed_by="fixture",
            reviewed_at=SIGNAL_VISIBLE,
        )
    )
    SQLiteDatasetLicenseStore(client).append_license(record)
    return record


def _snapshot(
    client: SQLiteClient,
    payloads: FilesystemProviderPayloadStore,
    *,
    dataset: str,
    day: date,
    visible: datetime,
    frame: pl.DataFrame,
    license_record: DatasetLicenseRecord,
) -> ProviderSnapshot:
    artifact = payloads.retain_payload(
        dataset_id=dataset, source=_SOURCE, payload=frame
    )
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=dataset,
            source=_SOURCE,
            request_start=day.isoformat(),
            request_end=day.isoformat(),
            schema_version=f"fixture.{dataset}.v1",
            checksum=artifact.checksum,
            canonical_asset=DataAssetRef(dataset_id=dataset, namespace="market"),
            request_parameters_hash=f"fixture:{dataset}:{day}",
            response_metadata=(("fixture", "etf-paper-browser"),),
            license_record_id=license_record.record_id,
            row_count=artifact.row_count,
            payload_uri=artifact.uri,
            payload_retained=True,
            created_at=visible,
        )
    )
    SQLiteProviderSnapshotStore(client).append_snapshot(snapshot)
    lifecycle = SQLitePartitionLifecycleStore(client)
    chunk = f"etf-paper-{dataset}-{day}"
    lifecycle.plan_partition(
        PartitionCheckpoint(
            chunk_id=chunk,
            dataset_id=dataset,
            source=_SOURCE,
            request_start=snapshot.request_start,
            request_end=snapshot.request_end,
            status=PartitionLifecycleStatus.PLANNED,
            last_successful_stage=None,
            attempt=1,
            retry_budget=3,
            payload_id=None,
            catalog_asset_id=None,
            lineage_run_id=None,
            ingestion_log_id=None,
            error_code=None,
            updated_at=visible,
        )
    )
    for stage in (
        PartitionLifecycleStatus.FETCHED,
        PartitionLifecycleStatus.NORMALIZED,
        PartitionLifecycleStatus.PIT_PASSED,
        PartitionLifecycleStatus.DQ_PASSED,
        PartitionLifecycleStatus.PAYLOAD_COMMITTED,
        PartitionLifecycleStatus.CATALOG_ATTESTED,
        PartitionLifecycleStatus.LINEAGE_RECORDED,
        PartitionLifecycleStatus.SUCCESS_RECORDED,
        PartitionLifecycleStatus.COMPLETE,
    ):
        lifecycle.advance_partition(
            chunk,
            stage,
            occurred_at=visible,
            evidence_id=(
                f"payload:{snapshot.checksum}:{chunk}:{snapshot.snapshot_id}"
                if stage is PartitionLifecycleStatus.PAYLOAD_COMMITTED
                else snapshot.snapshot_id
            ),
        )
    return snapshot


def _certify(
    client: SQLiteClient,
    *,
    dataset: str,
    snapshots: tuple[ProviderSnapshot, ...],
    licenses: tuple[DatasetLicenseRecord, ...],
    fields: tuple[str, ...],
) -> None:
    dates = [date.fromisoformat(item.request_start) for item in snapshots]
    check = (EvidenceCheck("fixture", "evidence://etf-paper-browser", True),)
    report = DatasetCertificationReport.create(
        dataset_id=dataset,
        profile="selection-fields-v1",
        coverage=DatasetCoverage(
            dataset_id=dataset,
            schedule="trading_days",
            target_from=min(dates),
            target_to=max(dates),
            native_from=min(dates),
            native_to=max(dates),
            actual_from=min(dates),
            actual_to=max(dates),
            raw_from=min(dates),
            complete_from=min(dates),
            expected_partitions=len(snapshots),
            actual_partitions=len(snapshots),
            gaps=(),
            exceptions=(),
            collected_at=EXECUTION_VISIBLE,
        ),
        evidence=CertificationEvidence(
            source_ids=(_SOURCE,),
            schema_versions=tuple(sorted({item.schema_version for item in snapshots})),
            snapshot_ids=tuple(item.snapshot_id for item in snapshots),
            dq_rule_version="fixture-v1",
            dq_results=check,
            pit_replay_results=check,
            fallback_history=("none",),
            override_history=(),
            freshness_results=check,
            recovery_results=check,
            license_record_ids=tuple(item.record_id for item in licenses),
            consumer_results=check,
            certified_fields=tuple(
                CertifiedField(
                    field=field,
                    snapshot_id=snapshot.snapshot_id,
                    instrument_ids=(ETF_ID, BLOCKED_ID),
                    covered_from=date.fromisoformat(snapshot.request_start),
                    covered_to=date.fromisoformat(snapshot.request_end),
                    available_at=snapshot.created_at,
                    publication_at=snapshot.created_at,
                    time_precision="timestamp",
                    observed_at=snapshot.created_at,
                    evidence_uri=f"evidence://etf-paper-browser/{field}",
                )
                for snapshot in snapshots
                for field in fields
            ),
        ),
        generated_at=EXECUTION_VISIBLE,
    )
    store = SQLiteCertificationStore(client)
    store.append_report(report)
    store.approve_report(
        report.report_id, reviewer="fixture", reviewed_at=EXECUTION_VISIBLE
    )


def _reference_rows(snapshot: ProviderSnapshot, day: date) -> list[list[object]]:
    rows: list[list[object]] = []
    for instrument, restriction, tracking in (
        (ETF_ID, "none", "000300.SH"),
        (BLOCKED_ID, "suspended", "000300.SH"),
    ):
        values = {
            "tracking_index": tracking,
            "trading_restriction": restriction,
            "price_close": "10" if day == SIGNAL else "10.1",
            **_RULES,
        }
        for field, value in values.items():
            rows.append(
                [
                    instrument,
                    field,
                    value,
                    "text",
                    day.isoformat(),
                    snapshot.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    day.isoformat(),
                    _SOURCE,
                    snapshot.snapshot_id,
                ]
            )
    return rows


def _seed() -> dict[str, str]:
    create_fresh_runtime(_state)
    pool = SQLitePool(str(_state / "metadata/metadata.sqlite"))
    client = SQLiteClient(pool)
    payloads = FilesystemProviderPayloadStore(_state)
    try:
        writer = InstrumentWriter(client=client, cache=None)
        for instrument, ticker, name in (
            (ETF_ID, "510300", "沪深300ETF-Paper验收"),
            (BLOCKED_ID, "510301", "受限ETF-Paper验收"),
        ):
            writer.register(
                instrument,
                InstrumentRegistration(
                    source_ticker=f"{ticker}.SH",
                    ticker=ticker,
                    name=name,
                    exchange="SSE",
                    asset_class="etf",
                    list_date="2020-01-01",
                    source=_SOURCE,
                ),
            )
        for day, previous, following in (
            ("2026-09-01", None, "2026-09-02"),
            ("2026-09-02", "2026-09-01", "2026-09-03"),
            ("2026-09-03", "2026-09-02", None),
        ):
            client.execute(
                """INSERT INTO trading_calendar
                   (trade_date, is_open, exchange, prev_trade_date, next_trade_date)
                   VALUES (?, 1, 'SSE', ?, ?)""",
                [day, previous, following],
            )
        client.commit()
        ref_license = _license(client, "etf_reference")
        daily_license = _license(client, "etf_daily")
        calendar_license = _license(client, "calendar")
        signal = _snapshot(
            client,
            payloads,
            dataset="etf_reference",
            day=SIGNAL,
            visible=SIGNAL_VISIBLE,
            frame=pl.DataFrame(
                {
                    "instrument_id": [ETF_ID, BLOCKED_ID],
                    "trade_date": [SIGNAL.isoformat()] * 2,
                }
            ),
            license_record=ref_license,
        )
        execution = _snapshot(
            client,
            payloads,
            dataset="etf_reference",
            day=TRADE,
            visible=EXECUTION_VISIBLE,
            frame=pl.DataFrame(
                {
                    "instrument_id": [ETF_ID, BLOCKED_ID],
                    "trade_date": [TRADE.isoformat()] * 2,
                }
            ),
            license_record=ref_license,
        )
        client.executemany(
            """INSERT INTO etf_reference_observation
               (instrument_id, field, value, unit, observed_on, published_at,
                effective_from, source, source_snapshot_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            _reference_rows(signal, SIGNAL) + _reference_rows(execution, TRADE),
        )
        client.commit()
        _certify(
            client,
            dataset="etf_reference",
            snapshots=(signal, execution),
            licenses=(ref_license,),
            fields=("tracking_index", "trading_restriction", "price_close", *_RULES),
        )
        bar = _snapshot(
            client,
            payloads,
            dataset="etf_daily",
            day=TRADE,
            visible=EXECUTION_VISIBLE,
            frame=pl.DataFrame(
                {
                    "source_ticker": ["510300.SH"],
                    "trade_date": [TRADE.isoformat()],
                    "event_time": [datetime(2026, 9, 2, 7, tzinfo=UTC)],
                    "published_at": [EXECUTION_VISIBLE],
                    "available_at": [EXECUTION_VISIBLE],
                    "open": [10.0],
                    "high": [10.2],
                    "low": [9.9],
                    "close": [10.1],
                    "pre_close": [10.0],
                    "volume": [1_000_000.0],
                    "amount": [10_000_000.0],
                }
            ),
            license_record=daily_license,
        )
        _certify(
            client,
            dataset="etf_daily",
            snapshots=(bar,),
            licenses=(daily_license,),
            fields=_BAR_FIELDS,
        )
        _snapshot(
            client,
            payloads,
            dataset="calendar",
            day=SIGNAL,
            visible=SIGNAL_VISIBLE,
            frame=pl.DataFrame(
                {
                    "trade_date": ["2026-09-01", "2026-09-02", "2026-09-03"],
                    "is_open": [True, True, True],
                }
            ),
            license_record=calendar_license,
        )
    finally:
        pool.close_all()
    with SqliteAccountEventJournal(str(_state / "trading/trading.sqlite")) as journal:
        CreatePaperAccountHandler(journal=journal, clock=lambda: SIGNAL_VISIBLE).handle(
            CreatePaperAccountCommand(
                account_id=ACCOUNT_ID,
                name="ETF Paper 浏览器验收",
                opened_at=SIGNAL_VISIBLE,
                trade_date=SIGNAL.isoformat(),
                initial_cash=Decimal("100000"),
                idempotency_key="etf-browser-opening",
            )
        )
    return {
        "signal_reference": signal.snapshot_id,
        "execution_reference": execution.snapshot_id,
        "market": bar.snapshot_id,
        "account_id": ACCOUNT_ID,
    }


_identity = _seed()
app = importlib.import_module("ditto_apps.main").app


@app.get("/system-fixture/etf-paper")
async def fixture_identity() -> dict[str, str]:
    """Expose only fixed test identities; requests use production routes."""
    return _identity
