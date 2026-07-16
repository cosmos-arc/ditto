"""账户基线与 D 日市场事实到人工 sizing 上下文的适配。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from math import isfinite
from typing import Literal, Protocol

import polars as pl
from ditto_kernel.trading import DEFAULT_COMMISSION_RATE, DEFAULT_MIN_COMMISSION

from ditto_application.exceptions import AppProcessError
from ditto_application.queries.account import AccountBaselineReadModel


class _AccountBaselineReader(Protocol):
    def get_latest(
        self,
        *,
        account_id: str,
        strategy_id: str,
        signal_date: str,
    ) -> AccountBaselineReadModel | None: ...


class _MarketCloseReader(Protocol):
    def find_bars(
        self,
        *,
        instrument_ids: list[int] | None = None,
        start: str | None = None,
        end: str | None = None,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame: ...


@dataclass(frozen=True)
class ManualSizingContext:
    """SignalSnapshotProcess 可按标的提供的账户和行情上下文。"""

    nav: float
    current_quantity: int
    available_quantity: int
    cash_available: float
    reference_price: float | None
    lot_size: int = 100
    risk_quantity_limit: int | None = None
    commission_rate: float = DEFAULT_COMMISSION_RATE
    min_commission: float = DEFAULT_MIN_COMMISSION
    settlement_cycle: int = 1
    is_suspended: bool = False
    at_price_limit: bool = False
    is_limit_up: bool = False
    is_limit_down: bool = False
    is_risk_locked: bool = False
    tradability_reason: Literal["tradability_unverified"] | None = None
    current_weight: float | None = None


@dataclass(frozen=True)
class ManualSizingContexts:
    """来自同一账户基线的 sizing 上下文及其显式身份。"""

    account_id: str
    sleeve_id: str
    contexts: dict[int, ManualSizingContext]


@dataclass(frozen=True)
class _MarketSizingFacts:
    reference_price: float | None
    is_suspended: bool
    at_price_limit: bool
    is_limit_up: bool
    is_limit_down: bool
    tradability_reason: Literal["tradability_unverified"] | None


class ManualSizingContextBuilder:
    """从账户基线、D 日收盘价与权威可交易性事实构建 sizing 上下文。"""

    def __init__(
        self,
        *,
        account_query: _AccountBaselineReader,
        market_query: _MarketCloseReader,
    ) -> None:
        self._account_query = account_query
        self._market_query = market_query

    def build(
        self,
        *,
        account_id: str,
        strategy_id: str,
        signal_date: str,
        instrument_ids: tuple[int, ...],
        allow_experimental_data: bool = False,
        risk_locked_instruments: tuple[int, ...] = (),
        risk_quantity_limits: Mapping[int, int] | None = None,
    ) -> ManualSizingContexts:
        """
        读取完整基线与 D 日市场事实；无法证明可交易时保持阻塞。

        ``risk_quantity_limits`` 只接收权威风险策略显式产出的逐标的数量上限；
        strategy max-weight 等目标约束不在此处猜测或换算为数量上限。
        """
        if not account_id:
            raise AppProcessError("account_id is required for manual sizing")
        baseline = self._account_query.get_latest(
            account_id=account_id,
            strategy_id=strategy_id,
            signal_date=signal_date,
        )
        if baseline is None:
            baseline_key = ", ".join(
                (
                    f"account_id={account_id}",
                    f"strategy_id={strategy_id}",
                    f"signal_date={signal_date}",
                )
            )
            raise AppProcessError(
                f"Account baseline missing for {baseline_key}",
                code="ACCOUNT_BASELINE_MISSING",
                account_id=account_id,
                strategy_id=strategy_id,
                signal_date=signal_date,
            )

        account = baseline.account
        if account.account_id != account_id or account.strategy_id != strategy_id:
            raise AppProcessError("Account baseline identity does not match request")
        if not account.run_id:
            raise AppProcessError("Account baseline sleeve_id is missing")
        locked = {int(instrument_id) for instrument_id in risk_locked_instruments}
        quantity_limits = _validated_risk_quantity_limits(risk_quantity_limits)

        unique_instruments = tuple(
            sorted(
                set(instrument_ids).union(
                    position.instrument_id for position in baseline.positions
                )
            )
        )
        market_facts = self._load_market_facts(
            instrument_ids=unique_instruments,
            signal_date=signal_date,
            allow_experimental_data=allow_experimental_data,
        )
        positions = {
            position.instrument_id: position for position in baseline.positions
        }
        contexts: dict[int, ManualSizingContext] = {}
        for instrument_id in unique_instruments:
            position = positions.get(instrument_id)
            market_value = position.market_value if position is not None else 0.0
            current_weight = (
                market_value / account.total_value if account.total_value > 0 else 0.0
            )
            facts = market_facts.get(
                instrument_id,
                _MarketSizingFacts(
                    reference_price=None,
                    is_suspended=False,
                    at_price_limit=False,
                    is_limit_up=False,
                    is_limit_down=False,
                    tradability_reason="tradability_unverified",
                ),
            )
            contexts[instrument_id] = ManualSizingContext(
                nav=account.total_value,
                current_quantity=position.quantity if position is not None else 0,
                available_quantity=(
                    position.available_quantity if position is not None else 0
                ),
                cash_available=account.cash_available,
                reference_price=facts.reference_price,
                risk_quantity_limit=quantity_limits.get(instrument_id),
                is_suspended=facts.is_suspended,
                at_price_limit=facts.at_price_limit,
                is_limit_up=facts.is_limit_up,
                is_limit_down=facts.is_limit_down,
                is_risk_locked=instrument_id in locked,
                tradability_reason=facts.tradability_reason,
                current_weight=current_weight,
            )
        return ManualSizingContexts(
            account_id=account.account_id,
            sleeve_id=account.run_id,
            contexts=contexts,
        )

    def _load_market_facts(
        self,
        *,
        instrument_ids: tuple[int, ...],
        signal_date: str,
        allow_experimental_data: bool,
    ) -> dict[int, _MarketSizingFacts]:
        if not instrument_ids:
            return {}
        frame = self._market_query.find_bars(
            instrument_ids=list(instrument_ids),
            start=signal_date,
            end=signal_date,
            allow_experimental_data=allow_experimental_data,
        )
        if frame.is_empty():
            return {}
        required_columns = {"instrument_id", "trade_date", "close"}
        if not required_columns.issubset(frame.columns):
            missing = sorted(required_columns.difference(frame.columns))
            raise AppProcessError(f"Market close response missing columns: {missing}")

        facts_by_instrument: dict[int, _MarketSizingFacts] = {}
        for row in frame.iter_rows(named=True):
            row_date = row["trade_date"]
            date_text = (
                row_date.isoformat()
                if hasattr(row_date, "isoformat")
                else str(row_date)
            )
            if date_text != signal_date:
                continue
            instrument_id = int(row["instrument_id"])
            if instrument_id in facts_by_instrument:
                close_key = ", ".join(
                    (
                        f"instrument_id={instrument_id}",
                        f"signal_date={signal_date}",
                    )
                )
                raise AppProcessError(f"Duplicate market close for {close_key}")
            reference_price = _positive_number(row["close"])
            suspension_state = _optional_bool(row.get("is_suspended"))
            limit_up_state = _optional_bool(row.get("is_limit_up"))
            limit_down_state = _optional_bool(row.get("is_limit_down"))
            traded_volume = _nonnegative_number(row.get("volume"))
            traded_amount = _nonnegative_number(row.get("amount"))
            if suspension_state is None and (
                (traded_volume is not None and traded_volume > 0)
                or (traded_amount is not None and traded_amount > 0)
            ):
                suspension_state = False
            is_suspended = suspension_state is True
            is_limit_up = limit_up_state is True
            is_limit_down = limit_down_state is True
            limit_state_known = (
                limit_up_state is not None and limit_down_state is not None
            )
            up_limit = _positive_number(row.get("up_limit"))
            down_limit = _positive_number(row.get("down_limit"))
            if (
                reference_price is not None
                and up_limit is not None
                and down_limit is not None
            ):
                limit_state_known = True
                is_limit_up = is_limit_up or _matches_price_limit(
                    reference_price,
                    up_limit,
                )
                is_limit_down = is_limit_down or _matches_price_limit(
                    reference_price,
                    down_limit,
                )
            pre_close = _positive_number(row.get("pre_close"))
            if (
                reference_price is not None
                and not limit_state_known
                and pre_close is not None
            ):
                limit_state_known = True
                inferred_up, inferred_down = _a_share_fund_limit_sides(
                    close=reference_price,
                    pre_close=pre_close,
                )
                is_limit_up = is_limit_up or inferred_up
                is_limit_down = is_limit_down or inferred_down
            at_price_limit = is_limit_up or is_limit_down
            # Limit evidence says nothing about suspension.  Only an explicit
            # suspension flag or positive trading activity can establish that
            # dimension; otherwise even the normally permitted opposite-side
            # trade at a price limit must remain fail-closed.
            tradability_known = is_suspended or (
                suspension_state is not None and limit_state_known
            )
            facts_by_instrument[instrument_id] = _MarketSizingFacts(
                reference_price=reference_price,
                is_suspended=is_suspended,
                at_price_limit=at_price_limit,
                is_limit_up=is_limit_up,
                is_limit_down=is_limit_down,
                tradability_reason=(
                    None if tradability_known else "tradability_unverified"
                ),
            )
        return facts_by_instrument


def _validated_risk_quantity_limits(
    values: Mapping[int, int] | None,
) -> dict[int, int]:
    result: dict[int, int] = {}
    for raw_instrument_id, raw_limit in (values or {}).items():
        if not _is_non_negative_int(raw_instrument_id) or not _is_non_negative_int(
            raw_limit
        ):
            raise AppProcessError("risk quantity limits must be non-negative integers")
        result[int(raw_instrument_id)] = raw_limit
    return result


def _is_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _positive_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) and number > 0 else None


def _nonnegative_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) and number >= 0 else None


def _matches_price_limit(close: float, limit: float) -> bool:
    return abs(close - limit) <= max(1e-8, abs(limit) * 1e-8)


def _a_share_fund_limit_sides(*, close: float, pre_close: float) -> tuple[bool, bool]:
    """Conservatively match the exchange fund upper/lower limit separately."""
    close_decimal = Decimal(str(close))
    pre_close_decimal = Decimal(str(pre_close))
    tick = Decimal("0.001")
    is_limit_up = False
    is_limit_down = False
    for ratio in (Decimal("0.10"), Decimal("0.20")):
        for direction in (Decimal("-1"), Decimal("1")):
            limit = (pre_close_decimal * (1 + direction * ratio)).quantize(
                tick,
                rounding=ROUND_HALF_UP,
            )
            if abs(close_decimal - limit) <= tick / 2:
                is_limit_up = is_limit_up or direction > 0
                is_limit_down = is_limit_down or direction < 0
    return is_limit_up, is_limit_down
