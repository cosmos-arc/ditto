from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.runtime.temporal_context import (
    TemporalContextError,
    TemporalContextFactory,
)

DECISION_TIME = datetime(2026, 8, 16, 7, 0, tzinfo=UTC)


def _authority() -> TemporalContextInput:
    return TemporalContextInput(
        decision_time=DECISION_TIME,
        knowledge_cutoff=DECISION_TIME - timedelta(minutes=5),
        publication_cutoff=DECISION_TIME - timedelta(minutes=10),
        source_snapshot_id="snapshot-20260816",
        execution_eligible_at="not_applicable",
        allowed_universe=("510300.SH", "510500.SH"),
        license_class="internal_research",
        egress_class=EgressClass.LOCAL_ONLY,
    )


@pytest.mark.parametrize(
    ("authority", "reason_code"),
    [
        (
            replace(
                _authority(),
                knowledge_cutoff=DECISION_TIME + timedelta(microseconds=1),
            ),
            "temporal_cutoff_order_invalid",
        ),
        (
            replace(
                _authority(),
                publication_cutoff=DECISION_TIME - timedelta(minutes=4),
            ),
            "temporal_cutoff_order_invalid",
        ),
        (
            replace(_authority(), source_snapshot_id=""),
            "temporal_context_invalid",
        ),
        (
            replace(_authority(), allowed_universe=()),
            "temporal_context_invalid",
        ),
        (
            replace(
                _authority(),
                execution_eligible_at=DECISION_TIME - timedelta(microseconds=1),
            ),
            "temporal_execution_precedes_decision",
        ),
    ],
)
@pytest.mark.pit
def test_factory_fails_closed_on_future_or_incomplete_authority(
    authority: TemporalContextInput,
    reason_code: str,
) -> None:
    factory = TemporalContextFactory()

    with pytest.raises(TemporalContextError) as exc_info:
        factory.build(authority)

    assert exc_info.value.reason_code == reason_code


@pytest.mark.pit
def test_factory_accepts_adjacent_visible_boundary_without_wall_clock_fallback() -> (
    None
):
    authority = replace(
        _authority(),
        publication_cutoff=DECISION_TIME - timedelta(microseconds=2),
        knowledge_cutoff=DECISION_TIME - timedelta(microseconds=1),
    )

    context = TemporalContextFactory().build(authority)

    assert context.publication_cutoff == DECISION_TIME - timedelta(microseconds=2)
    assert context.knowledge_cutoff == DECISION_TIME - timedelta(microseconds=1)


def test_model_cannot_override_host_temporal_fields() -> None:
    factory = TemporalContextFactory()
    model_callable = cast(Callable[..., TemporalToolContext], factory.build)

    with pytest.raises(TypeError):
        model_callable(
            _authority(),
            knowledge_cutoff=DECISION_TIME + timedelta(days=1),
        )


def test_cache_identity_covers_parameters_and_every_temporal_authority_field() -> None:
    factory = TemporalContextFactory()
    baseline_input = _authority()
    baseline = factory.build(baseline_input)
    baseline_key = factory.cache_key(
        namespace="experiment-evidence",
        parameters={"experiment_id": "experiment-001", "limit": 10},
        context=baseline,
    )
    variants = (
        replace(baseline_input, decision_time=DECISION_TIME + timedelta(seconds=1)),
        replace(
            baseline_input,
            knowledge_cutoff=baseline_input.knowledge_cutoff - timedelta(seconds=1),
        ),
        replace(
            baseline_input,
            publication_cutoff=baseline_input.publication_cutoff - timedelta(seconds=1),
        ),
        replace(baseline_input, source_snapshot_id="snapshot-20260815"),
        replace(baseline_input, execution_eligible_at=DECISION_TIME),
        replace(baseline_input, allowed_universe=("510300.SH",)),
        replace(baseline_input, license_class="redistribution_reviewed"),
        replace(baseline_input, egress_class=EgressClass.CLOUD_ALLOWED),
        replace(
            baseline_input,
            campaign_authorization_id="campaign-auth-001",
            campaign_authority_hash="a" * 64,
        ),
    )

    variant_keys = {
        factory.cache_key(
            namespace="experiment-evidence",
            parameters={"limit": 10, "experiment_id": "experiment-001"},
            context=factory.build(item),
        )
        for item in variants
    }

    assert len(baseline_key) == 64
    assert baseline_key not in variant_keys
    assert len(variant_keys) == len(variants)
    assert baseline_key != factory.cache_key(
        namespace="experiment-evidence",
        parameters={"experiment_id": "experiment-002", "limit": 10},
        context=baseline,
    )
