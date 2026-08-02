"""Build one canonical, content-addressed R3 live planning document."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, cast

import orjson
from ditto_analysis.experiments import (
    ExperimentFailurePolicy,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
)
from ditto_analysis.experiments.promotion_objective import (
    promotion_objective_payload,
)
from ditto_analysis.experiments.trial_ledger import (
    ConstraintOperator,
    MetricConstraint,
    ObjectiveMetric,
    PromotionObjective,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_application.builders.research_executor_probe import (
    BuilderBackedResearchExecutorProbe,
)
from ditto_application.builders.research_validation_authority_source import (
    IndexedSnapshotValidationAuthoritySource,
    SnapshotValidationAuthorityRequest,
)
from ditto_application.commands.strategy import (
    UpdateStrategyCommand,
    UpdateStrategyHandler,
)
from ditto_application.processes.experiments._planning_request_identity import (
    plain_planning_value,
)
from ditto_application.processes.experiments.planning import (
    BaselineDescriptor,
    CandidateMatrixSpec,
    ExperimentBudgetSpec,
    ResourceCostModel,
    expand_candidate_matrix,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPlanningRequest,
    declare_trial_family,
    derive_canonical_research_cycle_hash,
)
from ditto_application.processes.experiments.planning_document_codec import (
    candidate_matrix_spec_payload,
)
from ditto_application.processes.experiments.planning_probes import (
    ExperimentSnapshotIdentity,
    ResearchDatasetRequirement,
    ResearchExecutorProbeRequest,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
    ExperimentPreflightStatus,
)
from ditto_application.processes.experiments.planning_request_builder import (
    build_experiment_planning_request,
)
from ditto_application.research_validation_protocol import (
    canonical_validation_protocol_payload,
)
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
)
from ditto_data.catalog.certification import CertificationReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.strategy import create_strategy_bundle
from ditto_apps.registry.live.r3_live_snapshot_builder import (
    LiveResearchSnapshotBuild,
    build_live_research_snapshot,
)

__all__ = [
    "LivePlanningArtifact",
    "LivePlanningServices",
    "build_live_planning_artifact",
    "ensure_research_candidate",
    "planning_request_document",
    "write_live_planning_artifact",
]

type LiveLane = Literal["stock", "etf"]

_STRATEGY_BY_LANE = {
    "stock": "seed_stock_selection_rotation",
    "etf": "seed_etf_industry_rotation",
}
_BASELINE_BY_LANE = {
    "stock": "stock-universe-equal-weight",
    "etf": "etf-current-active",
}
_PURPOSE_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_PROMOTION_MONTHS = 96


@dataclass(frozen=True, slots=True)
class LivePlanningServices:
    """Production ports used to build and preflight one live planning document."""

    artifact_service: ResearchArtifactService
    research_catalog: ResearchCatalogService
    certification_reader: CertificationReader
    snapshot_reader: ProviderSnapshotReader
    strategy_catalog: StrategyCatalogService
    update_handler: UpdateStrategyHandler
    executor_probe: BuilderBackedResearchExecutorProbe
    planning_process: ExperimentPlanningProcess


@dataclass(frozen=True, slots=True)
class LivePlanningArtifact:
    """Canonical planning bytes plus the production preflight result they earned."""

    schema: str
    lane: LiveLane
    purpose: str
    strategy_id: str
    strategy_version: int
    strategy_spec_hash: str
    snapshot_id: str
    snapshot_manifest_hash: str
    experiment_id: str
    research_cycle_id: str
    planning_document_hash: str
    plan_hash: str
    preflight_status: str
    eligible_month_count: int
    candidate_count: int
    planning_document: dict[str, object]


def _plain_seed_payload(strategy_id: str) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        orjson.loads(orjson.dumps(asdict(SEED_STRATEGY_SPECS[strategy_id]))),
    )


def _require_seed_record(
    catalog: StrategyCatalogService,
    strategy_id: str,
) -> StrategySpecRecord:
    expected = SEED_STRATEGY_SPECS[strategy_id]
    expected_payload = _plain_seed_payload(strategy_id)
    record = catalog.get_spec(strategy_id, 1)
    if record is None:
        raise ValueError(f"canonical seed v1 is missing: {strategy_id}")
    if (
        record.name != expected.name
        or record.tags != expected.tags
        or orjson.dumps(record.spec_json, option=orjson.OPT_SORT_KEYS)
        != orjson.dumps(expected_payload, option=orjson.OPT_SORT_KEYS)
        or record.spec_hash != canonical_spec_hash_for_record(record)
        or catalog.get_version_state(strategy_id, 1) != "published"
    ):
        raise ValueError(f"canonical seed v1 drifted: {strategy_id}")
    return record


def ensure_research_candidate(
    *,
    lane: LiveLane,
    catalog: StrategyCatalogService,
    update_handler: UpdateStrategyHandler,
) -> StrategySpecRecord:
    """Create one append-only draft from seed v1, or reuse an exact open version."""
    strategy_id = _STRATEGY_BY_LANE[lane]
    _require_seed_record(catalog, strategy_id)
    latest = catalog.get_spec(strategy_id)
    if latest is None:
        raise ValueError(
            f"strategy catalog is empty after seed bootstrap: {strategy_id}"
        )
    state = catalog.get_version_state(strategy_id, latest.version)
    if state in {"published", "deprecated"}:
        next_version = latest.version + 1
        update_handler.handle(
            UpdateStrategyCommand(
                strategy_id=strategy_id,
                name=latest.name,
                spec_json=_plain_seed_payload(strategy_id),
                version=latest.version,
                tags=latest.tags,
            )
        )
        updated = catalog.get_spec(strategy_id, next_version)
        if updated is None:
            raise ValueError(f"strategy update disappeared: {strategy_id}")
        latest = updated
        state = catalog.get_version_state(strategy_id, next_version)
    if state not in {"draft", "review"}:
        raise ValueError(
            f"strategy has no reusable research candidate: {strategy_id}/{state}"
        )
    if latest.spec_hash != canonical_spec_hash_for_record(latest) or orjson.dumps(
        latest.spec_json, option=orjson.OPT_SORT_KEYS
    ) != orjson.dumps(
        _plain_seed_payload(strategy_id),
        option=orjson.OPT_SORT_KEYS,
    ):
        raise ValueError(
            f"research candidate drifted from seed semantics: {strategy_id}"
        )
    return latest


def _baseline(
    lane: LiveLane,
    seed_v1: StrategySpecRecord,
) -> BaselineDescriptor:
    payload: dict[str, str | int] = {}
    if lane == "etf":
        payload = {
            "strategy_id": seed_v1.strategy_id,
            "version": seed_v1.version,
            "spec_hash": seed_v1.spec_hash,
        }
    return BaselineDescriptor(
        descriptor_type=_BASELINE_BY_LANE[lane],
        payload=payload,
    )


def _planning_time(
    candidate: StrategySpecRecord,
    snapshot: LiveResearchSnapshotBuild,
) -> datetime:
    values = [datetime.fromisoformat(candidate.created_at.replace("Z", "+00:00"))]
    values.extend(
        datetime.fromisoformat(item.certified_at) for item in snapshot.dataset_bindings
    )
    if any(value.tzinfo is None for value in values):
        raise ValueError("live planning authority timestamps must be timezone-aware")
    return max(value.astimezone(UTC) for value in values)


def _requirements(
    snapshot: LiveResearchSnapshotBuild,
    required_datasets: tuple[str, ...],
) -> tuple[ResearchDatasetRequirement, ...]:
    bindings = {item.dataset_id: item for item in snapshot.dataset_bindings}
    missing = tuple(sorted(set(required_datasets) - set(bindings)))
    if missing:
        raise ValueError(
            f"live snapshot lacks required certification bindings: {missing}"
        )
    snapshot_start = date.fromisoformat(snapshot.snapshot_start)
    return tuple(
        ResearchDatasetRequirement(
            dataset_id=dataset_id,
            expected_snapshot_ids=bindings[dataset_id].snapshot_ids,
            requires_pit_universe=True,
            certified_from=max(
                date.fromisoformat(bindings[dataset_id].certified_from),
                snapshot_start,
            ),
        )
        for dataset_id in sorted(required_datasets)
    )


def _objective(
    *,
    experiment_id: str,
    family_id: str,
    matrix: CandidateMatrixSpec,
) -> PromotionObjective:
    family = declare_trial_family(
        experiment_id=experiment_id,
        matrix_spec=matrix,
        family_id=family_id,
    )
    return PromotionObjective(
        primary=ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        hard_constraints=(
            MetricConstraint(
                ResearchMetricValue(ResearchMetricId.MAX_DRAWDOWN, -100.0),
                ConstraintOperator.GREATER_THAN_OR_EQUAL,
            ),
            MetricConstraint(
                ResearchMetricValue(ResearchMetricId.SHARPE_RATIO, -100.0),
                ConstraintOperator.GREATER_THAN_OR_EQUAL,
            ),
        ),
        tie_break_order=(
            ObjectiveMetric(
                ResearchMetricId.TURNOVER,
                ResearchMetricDirection.MINIMIZE,
            ),
        ),
        baseline_candidate_id=family.current_members[0].candidate_id,
        economic_rationale="Promote durable live-data returns after frozen costs.",
        trial_family=family,
    )


def planning_request_document(
    request: ExperimentPlanningRequest,
) -> dict[str, object]:
    """Project one typed request into the strict public canonical document shape."""
    created_at = request.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    document = {
        "experiment_id": request.experiment_id,
        "research_cycle_id": request.research_cycle_id,
        "research_cycle_hash": request.research_cycle_hash,
        "strategy": {
            "strategy_id": request.strategy_record.strategy_id,
            "version": request.strategy_record.version,
            "spec_hash": request.strategy_record.spec_hash,
            "spec_json": plain_planning_value(request.strategy_record.spec_json),
        },
        "snapshot": {
            "snapshot_id": request.snapshot_identity.snapshot_id,
            "manifest_hash": request.snapshot_identity.manifest_hash,
        },
        "validation": dict(
            canonical_validation_protocol_payload(request.validation_request)
        ),
        "matrix": dict(candidate_matrix_spec_payload(request.matrix_spec)),
        "promotion_objective": dict(
            promotion_objective_payload(request.promotion_objective)
        ),
        "dataset_requirements": [
            dict(item.as_payload()) for item in request.dataset_requirements
        ],
        "cost_model": asdict(request.cost_model),
        "budget": asdict(request.budget),
        "seed": request.seed,
        "worker_count": request.worker_count,
        "failure_policy": request.failure_policy.value,
        "created_at": created_at,
    }
    plain_document = plain_planning_value(document)
    return cast(
        "dict[str, object]",
        orjson.loads(orjson.dumps(plain_document, option=orjson.OPT_SORT_KEYS)),
    )


def _identity(
    *,
    lane: LiveLane,
    purpose: str,
    candidate: StrategySpecRecord,
    snapshot: LiveResearchSnapshotBuild,
) -> tuple[str, str, str]:
    digest = hashlib.sha256(
        orjson.dumps(
            {
                "lane": lane,
                "purpose": purpose,
                "strategy_id": candidate.strategy_id,
                "strategy_version": candidate.version,
                "strategy_spec_hash": candidate.spec_hash,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_manifest_hash": snapshot.manifest_hash,
            },
            option=orjson.OPT_SORT_KEYS,
        )
    ).hexdigest()
    suffix = digest[:24]
    return (
        f"r3-live-{lane}-{purpose}-{suffix}",
        f"r3-live-cycle-{lane}-{purpose}-{suffix}",
        f"r3-live-family-{lane}-{purpose}-{suffix}",
    )


def build_live_planning_artifact(
    *,
    lane: LiveLane,
    purpose: str,
    data_root: Path,
    services: LivePlanningServices,
) -> LivePlanningArtifact:
    """Build, canonical-roundtrip, and production-preflight one live plan."""
    if _PURPOSE_PATTERN.fullmatch(purpose) is None:
        raise ValueError("live planning purpose must be canonical lowercase kebab-case")
    snapshot = build_live_research_snapshot(
        lane=lane,
        data_root=data_root,
        artifact_service=services.artifact_service,
        catalog_service=services.research_catalog,
        certification_reader=services.certification_reader,
        snapshot_reader=services.snapshot_reader,
    )
    candidate = ensure_research_candidate(
        lane=lane,
        catalog=services.strategy_catalog,
        update_handler=services.update_handler,
    )
    seed_v1 = _require_seed_record(services.strategy_catalog, candidate.strategy_id)
    matrix = CandidateMatrixSpec(
        baseline=_baseline(lane, seed_v1),
        candidate_limit=4,
    )
    matrix_plan = expand_candidate_matrix(matrix)
    snapshot_identity = ExperimentSnapshotIdentity(
        snapshot.snapshot_id,
        snapshot.manifest_hash,
    )
    executor = services.executor_probe.probe(
        ResearchExecutorProbeRequest(
            strategy_record=candidate,
            snapshot_identity=snapshot_identity,
            baseline=matrix.baseline,
            candidates=matrix_plan.binder_candidates,
        )
    )
    if not executor.available or executor.runtime_validation_evidence is None:
        raise ValueError(
            "live strategy executor preflight failed: "
            + f"{executor.code}/{executor.reason}"
        )
    requirements = _requirements(snapshot, executor.required_datasets)
    created_at = _planning_time(candidate, snapshot)
    authority = IndexedSnapshotValidationAuthoritySource(
        services.artifact_service
    ).resolve_snapshot(
        SnapshotValidationAuthorityRequest(
            snapshot_identity=snapshot_identity,
            runtime_validation=executor.runtime_validation_evidence,
            declared_requirements=requirements,
            planning_decision_date=created_at.date(),
        )
    )
    experiment_id, cycle_id, family_id = _identity(
        lane=lane,
        purpose=purpose,
        candidate=candidate,
        snapshot=snapshot,
    )
    objective = _objective(
        experiment_id=experiment_id,
        family_id=family_id,
        matrix=matrix,
    )
    request = ExperimentPlanningRequest(
        experiment_id=experiment_id,
        research_cycle_id=cycle_id,
        research_cycle_hash=derive_canonical_research_cycle_hash(
            strategy_family_id=candidate.strategy_id,
            validation_request=authority.protocol,
        ),
        strategy_record=candidate,
        snapshot_identity=snapshot_identity,
        validation_request=authority.protocol,
        matrix_spec=matrix,
        promotion_objective=objective,
        dataset_requirements=requirements,
        cost_model=ResourceCostModel(
            bytes_per_run=10_000_000,
            bytes_per_trading_session=50_000,
        ),
        budget=ExperimentBudgetSpec(
            candidate_limit=4,
            fold_run_limit=1_000,
            trading_session_limit=10_000_000,
            disk_byte_limit=100_000_000_000,
        ),
        seed=17,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        created_at=created_at,
    )
    document = planning_request_document(request)
    canonical_request = build_experiment_planning_request(document)
    report = services.planning_process.preflight(canonical_request)
    if (
        report.status is not ExperimentPreflightStatus.READY
        or report.plan_hash is None
        or report.eligible_month_count < _PROMOTION_MONTHS
    ):
        blockers = tuple(
            f"{item.rule_id}:{item.code or item.reason}"
            for item in report.checks
            if item.outcome.value == "fail"
        )
        raise ValueError(
            "live planning preflight did not earn promotion readiness: "
            + f"{report.status}/{blockers}"
        )
    document_bytes = orjson.dumps(document, option=orjson.OPT_SORT_KEYS)
    return LivePlanningArtifact(
        schema="ditto.r3-live-planning-artifact.v1",
        lane=lane,
        purpose=purpose,
        strategy_id=candidate.strategy_id,
        strategy_version=candidate.version,
        strategy_spec_hash=candidate.spec_hash,
        snapshot_id=snapshot.snapshot_id,
        snapshot_manifest_hash=snapshot.manifest_hash,
        experiment_id=experiment_id,
        research_cycle_id=cycle_id,
        planning_document_hash=hashlib.sha256(document_bytes).hexdigest(),
        plan_hash=report.plan_hash,
        preflight_status=report.status.value,
        eligible_month_count=report.eligible_month_count,
        candidate_count=report.candidate_count,
        planning_document=document,
    )


def write_live_planning_artifact(
    artifact: LivePlanningArtifact,
    output_root: Path,
) -> Path:
    """Publish canonical document bytes at a hash-addressed immutable path."""
    root = output_root.expanduser().resolve(strict=False)
    path = (
        root
        / "planning"
        / artifact.lane
        / artifact.purpose
        / f"{artifact.planning_document_hash}.json"
    )
    payload = (
        orjson.dumps(
            artifact.planning_document,
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n"
    )
    compact_hash = hashlib.sha256(
        orjson.dumps(artifact.planning_document, option=orjson.OPT_SORT_KEYS)
    ).hexdigest()
    if compact_hash != artifact.planning_document_hash:
        raise ValueError("planning document changed before artifact publication")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise ValueError("content-addressed planning artifact replay drift")
    if not path.exists():
        path.write_bytes(payload)
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", required=True, choices=("stock", "etf"))
    parser.add_argument("--purpose", required=True)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Compose production ports and publish one addressed live planning document."""
    args = _parser().parse_args(argv)
    data_root = args.data_root.expanduser().resolve(strict=True)
    configured_root = os.environ.get("DITTO_DATA_ROOT")
    if (
        configured_root is None
        or Path(configured_root).expanduser().resolve() != data_root
    ):
        raise SystemExit("DITTO_DATA_ROOT must exactly match --data-root")
    lane = cast("LiveLane", args.lane)
    strategy_id = _STRATEGY_BY_LANE[lane]
    with create_strategy_bundle() as strategy_bundle:
        if strategy_bundle.catalog_service is None:
            raise SystemExit("strategy catalog is unavailable")
        if strategy_bundle.catalog_service.get_spec(strategy_id, 1) is None:
            if strategy_bundle.seed_bootstrap is None:
                raise SystemExit("seed bootstrap is unavailable")
            strategy_bundle.seed_bootstrap.run()
    container = make_app_container()
    try:
        artifact = build_live_planning_artifact(
            lane=lane,
            purpose=args.purpose,
            data_root=data_root,
            services=LivePlanningServices(
                artifact_service=container.get(ResearchArtifactService),
                research_catalog=container.get(ResearchCatalogService),
                certification_reader=container.get(CertificationReader),
                snapshot_reader=container.get(ProviderSnapshotReader),
                strategy_catalog=container.get(StrategyCatalogService),
                update_handler=container.get(UpdateStrategyHandler),
                executor_probe=container.get(BuilderBackedResearchExecutorProbe),
                planning_process=container.get(ExperimentPlanningProcess),
            ),
        )
    finally:
        container.close()
    path = write_live_planning_artifact(artifact, args.output_root)
    sys.stdout.write(
        orjson.dumps(
            {
                "artifact_path": str(path),
                "candidate_count": artifact.candidate_count,
                "eligible_month_count": artifact.eligible_month_count,
                "experiment_id": artifact.experiment_id,
                "lane": artifact.lane,
                "plan_hash": artifact.plan_hash,
                "planning_document_hash": artifact.planning_document_hash,
                "preflight_status": artifact.preflight_status,
                "strategy_version": artifact.strategy_version,
            },
            option=orjson.OPT_SORT_KEYS,
        ).decode()
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
