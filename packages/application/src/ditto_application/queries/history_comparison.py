"""
Exact application composition of the MODEL/PAPER/MANUAL common-window compare.

The query reuses the three leg history queries (MODEL target replay, the
session-bound PAPER revision replay, and the MANUAL revision replay) so every
leg keeps its own PIT context, ledger revision identity, and replayable
``result_id``. The server resolves the current PAPER/MANUAL ledger revisions
and binds them into the result; the numeric common-window rule itself lives
in :mod:`ditto_portfolio.history_window_comparison`. Read-only: no backtest,
no ledger write, no "latest" fallback.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256

import orjson
from ditto_portfolio.account_ledger import (
    AccountEventJournalPort,
    AccountKind,
    ledger_hash,
)
from ditto_portfolio.history_window_comparison import (
    COMMON_WINDOW_POLICY_VERSION,
    WindowComparison,
    WindowLeg,
    WindowLegPoint,
    WindowRun,
    compare_common_windows,
)

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.account_ledger import LedgerRevision
from ditto_application.queries.history_valuation import (
    VALUATION_POLICY_VERSION,
    HistoryPointView,
)
from ditto_application.queries.model_history import (
    GetModelHistoryQuery,
    ModelHistoryRequest,
    ModelHistoryView,
)
from ditto_application.queries.portfolio_history import (
    AccountHistoryRequest,
    AccountHistoryView,
    GetManualHistoryQuery,
    GetPaperHistoryQuery,
    PaperHistoryRequest,
)

__all__ = [
    "COMPARISON_POLICY_VERSION",
    "GetHistoryComparisonQuery",
    "HistoryComparisonLegView",
    "HistoryComparisonRequest",
    "HistoryComparisonRunPointView",
    "HistoryComparisonRunView",
    "HistoryComparisonView",
]

COMPARISON_POLICY_VERSION = COMMON_WINDOW_POLICY_VERSION
_RESULT_PREFIX = "history-comparison:sha256:"
_KINDS = ("model", "paper", "manual")
_ZERO = Decimal("0")


def _error(code: str, reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"history comparison query failed closed: {reason}",
        details={
            "code": f"HISTORY_COMPARISON_{code}",
            "reason": reason,
            **details,
        },
    )


@dataclass(frozen=True, kw_only=True)
class HistoryComparisonRequest:
    """Caller-selected identities shared by all three legs."""

    strategy_id: str
    paper_account_id: str
    paper_session_id: str
    manual_account_id: str
    start_date: str
    end_date: str
    model_initial_capital: Decimal
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    model_artifact_ids: tuple[str, ...] = ()

    def result_identity(self) -> dict[str, object]:
        """Request facts bound into the comparison result identity."""
        return {
            "strategy_id": self.strategy_id,
            "paper_account_id": self.paper_account_id,
            "paper_session_id": self.paper_session_id,
            "manual_account_id": self.manual_account_id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "model_initial_capital": str(self.model_initial_capital),
            "knowledge_cutoff": self.knowledge_cutoff.isoformat(),
            "publication_cutoff": self.publication_cutoff.isoformat(),
            "source_snapshot_ids": list(self.source_snapshot_ids),
            "model_artifact_ids": list(self.model_artifact_ids),
        }


@dataclass(frozen=True, kw_only=True)
class HistoryComparisonLegView:
    """Per-leg provenance for drilldown; identity stays the leg result_id."""

    kind: str
    result_id: str
    currency: str
    empty_reason: str | None
    point_count: int
    valued_point_count: int
    gap_count: int
    segment_count: int
    first_valued_date: str | None
    last_valued_date: str | None
    ledger_revision: LedgerRevision | None
    target_count: int | None


@dataclass(frozen=True, kw_only=True)
class HistoryComparisonRunPointView:
    """One common date: growth is anchored to 1 at the run start."""

    on_date: str
    growth: dict[str, Decimal]
    assets: dict[str, Decimal]


@dataclass(frozen=True, kw_only=True)
class HistoryComparisonRunView:
    """One common continuous run with per-leg window returns."""

    start_date: str
    end_date: str
    point_count: int
    points: tuple[HistoryComparisonRunPointView, ...]
    window_returns: dict[str, Decimal | None]


@dataclass(frozen=True, kw_only=True)
class HistoryComparisonView:
    """Complete replayable common-window comparison result."""

    result_id: str
    strategy_id: str
    paper_account_id: str
    paper_session_id: str
    manual_account_id: str
    model_initial_capital: Decimal
    currency: str
    method: str
    valuation_policy_version: str
    comparison_policy_version: str
    status: str
    empty_reason: str | None
    start_date: str
    end_date: str
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    runs: tuple[HistoryComparisonRunView, ...]
    legs: tuple[HistoryComparisonLegView, ...]


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _error("REQUEST_INVALID", f"{field} must be an ISO date") from exc


def _validate_request(request: HistoryComparisonRequest) -> None:
    _validate_entities_and_range(request)
    _validate_research_context(request)


def _validate_entities_and_range(request: HistoryComparisonRequest) -> None:
    for field_name in (
        "strategy_id",
        "paper_account_id",
        "paper_session_id",
        "manual_account_id",
    ):
        if not getattr(request, field_name).strip():
            raise _error(
                "REQUEST_INVALID",
                f"{field_name} must be non-empty",
            )
    start = _parse_date(request.start_date, "start_date")
    end = _parse_date(request.end_date, "end_date")
    if start > end:
        raise _error("REQUEST_INVALID", "start_date cannot be after end_date")


def _validate_research_context(request: HistoryComparisonRequest) -> None:
    if request.knowledge_cutoff.tzinfo is None:
        raise _error("REQUEST_INVALID", "knowledge_cutoff must be timezone-aware")
    if request.publication_cutoff.tzinfo is None:
        raise _error("REQUEST_INVALID", "publication_cutoff must be timezone-aware")
    if request.publication_cutoff > request.knowledge_cutoff:
        raise _error(
            "REQUEST_INVALID",
            "publication_cutoff cannot exceed knowledge_cutoff",
        )
    if not request.source_snapshot_ids:
        raise _error(
            "REQUEST_INVALID",
            "at least one price source snapshot is required",
        )
    if len(set(request.source_snapshot_ids)) != len(request.source_snapshot_ids):
        raise _error("REQUEST_INVALID", "price source snapshots must be unique")
    capital = request.model_initial_capital
    if not capital.is_finite() or capital <= _ZERO:
        raise _error(
            "REQUEST_INVALID",
            "model_initial_capital must be a positive finite amount",
        )
    if len(set(request.model_artifact_ids)) != len(request.model_artifact_ids):
        raise _error("REQUEST_INVALID", "model_artifact_ids must be unique")


class GetHistoryComparisonQuery:
    """Compose the three leg replays into one common-window comparison."""

    def __init__(
        self,
        *,
        manual_query: GetManualHistoryQuery,
        paper_query: GetPaperHistoryQuery,
        model_query: GetModelHistoryQuery,
        journal: AccountEventJournalPort,
    ) -> None:
        self._manual = manual_query
        self._paper = paper_query
        self._model = model_query
        self._journal = journal

    def history(self, request: HistoryComparisonRequest) -> HistoryComparisonView:
        """Return the exact common-window comparison or fail closed."""
        _validate_request(request)
        manual_revision = self._resolve_revision(
            request.manual_account_id,
            kind=AccountKind.MANUAL,
        )
        paper_revision = self._resolve_revision(
            request.paper_account_id,
            kind=AccountKind.PAPER,
        )
        manual = self._manual.history(
            AccountHistoryRequest(
                account_id=request.manual_account_id,
                start_date=request.start_date,
                end_date=request.end_date,
                knowledge_cutoff=request.knowledge_cutoff,
                publication_cutoff=request.publication_cutoff,
                source_snapshot_ids=request.source_snapshot_ids,
                ledger_event_count=manual_revision.event_count,
                ledger_hash=manual_revision.ledger_hash,
            )
        )
        paper = self._paper.history(
            PaperHistoryRequest(
                account_id=request.paper_account_id,
                session_id=request.paper_session_id,
                start_date=request.start_date,
                end_date=request.end_date,
                knowledge_cutoff=request.knowledge_cutoff,
                publication_cutoff=request.publication_cutoff,
                source_snapshot_ids=request.source_snapshot_ids,
                ledger_event_count=paper_revision.event_count,
                ledger_hash=paper_revision.ledger_hash,
            )
        )
        model = self._model.history(
            ModelHistoryRequest(
                strategy_id=request.strategy_id,
                start_date=request.start_date,
                end_date=request.end_date,
                initial_capital=request.model_initial_capital,
                knowledge_cutoff=request.knowledge_cutoff,
                publication_cutoff=request.publication_cutoff,
                artifact_ids=request.model_artifact_ids,
            )
        )
        currency = self._shared_currency(manual, paper, model)
        method = self._shared_method(manual, paper, model)
        comparison = compare_common_windows(
            (
                _leg_input("model", model.points),
                _leg_input("paper", paper.points),
                _leg_input("manual", manual.points),
            )
        )
        return HistoryComparisonView(
            result_id=_result_id(request, manual, paper, model, comparison),
            strategy_id=request.strategy_id,
            paper_account_id=request.paper_account_id,
            paper_session_id=request.paper_session_id,
            manual_account_id=request.manual_account_id,
            model_initial_capital=request.model_initial_capital,
            currency=currency,
            method=method,
            valuation_policy_version=VALUATION_POLICY_VERSION,
            comparison_policy_version=COMPARISON_POLICY_VERSION,
            status=comparison.status,
            empty_reason=comparison.empty_reason,
            start_date=request.start_date,
            end_date=request.end_date,
            knowledge_cutoff=request.knowledge_cutoff,
            publication_cutoff=request.publication_cutoff,
            runs=tuple(_run_view(run) for run in comparison.runs),
            legs=(
                _leg_view(
                    "model",
                    _LegFacts(
                        result_id=model.result_id,
                        currency=model.currency,
                        empty_reason=model.empty_reason,
                        points=model.points,
                        segment_count=len(model.segments),
                        ledger_revision=None,
                        target_count=len(model.targets),
                    ),
                ),
                _leg_view(
                    "paper",
                    _LegFacts(
                        result_id=paper.result_id,
                        currency=paper.currency,
                        empty_reason=None,
                        points=paper.points,
                        segment_count=len(paper.segments),
                        ledger_revision=paper.ledger_revision,
                        target_count=None,
                    ),
                ),
                _leg_view(
                    "manual",
                    _LegFacts(
                        result_id=manual.result_id,
                        currency=manual.currency,
                        empty_reason=None,
                        points=manual.points,
                        segment_count=len(manual.segments),
                        ledger_revision=manual.ledger_revision,
                        target_count=None,
                    ),
                ),
            ),
        )

    def _resolve_revision(
        self,
        account_id: str,
        *,
        kind: AccountKind,
    ) -> LedgerRevision:
        account = self._journal.get_account(account_id)
        if account is None:
            raise _error(
                "ACCOUNT_NOT_FOUND",
                "account not found",
                account_id=account_id,
                account_kind=kind.value,
            )
        if account.kind is not kind:
            raise _error(
                "ACCOUNT_KIND_MISMATCH",
                f"account is not a {kind.value} account",
                account_id=account_id,
                actual_kind=account.kind.value,
            )
        events = self._journal.list_events(account_id)
        if not events:
            raise _error(
                "LEDGER_EMPTY",
                "account has no recorded events to replay",
                account_id=account_id,
            )
        return LedgerRevision(
            event_count=len(events),
            ledger_hash=ledger_hash(events),
        )

    def _shared_currency(
        self,
        manual: AccountHistoryView,
        paper: AccountHistoryView,
        model: ModelHistoryView,
    ) -> str:
        currencies = {manual.currency, paper.currency, model.currency}
        if len(currencies) != 1:
            raise _error(
                "CURRENCY_MISMATCH",
                "legs do not share one currency",
                currencies=sorted(currencies),
            )
        return manual.currency

    def _shared_method(
        self,
        manual: AccountHistoryView,
        paper: AccountHistoryView,
        model: ModelHistoryView,
    ) -> str:
        methods = {manual.method, paper.method, model.method}
        if len(methods) != 1:
            raise _error(
                "METHOD_MISMATCH",
                "legs do not share one return method",
                methods=sorted(methods),
            )
        return manual.method


def _leg_input(
    kind: str,
    points: Sequence[HistoryPointView],
) -> WindowLeg:
    return WindowLeg(
        kind=kind,
        points=tuple(
            WindowLegPoint(
                on_date=point.on_date,
                total_value=point.total_value,
                period_return=point.period_return,
                segment_id=point.segment_id,
            )
            for point in points
        ),
    )


@dataclass(frozen=True, kw_only=True)
class _LegFacts:
    """One leg's inputs to the provenance view."""

    result_id: str
    currency: str
    empty_reason: str | None
    points: Sequence[HistoryPointView]
    segment_count: int
    ledger_revision: LedgerRevision | None
    target_count: int | None


