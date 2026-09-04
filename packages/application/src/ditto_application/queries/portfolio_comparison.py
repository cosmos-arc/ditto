"""Exact application read model for MODEL/PAPER/MANUAL portfolio comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from ditto_portfolio.portfolio_comparison import (
    NormalizedPortfolio,
    PortfolioAttribution,
    PortfolioComparisonError,
    PortfolioDriftView,
    PortfolioValuationInput,
    compare_portfolio_pair,
    normalize_portfolio,
)

from ditto_application.exceptions import AppQueryError

__all__ = [
    "GetPortfolioComparisonQuery",
    "PortfolioComparisonQueryPort",
    "PortfolioComparisonRequest",
    "PortfolioComparisonSource",
    "PortfolioComparisonSourcePort",
    "PortfolioComparisonView",
]


@dataclass(frozen=True, kw_only=True)
class PortfolioComparisonRequest:
    """Caller-selected identities; no field may silently resolve to latest."""

    strategy_id: str
    model_portfolio_id: str
    paper_account_id: str
    manual_account_id: str
    paper_session_id: str
    as_of: str
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    valuation_snapshot_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class PortfolioComparisonSource:
    """Provider facts loaded before application aggregation."""

    model: PortfolioValuationInput
    paper: PortfolioValuationInput
    manual: PortfolioValuationInput
    paper_attribution: PortfolioAttribution = field(
        default_factory=PortfolioAttribution
    )
    manual_attribution: PortfolioAttribution = field(
        default_factory=PortfolioAttribution
    )


@runtime_checkable
class PortfolioComparisonSourcePort(Protocol):
    """Load all three legs from exact source identities."""

    def load(self, request: PortfolioComparisonRequest) -> PortfolioComparisonSource:
        """Return source facts without mutating targets, sessions, or ledgers."""
        ...


@dataclass(frozen=True, kw_only=True)
class PortfolioComparisonView:
    """Unified three-column read model produced only by application."""

    strategy_id: str
    as_of: str
    valuation_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]
    model: NormalizedPortfolio
    paper: NormalizedPortfolio
    manual: NormalizedPortfolio
    model_vs_paper: PortfolioDriftView
    model_vs_manual: PortfolioDriftView
    paper_vs_manual: PortfolioDriftView


@runtime_checkable
class PortfolioComparisonQueryPort(Protocol):
    """Agent/apps-facing leaf contract for exact comparison evidence."""

    def get(self, request: PortfolioComparisonRequest) -> PortfolioComparisonView:
        """Return a complete same-snapshot comparison or fail closed."""
        ...


def _request_error(reason: str, request: PortfolioComparisonRequest) -> AppQueryError:
    return AppQueryError(
        f"portfolio comparison failed closed: {reason}",
        code="PORTFOLIO_COMPARISON_IDENTITY_MISMATCH",
        strategy_id=request.strategy_id,
        as_of=request.as_of,
        valuation_snapshot_id=request.valuation_snapshot_id,
        source_snapshot_ids=request.source_snapshot_ids,
        reason=reason,
    )


def _validate_request(request: PortfolioComparisonRequest) -> None:
    for field_name in (
        "strategy_id",
        "model_portfolio_id",
        "paper_account_id",
        "manual_account_id",
        "paper_session_id",
        "as_of",
    ):
        value = getattr(request, field_name)
        if not value or value.strip() != value:
            raise _request_error(f"{field_name} is invalid", request)
    if not request.source_snapshot_ids or len(set(request.source_snapshot_ids)) != len(
        request.source_snapshot_ids
    ):
        raise _request_error("source snapshot IDs are ambiguous", request)


def _assert_request_identity(
    request: PortfolioComparisonRequest,
    portfolio: PortfolioValuationInput,
    *,
    expected_kind: str,
    expected_id: str | None,
) -> None:
    if portfolio.portfolio_kind != expected_kind:
        raise _request_error(f"{expected_kind} leg kind mismatch", request)
    if expected_id is not None and portfolio.portfolio_id != expected_id:
        raise _request_error(f"{expected_kind} portfolio identity mismatch", request)
    if portfolio.as_of != request.as_of:
        raise _request_error(f"{expected_kind} as_of mismatch", request)
    if (
        request.valuation_snapshot_id is not None
        and portfolio.valuation_snapshot_id != request.valuation_snapshot_id
    ):
        raise _request_error(f"{expected_kind} valuation snapshot mismatch", request)
    if portfolio.source_snapshot_ids != request.source_snapshot_ids:
        raise _request_error(f"{expected_kind} source snapshot mismatch", request)


class GetPortfolioComparisonQuery:
    """Normalize source legs and aggregate all pairwise drift read models."""

    def __init__(self, *, source: PortfolioComparisonSourcePort) -> None:
        self._source = source

    def get(self, request: PortfolioComparisonRequest) -> PortfolioComparisonView:
        """Return the comparison without a latest fallback or partial success."""
        _validate_request(request)
        source = self._source.load(request)
        resolved_valuation_snapshot_id = source.model.valuation_snapshot_id
        if source.paper.valuation_snapshot_id != resolved_valuation_snapshot_id:
            raise _request_error("paper valuation snapshot mismatch", request)
        if source.manual.valuation_snapshot_id != resolved_valuation_snapshot_id:
            raise _request_error("manual valuation snapshot mismatch", request)
        _assert_request_identity(
            request,
            source.model,
            expected_kind="model",
            expected_id=request.model_portfolio_id,
        )
        _assert_request_identity(
            request,
            source.paper,
            expected_kind="paper",
            expected_id=request.paper_account_id,
        )
        _assert_request_identity(
            request,
            source.manual,
            expected_kind="manual",
            expected_id=request.manual_account_id,
        )
        try:
            model = normalize_portfolio(source.model)
            paper = normalize_portfolio(source.paper)
            manual = normalize_portfolio(source.manual)
            return PortfolioComparisonView(
                strategy_id=request.strategy_id,
                as_of=request.as_of,
                valuation_snapshot_id=resolved_valuation_snapshot_id,
                source_snapshot_ids=request.source_snapshot_ids,
                model=model,
                paper=paper,
                manual=manual,
                model_vs_paper=compare_portfolio_pair(
                    model,
                    paper,
                    attribution=source.paper_attribution,
                ),
                model_vs_manual=_manual_drift(
                    model,
                    manual,
                    source.manual_attribution,
                ),
                paper_vs_manual=compare_portfolio_pair(paper, manual),
            )
        except PortfolioComparisonError as exc:
            raise _request_error(str(exc), request) from exc


def _manual_drift(
    model: NormalizedPortfolio,
    manual: NormalizedPortfolio,
    attribution: PortfolioAttribution,
) -> PortfolioDriftView:
    """Default unexplained Model/Manual drift to explicit user-choice semantics."""
    preliminary = compare_portfolio_pair(model, manual)
    if attribution.user_choice_bps != 0:
        return compare_portfolio_pair(model, manual, attribution=attribution)
    return compare_portfolio_pair(
        model,
        manual,
        attribution=PortfolioAttribution(
            user_choice_bps=preliminary.total_abs_drift_bps,
        ),
    )
