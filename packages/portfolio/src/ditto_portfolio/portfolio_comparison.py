"""Money-precise normalization and drift for MODEL, PAPER, and MANUAL portfolios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal, cast

__all__ = [
    "NormalizedPortfolio",
    "NormalizedPortfolioPosition",
    "PortfolioAttribution",
    "PortfolioComparisonError",
    "PortfolioDriftItem",
    "PortfolioDriftView",
    "PortfolioHoldingInput",
    "PortfolioValuationInput",
    "compare_portfolio_pair",
    "constrained_target_weights",
    "normalize_portfolio",
]

type PortfolioKind = Literal["model", "paper", "manual"]
type ComparisonKind = Literal[
    "model_vs_paper",
    "model_vs_manual",
    "paper_vs_manual",
]

_ZERO = Decimal("0")
_ONE = Decimal("1")
_MONEY = Decimal("0.01")
_WEIGHT = Decimal("0.00000001")
_BPS = Decimal("10000")


class PortfolioComparisonError(ValueError):
    """Raised when exact comparison identities or valuation facts are invalid."""


@dataclass(frozen=True, kw_only=True)
class PortfolioHoldingInput:
    """One holding valued under the portfolio's declared exact snapshot."""

    instrument_id: int
    quantity: Decimal
    last_price: Decimal
    market_value: Decimal
    average_cost_value: Decimal = _ZERO
    realized_pnl: Decimal = _ZERO
    unrealized_pnl: Decimal = _ZERO
    fees: Decimal = _ZERO
    industry: str | None = None


@dataclass(frozen=True, kw_only=True)
class PortfolioValuationInput:
    """Complete portfolio facts before deterministic weight normalization."""

    portfolio_id: str
    portfolio_kind: PortfolioKind | str
    as_of: str
    valuation_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]
    currency: str
    cash: Decimal
    total_value: Decimal
    positions: tuple[PortfolioHoldingInput, ...]
    valuation_complete: bool
    pending_event_count: int = 0
    alert_codes: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class NormalizedPortfolioPosition:
    """One holding with a stable eight-decimal portfolio weight."""

    instrument_id: int
    quantity: Decimal
    last_price: Decimal
    market_value: Decimal
    weight: Decimal
    average_cost_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    industry: str | None


@dataclass(frozen=True, kw_only=True)
class NormalizedPortfolio:
    """Comparable immutable portfolio on one exact valuation identity."""

    portfolio_id: str
    portfolio_kind: PortfolioKind
    as_of: str
    valuation_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]
    currency: str
    cash: Decimal
    cash_weight: Decimal
    total_value: Decimal
    invested_weight: Decimal
    positions: tuple[NormalizedPortfolioPosition, ...]
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    pending_event_count: int
    alert_codes: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class PortfolioAttribution:
    """Host-computed explanation categories for one pairwise drift."""

    unfilled_bps: Decimal = _ZERO
    slippage_amount: Decimal = _ZERO
    fee_amount: Decimal = _ZERO
    risk_blocked_bps: Decimal = _ZERO
    user_choice_bps: Decimal = _ZERO


@dataclass(frozen=True, kw_only=True)
class PortfolioDriftItem:
    """Weight difference for one instrument in basis points."""

    instrument_id: int
    baseline_weight: Decimal
    observed_weight: Decimal
    drift_weight: Decimal
    drift_bps: Decimal


@dataclass(frozen=True, kw_only=True)
class PortfolioDriftView:
    """Pairwise drift with semantically constrained attribution."""

    comparison_kind: ComparisonKind
    baseline_portfolio_id: str
    observed_portfolio_id: str
    total_abs_drift_bps: Decimal
    cash_drift_bps: Decimal
    items: tuple[PortfolioDriftItem, ...]
    attribution: PortfolioAttribution


def _decimal(value: Decimal, field: str) -> Decimal:
    try:
        normalized = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PortfolioComparisonError(f"{field} must be a decimal") from exc
    if not normalized.is_finite():
        raise PortfolioComparisonError(f"{field} must be finite")
    return normalized


def _money(value: Decimal, field: str) -> Decimal:
    return _decimal(value, field).quantize(_MONEY, rounding=ROUND_HALF_UP)


