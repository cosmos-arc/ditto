"""Policy registry plus EOD/backtest portfolio-construction adapters."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace

from ditto_backtest.portfolio_construction import (
    PortfolioConstructionContext,
    PortfolioConstructionOutcome,
)
from ditto_portfolio.rebalancing.optimization_models import (
    PortfolioConstructionPolicy,
)
from ditto_strategy.alpha.models import TargetPortfolio

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.eod_coordinator import EodStrategyRequest
from ditto_application.processes.execution.strategy_run_process import (
    StrategyRunResult,
)
from ditto_application.processes.portfolio.construction import (
    PortfolioConstructionIdentity,
    PortfolioConstructionProcess,
    PortfolioConstructionTemporalContext,
)

__all__ = [
    "BacktestPortfolioConstructionAdapter",
    "EodPortfolioConstructionAdapter",
    "PortfolioPolicyBinding",
    "VersionedPortfolioPolicyRegistry",
]


@dataclass(frozen=True)
class PortfolioPolicyBinding:
    """One explicit strategy/sleeve opt-in to a versioned policy."""

    strategy_id: str
    sleeve_id: str
    policy: PortfolioConstructionPolicy

    def __post_init__(self) -> None:
        """Reject an ambiguous registry identity."""
        if not self.strategy_id.strip() or not self.sleeve_id.strip():
            raise AppProcessError("portfolio policy binding identity must be non-empty")


class VersionedPortfolioPolicyRegistry:
    """Deterministic registry whose missing binding preserves legacy behavior."""

    def __init__(self, bindings: Sequence[PortfolioPolicyBinding] = ()) -> None:
        policies: dict[tuple[str, str], PortfolioConstructionPolicy] = {}
        for binding in bindings:
            key = (binding.strategy_id, binding.sleeve_id)
            if key in policies:
                raise AppProcessError(f"duplicate portfolio policy binding: {key!r}")
            policies[key] = binding.policy
        self._policies = policies

    def resolve(
        self,
        identity: PortfolioConstructionIdentity,
    ) -> PortfolioConstructionPolicy | None:
        """Resolve only an exact strategy/sleeve binding."""
        return self._policies.get((identity.strategy_id, identity.sleeve_id))


class BacktestPortfolioConstructionAdapter:
    """Adapt the application process to the backtest consumer-owned port."""

    def __init__(
        self,
        *,
        process: PortfolioConstructionProcess,
        account_id: str,
        sleeve_id: str,
        strategy_id: str,
    ) -> None:
        self._process = process
        self._account_id = account_id
        self._sleeve_id = sleeve_id
        self._strategy_id = strategy_id

    def construct(
        self,
        context: PortfolioConstructionContext,
    ) -> PortfolioConstructionOutcome:
        """Map explicit PIT inputs and preserve structured failure evidence."""
        candidate = TargetPortfolio(
            trade_date=context.trade_date,
            strategy_id=self._strategy_id,
            run_id=_target_run_id(context.candidate_target),
            positions=dict(context.candidate_target.positions),
            cash_target=_target_cash(context.candidate_target),
        )
        decision = self._process.construct(
            candidate=candidate,
            identity=PortfolioConstructionIdentity(
                account_id=self._account_id,
                sleeve_id=self._sleeve_id,
                strategy_id=self._strategy_id,
                run_id=candidate.run_id,
                trade_date=context.trade_date,
            ),
            temporal=PortfolioConstructionTemporalContext(
                decision_time=context.decision_time,
                knowledge_cutoff=context.knowledge_cutoff,
                publication_cutoff=context.publication_cutoff,
                source_snapshot_ids=context.source_snapshot_ids,
            ),
        )
        if not decision.success or decision.target is None:
            return PortfolioConstructionOutcome.failed(
                code=decision.failure_code or "portfolio_construction_failed",
                message=decision.failure_message or "portfolio construction failed",
                evidence=decision.evidence,
            )
        return PortfolioConstructionOutcome.completed(
            target_portfolio=decision.target,
            evidence=decision.evidence,
        )


class EodPortfolioConstructionAdapter:
    """Callable EOD vertical-link adapter inserted before signal publication."""

    def __init__(
        self,
        *,
        process: PortfolioConstructionProcess,
        account_id: str,
        sleeve_id: str,
        temporal_context_for: Callable[
            [str, Mapping[str, str]],
            PortfolioConstructionTemporalContext,
        ],
    ) -> None:
        self._process = process
        self._account_id = account_id
        self._sleeve_id = sleeve_id
        self._temporal_context_for = temporal_context_for

    def __call__(
        self,
        run_result: object,
        request: EodStrategyRequest,
        signal_date: str,
        snapshots: Mapping[str, str],
    ) -> StrategyRunResult:
        """Construct the EOD target or raise to block package publication."""
        if not isinstance(run_result, StrategyRunResult):
            raise AppProcessError(
                "EOD portfolio construction requires StrategyRunResult"
            )
        decision = self._process.construct(
            candidate=run_result.target,
            identity=PortfolioConstructionIdentity(
                account_id=self._account_id,
                sleeve_id=self._sleeve_id,
                strategy_id=request.strategy_id,
                run_id=run_result.run_id,
                trade_date=signal_date,
            ),
            temporal=self._temporal_context_for(signal_date, snapshots),
        )
        if not decision.success or decision.target is None:
            code = decision.failure_code or "portfolio_construction_failed"
            message = decision.failure_message or "portfolio construction failed"
            raise AppProcessError(
                message,
                code="PORTFOLIO_CONSTRUCTION_BLOCKED",
                failure_code=code,
                evidence=dict(decision.evidence),
            )
        return replace(run_result, target=decision.target)


def _target_run_id(target: object) -> str:
    run_id = getattr(target, "run_id", "")
    return run_id if isinstance(run_id, str) else ""


def _target_cash(target: object) -> float:
    cash = getattr(target, "cash_target", 0.0)
    if isinstance(cash, bool) or not isinstance(cash, int | float):
        return 0.0
    return float(cash)
