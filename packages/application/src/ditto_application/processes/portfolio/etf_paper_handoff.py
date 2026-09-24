"""Fixed ETF research target to one controlled Paper session."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Protocol
from zoneinfo import ZoneInfo

from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.models import ArtifactKind
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_application.commands.paper_session import (
    CreatePaperSessionCommand,
    PaperSessionCommandHandler,
    PaperSessionCommandReceipt,
    StartPaperSessionCommand,
)
from ditto_application.exceptions import AppCommandError, AppConflictError
from ditto_application.mutation_idempotency import build_mutation_idempotency
from ditto_application.processes.execution.signal_package import (
    SignalPackagePublisher,
    SignalPackagePublishRequest,
)
from ditto_application.processes.portfolio.etf_allocation import ETFAllocationCommand


@dataclass(frozen=True)
class ETFPaperHandoffRequest:
    """Exact target, account, PIT and retry identity for one handoff."""

    allocation_id: str
    version_id: str
    authorization_id: str
    account_id: str
    session_id: str
    idempotency_key: str
    signal_date: str
    decision_date: str
    intended_trade_date: str
    knowledge_cutoff: datetime
    source_snapshot_id: str


@dataclass(frozen=True)
class ETFPaperHandoffFacts:
    """Execution-day facts supplied by a trusted, PIT-bound provider."""

    signal_date: str
    knowledge_cutoff: datetime
    source_snapshot_id: str
    current_positions: dict[int, float]
    investable_instrument_ids: frozenset[int]


class ETFPaperHandoffFactsPort(Protocol):
    """Provide current account and tradability evidence without caller claims."""

    def resolve(self, request: ETFPaperHandoffRequest) -> ETFPaperHandoffFacts:
        """Resolve exact execution-day facts or fail closed."""
        ...


class ETFPaperHandoff:
    """Publish a reviewed fixed target before starting its Paper session."""

    def __init__(
        self,
        *,
        allocations: ETFAllocationCommand,
        artifacts: StrategyArtifactService,
        facts: ETFPaperHandoffFactsPort,
        packages: SignalPackagePublisher,
        sessions: PaperSessionCommandHandler,
    ) -> None:
        self._allocations = allocations
        self._artifacts = artifacts
        self._facts = facts
        self._packages = packages
        self._sessions = sessions

    def handoff(self, request: ETFPaperHandoffRequest) -> PaperSessionCommandReceipt:
        """Publish the exact reviewed target and start an idempotent Paper session."""
        version = next(
            (
                item
                for item in self._allocations.list_versions(request.allocation_id)
                if item.version_id == request.version_id
            ),
            None,
        )
        record = self._artifacts.get_artifact(request.version_id)
        authorization = self._artifacts.get_artifact(request.authorization_id)
        strategy_id = f"etf-allocation:{request.allocation_id}"
        if (
            version is None
            or record is None
            or record.strategy_id != strategy_id
            or record.status != "approved"
            or authorization is None
            or authorization.strategy_id != strategy_id
            or authorization.artifact_type is not ArtifactKind.DIAGNOSTICS
            or authorization.status != "active"
            or authorization.metadata.get("action") != "authorize_paper"
            or authorization.metadata.get("version_id") != request.version_id
            or authorization.metadata.get("account_id") != request.account_id
            or authorization.metadata.get("session_id") != request.session_id
            or authorization.metadata.get("intended_trade_date")
            != request.intended_trade_date
            or authorization.metadata.get("target_request_hash")
            != record.metadata.get("request_hash")
        ):
            raise AppConflictError("ETF Paper target authorization is missing")
        if (
            not request.idempotency_key
            or not request.account_id
            or not request.session_id
        ):
            raise AppCommandError("Paper account, session and retry key are required")
        build_mutation_idempotency(
            operation_id="etf_paper_handoff",
            resource_id=request.session_id,
            raw_key=request.idempotency_key,
            request_payload={
                "allocation_id": request.allocation_id,
                "version_id": request.version_id,
                "authorization_id": request.authorization_id,
                "account_id": request.account_id,
                "signal_date": request.signal_date,
                "intended_trade_date": request.intended_trade_date,
                "source_snapshot_id": request.source_snapshot_id,
            },
        )
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
                idempotency_key=request.idempotency_key,
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
                idempotency_key=f"{request.idempotency_key}:start",
            )
        )
