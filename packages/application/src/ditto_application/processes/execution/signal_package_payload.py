"""Canonical payload helpers for deterministic R1 signal packages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from math import isfinite
from typing import Literal, cast

from ditto_execution.models import SignalRecord
from ditto_execution.targets import TargetPortfolioLike
from ditto_strategy.models import StrategyArtifactRecord

from ditto_application.exceptions import AppProcessError
from ditto_application.execution_dto import TradeIntent
from ditto_application.processes.execution.signal_package_models import (
    SelectionReason,
    SignalPackage,
)
from ditto_application.signal_package_contract import (
    canonical_signal_package_metadata,
    compute_signal_package_checksum,
)


def artifact_intent_ids(existing: StrategyArtifactRecord) -> set[str] | None:
    """Read the artifact's unique intent IDs or fail closed."""
    raw_artifact_intents = existing.metadata.get("intents")
    if not isinstance(raw_artifact_intents, list):
        return None

    intent_ids: set[str] = set()
    for raw_item in cast("list[object]", raw_artifact_intents):
        if not isinstance(raw_item, dict):
            return None
        intent_id = cast("dict[str, object]", raw_item).get("intent_id")
        if not isinstance(intent_id, str) or not intent_id or intent_id in intent_ids:
            return None
        intent_ids.add(intent_id)
    return intent_ids


def same_intent_payload(left: SignalRecord, right: SignalRecord) -> bool:
    """Compare immutable intent facts while ignoring lifecycle fields."""
    left_payload = asdict(left)
    right_payload = asdict(right)
    for mutable_field in ("status", "created_at"):
        left_payload.pop(mutable_field)
        right_payload.pop(mutable_field)
    return left_payload == right_payload


def validate_target_numbers(
    target: TargetPortfolioLike,
    *,
    threshold: float,
) -> float:
    """Reject non-finite target weights, cash, and publication threshold."""
    _require_finite(threshold, "threshold")
    raw_cash_target = getattr(target, "cash_target", None)
    if not isinstance(raw_cash_target, (int, float)):
        raise AppProcessError("cash_target must be finite")
    cash_target = float(raw_cash_target)
    _require_finite(cash_target, "cash_target")
    for instrument_id, weight in target.positions.items():
        _require_finite(weight, f"target weight for {instrument_id}")
    return cash_target


def validate_factor_values(
    factor_values: Mapping[int, Mapping[str, float]],
) -> None:
    """Reject non-finite factor evidence before canonical serialization."""
    for instrument_id, values in factor_values.items():
        for factor_id, value in values.items():
            _require_finite(value, f"factor {factor_id} for {instrument_id}")


def validate_intent_numbers(intents: Sequence[TradeIntent]) -> None:
    """Reject non-finite intent sizing evidence."""
    fields = (
        "target_weight",
        "current_weight",
        "delta_weight",
        "reference_price",
        "cash_impact",
    )
    for intent in intents:
        for field in fields:
            value = getattr(intent, field)
            if value is not None:
                _require_finite(value, f"intent {intent.instrument_id} {field}")


def _require_finite(value: float, field: str) -> None:
    try:
        finite = isfinite(value)
    except TypeError:
        finite = False
    if not finite:
        raise AppProcessError(f"{field} must be finite")


def artifact_business_payload(
    artifact: StrategyArtifactRecord,
) -> dict[str, object]:
    """Read the checksum-covered business payload from an artifact."""
    raw_payload = artifact.metadata.get("business_payload")
    if not isinstance(raw_payload, dict):
        raise AppProcessError("signal package business payload is missing")
    return dict(cast("dict[str, object]", raw_payload))


