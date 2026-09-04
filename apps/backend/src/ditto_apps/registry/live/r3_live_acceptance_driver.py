"""Production-composed Task 18 live golden, governance, and recovery driver."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, cast

import orjson
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_application.builders.research_executor_probe import (
    BuilderBackedResearchExecutorProbe,
)
from ditto_application.candidate_selection import CandidateSelectionRequest
from ditto_application.commands.candidate_selection import (
    CandidateSelectionCommand,
)
from ditto_application.commands.experiments import (
    ClaimHoldoutCandidateCommand,
    LaunchExperimentCommand,
)
from ditto_application.commands.strategy import UpdateStrategyHandler
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
from ditto_application.exceptions import AppCommandError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    build_mutation_idempotency,
    canonical_resource_id,
)
from ditto_application.processes.experiments.candidate_evidence_reader import (
    CandidateEvidenceBundle,
)
from ditto_application.processes.experiments.execution_bundle import (
    CodeEnvironmentLock,
)
from ditto_application.processes.experiments.holdout import (
    ClaimHoldoutCandidateRequest,
    HoldoutSelectionReason,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
    ExperimentPreflightStatus,
)
from ditto_application.processes.experiments.planning_request_builder import (
    build_experiment_planning_request,
)
from ditto_application.processes.experiments.scheduler_store import ExperimentId
from ditto_application.queries.experiments import (
    ExperimentDetailReadModel,
    ExperimentReviewPacketReadModel,
)
from ditto_data.catalog.certification import CertificationReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from pydantic import TypeAdapter

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.bundle import ResearchBundle
from ditto_apps.registry.contexts.research import create_research_bundle
from ditto_apps.registry.contexts.strategy import create_strategy_bundle
from ditto_apps.registry.live.r3_live_evidence_store import (
    canonical_bytes,
    sha256_file,
    write_addressed,
)
from ditto_apps.registry.live.r3_live_planning_builder import (
    LivePlanningArtifact,
    LivePlanningOptions,
    LivePlanningServices,
    build_live_planning_artifact,
    write_live_planning_artifact,
)
from ditto_apps.registry.live.r3_live_recovery_driver import (
    LiveBackupRestoreResult,
    run_live_backup_restore,
)

__all__ = [
    "LiveBackupRestoreResult",
    "LiveGoldenLaneResult",
    "LiveGovernanceLaneResult",
    "LiveGovernanceLifecycleResult",
    "run_live_backup_restore",
    "run_live_golden_lane",
    "run_live_governance_lifecycle",
    "select_and_claim_with_bundle",
]

type LiveLane = Literal["stock", "etf"]


class SchedulerTick(Protocol):
    """Injected jobs-layer scheduler entrypoint used by live acceptance."""

    def __call__(self, *, occurred_at: datetime) -> Mapping[str, object]: ...


class SelectAndClaim(Protocol):
    """Operator mutations bound to the scheduler's live lease authority."""

    def __call__(self, experiment_id: str) -> tuple[str, str, str, bool]: ...


# Live golden lanes use wall-clock termination; tests replace this clock alias.
_LIVE_LANE_WALL_CLOCK_SECONDS = 3600.0
_LIVE_LANE_MAX_TICKS = 6000
_monotonic: Callable[[], float] = time.monotonic
_TERMINAL_FAILURES = {"cancelled", "completed_with_failures", "failed"}
_STRATEGY_BY_LANE = {
    "stock": "seed_stock_selection_rotation",
    "etf": "seed_etf_industry_rotation",
}


@dataclass(frozen=True, slots=True)
class LiveGoldenLaneResult:
    """Content-addressable result from one real-data golden lane."""

    schema: str
    generated_at: str
    lane: LiveLane
    purpose: str
    experiment_id: str
    status: str
    eligible_month_count: int
    strategy_id: str
    candidate_version: int
    candidate_id: str
    strategy_spec_hash: str
    snapshot_id: str
    snapshot_manifest_hash: str
    planning_document_path: str
    planning_document_hash: str
    plan_hash: str
    parameter_hash: str
    registry_hash: str
    review_bundle_hash: str
    selection_evidence_hash: str
    holdout_claim_id: str
    holdout_duplicate_blocked: bool
    factor_contribution_count: int
    industry_exposure_count: int
    size_exposure_count: int
    r2_live_gate: str
    replay_dispatch_count: int


