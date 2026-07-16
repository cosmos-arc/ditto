"""Signal-to-fill deviation query facade for manual execution."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from ditto_execution.contracts import FillDataPort, IntentDataPort, PositionDataPort
from ditto_execution.models import PositionRecord

from ditto_application.execution_dto import record_to_intent

__all__ = [
    "SignalDeviationItem",
    "SignalDeviationQueryFacade",
    "SignalDeviationReport",
]

_BPS_FACTOR = 10_000.0


@dataclass(frozen=True)
class SignalDeviationItem:
    """Deviation for one manual trading signal."""

    instrument_id: int
    signal_action: str
    signal_weight: float
    actual_weight: float | None
    deviation_bps: float | None
    fill_status: str


@dataclass(frozen=True)
class SignalDeviationReport:
    """Signal-to-fill deviation report for one strategy and signal date."""

    strategy_id: str
    signal_date: str
    total_signals: int
    filled: int
    unfilled: int
    items: tuple[SignalDeviationItem, ...]


class SignalDeviationQueryFacade:
    """Build a manual execution deviation report from stored intents/fills/positions."""

    def __init__(
        self,
        *,
        intent_port: IntentDataPort,
        fill_port: FillDataPort,
        position_port: PositionDataPort,
    ) -> None:
        self._intent_port = intent_port
        self._fill_port = fill_port
        self._position_port = position_port

    def get_deviation(
        self,
        *,
        strategy_id: str,
        signal_date: str,
        execution_date: str | None = None,
        intent_ids: Collection[str] | None = None,
    ) -> SignalDeviationReport:
        """
        Return one package revision's signal/fill deviation.

        ``signal_date`` selects the decision intents while ``execution_date``
        selects the fills and positions used for post-trade review.  Callers
        that own a signal package should also pass its exact ``intent_ids`` so
        archived revisions from the same signal date cannot enter the report.
        """
        resolved_execution_date = execution_date or signal_date
        intent_records = self._intent_port.list_intents(
            strategy_id=strategy_id,
            signal_date=signal_date,
            status=None,
        )
        if intent_ids is not None:
            allowed_intent_ids = set(intent_ids)
            intent_records = [
                record
                for record in intent_records
                if record.intent_id in allowed_intent_ids
            ]
        fill_records = self._fill_port.list_effective_fills(
            strategy_id=strategy_id,
            trade_date=resolved_execution_date,
            end_date=resolved_execution_date,
        )
        position_records = self._position_port.list_positions(
            strategy_id=strategy_id,
            snapshot_date=resolved_execution_date,
        )

        filled_intent_ids = {record.intent_id for record in fill_records}
        actual_weights = _actual_weights_by_instrument(position_records)

        items: list[SignalDeviationItem] = []
        filled_count = 0
        for intent_record in intent_records:
            intent = record_to_intent(intent_record)
            has_fill = intent.intent_id in filled_intent_ids
            if has_fill:
                filled_count += 1

            actual_weight = (
                _actual_weight_for_filled_signal(
                    intent_target_weight=intent.target_weight,
                    instrument_id=intent.instrument_id,
                    actual_weights=actual_weights,
                )
                if has_fill
                else None
            )
            deviation_bps = (
                (actual_weight - intent.target_weight) * _BPS_FACTOR
                if actual_weight is not None
                else None
            )
            items.append(
                SignalDeviationItem(
                    instrument_id=intent.instrument_id,
                    signal_action=intent.direction,
                    signal_weight=intent.target_weight,
                    actual_weight=actual_weight,
                    deviation_bps=deviation_bps,
                    fill_status="filled" if has_fill else "unfilled",
                )
            )

        return SignalDeviationReport(
            strategy_id=strategy_id,
            signal_date=signal_date,
            total_signals=len(items),
            filled=filled_count,
            unfilled=len(items) - filled_count,
            items=tuple(sorted(items, key=lambda item: item.instrument_id)),
        )


def _actual_weight_for_filled_signal(
    *,
    intent_target_weight: float,
    instrument_id: int,
    actual_weights: dict[int, float],
) -> float:
    return actual_weights.get(instrument_id, intent_target_weight)


def _actual_weights_by_instrument(records: list[PositionRecord]) -> dict[int, float]:
    notionals = {
        record.instrument_id: notional
        for record in records
        if (notional := _position_notional(record)) > 0.0
    }
    total_notional = sum(notionals.values())
    if total_notional <= 0.0:
        return {}
    return {
        instrument_id: notional / total_notional
        for instrument_id, notional in sorted(notionals.items())
    }


def _position_notional(record: PositionRecord) -> float:
    if record.market_value > 0.0:
        return record.market_value
    return record.average_cost * record.quantity
