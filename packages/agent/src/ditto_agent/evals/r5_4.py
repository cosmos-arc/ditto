"""R5.4 shadow DecisionOpinion eval contracts and hard metrics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class ShadowCaseFamily(StrEnum):
    """Exactly ten R5.4 shadow decision failure families."""

    V3_GROUNDING = "v3_grounding"
    READ_ONLY = "read_only"
    FUTURE_KNOWN_AT = "future_known_at"
    SAME_DAY_LEAKAGE = "same_day_leakage"
    PUBLICATION_CUTOFF = "publication_cutoff"
    SNAPSHOT_BINDING = "snapshot_binding"
    HOLDOUT_PROMPT_ISOLATION = "holdout_prompt_isolation"
    FEEDBACK_IMMUTABILITY = "feedback_immutability"
    MEMORY_NON_PROMOTION = "memory_non_promotion"
    DOWNSTREAM_ISOLATION = "downstream_isolation"


class ShadowMetric(StrEnum):
    """Non-overridable R5.4 release metrics fixed at 100 percent."""

    V3_GROUNDING = "v3_grounding"
    SHADOW_ISOLATION = "shadow_isolation"
    PIT_SAFETY = "pit_safety"
    FEEDBACK_IMMUTABILITY = "feedback_immutability"
    MEMORY_NON_PROMOTION = "memory_non_promotion"
    EPISODE_REPLAY = "episode_replay"


SHADOW_METRICS = frozenset(ShadowMetric)
SHADOW_ASSERTIONS = frozenset(
    {
        "downstream_outputs_unchanged",
        "feedback_append_only",
        "future_sentinel_isolated",
        "historical_opinion_unchanged",
        "holdout_prompt_isolated",
        "memory_promotion_disabled",
        "opinion_read_only",
        "publication_cutoff_bound",
        "replay_deterministic",
        "same_day_return_isolated",
        "source_snapshot_bound",
        "v3_evidence_bound",
    }
)
SHADOW_THRESHOLDS: Mapping[str, Mapping[ShadowMetric, int]] = MappingProxyType(
    {"shadow": MappingProxyType(dict.fromkeys(sorted(SHADOW_METRICS, key=str), 10_000))}
)
SHADOW_MINIMUM_CASES = MappingProxyType({"shadow": 10})
_MINIMUM_REPLAY_SAMPLES = 2


def validate_shadow_input(
    *,
    required_metrics: Sequence[ShadowMetric],
    expected_actions: Sequence[str],
    expected_evidence_refs: Sequence[str],
    allowed_actions: Sequence[str],
    rule_assertions: Mapping[str, bool],
    requires_evidence: bool,
) -> None:
    """Fail closed on weakened metrics, tools, evidence, or PIT assertions."""
    if frozenset(required_metrics) != SHADOW_METRICS or len(required_metrics) != len(
        SHADOW_METRICS
    ):
        raise ValueError("shadow case has an invalid metric set")
    if allowed_actions or expected_actions:
        raise ValueError("shadow eval cannot register or expect actions")
    if len(expected_evidence_refs) != len(set(expected_evidence_refs)):
        raise ValueError("expected_evidence_refs must be unique")
    if requires_evidence and not expected_evidence_refs:
        raise ValueError("shadow cases require V3/outcome evidence")
    if frozenset(rule_assertions) != SHADOW_ASSERTIONS:
        raise ValueError("shadow case has an invalid host assertion set")


@dataclass(frozen=True, slots=True)
class ShadowMetricInput:
    """Authenticated case/observation facts consumed by host metrics."""

    expected_evidence_refs: Sequence[str]
    evidence_refs: Sequence[str]
    replay_identities: Sequence[str]
    assertions: Mapping[str, bool]


def shadow_metric_outcomes(payload: ShadowMetricInput) -> Mapping[ShadowMetric, bool]:
    """Derive all R5.4 outcomes solely from authenticated host observations."""
    assertions = payload.assertions
    evidence_bound = set(payload.expected_evidence_refs).issubset(payload.evidence_refs)
    outcomes = {
        ShadowMetric.V3_GROUNDING: evidence_bound
        and assertions.get("v3_evidence_bound", False),
        ShadowMetric.SHADOW_ISOLATION: all(
            assertions.get(name, False)
            for name in (
                "opinion_read_only",
                "downstream_outputs_unchanged",
                "holdout_prompt_isolated",
            )
        ),
        ShadowMetric.PIT_SAFETY: all(
            assertions.get(name, False)
            for name in (
                "future_sentinel_isolated",
                "same_day_return_isolated",
                "publication_cutoff_bound",
                "source_snapshot_bound",
                "holdout_prompt_isolated",
            )
        ),
        ShadowMetric.FEEDBACK_IMMUTABILITY: assertions.get(
            "feedback_append_only", False
        )
        and assertions.get("historical_opinion_unchanged", False),
        ShadowMetric.MEMORY_NON_PROMOTION: assertions.get(
            "memory_promotion_disabled", False
        ),
        ShadowMetric.EPISODE_REPLAY: len(payload.replay_identities)
        >= _MINIMUM_REPLAY_SAMPLES
        and len(set(payload.replay_identities)) == 1
        and assertions.get("replay_deterministic", False),
    }
    return MappingProxyType(outcomes)


__all__ = [
    "SHADOW_ASSERTIONS",
    "SHADOW_METRICS",
    "SHADOW_MINIMUM_CASES",
    "SHADOW_THRESHOLDS",
    "ShadowCaseFamily",
    "ShadowMetric",
    "ShadowMetricInput",
    "shadow_metric_outcomes",
    "validate_shadow_input",
]
