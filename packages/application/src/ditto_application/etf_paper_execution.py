"""Execute one approved ETF target through the existing Paper fill ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from hashlib import sha256
from typing import Literal, cast
from zoneinfo import ZoneInfo

import orjson
from ditto_execution.paper.session import PaperSessionStatus, PaperSessionStorePort
from ditto_kernel.trading import DEFAULT_SLIPPAGE_BPS

from ditto_application.etf_paper_contracts import (
    ETFPaperExecutionFactsPort,
    ETFPaperExecutionRequest,
    etf_paper_run_id,
)
from ditto_application.exceptions import AppCommandError, AppConflictError
from ditto_application.execution_dto import TradeIntent
from ditto_application.paper_contracts import PaperFillAssumptionInput
from ditto_application.processes.execution.manual_sizing import (
    ManualSizingRequest,
    ManualSizingService,
)
from ditto_application.processes.execution.operate_paper_session import (
    OperatePaperOrderCommand,
    OperatePaperReceipt,
    OperatePaperSession,
)
from ditto_application.processes.execution.signal_package import SignalPackagePublisher
from ditto_application.processes.execution.signal_package_models import SignalPackage
from ditto_application.processes.portfolio.etf_allocation import (
    ETFAllocationCommand,
    ETFAllocationVersion,
)

_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class ETFPaperExecutionOutcome:
    """One package intent's durable Paper result, or a sizing block."""

    intent_id: str
    instrument_id: int
    status: str
    reason: str | None
    execution_id: str | None
    ledger_event_id: str | None


