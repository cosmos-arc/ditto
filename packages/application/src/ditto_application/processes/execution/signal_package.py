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
    "SignalPackage",
    "SignalPackagePublisher",
]


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


def _checksum(payload: Mapping[str, object]) -> str:
    data = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return f"sha256:{sha256(data).hexdigest()}"