_LIVE_GOLDEN_LANE_RESULT_ADAPTER = TypeAdapter(LiveGoldenLaneResult)


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


def _write_lane_index(
    evidence_root: Path,
    result: LiveGoldenLaneResult,
    path: Path,
    content_hash: str,
) -> None:
    index = evidence_root / "lanes" / result.lane / "current.json"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_bytes(
        canonical_bytes(
            {
                "lane": result.lane,
                "purpose": result.purpose,
                "relative_path": path.relative_to(evidence_root).as_posix(),
                "sha256": content_hash,
            }
        )
    )


def _read_lane_result(
    evidence_root: Path,
    lane: LiveLane,
) -> LiveGoldenLaneResult:
    root = evidence_root.resolve(strict=True)
    index_path = root / "lanes" / lane / "current.json"
    index = cast("dict[str, object]", orjson.loads(index_path.read_bytes()))
    relative = index.get("relative_path")
    expected_hash = index.get("sha256")
    if type(relative) is not str or type(expected_hash) is not str:
        raise ValueError(f"live lane evidence index is invalid: {lane}")
    path = (root / relative).resolve(strict=True)
    path.relative_to(root)
    if sha256_file(path) != expected_hash:
        raise ValueError(f"live lane evidence hash drifted: {lane}")
    payload = cast("dict[str, object]", orjson.loads(path.read_bytes()))
    return _LIVE_GOLDEN_LANE_RESULT_ADAPTER.validate_python(payload)


def _ensure_seed_v1(lane: LiveLane) -> None:
    strategy_id = _STRATEGY_BY_LANE[lane]
    with create_strategy_bundle() as bundle:
        if bundle.catalog_service is None:
            raise ValueError("strategy catalog is unavailable")
        if bundle.catalog_service.get_spec(strategy_id, 1) is not None:
            return
        if bundle.seed_bootstrap is None:
            raise ValueError("seed bootstrap is unavailable")
        bundle.seed_bootstrap.run()
        if bundle.catalog_service.get_spec(strategy_id, 1) is None:
            raise ValueError(f"seed bootstrap did not create v1: {strategy_id}")


def _build_planning(
    *,
    lane: LiveLane,
    purpose: str,
    data_root: Path,
    evidence_root: Path,
    planning_options: LivePlanningOptions | None = None,
) -> tuple[LivePlanningArtifact, Path]:
    _ensure_seed_v1(lane)
    container = make_app_container()
    try:
        artifact = build_live_planning_artifact(
            lane=lane,
            purpose=purpose,
            data_root=data_root,
            options=planning_options,
            services=LivePlanningServices(
                artifact_service=container.get(ResearchArtifactService),
                research_catalog=container.get(ResearchCatalogService),
                certification_reader=container.get(CertificationReader),
                snapshot_reader=container.get(ProviderSnapshotReader),
                strategy_catalog=container.get(StrategyCatalogService),
                update_handler=container.get(UpdateStrategyHandler),
                executor_probe=container.get(BuilderBackedResearchExecutorProbe),
                planning_process=container.get(ExperimentPlanningProcess),
                environment=container.get(CodeEnvironmentLock),
            ),
        )
    finally:
        container.close()
    path = write_live_planning_artifact(artifact, evidence_root)
    return artifact, path


def _launch(artifact: LivePlanningArtifact) -> None:
    request = build_experiment_planning_request(artifact.planning_document)
    with create_research_bundle() as bundle:
        report = bundle.planning_process.preflight(request)
        if (
            report.status is not ExperimentPreflightStatus.READY
            or report.plan_hash != artifact.plan_hash
        ):
            raise ValueError("live planning drifted before launch")
        plan_hash = report.plan_hash
        if plan_hash is None:
            raise ValueError("live planning lost its confirmed plan hash")
        resource_id = canonical_resource_id(
            "experiment",
            {"experiment_id": request.experiment_id},
        )
        idempotency = build_mutation_idempotency(
            operation_id="research_launch_experiment",
            resource_id=resource_id,
            raw_key=f"r3-live-{artifact.lane}-{artifact.purpose}-launch",
            request_payload={
                **artifact.planning_document,
                "confirmed_plan_hash": plan_hash,
            },
        )
        command = LaunchExperimentCommand(
            request=request,
            confirmed_plan_hash=plan_hash,
            idempotency=idempotency,
        )
        first = bundle.launch_handler.handle(command)
        if bundle.launch_handler.handle(command) != first:
            raise ValueError("live launch idempotency replay drifted")


