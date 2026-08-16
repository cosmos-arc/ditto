"""Pure governed-research campaign domain contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import StrEnum
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.generated_code import SandboxResourceLimits
from ditto_analysis.experiments.metric_schema import ResearchMetricId
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    SnapshotId,
)
from ditto_analysis.experiments.persistence import (
    CanonicalPayload,
    canonical_payload,
)
from ditto_analysis.experiments.specs import (
    CandidateSpec,
    ExperimentBudget,
    FoldProtocolSpec,
)

__all__ = [
    "CampaignBudget",
    "EvaluationResult",
    "ExperimentPlan",
    "HypothesisSpec",
    "ResearchCampaignManifest",
    "ResearchCandidateSpec",
    "SearchAxis",
]

_MAX_GENERATIONS = 6
_MAX_FOLD_RUNS = 384
_MAX_CONCURRENT_SANDBOXES = 2
_MAX_WALL_TIME_SECONDS = 4 * 60 * 60
_MAX_TEMPORARY_STORAGE_BYTES = 20 * 1024**3
_MAX_MODEL_SPEND_USD_MICROS = 8_000_000
_MAX_SANDBOX_CPU_COUNT = 2
_MAX_SANDBOX_MEMORY_BYTES = 4 * 1024**3


def _campaign_error(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _non_empty(value: object, field: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise _campaign_error(
            f"{field} must be a non-empty unpadded string",
            "invalid_campaign_text",
            field=field,
        )
    return value


def _positive_int(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise _campaign_error(
            f"{field} must be a positive integer",
            "invalid_campaign_budget",
            field=field,
        )
    return value


def _non_negative_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise _campaign_error(
            f"{field} must be a non-negative integer",
            "invalid_experiment_plan",
            field=field,
        )
    return value


def _freeze_hashes(
    value: object,
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[ContentHash, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _campaign_error(
            f"{field} must be an ordered sequence of ContentHash values",
            "invalid_campaign_hash_sequence",
            field=field,
        )
    items = tuple(cast("Sequence[object]", value))
    if (not items and not allow_empty) or any(
        type(item) is not ContentHash for item in items
    ):
        raise _campaign_error(
            f"{field} must contain ContentHash values",
            "invalid_campaign_hash_sequence",
            field=field,
        )
    typed = cast("tuple[ContentHash, ...]", items)
    if len(set(typed)) != len(typed):
        raise _campaign_error(
            f"{field} cannot contain duplicates",
            "duplicate_campaign_hash",
            field=field,
        )
    return tuple(sorted(typed, key=str))


def _freeze_names(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _campaign_error(
            f"{field} must be an ordered sequence",
            "invalid_campaign_name_sequence",
            field=field,
        )
    names = tuple(cast("Sequence[object]", value))
    if not names or any(
        type(item) is not str or not item.strip() or item != item.strip()
        for item in names
    ):
        raise _campaign_error(
            f"{field} must contain non-empty unpadded strings",
            "invalid_campaign_name_sequence",
            field=field,
        )
    typed = cast("tuple[str, ...]", names)
    if len(set(typed)) != len(typed):
        raise _campaign_error(
            f"{field} cannot contain duplicates",
            "duplicate_campaign_name",
            field=field,
        )
    return tuple(sorted(typed))


class SearchAxis(StrEnum):
    """The one mutable dimension authorized for a research campaign."""

    FACTOR_CODE = "factor_code"
    MODEL_CODE = "model_code"
    PARAMETERS = "parameters"


@dataclass(frozen=True, slots=True)
class CampaignBudget:
    """Bounded autonomous work budget composed with the existing R3 budget."""

    experiment_budget: ExperimentBudget
    sandbox_resource_limits: SandboxResourceLimits = dataclass_field(
        default_factory=SandboxResourceLimits
    )
    generation_limit: int = _MAX_GENERATIONS
    concurrent_sandbox_limit: int = _MAX_CONCURRENT_SANDBOXES
    wall_time_limit_seconds: int = _MAX_WALL_TIME_SECONDS
    temporary_storage_limit_bytes: int = _MAX_TEMPORARY_STORAGE_BYTES
    model_spend_limit_usd_micros: int = _MAX_MODEL_SPEND_USD_MICROS

    def __post_init__(self) -> None:
        """Reject invalid or expanded autonomous work authority."""
        if type(self.experiment_budget) is not ExperimentBudget:
            raise _campaign_error(
                "experiment_budget must be ExperimentBudget",
                "invalid_campaign_budget",
                field="experiment_budget",
            )
        if type(self.sandbox_resource_limits) is not SandboxResourceLimits:
            raise _campaign_error(
                "sandbox_resource_limits must be SandboxResourceLimits",
                "invalid_campaign_budget",
                field="sandbox_resource_limits",
            )
        limits = (
            (self.generation_limit, "generation_limit", _MAX_GENERATIONS),
            (
                self.concurrent_sandbox_limit,
                "concurrent_sandbox_limit",
                _MAX_CONCURRENT_SANDBOXES,
            ),
            (
                self.wall_time_limit_seconds,
                "wall_time_limit_seconds",
                _MAX_WALL_TIME_SECONDS,
            ),
            (
                self.temporary_storage_limit_bytes,
                "temporary_storage_limit_bytes",
                _MAX_TEMPORARY_STORAGE_BYTES,
            ),
            (
                self.model_spend_limit_usd_micros,
                "model_spend_limit_usd_micros",
                _MAX_MODEL_SPEND_USD_MICROS,
            ),
        )
        for value, field, maximum in limits:
            _positive_int(value, field)
            if value > maximum:
                raise _campaign_error(
                    f"{field} exceeds the governed campaign maximum",
                    "campaign_budget_limit_exceeded",
                    field=field,
                    maximum=maximum,
                )
        if self.experiment_budget.fold_run_limit > _MAX_FOLD_RUNS:
            raise _campaign_error(
                "fold_run_limit exceeds the governed campaign maximum",
                "campaign_budget_limit_exceeded",
                field="fold_run_limit",
                maximum=_MAX_FOLD_RUNS,
            )
        sandbox_limits = (
            (
                self.sandbox_resource_limits.cpu_count,
                "sandbox_cpu_count",
                _MAX_SANDBOX_CPU_COUNT,
            ),
            (
                self.sandbox_resource_limits.memory_bytes,
                "sandbox_memory_bytes",
                _MAX_SANDBOX_MEMORY_BYTES,
            ),
        )
        for value, field_name, maximum in sandbox_limits:
            if value > maximum:
                raise _campaign_error(
                    f"{field_name} exceeds the governed campaign maximum",
                    "campaign_budget_limit_exceeded",
                    field=field_name,
                    maximum=maximum,
                )


@dataclass(frozen=True, slots=True)
class HypothesisSpec:
    """A preregistered, falsifiable research hypothesis."""

    statement: str
    mechanism: str
    universe_hash: ContentHash
    expected_signal: str
    failure_condition: str

    def __post_init__(self) -> None:
        """Require the hypothesis and its falsification boundary."""
        for field in (
            "statement",
            "mechanism",
            "expected_signal",
            "failure_condition",
        ):
            _non_empty(getattr(self, field), field)
        if type(self.universe_hash) is not ContentHash:
            raise _campaign_error(
                "universe_hash must be ContentHash",
                "invalid_hypothesis_spec",
                field="universe_hash",
            )


@dataclass(frozen=True, slots=True)
class ResearchCandidateSpec:
    """Campaign metadata around the existing immutable candidate contract."""

    candidate: CandidateSpec
    search_axis: SearchAxis
    parent_candidate_id: CandidateId | None
    factor_code_hash: ContentHash | None
    model_code_hash: ContentHash | None
    data_requirement_hashes: Sequence[ContentHash]

    def __post_init__(self) -> None:
        """Freeze data needs and enforce exactly one mutable search axis."""
        if type(self.candidate) is not CandidateSpec:
            raise _campaign_error(
                "candidate must reuse the existing CandidateSpec",
                "invalid_research_candidate",
            )
        if type(self.search_axis) is not SearchAxis:
            raise _campaign_error(
                "search_axis must be SearchAxis",
                "invalid_campaign_search_axis",
            )
        if (
            self.parent_candidate_id is not None
            and type(self.parent_candidate_id) is not CandidateId
        ):
            raise _campaign_error(
                "parent_candidate_id must be CandidateId when present",
                "invalid_candidate_lineage",
            )
        if self.parent_candidate_id == self.candidate.candidate_id:
            raise _campaign_error(
                "candidate cannot be its own parent",
                "invalid_candidate_lineage",
            )
        code_hashes = (self.factor_code_hash, self.model_code_hash)
        if any(
            item is not None and type(item) is not ContentHash for item in code_hashes
        ):
            raise _campaign_error(
                "candidate code hashes must be ContentHash values",
                "invalid_research_candidate",
            )
        expected = {
            SearchAxis.FACTOR_CODE: (True, False),
            SearchAxis.MODEL_CODE: (False, True),
            SearchAxis.PARAMETERS: (False, False),
        }[self.search_axis]
        observed = (
            self.factor_code_hash is not None,
            self.model_code_hash is not None,
        )
        if observed != expected:
            raise _campaign_error(
                "candidate hashes must describe exactly the registered search axis",
                "multiple_campaign_search_axes",
                search_axis=self.search_axis.value,
            )
        object.__setattr__(
            self,
            "data_requirement_hashes",
            _freeze_hashes(self.data_requirement_hashes, "data_requirement_hashes"),
        )

    @property
    def candidate_hash(self) -> ContentHash:
        """Bind code/parameters and data requirements to one candidate identity."""
        payload = canonical_payload(
            {
                "candidate_id": str(self.candidate.candidate_id),
                "search_axis": self.search_axis.value,
                "factor_code_hash": (
                    str(self.factor_code_hash)
                    if self.factor_code_hash is not None
                    else None
                ),
                "model_code_hash": (
                    str(self.model_code_hash)
                    if self.model_code_hash is not None
                    else None
                ),
                "parameter_hash": str(self.candidate.parameter_hash),
                "data_requirement_hashes": [
                    str(item) for item in self.data_requirement_hashes
                ],
            }
        )
        return payload.content_hash


@dataclass(frozen=True, slots=True)
class ExperimentPlan:
    """PIT-sensitive validation protocol frozen before campaign execution."""

    fold_protocol: FoldProtocolSpec
    snapshot_id: SnapshotId
    validation_objective_hash: ContentHash
    cost_model_hash: ContentHash
    seed: int
    purge_sessions: int
    embargo_sessions: int

    def __post_init__(self) -> None:
        """Require complete typed validation semantics."""
        typed_fields = (
            (self.fold_protocol, FoldProtocolSpec, "fold_protocol"),
            (self.snapshot_id, SnapshotId, "snapshot_id"),
            (
                self.validation_objective_hash,
                ContentHash,
                "validation_objective_hash",
            ),
            (self.cost_model_hash, ContentHash, "cost_model_hash"),
        )
        for value, expected, field in typed_fields:
            if type(value) is not expected:
                raise _campaign_error(
                    f"{field} must be {expected.__name__}",
                    "invalid_experiment_plan",
                    field=field,
                )
        _non_negative_int(self.seed, "seed")
        _non_negative_int(self.purge_sessions, "purge_sessions")
        _non_negative_int(self.embargo_sessions, "embargo_sessions")

    @property
    def validation_protocol_hash(self) -> ContentHash:
        """Hash every field that can change statistical/PIT interpretation."""
        return canonical_payload(
            {
                "fold_protocol_id": self.fold_protocol.protocol_id,
                "fold_protocol_version": self.fold_protocol.protocol_version,
                "fold_protocol_hash": str(self.fold_protocol.protocol_hash),
                "snapshot_id": str(self.snapshot_id),
                "validation_objective_hash": str(self.validation_objective_hash),
                "cost_model_hash": str(self.cost_model_hash),
                "seed": self.seed,
                "purge_sessions": self.purge_sessions,
                "embargo_sessions": self.embargo_sessions,
            }
        ).content_hash


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Trusted-host evaluation references, never candidate self-reported metrics."""

    candidate_id: CandidateId
    candidate_hash: ContentHash
    validation_protocol_hash: ContentHash
    metrics_artifact_hash: ContentHash
    constraints_passed: bool
    significance_evidence_hash: ContentHash
    failure_classification: str | None
    evidence_refs: Sequence[ContentHash]

    def __post_init__(self) -> None:
        """Reject partial or untyped host evaluation evidence."""
        typed_fields = (
            (self.candidate_id, CandidateId, "candidate_id"),
            (self.candidate_hash, ContentHash, "candidate_hash"),
            (
                self.validation_protocol_hash,
                ContentHash,
                "validation_protocol_hash",
            ),
            (self.metrics_artifact_hash, ContentHash, "metrics_artifact_hash"),
            (
                self.significance_evidence_hash,
                ContentHash,
                "significance_evidence_hash",
            ),
        )
        for value, expected, field in typed_fields:
            if type(value) is not expected:
                raise _campaign_error(
                    f"{field} must be {expected.__name__}",
                    "invalid_evaluation_result",
                    field=field,
                )
        if type(self.constraints_passed) is not bool:
            raise _campaign_error(
                "constraints_passed must be bool",
                "invalid_evaluation_result",
                field="constraints_passed",
            )
        if self.failure_classification is not None:
            _non_empty(self.failure_classification, "failure_classification")
        if self.constraints_passed == (self.failure_classification is not None):
            raise _campaign_error(
                "failure_classification must be present exactly for failed results",
                "invalid_evaluation_result",
                field="failure_classification",
            )
        object.__setattr__(
            self,
            "evidence_refs",
            _freeze_hashes(self.evidence_refs, "evidence_refs"),
        )


