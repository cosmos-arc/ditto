"""Production ETF provider shape reaches storage, PIT queries and Paper valuation."""

from __future__ import annotations

import json
import shutil
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from ditto_application.etf_paper_contracts import ETFPaperHandoffRequest
from ditto_application.exceptions import AppProcessError
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.etf_paper_handoff_facts import LiveETFPaperHandoffFacts
from ditto_application.queries.etf_paper_reference import (
    ETFPaperReferenceQuery,
    paper_reference_candidates,
)
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.snapshot_readiness import SnapshotReadinessQuery
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.ingestion import create_ingestion_bundle
from ditto_apps.registry.infra.init_providers import MetadataDbInitProvider
from ditto_data.catalog.provider_payload import ProviderPayloadReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    create_account_event,
)


def _response(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    api = body["api_name"]
    if api == "trade_cal":
        start = datetime.strptime(body["params"]["start_date"], "%Y%m%d").date()
        end = datetime.strptime(body["params"]["end_date"], "%Y%m%d").date()
        days = [
            start + timedelta(days=offset) for offset in range((end - start).days + 1)
        ]
        fields = ["cal_date", "is_open"]
        rows = [[day.strftime("%Y%m%d"), int(day.weekday() < 5)] for day in days]
    elif api == "etf_basic":
        fields = [
            "ts_code",
            "csname",
            "list_date",
            "list_status",
            "index_code",
            "etf_type",
        ]
        rows = [["510300.SH", "沪深300", "20120528", "L", "000300.SH", "境内"]]
    elif api == "fund_daily":
        fields = [
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "vol",
            "amount",
            "pct_chg",
        ]
        rows = [
            [
                "510300.SH",
                "20260930",
                4.4,
                4.5,
                4.3,
                4.432,
                4.4,
                100000.0,
                44320.0,
                0.7273,
            ]
        ]
    else:
        raise AssertionError(f"unexpected provider call: {api}")
    return httpx.Response(
        200, json={"code": 0, "msg": None, "data": {"fields": fields, "items": rows}}
    )


@pytest.mark.integration
@pytest.mark.pit
def test_provider_inputs_preserve_prices_and_refuse_missing_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock,
) -> None:
    repo = Path(__file__).parents[5]
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DITTO_CONFIG_ROOT", str(repo))
    monkeypatch.setenv("DITTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("DITTO_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("TUSHARE_TOKEN", "recorded-provider-test")
    root = tmp_path / "state"
    root.mkdir()
    assert MetadataDbInitProvider().initialize(root).success
    respx_mock.post("http://api.tushare.pro").mock(side_effect=_response)
    with create_ingestion_bundle("tushare") as bundle:
        for dataset in ("calendar", "etf_basic", "etf_daily"):
            result = bundle.coordinator.ingest_date(dataset, "2026-09-30")
            assert result.status == "success", result
        assert (
            bundle.coordinator.ingest_date("etf_daily", "2026-09-30").status
            == "skipped"
        )

    with (
        closing(make_app_container()) as container,
        SqliteAccountEventJournal(str(tmp_path / "paper.sqlite")) as journal,
    ):
        snapshots = container.get(ProviderSnapshotReader)
        by_dataset = {item.dataset_id: item for item in snapshots.list_snapshots()}
        account = journal.create_account(
            AccountDefinition(
                account_id="isolated-paper",
                kind=AccountKind.PAPER,
                name="isolated test capital",
                opened_at=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        now = datetime.now(UTC)
        journal.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_id="opening",
                    event_type=AccountEventType.OPENING_CASH,
                    trade_date="2026-09-30",
                    settlement_date="2026-09-30",
                    recorded_at=now,
                    idempotency_key="opening",
                    actor="test",
                    source=AccountEventSource.PAPER_ENGINE,
                    gross_amount=Decimal("10000"),
                ),
            )
        )
        metadata = container.get(MetadataQueryFacade)
        instrument = metadata.list_etf_candidates(
            asof="2026-09-30",
            cutoff=(datetime.now(UTC) + timedelta(seconds=2)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            source_snapshot_id=by_dataset["etf_basic"].snapshot_id,
        )[0]
        journal.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_id="holding",
                    event_type=AccountEventType.OPENING_POSITION,
                    trade_date="2026-09-30",
                    settlement_date="2026-09-30",
                    recorded_at=now,
                    idempotency_key="holding",
                    actor="test",
                    source=AccountEventSource.PAPER_ENGINE,
                    instrument_id=InstrumentId(instrument.instrument_id),
                    quantity=Decimal("100"),
                    price=Decimal("4.432"),
                    gross_amount=Decimal("443.2"),
                ),
            )
        )
        facts = LiveETFPaperHandoffFacts(
            metadata=container.get(MetadataQueryFacade),
            readiness=container.get(SnapshotReadinessQuery),
            snapshots=snapshots,
            payloads=container.get(ProviderPayloadReader),
            ledger=AccountLedgerQuery(journal=journal),
        )
        request = ETFPaperHandoffRequest(
            allocation_id="target",
            version_id="v1",
            authorization_id="approved",
            account_id=account.account_id,
            session_id="session",
            idempotency_key="once",
            signal_date="2026-09-30",
            decision_date=now.date().isoformat(),
            intended_trade_date="2026-10-01",
            knowledge_cutoff=datetime.now(UTC) + timedelta(seconds=2),
            source_snapshot_id=by_dataset["etf_basic"].snapshot_id,
            input_snapshot_ids={"etf_daily": by_dataset["etf_daily"].snapshot_id},
        )
        resolved = facts.resolve(request)
        assert resolved.current_positions[instrument.instrument_id] == pytest.approx(
            443.2 / 10443.2
        )
        assert resolved.investable_instrument_ids == frozenset()
        assert tuple(resolved.unavailable_reasons.values()) == (
            ("trading_restriction:missing", "trading_currency:missing"),
        )
        assert resolved.next_trading_day == "2026-10-01"
        with pytest.raises(AppProcessError, match="mismatched"):
            facts.resolve(
                replace(
                    request,
                    input_snapshot_ids={"etf_daily": request.source_snapshot_id},
                )
            )
        with pytest.raises(AppProcessError, match="future"):
            facts.resolve(
                replace(request, knowledge_cutoff=datetime(2026, 9, 30, tzinfo=UTC))
            )
        payload_uri = by_dataset["etf_daily"].payload_uri
        assert payload_uri is not None
        payload = root / payload_uri
        payload.unlink()
        with pytest.raises(AppProcessError, match="payload is unavailable"):
            facts.resolve(request)