def _detail(experiment_id: str) -> ExperimentDetailReadModel:
    with create_research_bundle() as bundle:
        detail = bundle.experiment_query.get(experiment_id)
    if detail is None:
        raise ValueError(f"live experiment is missing: {experiment_id}")
    if detail.status in _TERMINAL_FAILURES:
        raise ValueError(
            "live experiment entered terminal failure: "
            + f"{detail.status}/{detail.failure_code}"
        )
    return detail


def _tick_until(
    experiment_id: str,
    *,
    target: str,
    scheduler_tick: SchedulerTick,
) -> ExperimentDetailReadModel:
    started = _monotonic()
    for _ in range(_LIVE_LANE_MAX_TICKS):
        if _monotonic() - started > _LIVE_LANE_WALL_CLOCK_SECONDS:
            break
        detail = _detail(experiment_id)
        if target == "candidate_selection" and detail.stage == target:
            # Re-enter once to idempotently finish interrupted evidence publication.
            scheduler_tick(occurred_at=datetime.now(UTC))
            replayed = _detail(experiment_id)
            if replayed.stage != target:
                raise ValueError(
                    "live candidate-selection evidence replay changed stage: "
                    + f"{replayed.stage}/{replayed.status}"
                )
            return replayed
        if target == "completed" and detail.status == target:
            return detail
        scheduler_tick(occurred_at=datetime.now(UTC))
    detail = _detail(experiment_id)
    elapsed = _monotonic() - started
    raise ValueError(
        "live experiment did not reach "
        + f"{target} within {_LIVE_LANE_WALL_CLOCK_SECONDS:.0f}s"
        + f" (elapsed {elapsed:.0f}s): {detail.stage}/{detail.status}"
    )


def select_and_claim_with_bundle(
    bundle: ResearchBundle,
    experiment_id: str,
) -> tuple[str, str, str, bool]:
    """Select and claim through the scheduler container's lease authority."""
    detail = bundle.experiment_query.get(experiment_id)
    if detail is None:
        raise ValueError("live experiment is not ready for candidate selection")
    if detail.stage in {"holdout", "evidence"}:
        snapshot = bundle.candidate_evidence_reader.scheduler_store.load_snapshot(
            ExperimentId(experiment_id)
        )
        claim = snapshot.holdout_claim
        if claim is None:
            raise ValueError("live holdout stage lacks its persisted claim")
        return (
            claim.candidate_id,
            claim.claim_id,
            claim.selection_evidence_hash,
            True,
        )
    if detail.stage != "candidate_selection":
        raise ValueError("live experiment is not ready for candidate selection")
    selected = next(item for item in detail.candidates if not item.is_baseline)
    loaded = bundle.candidate_evidence_reader.load_current_bundle(
        experiment_id,
        selected.candidate_id,
    )
    if loaded is None:
        raise ValueError("live candidate evidence bundle is missing")
    _record, evidence_bundle = loaded
    comparison_hash = cast(
        "str",
        evidence_bundle.manifest["comparison_payload_hash"],
    )
    rationale = "Candidate won the registered live-data objective review."
    selection_payload = {
        "candidate_id": selected.candidate_id,
        "comparison_payload_hash": comparison_hash,
        "expected_revision": detail.revision,
        "rationale": rationale,
    }
    selection_request = CandidateSelectionRequest(
        experiment_id=experiment_id,
        candidate_id=selected.candidate_id,
        comparison_payload_hash=comparison_hash,
        expected_revision=detail.revision,
        rationale=rationale,
        occurred_at=datetime.now(UTC),
        idempotency=build_mutation_idempotency(
            operation_id="design_research_candidate_selection",
            resource_id=canonical_resource_id(
                "candidate_selection",
                {"experiment_id": experiment_id},
            ),
            raw_key=f"r3-live-{experiment_id}-candidate-selection",
            request_payload=selection_payload,
        ),
    )
    command = CandidateSelectionCommand(selection_request)
    selection = bundle.candidate_selection_handler.handle(command)
    if bundle.candidate_selection_handler.handle(command) != selection:
        raise ValueError("candidate selection idempotency replay drifted")
    reason = HoldoutSelectionReason(
        "objective_review",
        rationale,
    )
    holdout_payload = {
        "candidate_id": selected.candidate_id,
        "candidate_evidence_content_hash": selection.candidate_evidence_content_hash,
        "expected_revision": selection.experiment_revision,
        "selection_id": selection.selection_id,
        "selection_evidence_content_hash": selection.selection_evidence_content_hash,
    }
    holdout_request = ClaimHoldoutCandidateRequest(
        experiment_id=experiment_id,
        candidate_id=selected.candidate_id,
        expected_revision=selection.experiment_revision,
        expected_selection_evidence_hash=(selection.selection_evidence_content_hash),
        operator_confirmation="chevy reviewed immutable live candidate evidence",
        selection_reason=reason,
        occurred_at=datetime.now(UTC),
        selection_id=selection.selection_id,
        expected_candidate_evidence_content_hash=(
            selection.candidate_evidence_content_hash
        ),
        idempotency=build_mutation_idempotency(
            operation_id="design_research_holdout_evaluations",
            resource_id=canonical_resource_id(
                "holdout_evaluation",
                {"experiment_id": experiment_id},
            ),
            raw_key=f"r3-live-{experiment_id}-holdout",
            request_payload=holdout_payload,
        ),
    )
    holdout_command = ClaimHoldoutCandidateCommand(holdout_request)
    holdout = bundle.holdout_claim_handler.handle(holdout_command)
    if bundle.holdout_claim_handler.handle(holdout_command) != holdout:
        raise ValueError("holdout claim idempotency replay drifted")
    duplicate = replace(
        holdout_request,
        idempotency=build_mutation_idempotency(
            operation_id="design_research_holdout_evaluations",
            resource_id=canonical_resource_id(
                "holdout_evaluation",
                {"experiment_id": experiment_id},
            ),
            raw_key=f"r3-live-{experiment_id}-holdout-duplicate",
            request_payload=holdout_payload,
        ),
    )
    blocked = False
    try:
        bundle.holdout_claim_handler.handle(ClaimHoldoutCandidateCommand(duplicate))
    except AppCommandError as exc:
        blocked = exc.details.get("code") == "HOLDOUT_ALREADY_CLAIMED"
    if not blocked:
        raise ValueError("second live holdout claim was not blocked")
    return (
        selected.candidate_id,
        holdout.claim_id,
        selection.selection_evidence_content_hash,
        blocked,
    )


