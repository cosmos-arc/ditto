"""Live exact-snapshot source for the unified three-portfolio comparison."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from hashlib import sha256
from typing import Protocol, cast
from zoneinfo import ZoneInfo

import orjson
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader
from ditto_data.query.contracts import DatasetSnapshot, PITQueryContext
from ditto_execution.paper.session import PaperSessionStorePort
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_projection import PortfolioSnapshot
from ditto_portfolio.portfolio_comparison import (
    PortfolioAttribution,
    PortfolioHoldingInput,
    PortfolioValuationInput,
)
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.portfolio_comparison import (
    PortfolioComparisonRequest,
    PortfolioComparisonSource,
)
from ditto_application.queries.technical_analysis import TechnicalAnalysisSourcePort
from ditto_application.signal_package_contract import (
    canonical_signal_package_metadata,
    verify_signal_package_metadata,
)

__all__ = ["LivePortfolioComparisonSource"]

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_MONEY = Decimal("0.01")
_QUANTITY = Decimal("0.0001")
_BPS = Decimal("10000")


class _SignalPackageReader(Protocol):
    def list_by_strategy(self, strategy_id: str) -> list[StrategyArtifactRecord]: ...


@dataclass(frozen=True)
class _ValuationPrice:
    instrument_id: int
    price: Decimal
    occurred_at: datetime
    source_snapshot_id: str


def _error(code: str, reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"portfolio comparison source failed closed: {reason}",
        details={"code": code, "reason": reason, **details},
    )


def _dataset_snapshots(
    snapshots: tuple[ProviderSnapshot, ...],
) -> tuple[DatasetSnapshot, ...]:
    grouped: dict[str, list[ProviderSnapshot]] = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot.dataset_id, []).append(snapshot)
    result: list[DatasetSnapshot] = []
    for dataset_id, values in sorted(grouped.items()):
        versions = {item.schema_version for item in values}
        if len(versions) != 1:
            raise _error(
                "PORTFOLIO_VALUATION_SCHEMA_MIXED",
                "valuation snapshot set has mixed dataset versions",
                dataset_id=dataset_id,
            )
        result.append(
            DatasetSnapshot(
                dataset_id=dataset_id,
                dataset_version=next(iter(versions)),
                source_snapshot_ids=tuple(
                    item.snapshot_id
                    for item in sorted(values, key=lambda item: item.snapshot_id)
                ),
                created_at=max(item.created_at for item in values),
            )
        )
    return tuple(result)


def _context(
    request: PortfolioComparisonRequest,
    snapshot_reader: ProviderSnapshotReader,
) -> PITQueryContext:
    try:
        as_of_date = date.fromisoformat(request.as_of)
    except ValueError as exc:
        raise _error("PORTFOLIO_AS_OF_INVALID", "as_of must be YYYY-MM-DD") from exc
    snapshots: list[ProviderSnapshot] = []
    for snapshot_id in request.source_snapshot_ids:
        snapshot = snapshot_reader.get_snapshot(snapshot_id)
        if snapshot is None or snapshot.snapshot_id != snapshot_id:
            raise _error(
                "PORTFOLIO_SOURCE_SNAPSHOT_NOT_FOUND",
                "exact source snapshot was not found",
                snapshot_id=snapshot_id,
            )
        if snapshot.created_at > request.knowledge_cutoff:
            raise _error(
                "PORTFOLIO_SOURCE_SNAPSHOT_FUTURE",
                "source snapshot is after knowledge cutoff",
                snapshot_id=snapshot_id,
            )
        snapshots.append(snapshot)
    try:
        return PITQueryContext(
            as_of=datetime.combine(as_of_date, time.max, tzinfo=_SHANGHAI),
            knowledge_cutoff=request.knowledge_cutoff,
            publication_cutoff=request.publication_cutoff,
            source_snapshots=_dataset_snapshots(tuple(snapshots)),
        )
    except ValueError as exc:
        raise _error("PORTFOLIO_PIT_CONTEXT_INVALID", str(exc)) from exc


def _package(
    reader: _SignalPackageReader,
    request: PortfolioComparisonRequest,
) -> dict[str, object]:
    matches = tuple(
        artifact
        for artifact in reader.list_by_strategy(request.strategy_id)
        if artifact.artifact_id == request.model_portfolio_id
        and artifact.artifact_type is ArtifactKind.SIGNAL_PACKAGE
        and artifact.status == "active"
    )
    if len(matches) != 1:
        raise _error(
            "MODEL_PORTFOLIO_NOT_FOUND",
            "exact active signal package was not found",
            model_portfolio_id=request.model_portfolio_id,
        )
    artifact = matches[0]
    if not verify_signal_package_metadata(artifact.metadata):
        raise _error(
            "MODEL_PORTFOLIO_INTEGRITY_INVALID",
            "signal package checksum is invalid",
            model_portfolio_id=request.model_portfolio_id,
        )
    metadata = canonical_signal_package_metadata(artifact.metadata)
    if metadata.get("signal_date") != request.as_of:
        raise _error(
            "MODEL_PORTFOLIO_AS_OF_MISMATCH",
            "signal package date differs from comparison as_of",
        )
    raw_snapshots = metadata.get("dataset_snapshot_ids")
    if not isinstance(raw_snapshots, dict):
        raise _error(
            "MODEL_PORTFOLIO_LINEAGE_INVALID",
            "signal package dataset snapshot mapping is absent",
        )
    package_snapshots = tuple(
        sorted(
            str(value) for value in cast(dict[object, object], raw_snapshots).values()
        )
    )
    if package_snapshots != tuple(sorted(request.source_snapshot_ids)):
        raise _error(
            "MODEL_PORTFOLIO_LINEAGE_MISMATCH",
            "signal package and valuation source snapshots differ",
            package_snapshot_ids=package_snapshots,
        )
    return metadata


def _target_weights(metadata: Mapping[str, object]) -> dict[int, Decimal]:
    raw_reasons = metadata.get("selection_reasons")
    if not isinstance(raw_reasons, dict):
        raise _error(
            "MODEL_PORTFOLIO_TARGET_INVALID",
            "selection reasons are absent",
        )
    weights: dict[int, Decimal] = {}
    for raw_id, raw_reason in cast(dict[object, object], raw_reasons).items():
        if not isinstance(raw_reason, dict):
            raise _error(
                "MODEL_PORTFOLIO_TARGET_INVALID", "selection reason is malformed"
            )
        try:
            instrument_id = int(cast(str | int, raw_id))
            weight = Decimal(
                str(cast(dict[object, object], raw_reason)["target_weight"])
            )
        except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
            raise _error(
                "MODEL_PORTFOLIO_TARGET_INVALID",
                "target weight is malformed",
            ) from exc
        if instrument_id <= 0 or not weight.is_finite() or weight < 0:
            raise _error("MODEL_PORTFOLIO_TARGET_INVALID", "target weight is invalid")
        weights[instrument_id] = weight
    if not weights or sum(weights.values()) > Decimal("1.00000001"):
        raise _error(
            "MODEL_PORTFOLIO_TARGET_INVALID",
            "target weights are empty or exceed one",
        )
    return dict(sorted(weights.items()))


def _instrument_ids(
    weights: Mapping[int, Decimal],
    paper: PortfolioSnapshot,
    manual: PortfolioSnapshot,
) -> tuple[int, ...]:
    return tuple(
        sorted(
            set(weights)
            | {int(item.instrument_id) for item in paper.positions}
            | {int(item.instrument_id) for item in manual.positions}
        )
    )


def _latest_price(
    bars: tuple[TechnicalBar, ...],
    *,
    instrument_id: int,
) -> _ValuationPrice:
    if not bars:
        raise _error(
            "PORTFOLIO_VALUATION_PRICE_MISSING",
            "no PIT-visible valuation price exists",
            instrument_id=instrument_id,
        )
    latest = max(bars, key=lambda item: item.occurred_at)
    price = Decimal(str(latest.close))
    if not price.is_finite() or price <= 0:
        raise _error(
            "PORTFOLIO_VALUATION_PRICE_INVALID",
            "valuation close is not positive and finite",
            instrument_id=instrument_id,
        )
    return _ValuationPrice(
        instrument_id=instrument_id,
        price=price,
        occurred_at=latest.occurred_at,
        source_snapshot_id=latest.source_snapshot_id,
    )


def _valuation_prices(
    source: TechnicalAnalysisSourcePort,
    context: PITQueryContext,
    instrument_ids: tuple[int, ...],
) -> tuple[_ValuationPrice, ...]:
    return tuple(
        _latest_price(
            source.load(
                context,
                instrument_id=InstrumentId(instrument_id),
                instrument_code=str(instrument_id),
            ),
            instrument_id=instrument_id,
        )
        for instrument_id in instrument_ids
    )


def _valuation_snapshot_id(
    request: PortfolioComparisonRequest,
    prices: tuple[_ValuationPrice, ...],
) -> str:
    payload = {
        "as_of": request.as_of,
        "source_snapshot_ids": request.source_snapshot_ids,
        "prices": [
            (
                item.instrument_id,
                str(item.price),
                item.occurred_at.isoformat(),
                item.source_snapshot_id,
            )
            for item in prices
        ],
    }
    digest = sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()
    return f"portfolio-valuation:sha256:{digest}"


def _account_valuation(
    snapshot: PortfolioSnapshot,
    *,
    kind: str,
    valuation_snapshot_id: str,
    source_snapshot_ids: tuple[str, ...],
    pending_event_count: int = 0,
    alert_codes: tuple[str, ...] = (),
) -> PortfolioValuationInput:
    return PortfolioValuationInput(
        portfolio_id=snapshot.account_id,
        portfolio_kind=kind,
        as_of=snapshot.as_of,
        valuation_snapshot_id=valuation_snapshot_id,
        source_snapshot_ids=source_snapshot_ids,
        currency=snapshot.currency,
        cash=snapshot.cash.total,
        total_value=snapshot.total_value,
        positions=tuple(
            PortfolioHoldingInput(
                instrument_id=int(item.instrument_id),
                quantity=item.quantity,
                last_price=item.last_price,
                market_value=item.market_value,
                average_cost_value=(item.average_cost * item.quantity).quantize(_MONEY),
                realized_pnl=item.realized_pnl,
                unrealized_pnl=item.unrealized_pnl,
                fees=item.total_fees,
            )
            for item in snapshot.positions
        ),
        valuation_complete=snapshot.valuation_complete,
        pending_event_count=pending_event_count,
        alert_codes=alert_codes,
    )


def _model_valuation(
    *,
    request: PortfolioComparisonRequest,
    weights: Mapping[int, Decimal],
    prices: Mapping[int, Decimal],
    reference_total: Decimal,
    valuation_snapshot_id: str,
) -> PortfolioValuationInput:
    positions: list[PortfolioHoldingInput] = []
    for instrument_id, weight in weights.items():
        market_value = (reference_total * weight).quantize(
            _MONEY, rounding=ROUND_HALF_UP
        )
        price = prices[instrument_id]
        positions.append(
            PortfolioHoldingInput(
                instrument_id=instrument_id,
                quantity=(market_value / price).quantize(
                    _QUANTITY, rounding=ROUND_HALF_UP
                ),
                last_price=price,
                market_value=market_value,
            )
        )
    invested = sum((item.market_value for item in positions), Decimal("0"))
    cash = reference_total - invested
    if cash < 0:
        raise _error(
            "MODEL_PORTFOLIO_TARGET_INVALID",
            "rounded target values exceed reference total",
        )
    return PortfolioValuationInput(
        portfolio_id=request.model_portfolio_id,
        portfolio_kind="model",
        as_of=request.as_of,
        valuation_snapshot_id=valuation_snapshot_id,
        source_snapshot_ids=request.source_snapshot_ids,
        currency="CNY",
        cash=cash,
        total_value=reference_total,
        positions=tuple(positions),
        valuation_complete=True,
    )


def _paper_attribution(
    *,
    request: PortfolioComparisonRequest,
    store: PaperSessionStorePort,
    model_weights: Mapping[int, Decimal],
) -> PortfolioAttribution:
    session = store.get_session(request.paper_session_id)
    if (
        session is None
        or session.account_id != request.paper_account_id
        or session.strategy_id != request.strategy_id
        or session.trade_date != request.as_of
    ):
        raise _error(
            "PAPER_SESSION_IDENTITY_MISMATCH",
            "paper session does not match comparison identity",
            paper_session_id=request.paper_session_id,
        )
    unfilled: set[int] = set(model_weights)
    risk_blocked: set[int] = set()
    slippage = Decimal("0")
    fees = Decimal("0")
    for record in store.list_executions(request.paper_session_id):
        instrument_id = int(record.result.order.order.instrument_id)
        fill = record.result.fill
        if fill is None:
            unfilled.add(instrument_id)
            if record.result.reason and "risk" in record.result.reason.casefold():
                risk_blocked.add(instrument_id)
            continue
        unfilled.discard(instrument_id)
        slippage += abs(
            Decimal(str(fill.fill_price)) - Decimal(str(fill.reference_price))
        ) * Decimal(fill.quantity)
        fees += Decimal(str(fill.commission + fill.transfer_fee + fill.tax))
    return PortfolioAttribution(
        unfilled_bps=sum(
            (model_weights.get(item, Decimal("0")) for item in unfilled), Decimal("0")
        )
        * _BPS,
        slippage_amount=slippage.quantize(_MONEY, rounding=ROUND_HALF_UP),
        fee_amount=fees.quantize(_MONEY, rounding=ROUND_HALF_UP),
        risk_blocked_bps=sum(
            (model_weights.get(item, Decimal("0")) for item in risk_blocked),
            Decimal("0"),
        )
        * _BPS,
    )


class LivePortfolioComparisonSource:
    """Compose immutable packages, ledgers, Paper executions, and PIT prices."""

    def __init__(
        self,
        *,
        artifact_reader: _SignalPackageReader,
        account_query: AccountLedgerQuery,
        paper_store: PaperSessionStorePort,
        snapshot_reader: ProviderSnapshotReader,
        valuation_source: TechnicalAnalysisSourcePort,
    ) -> None:
        self._artifact_reader = artifact_reader
        self._account_query = account_query
        self._paper_store = paper_store
        self._snapshot_reader = snapshot_reader
        self._valuation_source = valuation_source

    def load(self, request: PortfolioComparisonRequest) -> PortfolioComparisonSource:
        """Load all exact facts and reject any missing or drifted identity."""
        metadata = _package(self._artifact_reader, request)
        weights = _target_weights(metadata)
        paper_unvalued = self._account_query.get_paper(
            account_id=request.paper_account_id,
            as_of=request.as_of,
        )
        manual_unvalued = self._account_query.get_manual(
            account_id=request.manual_account_id,
            as_of=request.as_of,
        )
        context = _context(request, self._snapshot_reader)
        price_rows = _valuation_prices(
            self._valuation_source,
            context,
            _instrument_ids(
                weights,
                paper_unvalued.snapshot,
                manual_unvalued.snapshot,
            ),
        )
        prices = {InstrumentId(item.instrument_id): item.price for item in price_rows}
        valuation_snapshot_id = _valuation_snapshot_id(request, price_rows)
        if (
            request.valuation_snapshot_id is not None
            and request.valuation_snapshot_id != valuation_snapshot_id
        ):
            raise _error(
                "PORTFOLIO_VALUATION_IDENTITY_MISMATCH",
                "computed valuation identity differs from request",
                expected=request.valuation_snapshot_id,
                actual=valuation_snapshot_id,
            )
        paper = self._account_query.get_paper(
            account_id=request.paper_account_id,
            as_of=request.as_of,
            valuation_prices=prices,
        )
        manual = self._account_query.get_manual(
            account_id=request.manual_account_id,
            as_of=request.as_of,
            valuation_prices=prices,
        )
        if (
            not paper.snapshot.valuation_complete
            or not manual.snapshot.valuation_complete
        ):
            raise _error(
                "PORTFOLIO_VALUATION_INCOMPLETE",
                "account projection lacks an exact valuation price",
            )
        reference_total = paper.snapshot.total_value
        if reference_total <= 0:
            raise _error(
                "MODEL_PORTFOLIO_REFERENCE_INVALID",
                "paper account total value must be positive",
            )
        return PortfolioComparisonSource(
            model=_model_valuation(
                request=request,
                weights=weights,
                prices={int(key): value for key, value in prices.items()},
                reference_total=reference_total,
                valuation_snapshot_id=valuation_snapshot_id,
            ),
            paper=_account_valuation(
                paper.snapshot,
                kind="paper",
                valuation_snapshot_id=valuation_snapshot_id,
                source_snapshot_ids=request.source_snapshot_ids,
            ),
            manual=_account_valuation(
                manual.snapshot,
                kind="manual",
                valuation_snapshot_id=valuation_snapshot_id,
                source_snapshot_ids=request.source_snapshot_ids,
            ),
            paper_attribution=_paper_attribution(
                request=request,
                store=self._paper_store,
                model_weights=weights,
            ),
        )