_DECLARATION: dict[str, object] = {
    "confirmed_at": "2026-09-30",
    "confirmed_by": "recorded integration test",
    "instruments": [
        {
            "source_ticker": "510300.SH",
            "facts": {
                "trading_currency": {
                    "value": "CNY",
                    "unit": "text",
                    "effective_from": "2026-09-01",
                    "basis": "recorded test basis: currency",
                },
                "trading_restriction": {
                    "value": "none",
                    "unit": "text",
                    "effective_from": "2026-09-01",
                    "basis": "recorded test basis: restriction",
                },
                "lot_size": {
                    "value": "100",
                    "unit": "count",
                    "effective_from": "2026-09-01",
                    "basis": "recorded test basis: lot",
                },
                "tick_size": {
                    "value": "0.001",
                    "unit": "price",
                    "effective_from": "2026-09-01",
                    "basis": "recorded test basis: tick",
                },
                "settlement_cycle": {
                    "value": "1",
                    "unit": "days",
                    "effective_from": "2026-09-01",
                    "basis": "recorded test basis: settlement",
                },
                "price_limit_pct": {
                    "value": "0.1",
                    "unit": "ratio",
                    "effective_from": "2026-09-01",
                    "basis": "recorded test basis: limit",
                },
                "commission_rate": {
                    "value": "0.0001",
                    "unit": "ratio",
                    "effective_from": "2026-09-01",
                    "basis": "recorded test basis: commission",
                },
                "min_commission": {
                    "value": "5",
                    "unit": "cny",
                    "effective_from": "2026-09-01",
                    "basis": "recorded test basis: minimum",
                },
                "stamp_duty_rate": {
                    "value": "0",
                    "unit": "ratio",
                    "effective_from": "2026-09-01",
                    "basis": "recorded test basis: stamp",
                },
                "transfer_fee_rate": {
                    "value": "0.00001",
                    "unit": "ratio",
                    "effective_from": "2026-09-01",
                    "basis": "recorded test basis: transfer",
                },
            },
        }
    ],
}