def _leg_view(kind: str, facts: _LegFacts) -> HistoryComparisonLegView:
    points = facts.points
    valued = [point for point in points if point.total_value is not None]
    return HistoryComparisonLegView(
        kind=kind,
        result_id=facts.result_id,
        currency=facts.currency,
        empty_reason=facts.empty_reason,
        point_count=len(points),
        valued_point_count=len(valued),
        gap_count=len(points) - len(valued),
        segment_count=facts.segment_count,
        first_valued_date=valued[0].on_date if valued else None,
        last_valued_date=valued[-1].on_date if valued else None,
        ledger_revision=facts.ledger_revision,
        target_count=facts.target_count,
    )


def _run_view(run: WindowRun) -> HistoryComparisonRunView:
    return HistoryComparisonRunView(
        start_date=run.start_date,
        end_date=run.end_date,
        point_count=len(run.points),
        points=tuple(
            HistoryComparisonRunPointView(
                on_date=point.on_date,
                growth=dict(point.growth),
                assets=dict(point.assets),
            )
            for point in run.points
        ),
        window_returns=dict(run.window_returns),
    )


def _result_id(
    request: HistoryComparisonRequest,
    manual: AccountHistoryView,
    paper: AccountHistoryView,
    model: ModelHistoryView,
    comparison: WindowComparison,
) -> str:
    payload = {
        **request.result_identity(),
        "legs": [
            {"kind": kind, "result_id": result_id}
            for kind, result_id in (
                ("model", model.result_id),
                ("paper", paper.result_id),
                ("manual", manual.result_id),
            )
        ],
        "runs": [[run.start_date, run.end_date] for run in comparison.runs],
        "status": comparison.status,
        "valuation_policy": VALUATION_POLICY_VERSION,
        "comparison_policy": COMPARISON_POLICY_VERSION,
        "method": manual.method,
    }
    digest = sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()
    return f"{_RESULT_PREFIX}{digest}"