def _completed_evidence(
    experiment_id: str,
    candidate_id: str,
) -> tuple[ExperimentReviewPacketReadModel, CandidateEvidenceBundle, str]:
    with create_research_bundle() as bundle:
        packet = bundle.experiment_query.get_review_packet(experiment_id)
        loaded = bundle.candidate_evidence_reader.load_current_bundle(
            experiment_id,
            candidate_id,
        )
    if packet is None or loaded is None:
        raise ValueError("completed live experiment lacks review evidence")
    if packet.hard_review_blocked:
        blocking = ", ".join(
            f"{item.rule_id}={item.outcome}"
            for item in packet.gate_outcomes
            if item.outcome != "pass"
        )
        raise ValueError(
            f"completed live review packet is hard-gate blocked: {blocking}"
        )
    r2_gates = tuple(
        item for item in packet.gate_outcomes if item.rule_id == "r2_live_gate"
    )
    if len(r2_gates) != 1:
        raise ValueError("live review packet has ambiguous R2 gate evidence")
    return packet, loaded[1], r2_gates[0].outcome


def run_live_golden_lane(
    *,
    lane: LiveLane,
    data_root: Path,
    evidence_root: Path,
    purpose: str,
    scheduler_tick: SchedulerTick,
    select_and_claim: SelectAndClaim,
    planning_options: LivePlanningOptions | None = None,
) -> LiveGoldenLaneResult:
    """Run one real-data planning, worker, selection, holdout, and packet closure."""
    root = evidence_root.expanduser().resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    artifact, planning_path = _build_planning(
        lane=lane,
        purpose=purpose,
        data_root=data_root.expanduser().resolve(strict=True),
        evidence_root=root,
        planning_options=planning_options,
    )
    _launch(artifact)
    detail = _detail(artifact.experiment_id)
    if detail.status == "completed":
        packet = None
        with create_research_bundle() as bundle:
            packet = bundle.experiment_query.get_review_packet(artifact.experiment_id)
            artifacts = bundle.experiment_query.list_artifacts(artifact.experiment_id)
        if (
            packet is None
            or packet.candidate_id is None
            or packet.holdout_claim_id is None
        ):
            raise ValueError("completed live experiment replay evidence is incomplete")
        candidate_id = packet.candidate_id
        holdout_claim_id = packet.holdout_claim_id
        selection_evidence_hash = next(
            item.content_hash
            for item in artifacts
            if item.artifact_id == packet.selection_evidence_artifact_id
        )
        duplicate_blocked = True
    else:
        if detail.stage not in {"holdout", "evidence"}:
            _tick_until(
                artifact.experiment_id,
                target="candidate_selection",
                scheduler_tick=scheduler_tick,
            )
        (
            candidate_id,
            holdout_claim_id,
            selection_evidence_hash,
            duplicate_blocked,
        ) = select_and_claim(artifact.experiment_id)
        _tick_until(
            artifact.experiment_id,
            target="completed",
            scheduler_tick=scheduler_tick,
        )
    packet, evidence, r2_gate = _completed_evidence(
        artifact.experiment_id,
        candidate_id,
    )
    exposure = packet.selection_exposure
    replay = scheduler_tick(occurred_at=datetime.now(UTC))
    result = LiveGoldenLaneResult(
        schema="ditto.r3-live-golden-lane.v1",
        generated_at=datetime.now(UTC).isoformat(),
        lane=lane,
        purpose=purpose,
        experiment_id=artifact.experiment_id,
        status=_detail(artifact.experiment_id).status,
        eligible_month_count=artifact.eligible_month_count,
        strategy_id=artifact.strategy_id,
        candidate_version=artifact.strategy_version,
        candidate_id=candidate_id,
        strategy_spec_hash=artifact.strategy_spec_hash,
        snapshot_id=artifact.snapshot_id,
        snapshot_manifest_hash=artifact.snapshot_manifest_hash,
        planning_document_path=planning_path.relative_to(root).as_posix(),
        planning_document_hash=artifact.planning_document_hash,
        plan_hash=artifact.plan_hash,
        parameter_hash=packet.parameter_hash,
        registry_hash=packet.registry_hash,
        review_bundle_hash=packet.bundle_hash,
        selection_evidence_hash=selection_evidence_hash,
        holdout_claim_id=holdout_claim_id,
        holdout_duplicate_blocked=duplicate_blocked,
        factor_contribution_count=len(evidence.factor_contributions),
        industry_exposure_count=(
            0 if exposure is None else len(exposure.industry_weights)
        ),
        size_exposure_count=(
            0 if exposure is None else len(exposure.size_bucket_weights)
        ),
        r2_live_gate=r2_gate,
        replay_dispatch_count=cast("int", replay["dispatch_count"]),
    )
    path, content_hash = write_addressed(
        evidence_root=root,
        category=f"lanes/{lane}/results",
        payload=asdict(result),
    )
    _write_lane_index(root, result, path, content_hash)
    return result


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