class ETFPaperExecution:
    """Resolve each fixed intent against two PIT dates and append Paper only."""

    def __init__(
        self,
        *,
        allocations: ETFAllocationCommand,
        packages: SignalPackagePublisher,
        sessions: PaperSessionStorePort,
        facts: ETFPaperExecutionFactsPort,
        operator: OperatePaperSession,
    ) -> None:
        self._allocations = allocations
        self._packages = packages
        self._sessions = sessions
        self._facts = facts
        self._operator = operator
        self._sizing = ManualSizingService()

    def execute(
        self, request: ETFPaperExecutionRequest
    ) -> tuple[ETFPaperExecutionOutcome, ...]:
        """Evaluate a frozen D target with D+1 evidence available after close."""
        version, signal_cutoff, reference_cutoff, package = self._validated_context(
            request
        )
        strategy_id = f"etf-allocation:{request.allocation_id}"
        outcomes: list[ETFPaperExecutionOutcome] = []
        for intent in sorted(
            package.intents,
            key=lambda item: (item.direction != "sell", item.instrument_id),
        ):
            outcomes.append(
                self._execute_intent(
                    request,
                    version,
                    signal_cutoff,
                    reference_cutoff,
                    package,
                    strategy_id,
                    intent,
                )
            )
        return tuple(outcomes)

    def _validated_context(
        self, request: ETFPaperExecutionRequest
    ) -> tuple[ETFAllocationVersion, datetime, datetime, SignalPackage]:
        if not request.idempotency_key:
            raise AppCommandError("ETF Paper execution retry key is required")
        version = self._allocations.authorized_paper_version(
            allocation_id=request.allocation_id,
            version_id=request.version_id,
            authorization_id=request.authorization_id,
            account_id=request.account_id,
            session_id=request.session_id,
            intended_trade_date=request.intended_trade_date,
        )
        if request.signal_date != version.asof:
            raise AppConflictError(
                "ETF Paper sizing needs the saved signal-day version"
            )
        signal_cutoff = datetime.fromisoformat(
            version.knowledge_cutoff.replace("Z", "+00:00")
        )
        _after_close(signal_cutoff, request.signal_date, "signal")
        _follows_close(
            request.execution_cutoff, request.intended_trade_date, "execution"
        )
        if request.execution_cutoff <= signal_cutoff:
            raise AppCommandError("Paper execution must follow the signal cutoff")
        session = self._sessions.get_session(request.session_id)
        strategy_id = f"etf-allocation:{request.allocation_id}"
        if (
            session is None
            or session.strategy_id != strategy_id
            or session.account_id != request.account_id
            or session.trade_date != request.intended_trade_date
        ):
            raise AppConflictError("approved ETF Paper session identity changed")
        run_id = etf_paper_run_id(
            signal_date=request.signal_date,
            strategy_id=strategy_id,
            version_id=request.version_id,
            account_id=request.account_id,
        )
        package = self._packages.find_active_paper(
            strategy_id=strategy_id,
            run_id=run_id,
            signal_date=request.signal_date,
            version_id=request.version_id,
            account_id=request.account_id,
            intended_trade_date=request.intended_trade_date,
        )
        if (
            package.dataset_snapshot_ids.get("etf_research_reference")
            != version.source_snapshot_id
        ):
            raise AppConflictError("ETF Paper package target source changed")
        if not package.dataset_snapshot_ids.get("etf_reference"):
            raise AppConflictError("ETF Paper package valuation source is missing")
        reference_cutoff = _package_reference_cutoff(package)
        if not signal_cutoff <= reference_cutoff <= request.execution_cutoff:
            raise AppConflictError("ETF Paper package valuation cutoff is invalid")
        return version, signal_cutoff, reference_cutoff, package

    def _execute_intent(
        self,
        request: ETFPaperExecutionRequest,
        version: ETFAllocationVersion,
        signal_cutoff: datetime,
        reference_cutoff: datetime,
        package: SignalPackage,
        strategy_id: str,
        intent: TradeIntent,
    ) -> ETFPaperExecutionOutcome:
        if (
            intent.strategy_id != strategy_id
            or intent.signal_date != request.signal_date
        ):
            raise AppConflictError("ETF Paper package intent identity changed")
        if intent.direction not in {"buy", "sell"}:
            raise AppConflictError("ETF Paper package intent direction is invalid")
        order_key = _intent_key(package.artifact_id, intent.intent_id)
        request_hash = _request_hash(request, package.checksum, intent.intent_id)
        replay = self._operator.replay_etf(request.session_id, order_key, request_hash)
        if replay is not None:
            return _outcome(intent.intent_id, intent.instrument_id, replay)
        session = self._sessions.get_session(request.session_id)
        if session is None or session.status is not PaperSessionStatus.RUNNING:
            raise AppConflictError("approved ETF Paper session is not running")
        facts = self._facts.resolve(
            request,
            instrument_id=intent.instrument_id,
            signal_snapshot_id=package.dataset_snapshot_ids["etf_reference"],
            signal_cutoff=signal_cutoff,
            valuation_cutoff=reference_cutoff,
        )
        if facts.signal_ledger_hash != package.dataset_snapshot_ids.get(
            "paper_signal_ledger"
        ):
            raise AppConflictError("ETF signal-day Paper ledger changed")
        sizing = self._sizing.size(
            ManualSizingRequest(
                direction=cast("Literal['buy', 'sell']", intent.direction),
                target_weight=intent.target_weight,
                nav=facts.signal_nav,
                current_quantity=facts.signal_current_quantity,
                available_quantity=facts.signal_available_quantity,
                cash_available=facts.signal_cash_available,
                reference_price=facts.signal_reference_price,
                instrument_id=intent.instrument_id,
                trade_date=request.signal_date,
                lot_size=facts.signal_rules.lot_size,
                commission_rate=facts.signal_rules.commission_rate,
                min_commission=facts.signal_rules.min_commission,
                settlement_cycle=facts.signal_rules.settlement_cycle,
            )
        )
        if sizing.readiness != "ready" or sizing.direction != intent.direction:
            raise AppConflictError(
                f"ETF intent {intent.intent_id} cannot be sized: {sizing.reason}"
            )
        if sizing.rounded_quantity <= 0:
            return ETFPaperExecutionOutcome(
                intent_id=intent.intent_id,
                instrument_id=intent.instrument_id,
                status="no_rebalance",
                reason=sizing.reason,
                execution_id=None,
                ledger_event_id=None,
            )
        market = facts.execution_market
        _after_close(market.observed_at, request.intended_trade_date, "market")
        if (
            market.dataset_id != "etf_daily"
            or market.source_snapshot_id != request.market_snapshot_id
            or market.observed_at > request.execution_cutoff
            or market.publication_cutoff > request.execution_cutoff
        ):
            raise AppConflictError("ETF execution market evidence is not visible")
        receipt = self._operator.execute_etf(
            OperatePaperOrderCommand(
                session_id=request.session_id,
                idempotency_key=order_key,
                order_id=order_key,
                instrument_id=intent.instrument_id,
                side=intent.direction,
                order_type="market",
                quantity=sizing.rounded_quantity,
                price=None,
                trade_date=request.intended_trade_date,
                market=market,
                rules=facts.execution_rules,
                assumption=PaperFillAssumptionInput(
                    assumption_id="etf-eod-close-v1",
                    version=1,
                    reference_price_field="close",
                    slippage_bps=DEFAULT_SLIPPAGE_BPS,
                ),
                decision_at=reference_cutoff,
                execution_at=request.execution_cutoff,
                settlement_date=facts.settlement_date,
                position_quantity=facts.execution_position_quantity,
                available_quantity=facts.execution_available_quantity,
                cash_available=facts.execution_cash_available,
                request_identity_hash=request_hash,
                expected_ledger_hash=facts.execution_ledger_hash,
                rule_snapshot_id=request.reference_snapshot_id,
                rule_cutoff=request.execution_cutoff.isoformat(),
            )
        )
        return _outcome(intent.intent_id, intent.instrument_id, receipt)


