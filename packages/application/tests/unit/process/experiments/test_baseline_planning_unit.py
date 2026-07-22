"""Planning-envelope adaptation tests for constrained research baselines."""

from __future__ import annotations

from dataclasses import replace

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.baseline_planning import (
    build_frozen_baseline_plan,
    resolve_planning_baseline,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselinePlanKind,
    default_baseline_registry,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactUniverseIdentity,
)
from ditto_application.processes.experiments.planning import BaselineDescriptor


def _etf_descriptor() -> BaselineDescriptor:
    return BaselineDescriptor(
        descriptor_type="etf-current-active",
        payload={
            "strategy_id": "seed_etf_rotation",
            "version": 2,
            "spec_hash": "a" * 64,
        },
    )


def test_etf_planning_descriptor_resolves_one_exact_registered_version() -> None:
    registry = default_baseline_registry()

    resolution = resolve_planning_baseline(_etf_descriptor(), registry)

    assert resolution.ref.identity == "etf_current_active.v1"
    assert (
        resolution.registration.descriptor.kind is BaselinePlanKind.ETF_CURRENT_ACTIVE
    )
    assert resolution.exact_strategy is not None
    assert resolution.exact_strategy.identity == "seed_etf_rotation@2"
    assert resolution.exact_strategy.spec_hash == "a" * 64


def test_stock_equal_weight_descriptor_has_no_moving_strategy_identity() -> None:
    registry = default_baseline_registry()
    descriptor = BaselineDescriptor(
        descriptor_type="stock-universe-equal-weight",
        payload={},
    )

    resolution = resolve_planning_baseline(descriptor, registry)

    assert resolution.ref.identity == "stock_universe_equal_weight.v1"
    assert resolution.exact_strategy is None


def test_frozen_plan_binds_exact_snapshot_membership_and_registered_policy() -> None:
    registry = default_baseline_registry()
    resolution = resolve_planning_baseline(_etf_descriptor(), registry)

    plan = build_frozen_baseline_plan(
        resolution,
        registry=registry,
        snapshot=ExactResearchSnapshot("snapshot-1", "b" * 64),
        universe=ExactUniverseIdentity("csi-etf-broad", "c" * 64),
    )

    assert plan.snapshot.snapshot_id == "snapshot-1"
    assert plan.universe.membership_hash == "c" * 64
    assert plan.exact_strategy == resolution.exact_strategy
    assert len(plan.canonical_hash) == 64


@pytest.mark.parametrize(
    ("descriptor", "reason"),
    [
        (
            BaselineDescriptor(
                descriptor_type="etf-current-active",
                payload={"strategy_id": "seed", "version": 2},
            ),
            "invalid_etf_baseline_payload",
        ),
        (
            BaselineDescriptor(
                descriptor_type="stock-universe-equal-weight",
                payload={"strategy_id": "unexpected"},
            ),
            "invalid_stock_baseline_payload",
        ),
        (
            BaselineDescriptor(descriptor_type="buy-and-hold", payload={}),
            "unknown_planning_baseline_descriptor",
        ),
    ],
)
def test_planning_descriptor_fails_closed(
    descriptor: BaselineDescriptor,
    reason: str,
) -> None:
    with pytest.raises(AppProcessError) as captured:
        resolve_planning_baseline(descriptor, default_baseline_registry())

    assert captured.value.details["code"] in {
        "SPEC_INVALID",
        "EXECUTOR_UNAVAILABLE",
    }
    assert captured.value.details["reason"] == reason


def test_resolution_is_bound_to_the_registry_manifest_used_at_preflight() -> None:
    registry = default_baseline_registry()
    resolution = resolve_planning_baseline(_etf_descriptor(), registry)
    drifted = replace(resolution, registry_manifest_hash="d" * 64)

    with pytest.raises(AppProcessError) as captured:
        build_frozen_baseline_plan(
            drifted,
            registry=registry,
            snapshot=ExactResearchSnapshot("snapshot-1", "b" * 64),
            universe=ExactUniverseIdentity("csi-etf-broad", "c" * 64),
        )

    assert captured.value.details == {
        "code": "REPRODUCIBILITY_FAILED",
        "reason": "baseline_registry_manifest_drift",
    }
