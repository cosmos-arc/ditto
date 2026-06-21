"""Deterministic signal package generation for manual trading."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from hashlib import sha256

import orjson
from ditto_execution.contracts import IntentDataPort
from ditto_execution.targets import TargetPortfolioLike

from ditto_application.execution_dto import TradeIntent, intent_to_record
from ditto_application.processes.execution.ports import PositionReader
from ditto_application.processes.execution.signal_snapshot import SignalSnapshotProcess

__all__ = [
    "SelectionReason",
    "SignalPackage",
    "SignalPackagePublisher",
]


@dataclass(frozen=True)
class SelectionReason:
    """Human-readable reason payload for one selected instrument."""

    instrument_id: int
    target_weight: float
    composite_score: float | None
    rank: int | None
    positive_contributors: tuple[str, ...]
    negative_contributors: tuple[str, ...]
    industry: str | None


@dataclass(frozen=True)
class SignalPackage:
    """Manual-trading signal package emitted from one target portfolio."""

    run_id: str
    strategy_id: str
    signal_date: str
    intents: tuple[TradeIntent, ...]
    dataset_snapshot_ids: dict[str, str]
    factor_ids: tuple[str, ...]
    risk_flags: tuple[str, ...]
    factor_values: dict[int, dict[str, float]]
    selection_reasons: dict[int, SelectionReason]
    checksum: str


class SignalPackagePublisher:
    """Build deterministic packages and persist their trade intents."""

    def __init__(
        self,
        *,
        position_reader: PositionReader,
        intent_port: IntentDataPort,
    ) -> None:
        self._snapshot = SignalSnapshotProcess(position_reader=position_reader)
        self._intent_port = intent_port

    def publish(
        self,
        *,
        target: TargetPortfolioLike,
        dataset_snapshot_ids: dict[str, str] | None = None,
        factor_ids: tuple[str, ...] = (),
        risk_flags: tuple[str, ...] = (),
        factor_values: dict[int, dict[str, float]] | None = None,
        industry_by_instrument: dict[int, str] | None = None,
        threshold: float = 0.01,
    ) -> SignalPackage:
        """Publish a deterministic manual-trading signal package."""
        strategy_id = _target_str(target, "strategy_id")
        signal_date = _target_str(target, "trade_date")
        run_id = _target_str(target, "run_id")
        raw_intents = self._snapshot.generate_intents(
            strategy_id=strategy_id,
            signal_date=signal_date,
            target=target,
            threshold=threshold,
        )
        intents = tuple(
            sorted(
                (
                    replace(
                        intent,
                        intent_id=_stable_intent_id(run_id, signal_date, intent),
                    )
                    for intent in raw_intents
                ),
                key=lambda item: item.instrument_id,
            )
        )
        for intent in intents:
            self._intent_port.save_intent(intent_to_record(intent))

        snapshots = dict(sorted((dataset_snapshot_ids or {}).items()))
        factors = factor_values or {}
        sorted_factor_values = {
            instrument_id: dict(sorted(values.items()))
            for instrument_id, values in sorted(factors.items())
        }
        selection_reasons = _selection_reasons(
            target=target,
            factor_ids=factor_ids,
            factor_values=sorted_factor_values,
            industry_by_instrument=industry_by_instrument or {},
        )
        payload = {
            "dataset_snapshot_ids": snapshots,
            "factor_ids": list(factor_ids),
            "factor_values": {
                str(instrument_id): values
                for instrument_id, values in sorted_factor_values.items()
            },
            "intents": [_intent_payload(intent) for intent in intents],
            "risk_flags": list(risk_flags),
            "run_id": run_id,
            "selection_reasons": {
                str(instrument_id): _selection_reason_payload(reason)
                for instrument_id, reason in sorted(selection_reasons.items())
            },
            "signal_date": signal_date,
            "strategy_id": strategy_id,
        }
        return SignalPackage(
            run_id=run_id,
            strategy_id=strategy_id,
            signal_date=signal_date,
            intents=intents,
            dataset_snapshot_ids=snapshots,
            factor_ids=factor_ids,
            risk_flags=risk_flags,
            factor_values=sorted_factor_values,
            selection_reasons=selection_reasons,
            checksum=_checksum(payload),
        )


def _target_str(target: TargetPortfolioLike, field_name: str) -> str:
    return str(getattr(target, field_name))


def _stable_intent_id(run_id: str, signal_date: str, intent: TradeIntent) -> str:
    direction = intent.direction
    return f"sig-{run_id}-{signal_date}-{intent.instrument_id}-{direction}"


def _intent_payload(intent: TradeIntent) -> dict[str, object]:
    payload = asdict(intent)
    payload.pop("intent_id", None)
    return dict(sorted(payload.items()))


def _selection_reasons(
    *,
    target: TargetPortfolioLike,
    factor_ids: tuple[str, ...],
    factor_values: dict[int, dict[str, float]],
    industry_by_instrument: dict[int, str],
) -> dict[int, SelectionReason]:
    raw_reasons: dict[int, SelectionReason] = {}
    scores: dict[int, float] = {}
    for instrument_key, target_weight in sorted(target.positions.items()):
        instrument_id = int(instrument_key)
        values = factor_values.get(instrument_id, {})
        score = _composite_score(values, factor_ids)
        if score is not None:
            scores[instrument_id] = score
        raw_reasons[instrument_id] = SelectionReason(
            instrument_id=instrument_id,
            target_weight=float(target_weight),
            composite_score=score,
            rank=None,
            positive_contributors=_positive_contributors(values, factor_ids),
            negative_contributors=_negative_contributors(values, factor_ids),
            industry=industry_by_instrument.get(instrument_id),
        )

    ranks = {
        instrument_id: index + 1
        for index, (instrument_id, _) in enumerate(
            sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        )
    }
    return {
        instrument_id: replace(reason, rank=ranks.get(instrument_id))
        for instrument_id, reason in sorted(raw_reasons.items())
    }


def _composite_score(
    values: dict[str, float],
    factor_ids: tuple[str, ...],
) -> float | None:
    factor_scores = [
        values[factor_id] for factor_id in factor_ids if factor_id in values
    ]
    if not factor_scores:
        return None
    return sum(factor_scores) / len(factor_scores)


def _positive_contributors(
    values: dict[str, float],
    factor_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        factor_id
        for factor_id, _ in sorted(
            (
                (factor_id, values[factor_id])
                for factor_id in factor_ids
                if values.get(factor_id, 0.0) > 0.0
            ),
            key=lambda item: (-item[1], item[0]),
        )
    )


def _negative_contributors(
    values: dict[str, float],
    factor_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        factor_id
        for factor_id, _ in sorted(
            (
                (factor_id, values[factor_id])
                for factor_id in factor_ids
                if values.get(factor_id, 0.0) < 0.0
            ),
            key=lambda item: (item[1], item[0]),
        )
    )


def _selection_reason_payload(reason: SelectionReason) -> dict[str, object]:
    return asdict(reason)


def _checksum(payload: Mapping[str, object]) -> str:
    data = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return f"sha256:{sha256(data).hexdigest()}"
