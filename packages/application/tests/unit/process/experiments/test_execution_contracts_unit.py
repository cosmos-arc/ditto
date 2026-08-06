"""Unit tests for frozen research baseline execution identities and policies."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest
from ditto_application.exceptions import AppProcessError


def test_exact_execution_identities_are_frozen_and_canonical() -> None:
    from ditto_application.processes.experiments.execution_contracts import (
        ExactResearchSnapshot,
        ExactStrategyIdentity,
        ExactUniverseIdentity,
    )

    strategy = ExactStrategyIdentity(
        strategy_id="r1_etf_rotation",
        version=7,
        spec_hash="a" * 64,
    )
    snapshot = ExactResearchSnapshot(
        snapshot_id="research-snapshot-2026-07-19",
        manifest_hash="b" * 64,
    )
    universe = ExactUniverseIdentity(
        universe_id="a-share-pit",
        membership_hash="c" * 64,
    )

    assert strategy.identity == "r1_etf_rotation@7"
    assert len(strategy.canonical_hash) == 64
    assert len(snapshot.canonical_hash) == 64
    assert len(universe.canonical_hash) == 64
    with pytest.raises(FrozenInstanceError):
        strategy.version = 8  # type: ignore[misc]


@pytest.mark.parametrize(
    ("factory", "reason"),
    [
        (
            lambda: __import__(
                "ditto_application.processes.experiments.execution_contracts",
                fromlist=["ExactStrategyIdentity"],
            ).ExactStrategyIdentity("strategy", 0, "a" * 64),
            "invalid_exact_strategy_version",
        ),
        (
            lambda: __import__(
                "ditto_application.processes.experiments.execution_contracts",
                fromlist=["ExactResearchSnapshot"],
            ).ExactResearchSnapshot("snapshot", "A" * 64),
            "invalid_content_hash",
        ),
        (
            lambda: __import__(
                "ditto_application.processes.experiments.execution_contracts",
                fromlist=["ExactUniverseIdentity"],
            ).ExactUniverseIdentity(" universe", "c" * 64),
            "invalid_canonical_identity",
        ),
    ],
)
def test_exact_execution_identities_fail_closed(
    factory: object,
    reason: str,
) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        factory()  # type: ignore[operator]

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == reason


def test_default_execution_policies_bind_pit_rules_fees_and_settlement() -> None:
    from ditto_application.processes.experiments.execution_contracts import (
        EvidenceSource,
        MissingExecutionEvidenceAction,
        ResearchAssetLane,
        default_etf_execution_policy,
        default_stock_execution_policy,
    )

    stock = default_stock_execution_policy()
    etf = default_etf_execution_policy()

    assert stock.identity == "a_share_stock_daily.v1"
    assert stock.lane is ResearchAssetLane.STOCK
    assert etf.identity == "a_share_etf_daily.v1"
    assert etf.lane is ResearchAssetLane.ETF
    for policy in (stock, etf):
        assert policy.rules.instrument_definition_source is EvidenceSource.FROZEN_PIT
        assert policy.rules.trading_rule_source is EvidenceSource.FROZEN_PIT
        assert policy.rules.fee_schedule_source is EvidenceSource.FROZEN_PIT
        assert (
            policy.rules.missing_evidence_action
            is MissingExecutionEvidenceAction.FAIL_CLOSED
        )
        assert policy.settlement.cycle_source is EvidenceSource.FROZEN_PIT
        assert policy.fees.schedule_source is EvidenceSource.FROZEN_PIT
        assert policy.slippage.basis_points == 1
        assert len(policy.canonical_hash) == 64
    assert stock.canonical_hash != etf.canonical_hash


def test_execution_policy_hash_covers_every_semantic_contract() -> None:
    from ditto_application.processes.experiments.execution_contracts import (
        default_stock_execution_policy,
    )

    source = default_stock_execution_policy()
    mutations = (
        replace(source, version=2),
        replace(source, settlement=replace(source.settlement, model_version=2)),
        replace(source, fees=replace(source.fees, model_version=2)),
        replace(source, rules=replace(source.rules, contract_version=2)),
        replace(
            source,
            slippage=replace(source.slippage, basis_points=2),
        ),
    )

    assert all(item.canonical_hash != source.canonical_hash for item in mutations)


def test_execution_policy_rejects_non_typed_or_non_fail_closed_semantics() -> None:
    from ditto_application.processes.experiments.execution_contracts import (
        MissingExecutionEvidenceAction,
        default_stock_execution_policy,
    )

    source = default_stock_execution_policy()
    with pytest.raises(AppProcessError) as exc_info:
        replace(
            source,
            rules=replace(
                source.rules,
                missing_evidence_action=MissingExecutionEvidenceAction.FALLBACK,
            ),
        )

    assert exc_info.value.details == {
        "code": "REPRODUCIBILITY_FAILED",
        "reason": "execution_evidence_fallback_forbidden",
    }