def _weight(value: Decimal) -> Decimal:
    return value.quantize(_WEIGHT, rounding=ROUND_HALF_UP)


def _text(value: str, field: str) -> str:
    if not value or value.strip() != value:
        raise PortfolioComparisonError(f"{field} must be non-empty and canonical")
    return value


def _validate_portfolio_identity(value: PortfolioValuationInput) -> None:
    _text(value.portfolio_id, "portfolio_id")
    if value.portfolio_kind not in {"model", "paper", "manual"}:
        raise PortfolioComparisonError("portfolio_kind is invalid")
    try:
        date.fromisoformat(value.as_of)
    except ValueError as exc:
        raise PortfolioComparisonError("as_of must be YYYY-MM-DD") from exc
    _text(value.valuation_snapshot_id, "valuation_snapshot_id")
    if not value.source_snapshot_ids or len(set(value.source_snapshot_ids)) != len(
        value.source_snapshot_ids
    ):
        raise PortfolioComparisonError(
            "source snapshot IDs must be explicit and unique"
        )
    for snapshot_id in value.source_snapshot_ids:
        _text(snapshot_id, "source_snapshot_id")
    if value.currency != "CNY":
        raise PortfolioComparisonError("portfolio comparison v1 requires CNY")
    if not value.valuation_complete:
        raise PortfolioComparisonError("portfolio valuation is incomplete")
    if value.pending_event_count < 0:
        raise PortfolioComparisonError("pending_event_count cannot be negative")


def _normalized_positions(
    value: PortfolioValuationInput,
    total_value: Decimal,
) -> tuple[NormalizedPortfolioPosition, ...]:
    """Validate and normalize every unique valued position."""
    seen: set[int] = set()
    positions: list[NormalizedPortfolioPosition] = []
    for item in sorted(value.positions, key=lambda position: position.instrument_id):
        if item.instrument_id <= 0 or item.instrument_id in seen:
            raise PortfolioComparisonError(
                "instrument identities must be positive and unique"
            )
        seen.add(item.instrument_id)
        quantity = _decimal(item.quantity, "quantity")
        last_price = _decimal(item.last_price, "last_price")
        market_value = _money(item.market_value, "market_value")
        if min(quantity, last_price, market_value) < _ZERO:
            raise PortfolioComparisonError("position values cannot be negative")
        if quantity > _ZERO and last_price <= _ZERO:
            raise PortfolioComparisonError(
                "held positions require a positive last_price"
            )
        positions.append(
            NormalizedPortfolioPosition(
                instrument_id=item.instrument_id,
                quantity=quantity,
                last_price=last_price,
                market_value=market_value,
                weight=_weight(market_value / total_value),
                average_cost_value=_money(
                    item.average_cost_value, "average_cost_value"
                ),
                realized_pnl=_money(item.realized_pnl, "realized_pnl"),
                unrealized_pnl=_money(item.unrealized_pnl, "unrealized_pnl"),
                fees=_money(item.fees, "fees"),
                industry=item.industry,
            )
        )
    return tuple(positions)


def normalize_portfolio(value: PortfolioValuationInput) -> NormalizedPortfolio:
    """Validate a complete valuation and derive stable weights without I/O."""
    _validate_portfolio_identity(value)
    total_value = _money(value.total_value, "total_value")
    cash = _money(value.cash, "cash")
    if total_value <= _ZERO:
        raise PortfolioComparisonError("total_value must be positive")
    if cash < _ZERO:
        raise PortfolioComparisonError("cash cannot be negative")
    positions = _normalized_positions(value, total_value)
    valued_total = cash + sum((item.market_value for item in positions), _ZERO)
    if abs(valued_total - total_value) > _MONEY:
        raise PortfolioComparisonError("cash plus positions does not equal total_value")
    invested_weight = _weight(
        sum((item.market_value for item in positions), _ZERO) / total_value
    )
    cash_weight = _weight(cash / total_value)
    if abs(invested_weight + cash_weight - _ONE) > _WEIGHT:
        raise PortfolioComparisonError("normalized weights do not sum to one")
    return NormalizedPortfolio(
        portfolio_id=value.portfolio_id,
        portfolio_kind=cast(PortfolioKind, value.portfolio_kind),
        as_of=value.as_of,
        valuation_snapshot_id=value.valuation_snapshot_id,
        source_snapshot_ids=value.source_snapshot_ids,
        currency=value.currency,
        cash=cash,
        cash_weight=cash_weight,
        total_value=total_value,
        invested_weight=invested_weight,
        positions=positions,
        realized_pnl=sum((item.realized_pnl for item in positions), _ZERO),
        unrealized_pnl=sum((item.unrealized_pnl for item in positions), _ZERO),
        fees=sum((item.fees for item in positions), _ZERO),
        pending_event_count=value.pending_event_count,
        alert_codes=tuple(dict.fromkeys(value.alert_codes)),
    )


