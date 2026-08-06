"""Typed durable receipt codecs for strategy governance mutations."""

from __future__ import annotations

from ditto_strategy.governance.models import StrategyDecision
from ditto_strategy.governance.service import GovernanceService

from ditto_application.contracts import (
    StrategyActivePointerInfo,
    StrategyVersionStateInfo,
)
from ditto_application.exceptions import AppCommandError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    canonical_resource_id,
    find_mutation_receipt_in_reasons,
    mutation_event_id,
)
from ditto_application.processes.strategy.promotion import StrategyPromotionProcess


def invalid_strategy_receipt() -> AppCommandError:
    """Return the stable fail-closed error for corrupt governance history."""
    return AppCommandError(
        "durable strategy receipt is invalid",
        details={
            "code": "IDEMPOTENCY_RECEIPT_INVALID",
            "reason": "idempotency_receipt_invalid",
        },
    )


def state_receipt(info: StrategyVersionStateInfo) -> dict[str, object]:
    """Encode the exact lifecycle response stored in a decision event."""
    return {
        "strategy_id": info.strategy_id,
        "version": info.version,
        "state": info.state,
        "review_outcome": info.review_outcome,
    }


def state_from_receipt(value: dict[str, object]) -> StrategyVersionStateInfo:
    if (
        set(value) != {"strategy_id", "version", "state", "review_outcome"}
        or type(value["strategy_id"]) is not str
        or type(value["version"]) is not int
        or type(value["state"]) is not str
        or type(value["review_outcome"]) is not str
    ):
        raise invalid_strategy_receipt()
    return StrategyVersionStateInfo(
        strategy_id=value["strategy_id"],
        version=value["version"],
        state=value["state"],
        review_outcome=value["review_outcome"],
    )


def pointer_receipt(info: StrategyActivePointerInfo) -> dict[str, object]:
    """Encode the exact active-pointer response stored in an event pair."""
    return {
        "strategy_id": info.strategy_id,
        "active_version": info.active_version,
        "pointer_revision": info.pointer_revision,
    }


def pointer_from_receipt(value: dict[str, object]) -> StrategyActivePointerInfo:
    if (
        set(value) != {"strategy_id", "active_version", "pointer_revision"}
        or type(value["strategy_id"]) is not str
        or type(value["active_version"]) is not int
        or type(value["pointer_revision"]) is not int
    ):
        raise invalid_strategy_receipt()
    return StrategyActivePointerInfo(
        strategy_id=value["strategy_id"],
        active_version=value["active_version"],
        pointer_revision=value["pointer_revision"],
    )


def replay_strategy_decision(
    governance: GovernanceService,
    identity: MutationIdempotency | None,
    *,
    strategy_id: str,
    version: int,
) -> StrategyVersionStateInfo | None:
    """Replay an exact decision receipt after validating lifecycle history."""
    if identity is None:
        return None
    event = governance.get_decision_event(mutation_event_id(identity))
    if event is None:
        return None
    expected = {
        "strategies_submit_strategy_review": (
            StrategyDecision.SUBMIT_REVIEW,
            "review",
            "pending",
        ),
        "strategies_approve_strategy_review": (
            StrategyDecision.APPROVE,
            "review",
            "approved",
        ),
        "strategies_reject_strategy_review": (
            StrategyDecision.REJECT,
            "review",
            "rejected",
        ),
        "strategies_deprecate_strategy_version": (
            StrategyDecision.DEPRECATE,
            "deprecated",
            "approved",
        ),
    }.get(identity.operation_id)
    if (
        expected is None
        or identity.resource_id
        != canonical_resource_id(
            "strategy_version",
            {"strategy_id": strategy_id, "version": version},
        )
        or event.event_id != mutation_event_id(identity)
        or event.strategy_id != strategy_id
        or event.version != version
        or event.decision is not expected[0]
        or not event.actor
        or not event.decided_at
    ):
        raise invalid_strategy_receipt()
    receipt = find_mutation_receipt_in_reasons((event.reason,), identity)
    if receipt is None:
        raise invalid_strategy_receipt()
    result = state_from_receipt(dict(receipt))
    if (
        result.strategy_id != strategy_id
        or result.version != version
        or result.state != expected[1]
        or result.review_outcome != expected[2]
    ):
        raise invalid_strategy_receipt()
    return result


def replay_strategy_activation(
    governance: GovernanceService,
    identity: MutationIdempotency | None,
    *,
    strategy_id: str,
    version: int,
) -> StrategyActivePointerInfo | None:
    """Replay an exact activation receipt after validating pointer history."""
    if identity is None:
        return None
    event = governance.get_activation_event(mutation_event_id(identity))
    if event is None:
        return None
    if (
        identity.operation_id != "strategies_reactivate_strategy_version"
        or identity.resource_id
        != canonical_resource_id(
            "strategy_version",
            {"strategy_id": strategy_id, "version": version},
        )
        or event.event_id != mutation_event_id(identity)
        or event.strategy_id != strategy_id
        or event.target_version != version
        or event.activation_kind is not StrategyDecision.REACTIVATE
        or not event.actor
        or not event.activated_at
    ):
        raise invalid_strategy_receipt()
    receipt = find_mutation_receipt_in_reasons((event.reason,), identity)
    if receipt is None:
        raise invalid_strategy_receipt()
    result = pointer_from_receipt(dict(receipt))
    if (
        result.strategy_id != strategy_id
        or result.active_version != version
        or result.pointer_revision <= 0
    ):
        raise invalid_strategy_receipt()
    return result


def replay_strategy_publish(
    process: StrategyPromotionProcess,
    identity: MutationIdempotency | None,
    *,
    strategy_id: str,
    version: int,
) -> StrategyActivePointerInfo | None:
    """Replay the paired publish decision and activation receipt."""
    if identity is None:
        return None
    publish_id = mutation_event_id(identity)
    activate_id = f"{publish_id}:activate"
    decision = process.get_decision_event(publish_id)
    activation = process.get_activation_event(activate_id)
    if decision is None and activation is None:
        return None
    if (
        decision is None
        or activation is None
        or decision.event_id != publish_id
        or activation.event_id != activate_id
        or identity.operation_id != "strategies_publish_strategy_version"
        or identity.resource_id
        != canonical_resource_id(
            "strategy_version",
            {"strategy_id": strategy_id, "version": version},
        )
        or decision.strategy_id != strategy_id
        or decision.version != version
        or activation.strategy_id != decision.strategy_id
        or activation.target_version != decision.version
        or decision.decision is not StrategyDecision.PUBLISH
        or activation.activation_kind is not StrategyDecision.PUBLISH
        or decision.reason != activation.reason
        or decision.actor != activation.actor
        or decision.decided_at != activation.activated_at
        or not decision.actor
        or not decision.decided_at
        or not activation.actor
        or not activation.activated_at
    ):
        raise invalid_strategy_receipt()
    receipt = find_mutation_receipt_in_reasons((decision.reason,), identity)
    if receipt is None:
        raise invalid_strategy_receipt()
    result = pointer_from_receipt(dict(receipt))
    if (
        result.strategy_id != strategy_id
        or result.active_version != version
        or result.pointer_revision <= 0
    ):
        raise invalid_strategy_receipt()
    return result


__all__ = [
    "invalid_strategy_receipt",
    "pointer_receipt",
    "replay_strategy_activation",
    "replay_strategy_decision",
    "replay_strategy_publish",
    "state_receipt",
]
