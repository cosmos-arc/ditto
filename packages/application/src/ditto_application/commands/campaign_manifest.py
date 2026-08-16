"""Strict public-document builder for immutable research Campaign manifests."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import cast

from ditto_analysis.experiments.campaign import (
    CampaignBudget,
    ExperimentPlan,
    HypothesisSpec,
    ResearchCampaignManifest,
    ResearchCandidateSpec,
    SearchAxis,
)
from ditto_analysis.experiments.generated_code import SandboxResourceLimits
from ditto_analysis.experiments.metric_schema import ResearchMetricId
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    SnapshotId,
)
from ditto_analysis.experiments.specs import (
    CandidateSpec,
    ExperimentBudget,
    FoldProtocolSpec,
    FrozenValue,
)

from ditto_application.exceptions import AppCommandError


def _error(field: str, message: str) -> AppCommandError:
    return AppCommandError(
        message,
        details={
            "code": "CAMPAIGN_MANIFEST_INVALID",
            "reason": "campaign_manifest_document_invalid",
            "field": field,
        },
    )


def _object(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _error(field, f"{field} must be an object")
    raw = cast("Mapping[object, object]", value)
    if any(type(key) is not str for key in raw):
        raise _error(field, f"{field} keys must be strings")
    return cast("Mapping[str, object]", raw)


def _exact(
    value: Mapping[str, object],
    field: str,
    expected: frozenset[str],
) -> None:
    observed = frozenset(value)
    if observed != expected:
        raise _error(
            field,
            f"{field} fields do not match the versioned Campaign schema",
        )


def _text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise _error(field, f"{field} must be a non-empty canonical string")
    return value


def _integer(value: object, field: str, *, positive: bool = False) -> int:
    if (
        type(value) is not int
        or (positive and value <= 0)
        or (not positive and value < 0)
    ):
        raise _error(field, f"{field} must be an integer in range")
    return value


def _hash(value: object, field: str) -> ContentHash:
    try:
        return ContentHash(_text(value, field))
    except ValueError as exc:
        raise _error(field, f"{field} must be a lowercase sha256 digest") from exc


def _optional_hash(value: object, field: str) -> ContentHash | None:
    return None if value is None else _hash(value, field)


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _error(field, f"{field} must be an array")
    return tuple(_text(item, f"{field}[]") for item in cast("Sequence[object]", value))


def _hashes(value: object, field: str) -> tuple[ContentHash, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _error(field, f"{field} must be an array")
    return tuple(_hash(item, f"{field}[]") for item in cast("Sequence[object]", value))


def _enum[EnumValue](
    enum_type: type[EnumValue], value: object, field: str
) -> EnumValue:
    try:
        constructor = cast("Callable[[str], EnumValue]", enum_type)
        return constructor(_text(value, field))
    except ValueError as exc:
        raise _error(field, f"{field} is unsupported") from exc


_ROOT_FIELDS = frozenset(
    {
        "campaign_id",
        "objective",
        "primary_metric_id",
        "hypothesis",
        "baseline_candidate",
        "experiment_plan",
        "budget",
        "search_axis",
        "search_space_hash",
        "lineage_root",
        "stopping_rule",
        "allowed_tools",
        "prohibited_actions",
    }
)
_HYPOTHESIS_FIELDS = frozenset(
    {
        "statement",
        "mechanism",
        "universe_hash",
        "expected_signal",
        "failure_condition",
    }
)
_BASELINE_FIELDS = frozenset(
    {
        "candidate_id",
        "ordinal",
        "parameters",
        "factor_code_hash",
        "model_code_hash",
        "data_requirement_hashes",
    }
)
_PLAN_FIELDS = frozenset(
    {
        "fold_protocol_id",
        "fold_protocol_version",
        "fold_protocol_hash",
        "snapshot_id",
        "validation_objective_hash",
        "cost_model_hash",
        "seed",
        "purge_sessions",
        "embargo_sessions",
    }
)
_BUDGET_FIELDS = frozenset(
    {
        "candidate_limit",
        "fold_run_limit",
        "generation_limit",
        "concurrent_sandbox_limit",
        "wall_time_limit_seconds",
        "temporary_storage_limit_bytes",
        "model_spend_limit_usd_micros",
        "sandbox_resource_limits",
    }
)
_SANDBOX_FIELDS = frozenset(
    {
        "cpu_count",
        "memory_bytes",
        "process_limit",
        "temporary_storage_bytes",
        "wall_time_seconds",
        "output_bytes",
    }
)


def build_research_campaign_manifest(
    document: Mapping[str, object],
) -> ResearchCampaignManifest:
    """Build and validate the complete v1 public Campaign manifest document."""
    root = _object(document, "manifest")
    _exact(root, "manifest", _ROOT_FIELDS)
    hypothesis = _object(root["hypothesis"], "hypothesis")
    baseline = _object(root["baseline_candidate"], "baseline_candidate")
    plan = _object(root["experiment_plan"], "experiment_plan")
    budget = _object(root["budget"], "budget")
    sandbox = _object(
        budget["sandbox_resource_limits"],
        "budget.sandbox_resource_limits",
    )
    _exact(hypothesis, "hypothesis", _HYPOTHESIS_FIELDS)
    _exact(baseline, "baseline_candidate", _BASELINE_FIELDS)
    _exact(plan, "experiment_plan", _PLAN_FIELDS)
    _exact(budget, "budget", _BUDGET_FIELDS)
    _exact(sandbox, "budget.sandbox_resource_limits", _SANDBOX_FIELDS)

    search_axis = _enum(SearchAxis, root["search_axis"], "search_axis")
    parameters = _object(baseline["parameters"], "baseline_candidate.parameters")
    try:
        return ResearchCampaignManifest(
            campaign_id=ExperimentId(_text(root["campaign_id"], "campaign_id")),
            objective=_text(root["objective"], "objective"),
            primary_metric_id=_enum(
                ResearchMetricId,
                root["primary_metric_id"],
                "primary_metric_id",
            ),
            hypothesis=HypothesisSpec(
                statement=_text(hypothesis["statement"], "hypothesis.statement"),
                mechanism=_text(hypothesis["mechanism"], "hypothesis.mechanism"),
                universe_hash=_hash(
                    hypothesis["universe_hash"], "hypothesis.universe_hash"
                ),
                expected_signal=_text(
                    hypothesis["expected_signal"], "hypothesis.expected_signal"
                ),
                failure_condition=_text(
                    hypothesis["failure_condition"], "hypothesis.failure_condition"
                ),
            ),
            baseline_candidate=ResearchCandidateSpec(
                candidate=CandidateSpec(
                    candidate_id=CandidateId(
                        _text(
                            baseline["candidate_id"],
                            "baseline_candidate.candidate_id",
                        )
                    ),
                    ordinal=_integer(
                        baseline["ordinal"],
                        "baseline_candidate.ordinal",
                        positive=True,
                    ),
                    is_baseline=True,
                    parameters=cast("Mapping[str, FrozenValue]", parameters),
                ),
                search_axis=search_axis,
                parent_candidate_id=None,
                factor_code_hash=_optional_hash(
                    baseline["factor_code_hash"],
                    "baseline_candidate.factor_code_hash",
                ),
                model_code_hash=_optional_hash(
                    baseline["model_code_hash"],
                    "baseline_candidate.model_code_hash",
                ),
                data_requirement_hashes=_hashes(
                    baseline["data_requirement_hashes"],
                    "baseline_candidate.data_requirement_hashes",
                ),
            ),
            experiment_plan=ExperimentPlan(
                fold_protocol=FoldProtocolSpec(
                    protocol_id=_text(
                        plan["fold_protocol_id"],
                        "experiment_plan.fold_protocol_id",
                    ),
                    protocol_version=_integer(
                        plan["fold_protocol_version"],
                        "experiment_plan.fold_protocol_version",
                        positive=True,
                    ),
                    protocol_hash=_hash(
                        plan["fold_protocol_hash"],
                        "experiment_plan.fold_protocol_hash",
                    ),
                ),
                snapshot_id=SnapshotId(
                    _text(plan["snapshot_id"], "experiment_plan.snapshot_id")
                ),
                validation_objective_hash=_hash(
                    plan["validation_objective_hash"],
                    "experiment_plan.validation_objective_hash",
                ),
                cost_model_hash=_hash(
                    plan["cost_model_hash"],
                    "experiment_plan.cost_model_hash",
                ),
                seed=_integer(plan["seed"], "experiment_plan.seed"),
                purge_sessions=_integer(
                    plan["purge_sessions"], "experiment_plan.purge_sessions"
                ),
                embargo_sessions=_integer(
                    plan["embargo_sessions"], "experiment_plan.embargo_sessions"
                ),
            ),
            budget=CampaignBudget(
                experiment_budget=ExperimentBudget(
                    candidate_limit=_integer(
                        budget["candidate_limit"],
                        "budget.candidate_limit",
                        positive=True,
                    ),
                    fold_run_limit=_integer(
                        budget["fold_run_limit"],
                        "budget.fold_run_limit",
                        positive=True,
                    ),
                ),
                sandbox_resource_limits=SandboxResourceLimits(
                    cpu_count=_integer(
                        sandbox["cpu_count"],
                        "budget.sandbox_resource_limits.cpu_count",
                        positive=True,
                    ),
                    memory_bytes=_integer(
                        sandbox["memory_bytes"],
                        "budget.sandbox_resource_limits.memory_bytes",
                        positive=True,
                    ),
                    process_limit=_integer(
                        sandbox["process_limit"],
                        "budget.sandbox_resource_limits.process_limit",
                        positive=True,
                    ),
                    temporary_storage_bytes=_integer(
                        sandbox["temporary_storage_bytes"],
                        "budget.sandbox_resource_limits.temporary_storage_bytes",
                        positive=True,
                    ),
                    wall_time_seconds=_integer(
                        sandbox["wall_time_seconds"],
                        "budget.sandbox_resource_limits.wall_time_seconds",
                        positive=True,
                    ),
                    output_bytes=_integer(
                        sandbox["output_bytes"],
                        "budget.sandbox_resource_limits.output_bytes",
                        positive=True,
                    ),
                ),
                generation_limit=_integer(
                    budget["generation_limit"],
                    "budget.generation_limit",
                    positive=True,
                ),
                concurrent_sandbox_limit=_integer(
                    budget["concurrent_sandbox_limit"],
                    "budget.concurrent_sandbox_limit",
                    positive=True,
                ),
                wall_time_limit_seconds=_integer(
                    budget["wall_time_limit_seconds"],
                    "budget.wall_time_limit_seconds",
                    positive=True,
                ),
                temporary_storage_limit_bytes=_integer(
                    budget["temporary_storage_limit_bytes"],
                    "budget.temporary_storage_limit_bytes",
                    positive=True,
                ),
                model_spend_limit_usd_micros=_integer(
                    budget["model_spend_limit_usd_micros"],
                    "budget.model_spend_limit_usd_micros",
                    positive=True,
                ),
            ),
            search_axis=search_axis,
            search_space_hash=_hash(root["search_space_hash"], "search_space_hash"),
            lineage_root=_hash(root["lineage_root"], "lineage_root"),
            stopping_rule=_text(root["stopping_rule"], "stopping_rule"),
            allowed_tools=_strings(root["allowed_tools"], "allowed_tools"),
            prohibited_actions=_strings(
                root["prohibited_actions"], "prohibited_actions"
            ),
        )
    except (TypeError, ValueError) as exc:
        raise _error("manifest", "Campaign manifest document is invalid") from exc


__all__ = ["build_research_campaign_manifest"]