@pytest.mark.integration
@pytest.mark.pit
def test_config_declaration_supplements_paper_reference_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock,
) -> None:
    """config-source etf_reference goes through the real ingestion chain."""
    repo = Path(__file__).parents[5]
    config_root = tmp_path / "config-root"
    shutil.copytree(repo / "config", config_root / "config")
    (config_root / "config" / "default" / "etf_reference.json").write_text(
        json.dumps(_DECLARATION, ensure_ascii=False)
    )
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DITTO_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("DITTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("DITTO_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("TUSHARE_TOKEN", "recorded-provider-test")
    root = tmp_path / "state"
    root.mkdir()
    assert MetadataDbInitProvider().initialize(root).success
    respx_mock.post("http://api.tushare.pro").mock(side_effect=_response)
    with create_ingestion_bundle("tushare") as bundle:
        for dataset in ("calendar", "etf_basic", "etf_daily"):
            result = bundle.coordinator.ingest_date(dataset, "2026-09-30")
            assert result.status == "success", result
    with create_ingestion_bundle("config") as bundle:
        result = bundle.coordinator.ingest_date("etf_reference", "2026-09-30")
        assert result.status == "success", result
        assert result.row_count == 10
        assert (
            bundle.coordinator.ingest_date("etf_reference", "2026-09-30").status
            == "skipped"
        )

    with (
        closing(make_app_container()) as container,
        SqliteAccountEventJournal(str(tmp_path / "paper.sqlite")) as journal,
    ):
        snapshots = container.get(ProviderSnapshotReader)
        by_dataset = {item.dataset_id: item for item in snapshots.list_snapshots()}
        declaration_snapshot = by_dataset["etf_reference"]
        assert declaration_snapshot.source == "config"
        metadata = container.get(MetadataQueryFacade)
        instrument = metadata.list_etf_candidates(
            asof="2026-09-30",
            cutoff=(datetime.now(UTC) + timedelta(seconds=2)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            source_snapshot_id=by_dataset["etf_basic"].snapshot_id,
        )[0]
        composed = paper_reference_candidates(
            metadata=metadata,
            readiness=container.get(SnapshotReadinessQuery),
            snapshots=snapshots,
            payloads=container.get(ProviderPayloadReader),
            query=ETFPaperReferenceQuery(
                asof="2026-09-30",
                cutoff=datetime.now(UTC) + timedelta(seconds=2),
                snapshot_id=by_dataset["etf_basic"].snapshot_id,
                input_snapshot_ids={
                    "etf_daily": by_dataset["etf_daily"].snapshot_id,
                    "etf_reference": declaration_snapshot.snapshot_id,
                },
            ),
        )[instrument.instrument_id]
        rules = {
            name: field.value
            for name, field in composed.fields.items()
            if field.source == "config"
        }
        assert rules["trading_currency"] == "CNY"
        assert rules["trading_restriction"] == "none"
        assert {
            name: float(value)
            for name, value in rules.items()
            if name not in ("trading_currency", "trading_restriction")
        } == pytest.approx(
            {
                "lot_size": 100.0,
                "tick_size": 0.001,
                "settlement_cycle": 1.0,
                "price_limit_pct": 0.1,
                "commission_rate": 0.0001,
                "min_commission": 5.0,
                "stamp_duty_rate": 0.0,
                "transfer_fee_rate": 0.00001,
            }
        )
        account = journal.create_account(
            AccountDefinition(
                account_id="isolated-paper",
                kind=AccountKind.PAPER,
                name="isolated test capital",
                opened_at=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        journal.append(
            create_account_event(
                account=account,
                draft=AccountEventDraft(
                    event_id="opening",
                    event_type=AccountEventType.OPENING_CASH,
                    trade_date="2026-09-30",
                    settlement_date="2026-09-30",
                    recorded_at=datetime.now(UTC),
                    idempotency_key="opening",
                    actor="test",
                    source=AccountEventSource.PAPER_ENGINE,
                    gross_amount=Decimal("10000"),
                ),
            )
        )
        facts = LiveETFPaperHandoffFacts(
            metadata=metadata,
            readiness=container.get(SnapshotReadinessQuery),
            snapshots=snapshots,
            payloads=container.get(ProviderPayloadReader),
            ledger=AccountLedgerQuery(journal=journal),
        )
        resolved = facts.resolve(
            ETFPaperHandoffRequest(
                allocation_id="target",
                version_id="v1",
                authorization_id="approved",
                account_id=account.account_id,
                session_id="session",
                idempotency_key="once",
                signal_date="2026-09-30",
                decision_date=datetime.now(UTC).date().isoformat(),
                intended_trade_date="2026-10-01",
                knowledge_cutoff=datetime.now(UTC) + timedelta(seconds=2),
                source_snapshot_id=by_dataset["etf_basic"].snapshot_id,
                input_snapshot_ids={
                    "etf_daily": by_dataset["etf_daily"].snapshot_id,
                    "etf_reference": declaration_snapshot.snapshot_id,
                },
            )
        )
        assert resolved.investable_instrument_ids == frozenset(
            {instrument.instrument_id}
        )
        assert tuple(resolved.unavailable_reasons.values()) == ((),)
        # 声明缺失的字段：补充快照不给 undisclosed 标的可投资性。
        with pytest.raises(AppProcessError, match="absent, mismatched or future"):
            facts.resolve(
                ETFPaperHandoffRequest(
                    allocation_id="target",
                    version_id="v1",
                    authorization_id="approved",
                    account_id=account.account_id,
                    session_id="session",
                    idempotency_key="once",
                    signal_date="2026-09-30",
                    decision_date=datetime.now(UTC).date().isoformat(),
                    intended_trade_date="2026-10-01",
                    knowledge_cutoff=datetime.now(UTC) + timedelta(seconds=2),
                    source_snapshot_id=by_dataset["etf_basic"].snapshot_id,
                    input_snapshot_ids={
                        "etf_daily": by_dataset["etf_daily"].snapshot_id,
                        "etf_reference": by_dataset["etf_basic"].snapshot_id,
                    },
                )
            )


@pytest.mark.integration
@pytest.mark.pit
def test_config_declaration_refuses_unresolved_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock,
) -> None:
    """声明引用未注册标的时摄取 fail closed，不产生观察行。"""
    repo = Path(__file__).parents[5]
    config_root = tmp_path / "config-root"
    shutil.copytree(repo / "config", config_root / "config")
    declaration = {
        "confirmed_at": "2026-09-30",
        "confirmed_by": "recorded integration test",
        "instruments": [
            {
                "source_ticker": "999999.SH",
                "facts": {
                    "trading_currency": {
                        "value": "CNY",
                        "unit": "text",
                        "effective_from": "2026-09-01",
                        "basis": "recorded test basis",
                    }
                },
            }
        ],
    }
    (config_root / "config" / "default" / "etf_reference.json").write_text(
        json.dumps(declaration, ensure_ascii=False)
    )
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DITTO_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("DITTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("DITTO_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("TUSHARE_TOKEN", "recorded-provider-test")
    root = tmp_path / "state"
    root.mkdir()
    assert MetadataDbInitProvider().initialize(root).success
    respx_mock.post("http://api.tushare.pro").mock(side_effect=_response)
    with create_ingestion_bundle("tushare") as bundle:
        for dataset in ("calendar", "etf_basic", "etf_daily"):
            result = bundle.coordinator.ingest_date(dataset, "2026-09-30")
            assert result.status == "success", result
    with create_ingestion_bundle("config") as bundle:
        result = bundle.coordinator.ingest_date("etf_reference", "2026-09-30")
        assert result.status == "failed", result
        assert "unresolved" in (result.message or "") or "unresolved" in (
            result.error or ""
        )