def _govern_lane(
    *,
    lane_result: LiveGoldenLaneResult,
    actor: str,
) -> LiveGovernanceLaneResult:
    strategy_id = lane_result.strategy_id
    version = lane_result.candidate_version
    container = make_app_container()
    try:
        submit = container.get(SubmitReviewHandler)
        approve = container.get(ApproveReviewHandler)
        publish = container.get(PublishStrategyVersionHandler)
        reactivate = container.get(ReactivateStrategyHandler)
        catalog = container.get(StrategyCatalogService)
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


def run_live_governance_lifecycle(
    *,
    data_root: Path,
    evidence_root: Path,
    actor: str,
) -> LiveGovernanceLifecycleResult:
    """Submit, approve, publish, read through R1, and reactivate both lanes."""
    del data_root  # Composition is already bound by the exact DITTO_STATE_ROOT.
    root = evidence_root.expanduser().resolve(strict=True)
    results = tuple(
        _govern_lane(
            lane_result=_read_lane_result(root, lane),
            actor=actor,
        )
        for lane in cast("tuple[LiveLane, ...]", ("stock", "etf"))
    )
    result = LiveGovernanceLifecycleResult(
        schema="ditto.r3-live-governance-lifecycle.v1",
        generated_at=datetime.now(UTC).isoformat(),
        actor=actor,
        lanes=tuple(item.lane for item in results),
        results=results,
    )
    write_addressed(
        evidence_root=root,
        category="governance",
        payload=asdict(result),
    )
    return result