def _comparison_kind(
    baseline: PortfolioKind,
    observed: PortfolioKind,
) -> ComparisonKind:
    key = (baseline, observed)
    mapping: dict[tuple[PortfolioKind, PortfolioKind], ComparisonKind] = {
        ("model", "paper"): "model_vs_paper",
        ("model", "manual"): "model_vs_manual",
        ("paper", "manual"): "paper_vs_manual",
    }
    try:
        return mapping[key]
    except KeyError as exc:
        raise PortfolioComparisonError(
            "unsupported portfolio comparison direction"
        ) from exc


def _validated_attribution(
    kind: ComparisonKind,
    value: PortfolioAttribution,
) -> PortfolioAttribution:
    fields = {
        "unfilled_bps": _decimal(value.unfilled_bps, "unfilled_bps"),
        "slippage_amount": _money(value.slippage_amount, "slippage_amount"),
        "fee_amount": _money(value.fee_amount, "fee_amount"),
        "risk_blocked_bps": _decimal(value.risk_blocked_bps, "risk_blocked_bps"),
        "user_choice_bps": _decimal(value.user_choice_bps, "user_choice_bps"),
    }
    if any(item < _ZERO for item in fields.values()):
        raise PortfolioComparisonError("attribution values cannot be negative")
    paper_fields = (
        fields["unfilled_bps"],
        fields["slippage_amount"],
        fields["fee_amount"],
        fields["risk_blocked_bps"],
    )
    if kind == "model_vs_manual" and any(paper_fields):
        raise PortfolioComparisonError(
            "manual drift cannot be labeled execution failure"
        )
    if kind == "model_vs_paper" and fields["user_choice_bps"]:
        raise PortfolioComparisonError("paper drift cannot be labeled user choice")
    return PortfolioAttribution(**fields)


def compare_portfolio_pair(
    baseline: NormalizedPortfolio,
    observed: NormalizedPortfolio,
    *,
    attribution: PortfolioAttribution | None = None,
) -> PortfolioDriftView:
    """Compare two normalized portfolios only when every PIT identity matches."""
    if baseline.as_of != observed.as_of:
        raise PortfolioComparisonError("portfolio as_of mismatch")
    if baseline.valuation_snapshot_id != observed.valuation_snapshot_id:
        raise PortfolioComparisonError("portfolio valuation snapshot mismatch")
    if baseline.source_snapshot_ids != observed.source_snapshot_ids:
        raise PortfolioComparisonError("portfolio source snapshot mismatch")
    if baseline.currency != observed.currency:
        raise PortfolioComparisonError("portfolio currency mismatch")
    kind = _comparison_kind(baseline.portfolio_kind, observed.portfolio_kind)
    baseline_weights = {item.instrument_id: item.weight for item in baseline.positions}
    observed_weights = {item.instrument_id: item.weight for item in observed.positions}
    items: list[PortfolioDriftItem] = []
    for instrument_id in sorted(set(baseline_weights) | set(observed_weights)):
        baseline_weight = baseline_weights.get(instrument_id, _ZERO)
        observed_weight = observed_weights.get(instrument_id, _ZERO)
        drift = _weight(observed_weight - baseline_weight)
        items.append(
            PortfolioDriftItem(
                instrument_id=instrument_id,
                baseline_weight=baseline_weight,
                observed_weight=observed_weight,
                drift_weight=drift,
                drift_bps=(drift * _BPS).quantize(Decimal("0.01")),
            )
        )
    total_abs = sum((abs(item.drift_weight) for item in items), _ZERO) / Decimal("2")
    cash_drift = observed.cash_weight - baseline.cash_weight
    return PortfolioDriftView(
        comparison_kind=kind,
        baseline_portfolio_id=baseline.portfolio_id,
        observed_portfolio_id=observed.portfolio_id,
        total_abs_drift_bps=(total_abs * _BPS).quantize(Decimal("0.01")),
        cash_drift_bps=(cash_drift * _BPS).quantize(Decimal("0.01")),
        items=tuple(items),
        attribution=_validated_attribution(
            kind,
            attribution or PortfolioAttribution(),
        ),
    )


