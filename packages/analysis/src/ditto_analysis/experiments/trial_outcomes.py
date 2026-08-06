"""Immutable observed evidence for each declared logical trial."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.metric_schema import (
    R3_RESEARCH_METRIC_SCHEMA,
    ResearchMetricId,
    ResearchMetricValue,
)
from ditto_analysis.experiments.models import CandidateId, ContentHash
from ditto_analysis.experiments.trial_family import LogicalTrialIdentity
from ditto_analysis.experiments.trial_statistics import (
    PboSamplingEvidence,
    SharpeSamplingEvidence,
)

__all__ = ["MetricEvidenceLineage", "TrialOutcome", "TrialStatus"]

_METRIC_ORDER = {
    definition.metric_id: index
    for index, definition in enumerate(R3_RESEARCH_METRIC_SCHEMA.definitions)
}


def _outcome_error(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _freeze_metrics(
    value: object,
    field_name: str,
) -> Mapping[ResearchMetricId, ResearchMetricValue]:
    if not isinstance(value, Mapping):
        raise _outcome_error(
            f"{field_name} must be a metric mapping",
            "invalid_trial_metrics",
            field=field_name,
        )
    frozen: dict[ResearchMetricId, ResearchMetricValue] = {}
    for raw_id, raw_value in cast("Mapping[object, object]", value).items():
        if (
            type(raw_id) is not ResearchMetricId
            or type(raw_value) is not ResearchMetricValue
        ):
            raise _outcome_error(
                f"{field_name} must use exact typed metric nodes",
                "invalid_trial_metrics",
                field=field_name,
            )
        metric_id = raw_id
        metric_value = raw_value
        if metric_value.metric_id is not metric_id:
            raise _outcome_error(
                "metric mapping key must match its value identity",
                "metric_identity_mismatch",
                field=field_name,
            )
        frozen[metric_id] = metric_value
    ordered = {
        metric_id: frozen[metric_id]
        for metric_id in sorted(frozen, key=lambda item: _METRIC_ORDER[item])
    }
    return MappingProxyType(ordered)


class TrialStatus(StrEnum):
    """Observed outcome of every declared logical trial."""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MetricEvidenceLineage:
    """Immutable source references and hashes supporting one metric value."""

    evidence_refs: Sequence[str]
    evidence_hashes: Sequence[ContentHash]

    def __post_init__(self) -> None:
        """Require non-empty canonical, duplicate-free source identities."""
        raw_refs = cast("object", self.evidence_refs)
        if not isinstance(raw_refs, Sequence) or isinstance(
            raw_refs,
            (str, bytes, bytearray),
        ):
            raise _outcome_error(
                "metric evidence refs must be an ordered sequence",
                "invalid_metric_evidence_lineage",
            )
        raw_hashes = cast("object", self.evidence_hashes)
        if not isinstance(raw_hashes, Sequence) or isinstance(
            raw_hashes,
            (str, bytes, bytearray),
        ):
            raise _outcome_error(
                "metric evidence hashes must be an ordered sequence",
                "invalid_metric_evidence_lineage",
            )
        refs = tuple(cast("Sequence[object]", raw_refs))
        hashes = tuple(cast("Sequence[object]", raw_hashes))
        if (
            not refs
            or any(
                type(item) is not str or not item or item != item.strip()
                for item in refs
            )
            or len(set(refs)) != len(refs)
            or not hashes
            or len(refs) != len(hashes)
            or any(type(item) is not ContentHash for item in hashes)
            or len(set(hashes)) != len(hashes)
        ):
            raise _outcome_error(
                "metric evidence lineage must use canonical refs and hashes",
                "invalid_metric_evidence_lineage",
            )
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "evidence_hashes", hashes)


def _freeze_metric_evidence(
    value: object,
    field_name: str,
) -> Mapping[ResearchMetricId, MetricEvidenceLineage]:
    if not isinstance(value, Mapping):
        raise _outcome_error(
            f"{field_name} must be a metric evidence mapping",
            "invalid_metric_evidence_lineage",
            field=field_name,
        )
    frozen: dict[ResearchMetricId, MetricEvidenceLineage] = {}
    for raw_id, raw_value in cast("Mapping[object, object]", value).items():
        if (
            type(raw_id) is not ResearchMetricId
            or type(raw_value) is not MetricEvidenceLineage
        ):
            raise _outcome_error(
                f"{field_name} must use typed metric evidence nodes",
                "invalid_metric_evidence_lineage",
                field=field_name,
            )
        frozen[raw_id] = raw_value
    ordered = {
        metric_id: frozen[metric_id]
        for metric_id in sorted(frozen, key=lambda item: _METRIC_ORDER[item])
    }
    return MappingProxyType(ordered)


def _empty_metric_evidence() -> dict[ResearchMetricId, MetricEvidenceLineage]:
    return {}


@dataclass(frozen=True, slots=True)
class TrialOutcome:
    """Evidence for one attempt-independent logical trial."""

    trial: LogicalTrialIdentity
    status: TrialStatus
    metrics: Mapping[ResearchMetricId, ResearchMetricValue]
    holdout_metrics: Mapping[ResearchMetricId, ResearchMetricValue]
    source_projection_hash: ContentHash
    metric_evidence: Mapping[
        ResearchMetricId,
        MetricEvidenceLineage,
    ] = field(default_factory=_empty_metric_evidence)
    holdout_metric_evidence: Mapping[
        ResearchMetricId,
        MetricEvidenceLineage,
    ] = field(default_factory=_empty_metric_evidence)
    sharpe_sampling: SharpeSamplingEvidence | None = None
    pbo_sampling: PboSamplingEvidence | None = None
    failure_reason: str | None = None

    def _validate_typed_nodes(self) -> None:
        if type(self.trial) is not LogicalTrialIdentity:
            raise _outcome_error(
                "trial must be LogicalTrialIdentity",
                "invalid_logical_trial_identity",
            )
        if type(self.status) is not TrialStatus:
            raise _outcome_error(
                "status must be TrialStatus",
                "invalid_trial_status",
            )
        if type(self.source_projection_hash) is not ContentHash:
            raise _outcome_error(
                "source_projection_hash must be ContentHash",
                "invalid_trial_source_projection_hash",
            )
        if self.sharpe_sampling is not None and (
            type(self.sharpe_sampling) is not SharpeSamplingEvidence
        ):
            raise _outcome_error(
                "sharpe_sampling must be SharpeSamplingEvidence",
                "invalid_sharpe_sampling_evidence",
            )
        if self.pbo_sampling is not None and (
            type(self.pbo_sampling) is not PboSamplingEvidence
        ):
            raise _outcome_error(
                "pbo_sampling must be PboSamplingEvidence",
                "invalid_pbo_sampling_evidence",
            )

    def _validate_status_evidence(
        self,
        metrics: Mapping[ResearchMetricId, ResearchMetricValue],
        holdout: Mapping[ResearchMetricId, ResearchMetricValue],
        metric_evidence: Mapping[ResearchMetricId, MetricEvidenceLineage],
        holdout_evidence: Mapping[ResearchMetricId, MetricEvidenceLineage],
    ) -> None:
        if self.status is TrialStatus.FAILED:
            if (
                metrics
                or holdout
                or metric_evidence
                or holdout_evidence
                or self.sharpe_sampling
                or self.pbo_sampling
            ):
                raise _outcome_error(
                    "failed trial cannot carry valid metric or sampling evidence",
                    "failed_trial_carries_evidence",
                )
            if (
                not isinstance(self.failure_reason, str)
                or not self.failure_reason.strip()
                or self.failure_reason != self.failure_reason.strip()
            ):
                raise _outcome_error(
                    "failed trial must carry a non-empty reason",
                    "trial_failure_reason_required",
                )
        elif self.failure_reason is not None:
            raise _outcome_error(
                "completed trial cannot carry a failure reason",
                "unexpected_trial_failure_reason",
            )

    def _validate_metric_bindings(
        self,
        metrics: Mapping[ResearchMetricId, ResearchMetricValue],
        holdout: Mapping[ResearchMetricId, ResearchMetricValue],
        metric_evidence: Mapping[ResearchMetricId, MetricEvidenceLineage],
        holdout_evidence: Mapping[ResearchMetricId, MetricEvidenceLineage],
    ) -> None:
        if tuple(metric_evidence) != tuple(metrics) or tuple(holdout_evidence) != tuple(
            holdout
        ):
            raise _outcome_error(
                "every metric value must retain its exact evidence lineage",
                "metric_evidence_identity_mismatch",
            )
        if (
            self.sharpe_sampling is not None
            and metrics.get(ResearchMetricId.SHARPE_RATIO)
            != self.sharpe_sampling.annualized_sharpe
        ):
            raise _outcome_error(
                "Sharpe sampling observation must equal the governance metric",
                "sharpe_sampling_metric_mismatch",
            )
        if (
            self.pbo_sampling is not None
            and metrics.get(self.pbo_sampling.score_metric_id)
            != self.pbo_sampling.aggregate_metric_value
        ):
            raise _outcome_error(
                "PBO raw returns must recompute to the governance metric",
                "pbo_sampling_metric_mismatch",
            )
        if (
            self.sharpe_sampling is not None
            and self.pbo_sampling is not None
            and (
                self.sharpe_sampling.return_frequency
                is not self.pbo_sampling.return_frequency
                or self.sharpe_sampling.periods_per_year
                != self.pbo_sampling.periods_per_year
            )
        ):
            raise _outcome_error(
                "sampling evidence on one trial must use one return frequency",
                "sampling_frequency_mismatch",
            )

    def __post_init__(self) -> None:
        """Freeze typed evidence and enforce failed/completed disjointness."""
        self._validate_typed_nodes()
        metrics = _freeze_metrics(self.metrics, "metrics")
        holdout = _freeze_metrics(self.holdout_metrics, "holdout_metrics")
        metric_evidence = _freeze_metric_evidence(
            self.metric_evidence,
            "metric_evidence",
        )
        holdout_evidence = _freeze_metric_evidence(
            self.holdout_metric_evidence,
            "holdout_metric_evidence",
        )
        self._validate_status_evidence(
            metrics,
            holdout,
            metric_evidence,
            holdout_evidence,
        )
        self._validate_metric_bindings(
            metrics,
            holdout,
            metric_evidence,
            holdout_evidence,
        )
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "holdout_metrics", holdout)
        object.__setattr__(self, "metric_evidence", metric_evidence)
        object.__setattr__(self, "holdout_metric_evidence", holdout_evidence)

    @property
    def candidate_id(self) -> CandidateId:
        """Return the logical trial candidate identity."""
        return self.trial.candidate_id

    @property
    def ordinal(self) -> int:
        """Return the logical trial family ordinal."""
        return self.trial.ordinal
