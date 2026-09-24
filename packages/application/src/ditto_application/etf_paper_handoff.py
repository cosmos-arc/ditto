"""Fixed ETF research target to one controlled Paper session."""

from __future__ import annotations

from hashlib import sha256
from math import isfinite
from zoneinfo import ZoneInfo

from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.models import TargetPortfolio

from ditto_application.commands.paper_session import (
    CreatePaperSessionCommand,
    PaperSessionCommandHandler,
    PaperSessionCommandReceipt,
    StartPaperSessionCommand,
)
from ditto_application.etf_paper_contracts import (
    ETFPaperHandoffFactsPort,
    ETFPaperHandoffRequest,
)
from ditto_application.exceptions import AppCommandError, AppConflictError
from ditto_application.mutation_idempotency import build_mutation_idempotency
from ditto_application.processes.execution.signal_package import (
    SignalPackagePublisher,
    SignalPackagePublishRequest,
)
from ditto_application.processes.portfolio.etf_allocation import ETFAllocationCommand


class ETFPaperHandoff:
    """Publish a reviewed fixed target before starting its Paper session."""

    def __init__(
        self,
        *,
        allocations: ETFAllocationCommand,
        facts: ETFPaperHandoffFactsPort,
        packages: SignalPackagePublisher,
        sessions: PaperSessionCommandHandler,
    ) -> None:
        self._allocations = allocations
        self._facts = facts
        self._packages = packages
        self._sessions = sessions

    def handoff(self, request: ETFPaperHandoffRequest) -> PaperSessionCommandReceipt:
        """Publish the exact reviewed target and start an idempotent Paper session."""
        version = self._allocations.authorized_paper_version(
            allocation_id=request.allocation_id,
            version_id=request.version_id,
            authorization_id=request.authorization_id,
            account_id=request.account_id,
            session_id=request.session_id,
            intended_trade_date=request.intended_trade_date,
        )
        strategy_id = f"etf-allocation:{request.allocation_id}"
        if (
            not request.idempotency_key
            or not request.account_id
            or not request.session_id
        ):
            raise AppCommandError("Paper account, session and retry key are required")
        identity = build_mutation_idempotency(
            operation_id="etf_paper_handoff",
            resource_id=request.session_id,
            raw_key=request.idempotency_key,
            request_payload={
                "allocation_id": request.allocation_id,
                "version_id": request.version_id,
                "authorization_id": request.authorization_id,
                "account_id": request.account_id,
                "signal_date": request.signal_date,
                "decision_date": request.decision_date,
                "intended_trade_date": request.intended_trade_date,
                "knowledge_cutoff": request.knowledge_cutoff.isoformat(),
                "source_snapshot_id": request.source_snapshot_id,
            },
        )
        session_key = sha256(
            f"{identity.key_hash}:{identity.request_hash}".encode("ascii")
        ).hexdigest()
        if (
            request.signal_date < version.asof
            or request.intended_trade_date <= request.signal_date
        ):
            raise AppCommandError("Paper execution must follow the research decision")
        if request.knowledge_cutoff.tzinfo is None:
            raise AppCommandError("ETF Paper knowledge cutoff needs a timezone")
        if (
            request.knowledge_cutoff.astimezone(ZoneInfo("Asia/Shanghai"))
            .date()
            .isoformat()
            > request.decision_date
        ):
            raise AppCommandError("Paper evidence is after the decision date")
        facts = self._facts.resolve(request)
        if (
            facts.signal_date != request.signal_date
            or facts.knowledge_cutoff != request.knowledge_cutoff
            or facts.source_snapshot_id != request.source_snapshot_id
            or not facts.source_snapshot_id
            or not facts.signal_ledger_hash
        ):
            raise AppConflictError("ETF Paper market evidence identity changed")
        selected = set(version.weights)
        blocked = selected - facts.investable_instrument_ids
        if blocked:
            raise AppConflictError(
                f"ETF tools are not investable; choose alternatives: {sorted(blocked)}"
            )
        if any(
            instrument_id <= 0 or not isfinite(weight) or weight < 0 or weight > 1
            for instrument_id, weight in facts.current_positions.items()
        ):
            raise AppCommandError("Paper account positions are invalid")
        target = TargetPortfolio(
            trade_date=request.signal_date,
            strategy_id=strategy_id,
            run_id=f"eod-{request.signal_date}-{strategy_id}-{request.version_id}",
            positions={
                InstrumentId(i): float(weight) for i, weight in version.weights.items()
            },
            cash_target=float(version.cash_weight),
        )
        self._sessions.create(
            CreatePaperSessionCommand(
                session_id=request.session_id,
                account_id=request.account_id,
                strategy_id=strategy_id,
                trade_date=request.intended_trade_date,
                idempotency_key=session_key,
            )
        )
        package = self._packages.publish(
            SignalPackagePublishRequest(
                target=target,
                strategy_version=request.version_id,
                account_id=request.account_id,
                sleeve_id=f"paper-{request.account_id}-{strategy_id}",
                sizing_contexts={},
                decision_date=request.decision_date,
                intended_trade_date=request.intended_trade_date,
                required_datasets=("etf_reference",),
                required_dataset_states=(),
                dataset_snapshot_ids={
                    "etf_reference": facts.source_snapshot_id,
                    "etf_research_reference": version.source_snapshot_id,
                    "paper_signal_ledger": facts.signal_ledger_hash,
                },
                execution_scope="paper",
                current_positions=facts.current_positions,
                origin_version_id=request.version_id,
            )
        )
        finalized = self._packages.finalize(package)
        if finalized.outcome not in {"completed", "no_rebalance"}:
            raise AppConflictError("ETF Signal Package could not be activated")
        return self._sessions.start(
            StartPaperSessionCommand(
                session_id=request.session_id,
                idempotency_key=f"{session_key}:start",
            )
        )