def package_from_artifact(artifact: StrategyArtifactRecord) -> SignalPackage:
    """Rehydrate the durable package needed to resume post-run activation."""
    metadata = canonical_signal_package_metadata(artifact.metadata)
    try:
        raw_intents = cast("list[dict[str, object]]", metadata["intents"])
        intents = tuple(_intent_from_metadata(item) for item in raw_intents)
        snapshots = cast("dict[str, str]", metadata["dataset_snapshot_ids"])
        factor_ids = tuple(cast("list[str]", metadata["factor_ids"]))
        risk_flags = tuple(cast("list[str]", metadata["risk_flags"]))
        raw_factor_values = cast(
            "dict[str, dict[str, float]]", metadata["factor_values"]
        )
        factor_values = {
            int(instrument_id): dict(values)
            for instrument_id, values in raw_factor_values.items()
        }
        raw_reasons = cast(
            "dict[str, dict[str, object]]", metadata["selection_reasons"]
        )
        selection_reasons = {
            int(instrument_id): _selection_reason_from_metadata(reason)
            for instrument_id, reason in raw_reasons.items()
        }
        signal_date = cast(str, metadata["signal_date"])
        checksum = cast(str, metadata["checksum"])
        outcome = cast(str, artifact.metadata["outcome"])
        no_rebalance = cast(bool, artifact.metadata["no_rebalance"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppProcessError("staged signal package cannot be rehydrated") from exc
    return SignalPackage(
        run_id=artifact.run_id,
        strategy_id=artifact.strategy_id,
        signal_date=signal_date,
        intents=intents,
        dataset_snapshot_ids=dict(snapshots),
        factor_ids=factor_ids,
        risk_flags=risk_flags,
        factor_values=factor_values,
        selection_reasons=selection_reasons,
        checksum=checksum,
        artifact_id=artifact.artifact_id,
        outcome=outcome,
        no_rebalance=no_rebalance,
        artifact_status=artifact.status,
    )


def _intent_from_metadata(raw: Mapping[str, object]) -> TradeIntent:
    readiness = raw.get("sizing_readiness")
    if readiness not in {None, "ready", "review", "blocked"}:
        raise AppProcessError("invalid sizing readiness")
    return TradeIntent(
        intent_id=cast(str, raw["intent_id"]),
        strategy_id=cast(str, raw["strategy_id"]),
        signal_date=cast(str, raw["signal_date"]),
        instrument_id=cast(int, raw["instrument_id"]),
        direction=cast(str, raw["direction"]),
        target_weight=cast(float, raw["target_weight"]),
        current_weight=cast(float, raw["current_weight"]),
        delta_weight=cast(float, raw["delta_weight"]),
        quantity=cast("int | None", raw.get("quantity")),
        raw_quantity=cast("int | None", raw.get("raw_quantity")),
        rounded_quantity=cast("int | None", raw.get("rounded_quantity")),
        lot_size=cast("int | None", raw.get("lot_size")),
        reference_price=cast("float | None", raw.get("reference_price")),
        cash_impact=cast("float | None", raw.get("cash_impact")),
        sizing_reason=cast("str | None", raw.get("sizing_reason")),
        sizing_readiness=cast(
            'Literal["ready", "review", "blocked"] | None', readiness
        ),
        status=cast(str, raw["status"]),
    )


def _selection_reason_from_metadata(raw: Mapping[str, object]) -> SelectionReason:
    return SelectionReason(
        instrument_id=cast(int, raw["instrument_id"]),
        target_weight=cast(float, raw["target_weight"]),
        composite_score=cast("float | None", raw.get("composite_score")),
        rank=cast("int | None", raw.get("rank")),
        positive_contributors=tuple(
            cast("list[str] | tuple[str, ...]", raw["positive_contributors"])
        ),
        negative_contributors=tuple(
            cast("list[str] | tuple[str, ...]", raw["negative_contributors"])
        ),
        industry=cast("str | None", raw.get("industry")),
    )


def conflict_artifact_id(
    package: SignalPackage,
    existing: StrategyArtifactRecord,
    reason: str,
) -> str:
    """Build a deterministic ID for one persisted publication conflict."""
    digest = compute_signal_package_checksum(
        {
            "candidate_artifact_id": package.artifact_id,
            "conflicting_artifact_id": existing.artifact_id,
            "reason": reason,
        }
    ).removeprefix("sha256:")[:12]
    return f"{package.artifact_id}-conflict-{digest}"


def target_str(target: TargetPortfolioLike, field_name: str) -> str:
    """Read a required target identity field as text."""
    return str(getattr(target, field_name))


def stable_intent_id(
    run_id: str,
    signal_date: str,
    checksum_revision: str,
    intent: TradeIntent,
) -> str:
    """Build a checksum-revision-scoped stable intent ID."""
    direction = intent.direction
    return (
        f"sig-{run_id}-{signal_date}-{checksum_revision}-"
        f"{intent.instrument_id}-{direction}"
    )


def intent_payload(intent: TradeIntent) -> dict[str, object]:
    """Project an intent into its checksum-covered business payload."""
    payload = asdict(intent)
    payload.pop("intent_id", None)
    return dict(sorted(payload.items()))


def intent_sort_key(intent: TradeIntent) -> tuple[object, ...]:
    """Return the deterministic ordering key for package intents."""
    return (
        intent.strategy_id,
        intent.signal_date,
        intent.instrument_id,
        intent.direction,
        intent.target_weight,
        intent.current_weight,
        intent.delta_weight,
        -1 if intent.quantity is None else intent.quantity,
        -1 if intent.raw_quantity is None else intent.raw_quantity,
        -1 if intent.rounded_quantity is None else intent.rounded_quantity,
        -1 if intent.lot_size is None else intent.lot_size,
        float("-inf") if intent.reference_price is None else intent.reference_price,
        float("-inf") if intent.cash_impact is None else intent.cash_impact,
        intent.sizing_reason or "",
        intent.sizing_readiness or "",
        intent.status,
    )


def selection_reasons(
    *,
    target: TargetPortfolioLike,
    factor_ids: tuple[str, ...],
    factor_values: dict[int, dict[str, float]],
    industry_by_instrument: dict[int, str],
) -> dict[int, SelectionReason]:
    """Build deterministic per-instrument selection evidence."""
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


def selection_reason_payload(reason: SelectionReason) -> dict[str, object]:
    """Serialize one selection reason for the canonical payload."""
    return asdict(reason)


def normalize_dataset_states(
    states: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Normalize required-dataset evidence into a stable ordering."""
    normalized = [dict(sorted(state.items())) for state in states]
    return sorted(
        normalized,
        key=lambda state: (
            str(state.get("dataset", "")),
            str(state.get("status", "")),
            str(state.get("snapshot_id", "")),
            str(state.get("reason", "")),
        ),
    )
