"""Production ETF provider shape reaches storage, PIT queries and Paper valuation."""

from __future__ import annotations

import json
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
