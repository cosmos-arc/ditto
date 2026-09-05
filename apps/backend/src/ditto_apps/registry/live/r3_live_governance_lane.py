"""Governance lane for an authenticated R3 live golden-lane result."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from dishka import Container
from ditto_application.commands.strategy_governance import (
    ApproveReviewCommand,
    ApproveReviewHandler,
    PublishStrategyVersionCommand,
    PublishStrategyVersionHandler,
    ReactivateStrategyCommand,
    ReactivateStrategyHandler,
    SubmitReviewCommand,
    SubmitReviewHandler,
    reactivate_confirmation_phrase,
)
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    build_mutation_idempotency,
    canonical_resource_id,
)

type LiveLane = Literal["stock", "etf"]


class LiveGoldenLaneEvidence(Protocol):
    """Golden-lane evidence consumed by governance without owning its schema."""

    @property
    def lane(self) -> LiveLane:
        """Return the governed product lane."""
        ...

    @property
    def strategy_id(self) -> str:
        """Return the strategy identity."""
        ...

    @property
    def candidate_version(self) -> int:
        """Return the reviewed candidate version."""
        ...

    @property
    def review_bundle_hash(self) -> str:
        """Return the authenticated review bundle hash."""
        ...


class ActiveStrategyVersion(Protocol):
    """Published strategy fields needed by live governance verification."""

    @property
    def version(self) -> int:
        """Return the active strategy version."""
        ...

    @property
    def spec_hash(self) -> str:
        """Return the active strategy specification hash."""
        ...


class StrategyCatalogReader(Protocol):
    """Narrow catalog projection consumed by the governance lane."""

    def get_active_published(self, strategy_id: str) -> ActiveStrategyVersion | None:
        """Read the currently published version for one strategy."""
        ...


@dataclass(frozen=True, slots=True)
class LiveGovernanceLaneResult:
    """One approved publication, active read, and historical reactivation proof."""

    lane: LiveLane
    strategy_id: str
    candidate_version: int
    bundle_hash: str
    published_active_version: int
    published_pointer_revision: int
    r1_active_spec_hash: str
    reactivated_active_version: int
    reactivated_pointer_revision: int


@dataclass(frozen=True, slots=True)
class LiveGovernanceLifecycleResult:
    """Both golden lanes governed by the authorized actor."""

    schema: str
    generated_at: str
    actor: str
    lanes: tuple[LiveLane, ...]
    results: tuple[LiveGovernanceLaneResult, ...]


def _governance_identity(
    *,
    operation_id: str,
    strategy_id: str,
    version: int,
    raw_key: str,
    request_payload: Mapping[str, object],
) -> MutationIdempotency:
    return build_mutation_idempotency(
        operation_id=operation_id,
        resource_id=canonical_resource_id(
            "strategy_version",
            {"strategy_id": strategy_id, "version": version},
        ),
        raw_key=raw_key,
        request_payload=dict(request_payload),
    )


def govern_live_lane(
    *,
    lane_result: LiveGoldenLaneEvidence,
    actor: str,
    container_factory: Callable[[], Container],
    strategy_catalog_type: type[object],
) -> LiveGovernanceLaneResult:
    """Govern one live candidate and prove rollback to its historical v1."""
    strategy_id = lane_result.strategy_id
    version = lane_result.candidate_version
    container = container_factory()
    try:
        submit = container.get(SubmitReviewHandler)
        approve = container.get(ApproveReviewHandler)
        publish = container.get(PublishStrategyVersionHandler)
        reactivate = container.get(ReactivateStrategyHandler)
        catalog = cast(
            "StrategyCatalogReader",
            container.get(strategy_catalog_type),
        )
        submit_reason = "submit verified live R3 evidence"
        submit_payload = {
            "actor": actor,
            "bundle_hash": lane_result.review_bundle_hash,
            "reason": submit_reason,
        }
        submit_command = SubmitReviewCommand(
            strategy_id=strategy_id,
            version=version,
            bundle_hash=lane_result.review_bundle_hash,
            actor=actor,
            reason=submit_reason,
            idempotency=_governance_identity(
                operation_id="strategies_submit_strategy_review",
                strategy_id=strategy_id,
                version=version,
                raw_key=f"r3-live-{lane_result.lane}-submit",
                request_payload=submit_payload,
            ),
        )
        submitted = submit.handle(submit_command)
        if submit.handle(submit_command) != submitted:
            raise ValueError("submit-review idempotency replay drifted")

        approve_reason = "approve verified live R3 evidence"
        approve_payload = {
            "actor": actor,
            "reason": approve_reason,
        }
        approve_command = ApproveReviewCommand(
            strategy_id=strategy_id,
            version=version,
            actor=actor,
            reason=approve_reason,
            idempotency=_governance_identity(
                operation_id="strategies_approve_strategy_review",
                strategy_id=strategy_id,
                version=version,
                raw_key=f"r3-live-{lane_result.lane}-approve",
                request_payload=approve_payload,
            ),
        )
        approved = approve.handle(approve_command)
        if approve.handle(approve_command) != approved:
            raise ValueError("approve idempotency replay drifted")

        publish_reason = "publish verified live R3 candidate"
        publish_payload = {
            "actor": actor,
            "bundle_hash": lane_result.review_bundle_hash,
            "reason": publish_reason,
        }
        publish_command = PublishStrategyVersionCommand(
            strategy_id=strategy_id,
            version=version,
            bundle_hash=lane_result.review_bundle_hash,
            actor=actor,
            reason=publish_reason,
            idempotency=_governance_identity(
                operation_id="strategies_publish_strategy_version",
                strategy_id=strategy_id,
                version=version,
                raw_key=f"r3-live-{lane_result.lane}-publish",
                request_payload=publish_payload,
            ),
        )
        pointer = publish.handle(publish_command)
        if publish.handle(publish_command) != pointer:
            raise ValueError("publish idempotency replay drifted")
        active = catalog.get_active_published(strategy_id)
        if active is None or active.version != version:
            raise ValueError("R1 active strategy did not advance to live candidate")

        confirmation = reactivate_confirmation_phrase(
            strategy_id,
            1,
            pointer.pointer_revision,
        )
        reactivate_payload = {
            "actor": actor,
            "confirmation": confirmation,
            "expected_pointer_revision": pointer.pointer_revision,
            "impact_summary": "return R1 to the reviewed historical seed baseline",
            "reason": "complete live rollback acceptance",
        }
        reactivate_command = ReactivateStrategyCommand(
            strategy_id=strategy_id,
            version=1,
            actor=actor,
            reason=cast("str", reactivate_payload["reason"]),
            confirmation=confirmation,
            impact_summary=cast("str", reactivate_payload["impact_summary"]),
            expected_pointer_revision=pointer.pointer_revision,
            idempotency=_governance_identity(
                operation_id="strategies_reactivate_strategy_version",
                strategy_id=strategy_id,
                version=1,
                raw_key=f"r3-live-{lane_result.lane}-reactivate-v1",
                request_payload=reactivate_payload,
            ),
        )
        restored = reactivate.handle(reactivate_command)
        if reactivate.handle(reactivate_command) != restored:
            raise ValueError("reactivation idempotency replay drifted")
        restored_active = catalog.get_active_published(strategy_id)
        if restored_active is None or restored_active.version != 1:
            raise ValueError("historical v1 reactivation did not restore R1 truth")

        return LiveGovernanceLaneResult(
            lane=lane_result.lane,
            strategy_id=strategy_id,
            candidate_version=version,
            bundle_hash=lane_result.review_bundle_hash,
            published_active_version=pointer.active_version,
            published_pointer_revision=pointer.pointer_revision,
            r1_active_spec_hash=active.spec_hash,
            reactivated_active_version=restored.active_version,
            reactivated_pointer_revision=restored.pointer_revision,
        )
    finally:
        container.close()