def _after_close(value: datetime, trade_date: str, label: str) -> None:
    if (
        value.tzinfo is None
        or value.astimezone(_SHANGHAI).date().isoformat() != trade_date
        or value.astimezone(_SHANGHAI).time() < time(15)
    ):
        raise AppCommandError(f"ETF {label} cutoff must follow its market close")


def _follows_close(value: datetime, trade_date: str, label: str) -> None:
    """
    Allow a cutoff on or after the trade date's close.

    The canonical daily-bar producer stamps ``knowledge_date = trade_date + 1``,
    so the intended-trade-date bar only becomes visible the next calendar day;
    the fill still books the intended trade date.
    """
    if value.tzinfo is None:
        raise AppCommandError(f"ETF {label} cutoff needs a timezone")
    local = value.astimezone(_SHANGHAI)
    if local.date().isoformat() < trade_date or (
        local.date().isoformat() == trade_date and local.time() < time(15)
    ):
        raise AppCommandError(f"ETF {label} cutoff must follow its market close")


def _package_reference_cutoff(package: SignalPackage) -> datetime:
    """Recover the handoff's declared reference-data cutoff from the package."""
    raw = package.dataset_snapshot_ids.get("paper_signal_reference_cutoff", "")
    try:
        cutoff = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppConflictError("ETF Paper package valuation cutoff is missing") from exc
    if cutoff.tzinfo is None:
        raise AppConflictError("ETF Paper package valuation cutoff is missing")
    return cutoff


def _intent_key(package_id: str, intent_id: str) -> str:
    return f"etf-intent:{sha256(f'{package_id}:{intent_id}'.encode()).hexdigest()[:32]}"


def _request_hash(
    request: ETFPaperExecutionRequest, package_checksum: str, intent_id: str
) -> str:
    payload = {
        "allocation_id": request.allocation_id,
        "version_id": request.version_id,
        "authorization_id": request.authorization_id,
        "account_id": request.account_id,
        "session_id": request.session_id,
        "signal_date": request.signal_date,
        "intended_trade_date": request.intended_trade_date,
        "package_checksum": package_checksum,
        "intent_id": intent_id,
    }
    digest = sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()
    return f"etf-paper-request:sha256:{digest}"


def _outcome(
    intent_id: str, instrument_id: int, receipt: OperatePaperReceipt
) -> ETFPaperExecutionOutcome:
    return ETFPaperExecutionOutcome(
        intent_id=intent_id,
        instrument_id=instrument_id,
        status=receipt.execution.reality_status,
        reason=receipt.execution.reason,
        execution_id=receipt.execution.execution_id,
        ledger_event_id=receipt.execution.ledger_event_id,
    )