@dataclass(frozen=True, slots=True)
class ResearchCampaignManifest:
    """Canonical preregistration for one bounded autonomous research campaign."""

    campaign_id: ExperimentId
    objective: str
    primary_metric_id: ResearchMetricId
    hypothesis: HypothesisSpec
    baseline_candidate: ResearchCandidateSpec
    experiment_plan: ExperimentPlan
    budget: CampaignBudget
    search_axis: SearchAxis
    search_space_hash: ContentHash
    lineage_root: ContentHash
    stopping_rule: str
    allowed_tools: Sequence[str]
    prohibited_actions: Sequence[str]

    def __post_init__(self) -> None:
        """Freeze the complete authority-relevant research preregistration."""
        typed_fields = (
            (self.campaign_id, ExperimentId, "campaign_id"),
            (self.primary_metric_id, ResearchMetricId, "primary_metric_id"),
            (self.hypothesis, HypothesisSpec, "hypothesis"),
            (self.baseline_candidate, ResearchCandidateSpec, "baseline_candidate"),
            (self.experiment_plan, ExperimentPlan, "experiment_plan"),
            (self.budget, CampaignBudget, "budget"),
            (self.search_axis, SearchAxis, "search_axis"),
            (self.search_space_hash, ContentHash, "search_space_hash"),
            (self.lineage_root, ContentHash, "lineage_root"),
        )
        for value, expected, field in typed_fields:
            if type(value) is not expected:
                raise _campaign_error(
                    f"{field} must be {expected.__name__}",
                    "invalid_campaign_manifest",
                    field=field,
                )
        _non_empty(self.objective, "objective")
        _non_empty(self.stopping_rule, "stopping_rule")
        if self.baseline_candidate.search_axis is not self.search_axis:
            raise _campaign_error(
                "baseline candidate must use the campaign search axis",
                "campaign_search_axis_mismatch",
            )
        if not self.baseline_candidate.candidate.is_baseline:
            raise _campaign_error(
                "campaign requires an explicit baseline candidate",
                "campaign_baseline_missing",
            )
        object.__setattr__(
            self,
            "allowed_tools",
            _freeze_names(self.allowed_tools, "allowed_tools"),
        )
        object.__setattr__(
            self,
            "prohibited_actions",
            _freeze_names(self.prohibited_actions, "prohibited_actions"),
        )

    @property
    def canonical_payload(self) -> CanonicalPayload:
        """Return the complete immutable authorization input."""
        candidate = self.baseline_candidate
        plan = self.experiment_plan
        hypothesis = self.hypothesis
        budget = self.budget
        return canonical_payload(
            {
                "schema_id": "r5-research-campaign-manifest",
                "schema_version": 1,
                "campaign_id": str(self.campaign_id),
                "objective": self.objective,
                "primary_metric_id": self.primary_metric_id.value,
                "hypothesis": {
                    "statement": hypothesis.statement,
                    "mechanism": hypothesis.mechanism,
                    "universe_hash": str(hypothesis.universe_hash),
                    "expected_signal": hypothesis.expected_signal,
                    "failure_condition": hypothesis.failure_condition,
                },
                "baseline_candidate": {
                    "candidate_id": str(candidate.candidate.candidate_id),
                    "ordinal": candidate.candidate.ordinal,
                    "parameter_hash": str(candidate.candidate.parameter_hash),
                    "candidate_hash": str(candidate.candidate_hash),
                    "parent_candidate_id": (
                        str(candidate.parent_candidate_id)
                        if candidate.parent_candidate_id is not None
                        else None
                    ),
                    "factor_code_hash": (
                        str(candidate.factor_code_hash)
                        if candidate.factor_code_hash is not None
                        else None
                    ),
                    "model_code_hash": (
                        str(candidate.model_code_hash)
                        if candidate.model_code_hash is not None
                        else None
                    ),
                    "data_requirement_hashes": [
                        str(item) for item in candidate.data_requirement_hashes
                    ],
                },
                "experiment_plan": {
                    "validation_protocol_hash": str(plan.validation_protocol_hash),
                    "fold_protocol_hash": str(plan.fold_protocol.protocol_hash),
                    "snapshot_id": str(plan.snapshot_id),
                    "validation_objective_hash": str(plan.validation_objective_hash),
                    "cost_model_hash": str(plan.cost_model_hash),
                    "seed": plan.seed,
                    "purge_sessions": plan.purge_sessions,
                    "embargo_sessions": plan.embargo_sessions,
                },
                "budget": {
                    "candidate_limit": budget.experiment_budget.candidate_limit,
                    "fold_run_limit": budget.experiment_budget.fold_run_limit,
                    "generation_limit": budget.generation_limit,
                    "concurrent_sandbox_limit": budget.concurrent_sandbox_limit,
                    "wall_time_limit_seconds": budget.wall_time_limit_seconds,
                    "temporary_storage_limit_bytes": (
                        budget.temporary_storage_limit_bytes
                    ),
                    "model_spend_limit_usd_micros": (
                        budget.model_spend_limit_usd_micros
                    ),
                    "sandbox_resource_limits": {
                        "cpu_count": budget.sandbox_resource_limits.cpu_count,
                        "memory_bytes": budget.sandbox_resource_limits.memory_bytes,
                        "process_limit": budget.sandbox_resource_limits.process_limit,
                        "temporary_storage_bytes": (
                            budget.sandbox_resource_limits.temporary_storage_bytes
                        ),
                        "wall_time_seconds": (
                            budget.sandbox_resource_limits.wall_time_seconds
                        ),
                        "output_bytes": budget.sandbox_resource_limits.output_bytes,
                    },
                },
                "search_axis": self.search_axis.value,
                "search_space_hash": str(self.search_space_hash),
                "lineage_root": str(self.lineage_root),
                "stopping_rule": self.stopping_rule,
                "allowed_tools": list(self.allowed_tools),
                "prohibited_actions": list(self.prohibited_actions),
            }
        )

    @property
    def manifest_hash(self) -> ContentHash:
        """Return the stable SHA-256 campaign identity."""
        return self.canonical_payload.content_hash