def _constraint_inputs(
    baseline_weights: dict[int, Decimal],
    *,
    excluded_instrument_ids: frozenset[int],
    max_position_weight: Decimal,
    cash_reserve_weight: Decimal,
) -> tuple[Decimal, Decimal, dict[int, Decimal]]:
    cap = _decimal(max_position_weight, "max_position_weight")
    cash = _decimal(cash_reserve_weight, "cash_reserve_weight")
    if cap <= _ZERO or cap > _ONE or cash < _ZERO or cash >= _ONE:
        raise PortfolioComparisonError("scenario weight constraints are invalid")
    target_total = _weight(_ONE - cash)
    normalized_weights = {
        instrument_id: _decimal(weight, "baseline_weight")
        for instrument_id, weight in baseline_weights.items()
    }
    if any(
        instrument_id <= 0 or weight < _ZERO
        for instrument_id, weight in normalized_weights.items()
    ):
        raise PortfolioComparisonError("baseline weights are invalid")
    if any(instrument_id <= 0 for instrument_id in excluded_instrument_ids):
        raise PortfolioComparisonError("excluded instrument identities are invalid")
    weights = {
        instrument_id: weight
        for instrument_id, weight in normalized_weights.items()
        if instrument_id not in excluded_instrument_ids and weight > _ZERO
    }
    if not weights and target_total:
        raise PortfolioComparisonError("constraints exclude every investable position")
    if Decimal(len(weights)) * cap < target_total:
        raise PortfolioComparisonError(
            "max position cap cannot satisfy invested target"
        )
    return cap, target_total, weights


def _waterfill(
    weights: dict[int, Decimal],
    *,
    cap: Decimal,
    target_total: Decimal,
) -> dict[int, Decimal]:
    """Proportionally redistribute weight until every position meets the cap."""
    if not weights:
        return {}

    remaining = set(weights)
    result: dict[int, Decimal] = {}
    remaining_total = target_total
    while remaining:
        source_total = sum((weights[item] for item in remaining), _ZERO)
        if source_total <= _ZERO:
            equal = remaining_total / Decimal(len(remaining))
            provisional = dict.fromkeys(remaining, equal)
        else:
            provisional = {
                item: remaining_total * weights[item] / source_total
                for item in remaining
            }
        capped = tuple(
            sorted(item for item, weight in provisional.items() if weight > cap)
        )
        if not capped:
            for item, weight in provisional.items():
                result[item] = weight
            break
        for item in capped:
            result[item] = cap
            remaining.remove(item)
            remaining_total -= cap
    rounded = {item: _weight(weight) for item, weight in sorted(result.items())}
    rounding_gap = target_total - sum(rounded.values(), _ZERO)
    if rounding_gap:
        recipient = min(
            (item for item in rounded if rounded[item] + rounding_gap <= cap),
            default=None,
        )
        if recipient is None:
            raise PortfolioComparisonError("rounded target weights violate cap")
        rounded[recipient] = _weight(rounded[recipient] + rounding_gap)
    return rounded


def constrained_target_weights(
    baseline_weights: dict[int, Decimal],
    *,
    excluded_instrument_ids: frozenset[int] = frozenset(),
    max_position_weight: Decimal,
    cash_reserve_weight: Decimal,
) -> dict[int, Decimal]:
    """Apply user constraints with deterministic proportional water filling."""
    cap, target_total, weights = _constraint_inputs(
        baseline_weights,
        excluded_instrument_ids=excluded_instrument_ids,
        max_position_weight=max_position_weight,
        cash_reserve_weight=cash_reserve_weight,
    )
    return _waterfill(weights, cap=cap, target_total=target_total)
