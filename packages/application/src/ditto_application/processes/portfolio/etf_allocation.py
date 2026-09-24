"""Immutable ETF research allocations from one dated comparison snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal, cast

import orjson
from ditto_portfolio.target_portfolios.explicit import explicit_target_weights
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
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    build_mutation_idempotency,
)
from ditto_application.queries.etf_candidates import ETFCandidate
from ditto_application.queries.metadata import MetadataQueryFacade

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
class ETFAllocationReviewRequest:
    """Explicit human decision for one immutable target version."""

    allocation_id: str
    version_id: str
    action: Literal["submit", "approve", "reject"]
    actor: str
    reason: str
    idempotency_key: str


@dataclass(frozen=True)
class ETFPaperAuthorizationRequest:
    """Separate operator consent to send one reviewed version to Paper."""

    allocation_id: str
    version_id: str
    account_id: str
    session_id: str
    intended_trade_date: str
    actor: str
    reason: str
    idempotency_key: str


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
    review_status: str
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
        request_hash = _request_hash(request)
        if prior is not None:
            if (
                prior.strategy_id != _strategy_id(request.allocation_id)
                or prior.metadata.get("request_hash") != request_hash
            ):
                raise AppConflictError(
                    "idempotency_key was reused with different input"
                )
            return _version(prior)
        versions = self.list_versions(request.allocation_id)
        if request.parent_version_id is None and versions:
            raise AppConflictError("existing allocation requires parent_version_id")
        if request.parent_version_id is not None and request.parent_version_id not in {
            item.version_id for item in versions
        }:
            raise AppConflictError("parent allocation version was not found")
        try:
            weights = explicit_target_weights(
                request.instrument_ids,
                request.mode,
                request.cash_weight,
                request.max_position_weight,
                request.manual_weights,
            )
        except ValueError as exc:
            raise AppCommandError(str(exc)) from exc
        _check_risk(request, weights)
        candidates = {
            item.instrument_id: item
            for item in self._metadata.list_etf_candidates(
                asof=request.asof,
                cutoff=request.knowledge_cutoff,
                source_snapshot_id=request.source_snapshot_id,
            )
        }
        selected = _select_candidates(request, candidates)
        payload = _payload(request, selected, weights, request_hash)
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

    def review(self, request: ETFAllocationReviewRequest) -> ETFAllocationVersion:
        """Record and apply a separate, exact-version review decision."""
        identity = _review_identity(request)
        strategy_id = _strategy_id(request.allocation_id)
        transitions = {
            "submit": ("draft", "review"),
            "approve": ("review", "approved"),
            "reject": ("review", "rejected"),
        }
        version = _validate_review_target(
            request, self._artifacts.get_artifact(request.version_id), strategy_id
        )
        current, target = transitions[request.action]
        completed_statuses = (
            {"review", "approved", "rejected"}
            if request.action == "submit"
            else {target}
        )
        # One durable fence per (version, idempotency key): the three review
        # actions share this mutation resource, so reusing a key for a different
        # action must conflict here instead of authorizing a second transition.
        receipt_id = _review_receipt_id(request.version_id, identity.key_hash)
        receipt = _review_receipt(request, version, strategy_id, receipt_id, identity)
        prior = self._artifacts.get_artifact(receipt_id)
        if prior is not None and not _same_review_receipt(prior, receipt):
            raise AppConflictError("ETF allocation review decision conflict")
        if version.status in completed_statuses and prior is not None:
            return _version(version)
        if version.status != current:
            raise AppConflictError("ETF allocation review state conflict")
        if request.action == "approve" and not self._has_review_submission(
            strategy_id, request.version_id
        ):
            raise AppConflictError("ETF allocation review submission is missing")
        if not self._artifacts.transition_with_receipt(
            request.version_id, target, current, receipt
        ):
            updated = self._artifacts.get_artifact(request.version_id)
            committed = self._artifacts.get_artifact(receipt_id)
            if (
                updated is not None
                and updated.status in completed_statuses
                and committed is not None
                and _same_review_receipt(committed, receipt)
            ):
                return _version(updated)
            raise AppConflictError("ETF allocation review state conflict")
        updated = self._artifacts.get_artifact(request.version_id)
        if updated is None:
            raise AppConflictError("ETF allocation review result disappeared")
        return _version(updated)

    def _has_review_submission(self, strategy_id: str, version_id: str) -> bool:
        """Find the durable submit receipt a review-state version implies."""
        return any(
            record.artifact_type
            in {ArtifactKind.DIAGNOSTICS, ArtifactKind.ETF_ALLOCATION_REVIEW}
            and record.metadata.get("action") == "submit"
            and record.metadata.get("version_id") == version_id
            for record in self._artifacts.list_by_strategy(strategy_id)
        )

    def authorize_paper(
        self, request: ETFPaperAuthorizationRequest
    ) -> StrategyArtifactRecord:
        """Record a separate operator decision for one approved fixed target."""
        if (
            not request.actor.strip()
            or not request.reason.strip()
            or not request.account_id
            or not request.session_id
        ):
            raise AppCommandError("Paper authorizer and reason are required")
        try:
            date.fromisoformat(request.intended_trade_date)
        except ValueError as exc:
            raise AppCommandError("Paper trade date is invalid") from exc
        strategy_id = _strategy_id(request.allocation_id)
        version = _validate_review_target(
            ETFAllocationReviewRequest(
                allocation_id=request.allocation_id,
                version_id=request.version_id,
                action="approve",
                actor=request.actor,
                reason=request.reason,
                idempotency_key=request.idempotency_key,
            ),
            self._artifacts.get_artifact(request.version_id),
            strategy_id,
        )
        if version.status != "approved" or not any(
            item.metadata.get("version_id") == request.version_id
            and item.metadata.get("target_request_hash")
            == version.metadata.get("request_hash")
            and item.metadata.get("action") == "approve"
            and item.status == "active"
            for item in self._artifacts.list_by_strategy(strategy_id)
        ):
            raise AppConflictError("ETF target needs a durable approved review")
        identity = build_mutation_idempotency(
            operation_id="etf_allocation_authorize_paper",
            resource_id=request.version_id,
            raw_key=request.idempotency_key,
            request_payload={
                "allocation_id": request.allocation_id,
                "version_id": request.version_id,
                "account_id": request.account_id,
                "session_id": request.session_id,
                "intended_trade_date": request.intended_trade_date,
                "actor": request.actor.strip(),
                "reason": request.reason.strip(),
            },
        )
        receipt = StrategyArtifactRecord(
            artifact_id=f"{request.version_id}:paper:{identity.key_hash[:32]}",
            strategy_id=strategy_id,
            run_id=request.version_id,
            artifact_type=ArtifactKind.DIAGNOSTICS,
            file_path="",
            metadata={
                "action": "authorize_paper",
                "version_id": request.version_id,
                "account_id": request.account_id,
                "session_id": request.session_id,
                "intended_trade_date": request.intended_trade_date,
                "target_request_hash": version.metadata["request_hash"],
                "actor": request.actor.strip(),
                "reason": request.reason.strip(),
                "key_hash": identity.key_hash,
            },
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
        try:
            return self._artifacts.save_artifact(receipt)
        except ValueError as exc:
            raise AppConflictError("ETF Paper authorization key conflict") from exc

    def authorized_paper_version(
        self,
        *,
        allocation_id: str,
        version_id: str,
        authorization_id: str,
        account_id: str,
        session_id: str,
        intended_trade_date: str,
    ) -> ETFAllocationVersion:
        """Resolve the exact approved target and its scoped Paper consent."""
        strategy_id = _strategy_id(allocation_id)
        version = self._artifacts.get_artifact(version_id)
        authorization = self._artifacts.get_artifact(authorization_id)
        if (
            version is None
            or version.strategy_id != strategy_id
            or version.artifact_type is not ArtifactKind.TARGET_PORTFOLIO
            or version.status != "approved"
            or authorization is None
            or authorization.strategy_id != strategy_id
            or authorization.artifact_type is not ArtifactKind.DIAGNOSTICS
            or authorization.status != "active"
            or authorization.metadata.get("action") != "authorize_paper"
            or authorization.metadata.get("version_id") != version_id
            or authorization.metadata.get("account_id") != account_id
            or authorization.metadata.get("session_id") != session_id
            or authorization.metadata.get("intended_trade_date") != intended_trade_date
            or authorization.metadata.get("target_request_hash")
            != version.metadata.get("request_hash")
        ):
            raise AppConflictError("ETF Paper target authorization is missing")
        return _version(version)


def _review_receipt_id(version_id: str, key_hash: str) -> str:
    return f"{version_id}:review:{key_hash[:32]}"


def _review_identity(request: ETFAllocationReviewRequest) -> MutationIdempotency:
    """Validate the transport key at the shared boundary and drop its raw form."""
    return build_mutation_idempotency(
        operation_id="etf_allocation_review",
        resource_id=request.version_id,
        raw_key=request.idempotency_key,
        request_payload={
            "allocation_id": request.allocation_id,
            "version_id": request.version_id,
            "action": request.action,
            "actor": request.actor.strip(),
            "reason": request.reason.strip(),
        },
    )


def _review_receipt(
    request: ETFAllocationReviewRequest,
    version: StrategyArtifactRecord,
    strategy_id: str,
    receipt_id: str,
    identity: MutationIdempotency,
) -> StrategyArtifactRecord:
    return StrategyArtifactRecord(
        artifact_id=receipt_id,
        strategy_id=strategy_id,
        run_id=request.version_id,
        artifact_type=ArtifactKind.DIAGNOSTICS,
        file_path="",
        metadata={
            "version_id": request.version_id,
            "target_request_hash": version.metadata["request_hash"],
            "action": request.action,
            "actor": request.actor.strip(),
            "reason": request.reason.strip(),
            "key_hash": identity.key_hash,
        },
        status="active",
        created_at=datetime.now(UTC).isoformat(),
    )


def _same_review_receipt(
    existing: StrategyArtifactRecord, expected: StrategyArtifactRecord
) -> bool:
    return (
        existing.status == "active"
        and existing.artifact_id == expected.artifact_id
        and existing.file_path == expected.file_path
        and existing.strategy_id == expected.strategy_id
        and existing.run_id == expected.run_id
        and existing.artifact_type
        in {ArtifactKind.DIAGNOSTICS, ArtifactKind.ETF_ALLOCATION_REVIEW}
        and existing.metadata == expected.metadata
    )


def _validate_review_target(
    request: ETFAllocationReviewRequest,
    version: StrategyArtifactRecord | None,
    strategy_id: str,
) -> StrategyArtifactRecord:
    if not request.actor.strip() or not request.reason.strip():
        raise AppCommandError("review actor and reason are required")
    if request.action not in {"submit", "approve", "reject"}:
        raise AppCommandError("unsupported ETF allocation review action")
    if (
        version is None
        or version.strategy_id != strategy_id
        or version.artifact_type is not ArtifactKind.TARGET_PORTFOLIO
        or version.metadata.get("kind") != "etf_allocation"
    ):
        raise AppConflictError("ETF allocation version was not found")
    return version


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
    request_hash: str,
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
        "request_hash": request_hash,
    }
    return payload


def _request_hash(request: ETFAllocationRequest) -> str:
    return sha256(
        orjson.dumps(
            {
                "allocation_id": request.allocation_id,
                "idempotency_key": request.idempotency_key,
                "parent_version_id": request.parent_version_id,
                "asof": request.asof,
                "knowledge_cutoff": request.knowledge_cutoff,
                "source_snapshot_id": request.source_snapshot_id,
                "instrument_ids": request.instrument_ids,
                "mode": request.mode,
                "cash_weight": str(request.cash_weight),
                "max_position_weight": str(request.max_position_weight),
                "manual_weights": {
                    str(i): str(w) for i, w in sorted(request.manual_weights.items())
                },
                "reason": request.reason,
            },
            option=orjson.OPT_SORT_KEYS,
        )
    ).hexdigest()


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
        # paper_status keeps the released v1 domain ("research_only" means no
        # Paper authority); review state is exposed additively so v1 clients
        # keep reading this record after a review decision lands.
        paper_status="research_only",
        review_status={
            "draft": "research_only",
            "review": "review_pending",
            "approved": "review_approved",
            "rejected": "rejected",
        }.get(record.status, "research_only"),
        created_at=record.created_at,
    )
