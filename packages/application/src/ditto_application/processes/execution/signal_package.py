"""Deterministic signal package generation for manual trading."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast

import orjson
from ditto_execution.contracts import IntentDataPort
from ditto_execution.targets import TargetPortfolioLike
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

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
    artifact_id: str = ""
    outcome: str = "completed"
    no_rebalance: bool = False


class SignalPackagePublisher:
    """Build deterministic packages and persist their trade intents."""

    def __init__(
        self,
        *,
        position_reader: PositionReader,
        intent_port: IntentDataPort,
        artifact_service: StrategyArtifactService | None = None,
    ) -> None:
        self._snapshot = SignalSnapshotProcess(position_reader=position_reader)
        self._intent_port = intent_port
        self._artifact_service = artifact_service

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
        business_payload = {
            "dataset_snapshot_ids": snapshots,
            "factor_ids": list(factor_ids),
            "factor_values": {
                str(instrument_id): values
                for instrument_id, values in sorted_factor_values.items()
            },
            "intents": [_intent_payload(intent) for intent in raw_intents],
            "risk_flags": list(risk_flags),
            "selection_reasons": {
                str(instrument_id): _selection_reason_payload(reason)
                for instrument_id, reason in sorted(selection_reasons.items())
            },
            "signal_date": signal_date,
            "strategy_id": strategy_id,
            "strategy_version": str(getattr(target, "strategy_version", "")),
        }
        checksum = _checksum(business_payload)
        checksum_revision = checksum.removeprefix("sha256:")[:12]
        intents = tuple(
            sorted(
                (
                    replace(
                        intent,
                        intent_id=_stable_intent_id(
                            run_id, signal_date, checksum_revision, intent
                        ),
                    )
                    for intent in raw_intents
                ),
                key=lambda item: item.instrument_id,
            )
        )
        artifact_id = (
            f"signal-package-{strategy_id}-{signal_date}-{run_id}-{checksum_revision}"
        )
        package = SignalPackage(
            run_id=run_id,
            strategy_id=strategy_id,
            signal_date=signal_date,
            intents=intents,
            dataset_snapshot_ids=snapshots,
            factor_ids=factor_ids,
            risk_flags=risk_flags,
            factor_values=sorted_factor_values,
            selection_reasons=selection_reasons,
            checksum=checksum,
            artifact_id=artifact_id,
            outcome="no_rebalance" if not intents else "completed",
            no_rebalance=not intents,
        )
        existing = self._find_existing(strategy_id, signal_date, run_id)
        if existing is not None and existing.metadata.get("checksum") == checksum:
            return replace(package, artifact_id=existing.artifact_id)
        if existing is not None and not self._supersede_pending(existing):
            return replace(
                package, artifact_id=existing.artifact_id, outcome="rerun_conflict"
            )

        for intent in intents:
            self._intent_port.save_intent(intent_to_record(intent))
        self._save_artifact(package, business_payload)
        return package

    def _find_existing(
        self, strategy_id: str, signal_date: str, run_id: str
    ) -> StrategyArtifactRecord | None:
        if self._artifact_service is None:
            return None
        matches = [
            artifact
            for artifact in self._artifact_service.list_by_strategy(strategy_id)
            if artifact.artifact_type == ArtifactKind.SIGNAL_PACKAGE
            and artifact.status == "active"
            and artifact.metadata.get("signal_date") == signal_date
            and artifact.metadata.get("batch_key") == run_id
        ]
        return matches[-1] if matches else None

    def _supersede_pending(
        self,
        existing: StrategyArtifactRecord,
    ) -> bool:
        old_intents = self._intent_port.list_intents(
            existing.strategy_id,
            signal_date=str(existing.metadata.get("signal_date", "")),
        )
        artifact_intent_ids: set[str] = set()
        raw_artifact_intents = existing.metadata.get("intents")
        if isinstance(raw_artifact_intents, list):
            for raw_item in cast("list[object]", raw_artifact_intents):
                if isinstance(raw_item, dict):
                    item = cast("dict[str, object]", raw_item)
                    intent_id = item.get("intent_id")
                    if intent_id is not None:
                        artifact_intent_ids.add(str(intent_id))
        if artifact_intent_ids:
            old_intents = [
                intent
                for intent in old_intents
                if intent.intent_id in artifact_intent_ids
            ]
        if any(intent.status != "pending" for intent in old_intents):
            return False
        for intent in old_intents:
            updated = self._intent_port.update_intent_status(
                intent.intent_id,
                "superseded",
                expected_current=("pending",),
            )
            if not updated:
                return False
        if self._artifact_service is not None:
            self._artifact_service.archive_artifact(existing.artifact_id)
        return True

    def _save_artifact(
        self,
        package: SignalPackage,
        business_payload: Mapping[str, object],
    ) -> None:
        if self._artifact_service is None:
            return
        metadata = {
            **business_payload,
            "schema_version": "1.0",
            "batch_key": package.run_id,
            "decision_date": package.signal_date,
            "intended_trade_date": package.signal_date,
            "checksum": package.checksum,
            "no_rebalance": package.no_rebalance,
            "outcome": package.outcome,
            "intents": [asdict(intent) for intent in package.intents],
        }
        self._artifact_service.save_artifact(
            StrategyArtifactRecord(
                artifact_id=package.artifact_id,
                strategy_id=package.strategy_id,
                run_id=package.run_id,
                artifact_type=ArtifactKind.SIGNAL_PACKAGE,
                file_path=f"inline://signal-packages/{package.artifact_id}",
                metadata=metadata,
                created_at=datetime.now(UTC).isoformat(),
            )
        )


def _target_str(target: TargetPortfolioLike, field_name: str) -> str:
    return str(getattr(target, field_name))


def _stable_intent_id(
    run_id: str,
    signal_date: str,
    checksum_revision: str,
    intent: TradeIntent,
) -> str:
    direction = intent.direction
    return (
        f"sig-{run_id}-{signal_date}-{checksum_revision}-"
        f"{intent.instrument_id}-{direction}"
    )


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
