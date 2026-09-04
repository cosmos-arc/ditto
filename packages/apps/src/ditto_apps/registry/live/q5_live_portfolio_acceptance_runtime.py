"""Production composition for the exactly approved Q5 portfolio closure."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Protocol, TypeVar, cast

import polars as pl
from ditto_application.commands.account import (
    AccountBaselineResult,
    ImportAccountBaselineCommand,
    ImportAccountBaselineHandler,
    PositionBaselineInput,
)
from ditto_application.processes.execution.eod_coordinator import (
    DatasetReadiness,
    EodCoordinator,
    EodStrategyOutcome,
    EodStrategyRequest,
)
from ditto_application.processes.execution.manual_sizing import ManualSizingContext
from ditto_application.processes.execution.signal_package import (
    SignalPackage,
    SignalPackagePublisher,
    SignalPackagePublishRequest,
)
from ditto_application.processes.execution.strategy_run_process import (
    StrategyFacade,
    StrategyRunMode,
    StrategyRunResult,
    StrategyRunServiceConfig,
)
from ditto_application.queries.account import AccountBaselineQuery
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.daily_decision import DailyDecisionQueryFacade
from ditto_application.queries.portfolio_comparison import (
    GetPortfolioComparisonQuery,
    PortfolioComparisonRequest,
)
from ditto_application.queries.source import SourceDataPort
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_backtest.data_feed import Slice
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.provider_payload import ProviderPayloadWriter
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
    ProviderSnapshotWriter,
)
from ditto_execution.paper.session import PaperSessionStorePort
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import MarketSnapshot
from ditto_portfolio.account_projection import PortfolioSnapshot
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)

from ditto_apps.operations.q4_live_account_acceptance import (
    SHANGHAI,
    atomic_write_json,
    canonical_hash,
    canonical_text,
    load_json,
    rfc3339,
)
from ditto_apps.operations.q5_live_portfolio_acceptance import (
    ApprovedLivePortfolioAcceptance,
    approved_live_portfolio_acceptance_request,
    canonical_provider_rows,
    provider_payload_frame,
)
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.infra.config import preload_runtime_secrets

__all__ = ["run_live_portfolio_acceptance"]

_STRATEGY_ID = "seed_etf_industry_rotation"
_STRATEGY_VERSION = 1
_MANUAL_ACCOUNT_ID = "manual-q4-owner-acceptance"
_PAPER_ACCOUNT_ID = "paper-pap09-owner-acceptance"
_PAPER_SESSION_ID = "pap09-session-2026-09-02"
_RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "generated_at",
        "passed",
        "status",
        "request_hash",
        "operator_id",
        "provider",
        "strategy_run",
        "signal_package",
        "manual_execution_baseline",
        "comparison_request",
        "comparison",
        "daily_decision_v2",
        "ui08",
        "safety",
        "evidence_hash",
    }
)
_ZERO_WRITE_SAFETY = {
    "broker_connections": 0,
    "real_orders": 0,
    "paper_or_manual_journal_mutations": 0,
    "strategy_governance_mutations": 0,
    "agent_write_tools": 0,
}

_T = TypeVar("_T")


class _MarketSource(Protocol):
    def fetch_etf_daily(self, **kwargs: object) -> pl.DataFrame: ...


class _Container(Protocol):
    def get(self, dependency_type: type[_T]) -> _T: ...

    def close(self) -> None: ...


def _date_text(value: object, *, field: str) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return canonical_text(value, field=field)


def _live_rows(
    frame: pl.DataFrame,
    approved: ApprovedLivePortfolioAcceptance,
) -> tuple[dict[str, object], ...]:
    if len(frame) != approved.raw_provider_row_count:
        raise ValueError("live provider row count drifted after approval")
    ids = {
        cast(str, row["source_ticker"]): cast(int, row["instrument_id"])
        for row in approved.provider_rows
    }
    selected = {
        str(row["source_ticker"]): row
        for row in frame.to_dicts()
        if str(row.get("source_ticker")) in ids
    }
    if set(selected) != set(ids):
        raise ValueError("live provider strategy universe drifted after approval")
    rows = tuple(
        {
            "instrument_id": ids[ticker],
            "source_ticker": ticker,
            "trade_date": _date_text(raw.get("trade_date"), field="trade_date"),
            "knowledge_date": _date_text(
                raw.get("knowledge_date"), field="knowledge_date"
            ),
            "open": raw.get("open"),
            "high": raw.get("high"),
            "low": raw.get("low"),
            "close": raw.get("close"),
            "pre_close": raw.get("pre_close"),
            "volume": raw.get("volume"),
            "amount": raw.get("amount"),
            "pct_change": raw.get("pct_change"),
        }
        for ticker, raw in sorted(selected.items(), key=lambda item: ids[item[0]])
    )
    canonical = canonical_provider_rows(rows)
    frozen = canonical_provider_rows(approved.provider_rows)
    if canonical_hash(canonical) != canonical_hash(frozen):
        raise ValueError("live provider payload drifted after approval")
    return canonical


def _slice(
    approved: ApprovedLivePortfolioAcceptance,
    *,
    snapshot_id: str,
) -> Slice:
    bars = {
        InstrumentId(cast(int, row["instrument_id"])): MarketSnapshot(
            trade_date=approved.signal_date,
            instrument_id=InstrumentId(cast(int, row["instrument_id"])),
            open=float(cast(float, row["open"])),
            high=float(cast(float, row["high"])),
            low=float(cast(float, row["low"])),
            close=float(cast(float, row["close"])),
            prev_close=float(cast(float, row["pre_close"])),
            volume=float(cast(float, row["volume"])),
            amount=float(cast(float, row["amount"])),
        )
        for row in approved.provider_rows
    }
    return Slice(
        trade_date=approved.signal_date,
        step_time=approved.observed_at.astimezone(SHANGHAI),
        bars=bars,
        source_snapshot_ids=dict.fromkeys(bars, snapshot_id),
    )


def _result_payload(result: StrategyRunResult) -> dict[str, object]:
    return {
        "positions": {
            str(int(key)): value
            for key, value in sorted(
                result.target.positions.items(), key=lambda item: int(item[0])
            )
        },
        "cash_target": result.target.cash_target,
        "factor_values": {
            str(key): dict(sorted(values.items()))
            for key, values in sorted(result.factor_values.items())
        },
    }


def _expected_payload(approved: ApprovedLivePortfolioAcceptance) -> dict[str, object]:
    return {
        "positions": {
            str(key): value for key, value in sorted(approved.target_positions.items())
        },
        "cash_target": approved.cash_target,
        "factor_values": {
            str(key): dict(sorted(values.items()))
            for key, values in sorted(approved.factor_values.items())
        },
    }


def _approved_provider_snapshot(
    approved: ApprovedLivePortfolioAcceptance,
) -> ProviderSnapshot:
    request_parameters_hash = canonical_hash(
        {
            "source": "tushare",
            "dataset_id": "etf_daily",
            "trade_date": approved.signal_date,
            "universe": approved.strategy_universe,
        }
    )
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="etf_daily",
            source="tushare",
            request_start=approved.signal_date,
            request_end=approved.signal_date,
            schema_version="etf.daily.v1",
            checksum=approved.provider_payload_checksum,
            canonical_asset=DataAssetRef(
                dataset_id="etf_daily",
                namespace="market",
                partition_keys=(f"trade_date={approved.signal_date}",),
            ),
            request_parameters_hash=request_parameters_hash,
            response_metadata=(
                ("acceptance_mode", "live_model_paper_manual_closure"),
                ("observed_at", rfc3339(approved.observed_at)),
                ("raw_provider_row_count", str(approved.raw_provider_row_count)),
                ("strategy_universe", approved.strategy_universe),
            ),
            license_record_id=(
                "license:tushare:etf_daily:sha256:"
                "c0f1403a9924d2cc71ad440c08ab743369721661a61d54ecb36637661bbcf6fc"
            ),
            row_count=len(approved.provider_rows),
            payload_uri=(
                "provider_payloads/tushare/etf_daily/"
                f"{approved.provider_payload_checksum}.parquet"
            ),
            payload_retained=True,
            created_at=approved.observed_at,
        )
    )
    if snapshot.snapshot_id != approved.provider_snapshot_id:
        raise ValueError("approved provider snapshot cannot be reconstructed")
    return snapshot


def _run_strategy(
    facade: StrategyFacade,
    approved: ApprovedLivePortfolioAcceptance,
    *,
    mode: StrategyRunMode,
    run_id: str,
) -> StrategyRunResult:
    return facade.run_strategy_from_catalog(
        config=StrategyRunServiceConfig(
            strategy_id=_STRATEGY_ID,
            strategy_version=str(_STRATEGY_VERSION),
            run_id=run_id,
            mode=mode,
            manage_run_lifecycle=False,
        ),
        trade_date=approved.signal_date,
        slice_=_slice(approved, snapshot_id=approved.provider_snapshot_id),
        version=_STRATEGY_VERSION,
    )


def _validate_strategy_and_accounts(
    container: _Container,
    approved: ApprovedLivePortfolioAcceptance,
) -> None:
    strategy = container.get(StrategyQueryFacade)
    active = strategy.get_active_published(_STRATEGY_ID)
    detail = strategy.get_version_detail(_STRATEGY_ID, _STRATEGY_VERSION)
    if (
        active is None
        or active.version != _STRATEGY_VERSION
        or detail is None
        or detail.state != "published"
        or detail.spec_hash != approved.strategy_spec_hash
        or active.spec_json.get("universe") != approved.strategy_universe
    ):
        raise ValueError("active strategy identity drifted after approval")

    account_evidence = load_json(
        approved.account_evidence_path,
        field="account evidence",
    )
    raw_account_identity = account_evidence.get("evidence_identity")
    if not isinstance(raw_account_identity, Mapping):
        raise ValueError("account evidence identity is invalid")
    expected_account = cast("Mapping[str, object]", raw_account_identity)
    ledger = container.get(AccountLedgerQuery)
    manual = ledger.get_manual(
        account_id=_MANUAL_ACCOUNT_ID, as_of=approved.signal_date
    )
    paper = ledger.get_paper(account_id=_PAPER_ACCOUNT_ID, as_of=approved.signal_date)
    if manual.snapshot.ledger_hash != expected_account.get(
        "manual_ledger_hash"
    ) or paper.snapshot.ledger_hash != expected_account.get("paper_ledger_hash"):
        raise ValueError("account ledger drifted after approval")
    paper_store = container.get(PaperSessionStorePort)
    session = paper_store.get_session(_PAPER_SESSION_ID)
    if (
        session is None
        or session.account_id != _PAPER_ACCOUNT_ID
        or session.strategy_id != _STRATEGY_ID
        or session.trade_date != approved.signal_date
    ):
        raise ValueError("Paper session drifted after approval")


def _import_manual_baseline(
    container: _Container,
    approved: ApprovedLivePortfolioAcceptance,
) -> tuple[PortfolioSnapshot, AccountBaselineResult]:
    prices = {
        InstrumentId(cast(int, row["instrument_id"])): Decimal(str(row["close"]))
        for row in approved.provider_rows
    }
    ledger = container.get(AccountLedgerQuery)
    manual = ledger.get_manual(
        account_id=_MANUAL_ACCOUNT_ID,
        as_of=approved.signal_date,
        valuation_prices=prices,
    )
    if not manual.snapshot.valuation_complete:
        raise ValueError("manual account valuation is incomplete")
    positions: list[PositionBaselineInput] = []
    for position in manual.snapshot.positions:
        quantity = int(position.quantity)
        available = int(position.available_quantity)
        if (
            Decimal(quantity) != position.quantity
            or Decimal(available) != position.available_quantity
        ):
            raise ValueError("manual account quantity is not integral")
        positions.append(
            PositionBaselineInput(
                instrument_id=int(position.instrument_id),
                quantity=quantity,
                available_quantity=available,
                average_cost=float(position.average_cost),
                market_value=float(position.market_value),
                unrealized_pnl=float(position.unrealized_pnl),
                realized_pnl=float(position.realized_pnl),
                total_fees=float(position.total_fees),
            )
        )
    result = container.get(ImportAccountBaselineHandler).handle(
        ImportAccountBaselineCommand(
            account_id=_MANUAL_ACCOUNT_ID,
            strategy_id=_STRATEGY_ID,
            snapshot_date=approved.signal_date,
            cash_available=float(manual.snapshot.cash.available),
            cash_settled=float(manual.snapshot.cash.settled),
            cash_frozen=float(manual.snapshot.cash.frozen),
            total_value=float(manual.snapshot.total_value),
            nav=1.0,
            positions=tuple(positions),
        )
    )
    baseline = container.get(AccountBaselineQuery).get_latest(
        account_id=_MANUAL_ACCOUNT_ID,
        strategy_id=_STRATEGY_ID,
        signal_date=approved.signal_date,
    )
    if baseline is None or baseline.account.snapshot_id != result.snapshot_id:
        raise ValueError("derived manual execution baseline was not durably rebuilt")
    return manual.snapshot, result


def _sizing_contexts(
    approved: ApprovedLivePortfolioAcceptance,
    manual_snapshot: PortfolioSnapshot,
) -> dict[int, ManualSizingContext]:
    positions = {int(item.instrument_id): item for item in manual_snapshot.positions}
    prices = {
        cast(int, row["instrument_id"]): float(cast(float, row["close"]))
        for row in approved.provider_rows
    }
    total_value = float(manual_snapshot.total_value)
    cash_available = float(manual_snapshot.cash.available)
    contexts: dict[int, ManualSizingContext] = {}
    for instrument_id in approved.target_positions:
        position = positions.get(instrument_id)
        market_value = float(position.market_value) if position is not None else 0.0
        contexts[instrument_id] = ManualSizingContext(
            nav=total_value,
            current_quantity=int(position.quantity) if position is not None else 0,
            available_quantity=(
                int(position.available_quantity) if position is not None else 0
            ),
            cash_available=cash_available,
            reference_price=prices[instrument_id],
            current_weight=(market_value / total_value if total_value > 0 else 0.0),
        )
    return contexts


def _execute_eod(
    container: _Container,
    approved: ApprovedLivePortfolioAcceptance,
    *,
    sizing_contexts: Mapping[int, ManualSizingContext],
) -> tuple[EodStrategyOutcome, StrategyRunResult]:
    facade = container.get(StrategyFacade)
    publisher = container.get(SignalPackagePublisher)
    captured: dict[str, StrategyRunResult] = {}

    def run_strategy(
        request: EodStrategyRequest, signal_date: str, batch_key: str
    ) -> object:
        if request.strategy_id != _STRATEGY_ID or signal_date != approved.signal_date:
            raise ValueError("EOD strategy identity drifted")
        result = _run_strategy(
            facade,
            approved,
            mode=StrategyRunMode.RECOMMENDATION,
            run_id=batch_key,
        )
        if canonical_hash(_result_payload(result)) != canonical_hash(
            _expected_payload(approved)
        ):
            raise ValueError("strategy output drifted after approval")
        captured[batch_key] = result
        return result.target

    def publish_signals(target: object, snapshots: Mapping[str, str]) -> SignalPackage:
        batch_key = f"eod-{approved.signal_date}-{_STRATEGY_ID}-{_STRATEGY_VERSION}"
        result = captured[batch_key]
        if target is not result.target:
            raise ValueError("EOD target identity drifted")
        return publisher.publish(
            SignalPackagePublishRequest(
                target=result.target,
                strategy_version=str(_STRATEGY_VERSION),
                account_id=_MANUAL_ACCOUNT_ID,
                sleeve_id=f"manual-{_MANUAL_ACCOUNT_ID}-{_STRATEGY_ID}",
                sizing_contexts=sizing_contexts,
                decision_date=approved.signal_date,
                intended_trade_date=approved.intended_trade_date,
                required_datasets=("etf_daily",),
                required_dataset_states=(
                    {
                        "dataset": "etf_daily",
                        "status": "ready",
                        "snapshot_id": approved.provider_snapshot_id,
                        "reason": "live_provider_observed_after_close",
                    },
                ),
                dataset_snapshot_ids=dict(snapshots),
                factor_ids=result.factor_ids,
                factor_values=result.factor_values,
                risk_flags=result.risk_flags,
                threshold=0.0,
            )
        )

    coordinator = EodCoordinator(
        run_strategy=run_strategy,
        publish_signals=publish_signals,
        finalize_signals=publisher.finalize,
        find_staged_signals=lambda request, signal_date, batch_key: (
            publisher.find_staged(
                strategy_id=request.strategy_id,
                run_id=batch_key,
                signal_date=signal_date,
            )
        ),
        run_service=container.get(StrategyRunLifecycleStore),
    )
    outcome = coordinator.run(
        signal_date=approved.signal_date,
        strategies=(
            EodStrategyRequest(
                strategy_id=_STRATEGY_ID,
                strategy_version=str(_STRATEGY_VERSION),
                required_datasets=("etf_daily",),
            ),
        ),
        dataset_states={
            "etf_daily": DatasetReadiness(
                dataset="etf_daily",
                status="ready",
                snapshot_id=approved.provider_snapshot_id,
                reason="live_provider_observed_after_close",
            )
        },
    )[0]
    batch_key = f"eod-{approved.signal_date}-{_STRATEGY_ID}-{_STRATEGY_VERSION}"
    if outcome.status != "completed" or outcome.artifact_id is None:
        raise ValueError(f"live EOD package did not complete: {outcome.reason}")
    return outcome, captured[batch_key]


def _json_value(value: object) -> object:
    if value is None or type(value) in {str, int, float, bool}:
        result = value
    elif isinstance(value, Decimal):
        result = str(value)
    elif isinstance(value, datetime):
        result = rfc3339(value)
    elif isinstance(value, Enum):
        result = str(value.value)
    elif is_dataclass(value) and not isinstance(value, type):
        result = _json_value(asdict(value))
    elif isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        result = {str(key): _json_value(item) for key, item in mapping.items()}
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[object]", value)
        result = [_json_value(item) for item in sequence]
    else:
        raise TypeError(f"unsupported evidence value: {type(value).__name__}")
    return result


def _configured_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} must be explicitly configured")
    return Path(value).expanduser().resolve(strict=False)


def _receipt_path(approved: ApprovedLivePortfolioAcceptance) -> Path:
    signal_date = approved.signal_date.replace("-", "")
    return approved.evidence_root / f"live-portfolio-acceptance-{signal_date}.json"


def _existing_receipt(
    approved: ApprovedLivePortfolioAcceptance,
) -> dict[str, object] | None:
    path = _receipt_path(approved)
    if not path.exists():
        return None
    receipt = load_json(path, field="Q5 portfolio acceptance receipt")
    evidence_hash = receipt.get("evidence_hash")
    body = {key: value for key, value in receipt.items() if key != "evidence_hash"}
    mappings = {
        field: receipt.get(field)
        for field in (
            "provider",
            "strategy_run",
            "signal_package",
            "manual_execution_baseline",
            "comparison_request",
            "comparison",
            "daily_decision_v2",
            "ui08",
            "safety",
        )
    }
    if any(not isinstance(value, Mapping) for value in mappings.values()):
        raise ValueError("existing Q5 portfolio acceptance receipt is invalid")
    provider = cast("Mapping[str, object]", mappings["provider"])
    strategy_run = cast("Mapping[str, object]", mappings["strategy_run"])
    comparison = cast("Mapping[str, object]", mappings["comparison"])
    safety = cast("Mapping[str, object]", mappings["safety"])
    if (
        frozenset(receipt) != _RECEIPT_FIELDS
        or receipt.get("schema") != "ditto.q5-live-portfolio-acceptance.v1"
        or receipt.get("status") != "passed"
        or receipt.get("passed") is not True
        or receipt.get("request_hash") != approved.request_hash
        or evidence_hash != canonical_hash(body)
        or provider.get("snapshot_id") != approved.provider_snapshot_id
        or strategy_run.get("strategy_id") != _STRATEGY_ID
        or strategy_run.get("strategy_version") != _STRATEGY_VERSION
        or comparison.get("as_of") != approved.signal_date
        or safety != _ZERO_WRITE_SAFETY
    ):
        raise ValueError("existing Q5 portfolio acceptance receipt is invalid")
    return receipt


def run_live_portfolio_acceptance(
    proposal: Mapping[str, object],
    *,
    approved_request_hash: str,
    operator_id: str,
    executed_at: datetime,
    source: _MarketSource | None = None,
    container_factory: Callable[[], _Container] = cast(
        "Callable[[], _Container]", make_app_container
    ),
) -> dict[str, object]:
    """Run exact provider drift checks, approved writes, and deterministic queries."""
    approved = approved_live_portfolio_acceptance_request(
        proposal,
        approved_request_hash=approved_request_hash,
    )
    operator = canonical_text(operator_id, field="operator_id")
    executed = executed_at.astimezone(UTC)
    if executed < approved.observed_at:
        raise ValueError("execution precedes the approved provider observation")
    existing = _existing_receipt(approved)
    if existing is not None:
        return existing

    owned_source_container: _Container | None = None
    if source is None:
        preload_runtime_secrets()
        owned_source_container = container_factory()
        source = cast(_MarketSource, owned_source_container.get(SourceDataPort))
    try:
        _live_rows(source.fetch_etf_daily(trade_date=approved.signal_date), approved)
    finally:
        if owned_source_container is not None:
            owned_source_container.close()

    if _configured_path("DITTO_DATA_ROOT") != approved.data_root:
        raise ValueError("DITTO_DATA_ROOT does not match the approved data root")
    if _configured_path("DITTO_TRADING_SQLITE_PATH") != approved.trading_database:
        raise ValueError("DITTO_TRADING_SQLITE_PATH does not match the approved store")

    container = container_factory()
    try:
        _validate_strategy_and_accounts(container, approved)
        facade = container.get(StrategyFacade)
        preview = _run_strategy(
            facade,
            approved,
            mode=StrategyRunMode.RESEARCH,
            run_id=f"preview-{approved.signal_date}-{_STRATEGY_ID}-{_STRATEGY_VERSION}",
        )
        if canonical_hash(_result_payload(preview)) != canonical_hash(
            _expected_payload(approved)
        ):
            raise ValueError("strategy preview drifted after approval")

        payload = provider_payload_frame(
            approved.provider_rows,
            observed_at=approved.observed_at,
        )
        payload_artifact = container.get(ProviderPayloadWriter).retain_payload(
            dataset_id="etf_daily", source="tushare", payload=payload
        )
        if (
            payload_artifact.checksum != approved.provider_payload_checksum
            or payload_artifact.row_count != len(approved.provider_rows)
        ):
            raise ValueError("retained provider payload differs from approval")
        snapshot = _approved_provider_snapshot(approved)
        container.get(ProviderSnapshotWriter).append_snapshot(snapshot)

        manual_snapshot, baseline_result = _import_manual_baseline(container, approved)
        outcome, strategy_result = _execute_eod(
            container,
            approved,
            sizing_contexts=_sizing_contexts(approved, manual_snapshot),
        )
        model_portfolio_id = cast(str, outcome.artifact_id)
        comparison_request = PortfolioComparisonRequest(
            strategy_id=_STRATEGY_ID,
            model_portfolio_id=model_portfolio_id,
            paper_account_id=_PAPER_ACCOUNT_ID,
            manual_account_id=_MANUAL_ACCOUNT_ID,
            paper_session_id=_PAPER_SESSION_ID,
            as_of=approved.signal_date,
            knowledge_cutoff=approved.observed_at,
            publication_cutoff=approved.observed_at,
            source_snapshot_ids=(approved.provider_snapshot_id,),
        )
        comparison = container.get(GetPortfolioComparisonQuery).get(comparison_request)
        decision = container.get(DailyDecisionQueryFacade).get_report_v2(
            strategy_id=_STRATEGY_ID,
            trade_date=approved.signal_date,
            account_id=_MANUAL_ACCOUNT_ID,
        )
        if decision.readiness.get("status") not in {"ready", "review"}:
            raise ValueError("Daily Decision is not reviewable after portfolio closure")

        result: dict[str, object] = {
            "schema": "ditto.q5-live-portfolio-acceptance.v1",
            "generated_at": rfc3339(executed),
            "passed": True,
            "status": "passed",
            "request_hash": approved.request_hash,
            "operator_id": operator,
            "provider": {
                "source": "tushare",
                "raw_row_count": approved.raw_provider_row_count,
                "strategy_universe_row_count": len(approved.provider_rows),
                "snapshot_id": approved.provider_snapshot_id,
                "payload_checksum": approved.provider_payload_checksum,
                "observed_at": rfc3339(approved.observed_at),
                "provider_knowledge_date_retained": True,
                "actual_observation_time_used_for_pit_visibility": True,
                "paper_snapshot_alias": approved.paper_snapshot_alias,
                "paper_alias_exact_bar_equivalent": True,
            },
            "strategy_run": {
                "strategy_id": _STRATEGY_ID,
                "strategy_version": _STRATEGY_VERSION,
                "spec_hash": approved.strategy_spec_hash,
                "batch_key": outcome.batch_key,
                "status": outcome.status,
                "target": _result_payload(strategy_result),
            },
            "signal_package": {
                "artifact_id": model_portfolio_id,
                "checksum": outcome.checksum,
                "source_snapshot_ids": [approved.provider_snapshot_id],
            },
            "manual_execution_baseline": _json_value(baseline_result),
            "comparison_request": _json_value(comparison_request),
            "comparison": _json_value(comparison),
            "daily_decision_v2": _json_value(decision),
            "ui08": {
                "step_9": "backend_exact_query_passed_ui_pending_browser_confirmation",
                "step_10": "reviewable_input_ready_agent_diagnostic_pending",
            },
            "safety": dict(_ZERO_WRITE_SAFETY),
        }
        result["evidence_hash"] = canonical_hash(result)
        atomic_write_json(_receipt_path(approved), result)
        return result
    finally:
        container.close()
