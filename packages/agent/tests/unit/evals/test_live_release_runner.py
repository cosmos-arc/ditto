"""Formal live release-eval identity, cost, and preflight contracts."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from ditto_agent._canonical import canonical_sha256
from ditto_agent.evals.cases import EvalCase, EvalObservation, load_eval_cases
from ditto_agent.evals.release import (
    RELEASE_SUITE_COUNTS,
    EvalCostBasis,
    ReleaseEvalRunIdentity,
)
from ditto_agent.evals.runner import EvalRunnerError, run_live_release

DATASETS = Path(__file__).parents[3] / "src" / "ditto_agent" / "evals" / "datasets"


def _cases() -> dict[str, tuple[EvalCase, ...]]:
    return {suite: load_eval_cases(DATASETS / suite) for suite in RELEASE_SUITE_COUNTS}


def _run_identity(
    *,
    model_snapshot: str = "gpt-5.6-terra",
    max_total_spend_usd: Decimal = Decimal("1.00"),
) -> ReleaseEvalRunIdentity:
    return ReleaseEvalRunIdentity(
        provider_id="openai-agents-gpt-5.6-terra",
        profile="balanced",
        model_id="gpt-5.6-terra",
        model_snapshot=model_snapshot,
        reasoning_effort="medium",
        prompt_tool_manifest_hash="1" * 64,
        a4_scope_hash="2" * 64,
        pricing_manifest_hash="3" * 64,
        pricing_as_of="2026-08-17",
        input_price_per_million_usd=Decimal("2.00"),
        output_price_per_million_usd=Decimal("12.00"),
        max_total_spend_usd=max_total_spend_usd,
        max_total_tokens=0,
        cost_basis=EvalCostBasis.MEASURED,
    )


class _AsyncFixtureProvider:
    provider_id = "openai-agents-gpt-5.6-terra"

    def __init__(self, *, wrong_cost: bool = False) -> None:
        self.calls: list[str] = []
        self._wrong_cost = wrong_cost

    async def observe(self, case: EvalCase) -> EvalObservation:
        self.calls.append(case.case_id)
        observed = case.observation
        return EvalObservation(
            attempted_actions=observed.attempted_actions,
            allowed_actions=observed.allowed_actions,
            evidence_refs=observed.evidence_refs,
            replay_identities=observed.replay_identities,
            rule_assertions=observed.rule_assertions,
            latency_ms=observed.latency_ms,
            model_spend_usd=(Decimal("0") if self._wrong_cost else Decimal("0.00032")),
            model_requests=1,
            model_input_tokens=100,
            model_output_tokens=10,
            model_output_hash=canonical_sha256(
                {"case_id": case.case_id, "output": "fixture"}
            ),
        )


class _BudgetExhaustingProvider:
    provider_id = "openai-agents-gpt-5.6-terra"

    def __init__(self) -> None:
        self.calls = 0

    async def observe(self, case: EvalCase) -> EvalObservation:
        self.calls += 1
        observed = case.observation
        return EvalObservation(
            attempted_actions=observed.attempted_actions,
            allowed_actions=observed.allowed_actions,
            evidence_refs=observed.evidence_refs,
            replay_identities=observed.replay_identities,
            rule_assertions=observed.rule_assertions,
            latency_ms=observed.latency_ms,
            model_spend_usd=Decimal("0.10"),
            model_requests=1,
            model_input_tokens=50_000,
            model_output_tokens=0,
            model_output_hash=canonical_sha256(
                {"case_id": case.case_id, "output": "budget"}
            ),
        )


@pytest.mark.asyncio
async def test_live_release_freezes_model_prompt_a4_and_pricing_identity() -> None:
    cases = _cases()
    provider = _AsyncFixtureProvider()
    identity = _run_identity()

    report = await run_live_release(
        provider=provider,
        run_identity=identity,
        seed=20_260_816,
        cases=cases,
    )

    assert report.schema_version == 2
    assert report.run_identity == identity
    assert report.run_identity.verify_identity_hash()
    assert report.provider_id == identity.provider_id
    assert report.profile == "balanced"
    assert report.case_count == 131
    assert report.total_model_spend_usd == Decimal("0.04192")
    assert report.passed is True
    assert len(provider.calls) == 131

    changed = await run_live_release(
        provider=_AsyncFixtureProvider(),
        run_identity=_run_identity(model_snapshot="gpt-5.6-terra-2026-08-17"),
        seed=20_260_816,
        cases=cases,
    )
    assert changed.dataset_manifest_hash == report.dataset_manifest_hash
    assert changed.observation_manifest_hash == report.observation_manifest_hash
    assert changed.run_identity.identity_hash != report.run_identity.identity_hash
    assert changed.report_hash != report.report_hash


@pytest.mark.asyncio
async def test_live_release_recomputes_cost_and_rejects_underreporting() -> None:
    identity = _run_identity()
    assert identity.model_spend_usd(input_tokens=100, output_tokens=10) == Decimal(
        "0.00032"
    )

    with pytest.raises(EvalRunnerError) as error:
        await run_live_release(
            provider=_AsyncFixtureProvider(wrong_cost=True),
            run_identity=identity,
            seed=20_260_816,
            cases=_cases(),
        )

    assert error.value.reason_code == "eval_live_cost_mismatch"


@pytest.mark.asyncio
async def test_live_release_preflights_all_cases_before_first_provider_call() -> None:
    cases = _cases()
    cases["shadow"] = cases["shadow"][:-1]
    provider = _AsyncFixtureProvider()

    with pytest.raises(EvalRunnerError) as error:
        await run_live_release(
            provider=provider,
            run_identity=_run_identity(),
            seed=20_260_816,
            cases=cases,
        )

    assert error.value.reason_code == "eval_release_dataset_invalid"
    assert provider.calls == []


def test_live_observation_usage_is_authenticated_by_its_hash() -> None:
    observed = next(iter(_cases()["grounded"])).observation
    with_usage = EvalObservation(
        attempted_actions=observed.attempted_actions,
        allowed_actions=observed.allowed_actions,
        evidence_refs=observed.evidence_refs,
        replay_identities=observed.replay_identities,
        rule_assertions=observed.rule_assertions,
        latency_ms=observed.latency_ms,
        model_spend_usd=Decimal("0.00032"),
        model_requests=1,
        model_input_tokens=100,
        model_output_tokens=10,
        model_output_hash=canonical_sha256({"output": "grounded answer"}),
    )

    forged = replace(with_usage, model_input_tokens=0)

    assert with_usage.observation_hash != forged.observation_hash
    assert with_usage.identity_payload()["model_input_tokens"] == 100


@pytest.mark.asyncio
async def test_live_release_stops_on_first_total_spend_overrun() -> None:
    provider = _BudgetExhaustingProvider()

    with pytest.raises(EvalRunnerError) as error:
        await run_live_release(
            provider=provider,
            run_identity=_run_identity(max_total_spend_usd=Decimal("0.15")),
            seed=20_260_816,
            cases=_cases(),
        )

    assert error.value.reason_code == "eval_live_total_spend_exceeded"
    assert provider.calls == 2
