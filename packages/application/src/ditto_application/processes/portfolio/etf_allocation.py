"""Immutable ETF research allocations from one dated comparison snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Literal, cast

import orjson
from ditto_risk.portfolio_scenario import (
    PortfolioScenarioInput,
    ScenarioPosition,
    preview_portfolio_scenario,
)
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_application.exceptions import AppCommandError, AppConflictError
from ditto_application.queries.etf_candidates import ETFCandidate
from ditto_application.queries.metadata import MetadataQueryFacade

_ONE = Decimal("1")
_PRECISION = Decimal("0.00000001")
_RULE_VERSION = "etf-allocation-v1"
_MAX_KEY_LENGTH = 128
_MAX_ID_LENGTH = 80


@dataclass(frozen=True)
class ETFAllocationRequest:
    """Exact user intent, source revision and retry identity."""

    allocation_id: str
    idempotency_key: str
    parent_version_id: str | None
    asof: str
    knowledge_cutoff: str
    source_snapshot_id: str
    instrument_ids: tuple[int, ...]
    mode: Literal["equal", "manual"]
    cash_weight: Decimal
    max_position_weight: Decimal
    manual_weights: dict[int, Decimal]
    reason: str


@dataclass(frozen=True)
class ETFAllocationVersion:
    """Saved research target that has no Paper execution authority."""

    version_id: str
    allocation_id: str
    parent_version_id: str | None
    asof: str
    knowledge_cutoff: str
    source_snapshot_id: str
    mode: str
    weights: dict[int, str]
    cash_weight: str
    max_position_weight: str
    tracking_exposure: dict[str, str]
    reason: str
    rule_version: str
    paper_status: str
    created_at: str


class ETFAllocationCommand:
    """Validate candidates and save immutable, idempotent research versions."""

    def __init__(
        self, metadata: MetadataQueryFacade, artifacts: StrategyArtifactService
    ) -> None:
        self._metadata = metadata
        self._artifacts = artifacts

    def list_versions(self, allocation_id: str) -> list[ETFAllocationVersion]:
        """Restore versions of one user-named allocation."""
        return [
            _version(record)
            for record in self._artifacts.list_by_strategy(_strategy_id(allocation_id))
            if record.artifact_type is ArtifactKind.TARGET_PORTFOLIO
            and record.metadata.get("kind") == "etf_allocation"
        ]

    def save(self, request: ETFAllocationRequest) -> ETFAllocationVersion:
        """Persist an exact revision or return its durable retry result."""
        _check_request(request)
        version_id = (
            "etf-allocation-"
            + sha256(
                f"{request.allocation_id}\0{request.idempotency_key}".encode()
            ).hexdigest()[:32]
        )
        prior = self._artifacts.get_artifact(version_id)
        versions = self.list_versions(request.allocation_id)
        if request.parent_version_id is None and versions and prior is None:
            raise AppConflictError("existing allocation requires parent_version_id")
        if request.parent_version_id is not None and request.parent_version_id not in {
            item.version_id for item in versions
        }:
            raise AppConflictError("parent allocation version was not found")
        candidates = {
            item.instrument_id: item
            for item in self._metadata.list_etf_candidates(
                asof=request.asof,
                cutoff=request.knowledge_cutoff,
                source_snapshot_id=request.source_snapshot_id,
            )
        }
        selected = _select_candidates(request, candidates)
        weights = _weights(request)
        _check_risk(request, weights)
        payload = _payload(request, selected, weights)
        if prior is not None:
            if (
                prior.strategy_id != _strategy_id(request.allocation_id)
                or prior.metadata != payload
            ):
                raise AppConflictError(
                    "idempotency_key was reused with different input"
                )
            return _version(prior)
        record = StrategyArtifactRecord(
            artifact_id=version_id,
            strategy_id=_strategy_id(request.allocation_id),
            run_id=version_id,
            artifact_type=ArtifactKind.TARGET_PORTFOLIO,
            file_path="",
            metadata=payload,
            status="draft",
            created_at=datetime.now(UTC).isoformat(),
        )
        try:
            return _version(self._artifacts.save_artifact(record))
        except ValueError as exc:
            raise AppConflictError("allocation version conflict") from exc


def _check_request(request: ETFAllocationRequest) -> None:
    _strategy_id(request.allocation_id)
    if not request.idempotency_key or len(request.idempotency_key) > _MAX_KEY_LENGTH:
        raise AppCommandError(
            "idempotency_key is required and limited to 128 characters"
        )
    if not request.reason.strip() or not request.source_snapshot_id:
        raise AppCommandError("reason and source_snapshot_id are required")
    if not request.instrument_ids or len(set(request.instrument_ids)) != len(
        request.instrument_ids
    ):
        raise AppCommandError("selected ETF identities must be non-empty and unique")
    if any(item <= 0 for item in request.instrument_ids):
        raise AppCommandError("selected ETF identities must be positive")
    if not _valid_weight(request.cash_weight, allow_one=False):
        raise AppCommandError(
            "cash_weight must be between zero and one at eight-decimal precision"
        )
    if not _valid_weight(request.max_position_weight, allow_zero=False):
        raise AppCommandError("max_position_weight must be positive and at most one")
    try:
        day = date.fromisoformat(request.asof)
        cutoff = datetime.fromisoformat(request.knowledge_cutoff.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppCommandError("asof or knowledge_cutoff is invalid") from exc
    if cutoff.tzinfo is None or cutoff.astimezone(UTC).date() < day:
        raise AppCommandError("knowledge_cutoff must include a timezone and cover asof")


def _select_candidates(
    request: ETFAllocationRequest, candidates: dict[int, ETFCandidate]
) -> list[ETFCandidate]:
    selected: list[ETFCandidate] = []
    for instrument_id in request.instrument_ids:
        item = candidates.get(instrument_id)
        if item is None:
            raise AppCommandError(
                f"ETF candidate {instrument_id} is not visible at this snapshot"
            )
        selected.append(item)
    return selected


def _weights(request: ETFAllocationRequest) -> dict[int, Decimal]:
    budget = _ONE - request.cash_weight
    if request.mode == "equal":
        if request.manual_weights:
            raise AppCommandError("equal mode must not include manual_weights")
        each = (budget / Decimal(len(request.instrument_ids))).quantize(_PRECISION)
        weights = dict.fromkeys(request.instrument_ids, each)
        weights[request.instrument_ids[-1]] += budget - sum(weights.values())
    elif request.mode == "manual":
        if set(request.manual_weights) != set(request.instrument_ids):
            raise AppCommandError("manual_weights must cover exactly the selected ETFs")
        weights = dict(request.manual_weights)
        if any(not _valid_weight(weight) for weight in weights.values()):
            raise AppCommandError(
                "manual_weights must be non-negative at eight-decimal precision"
            )
        if sum(weights.values()) != budget:
            raise AppCommandError("manual_weights plus cash_weight must equal one")
    else:
        raise AppCommandError("unsupported ETF allocation mode")
    if any(weight > request.max_position_weight for weight in weights.values()):
        raise AppCommandError("selected ETF weight exceeds max_position_weight")
    return weights


def _check_risk(request: ETFAllocationRequest, weights: dict[int, Decimal]) -> None:
    try:
        preview = preview_portfolio_scenario(
            PortfolioScenarioInput(
                as_of=request.asof,
                valuation_snapshot_id=request.source_snapshot_id,
                source_snapshot_ids=(request.source_snapshot_id,),
                current_positions=(),
                proposed_positions=tuple(
                    ScenarioPosition(instrument_id=i, weight=float(w))
                    for i, w in sorted(weights.items())
                ),
                cash_reserve_weight=float(request.cash_weight),
                max_position_weight=float(request.max_position_weight),
            )
        )
    except ValueError as exc:
        raise AppCommandError("ETF allocation risk input is invalid") from exc
    if preview.constraint_findings:
        raise AppCommandError("; ".join(preview.constraint_findings))


def _payload(
    request: ETFAllocationRequest,
    selected: list[ETFCandidate],
    weights: dict[int, Decimal],
) -> dict[str, object]:
    exposure: dict[str, Decimal] = {}
    for item in selected:
        tracking = item.fields["tracking_index"].value
        if isinstance(tracking, str):
            exposure[tracking] = (
                exposure.get(tracking, Decimal(0)) + weights[item.instrument_id]
            )
    payload: dict[str, object] = {
        "kind": "etf_allocation",
        "allocation_id": request.allocation_id,
        "parent_version_id": request.parent_version_id,
        "asof": request.asof,
        "knowledge_cutoff": request.knowledge_cutoff,
        "source_snapshot_id": request.source_snapshot_id,
        "mode": request.mode,
        "weights": {str(i): str(w) for i, w in sorted(weights.items())},
        "cash_weight": str(request.cash_weight),
        "max_position_weight": str(request.max_position_weight),
        "tracking_exposure": {
            key: str(value) for key, value in sorted(exposure.items())
        },
        "reason": request.reason,
        "rule_version": _RULE_VERSION,
        "paper_status": "research_only",
    }
    payload["request_hash"] = sha256(
        orjson.dumps(
            {
                "idempotency_key": request.idempotency_key,
                "instrument_ids": request.instrument_ids,
                "manual_weights": {
                    str(i): str(w) for i, w in sorted(request.manual_weights.items())
                },
                **payload,
            },
            option=orjson.OPT_SORT_KEYS,
        )
    ).hexdigest()
    return payload


def _strategy_id(allocation_id: str) -> str:
    if (
        not allocation_id
        or len(allocation_id) > _MAX_ID_LENGTH
        or any(
            not (char.isascii() and (char.isalnum() or char in "-_"))
            for char in allocation_id
        )
    ):
        raise AppCommandError(
            "allocation_id must use ASCII letters, digits, dash or underscore"
        )
    return f"etf-allocation:{allocation_id}"


def _valid_weight(
    value: Decimal, *, allow_zero: bool = True, allow_one: bool = True
) -> bool:
    try:
        return (
            value.is_finite()
            and (value >= 0 if allow_zero else value > 0)
            and (value <= 1 if allow_one else value < 1)
            and value == value.quantize(_PRECISION)
        )
    except (InvalidOperation, AttributeError):
        return False


def _version(record: StrategyArtifactRecord) -> ETFAllocationVersion:
    payload = record.metadata
    weights = payload["weights"]
    exposure = payload["tracking_exposure"]
    if not isinstance(weights, dict) or not isinstance(exposure, dict):
        raise AppCommandError("saved ETF allocation payload is invalid")
    parent = payload.get("parent_version_id")
    weight_values = cast("dict[str, object]", weights)
    exposure_values = cast("dict[str, object]", exposure)
    try:
        parsed_weights = {int(i): str(w) for i, w in weight_values.items()}
    except ValueError as exc:
        raise AppCommandError("saved ETF allocation weights are invalid") from exc
    return ETFAllocationVersion(
        version_id=record.artifact_id,
        allocation_id=str(payload["allocation_id"]),
        parent_version_id=parent if isinstance(parent, str) else None,
        asof=str(payload["asof"]),
        knowledge_cutoff=str(payload["knowledge_cutoff"]),
        source_snapshot_id=str(payload["source_snapshot_id"]),
        mode=str(payload["mode"]),
        weights=parsed_weights,
        cash_weight=str(payload["cash_weight"]),
        max_position_weight=str(payload["max_position_weight"]),
        tracking_exposure={str(i): str(w) for i, w in exposure_values.items()},
        reason=str(payload["reason"]),
        rule_version=str(payload["rule_version"]),
        paper_status=str(payload["paper_status"]),
        created_at=record.created_at,
    )
