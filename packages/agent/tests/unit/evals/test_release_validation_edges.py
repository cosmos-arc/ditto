"""Fail-closed identity and SLO edges for aggregate Agent release evidence."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from ditto_agent.evals.cases import EvalObservation, load_eval_cases
from ditto_agent.evals.release import (
    RELEASE_SUITE_COUNTS,
    EvalCohortPerformance,
    EvalCostBasis,
    ReleaseEvalReport,
    ReleaseEvalRunIdentity,
    build_release_eval_report,
)
from ditto_agent.evals.report import EvalReport
from ditto_agent.evals.runner import FakeEvalProvider, LocalEvalRunner

DATASETS = Path(__file__).parents[3] / "src" / "ditto_agent" / "evals" / "datasets"


def _identity(
    *,
    cost_basis: EvalCostBasis = EvalCostBasis.FIXTURE,
    input_price: Decimal = Decimal(0),
    output_price: Decimal = Decimal(0),
    max_tokens: int = 0,
) -> ReleaseEvalRunIdentity:
    return ReleaseEvalRunIdentity(
        provider_id="provider",
        profile="profile",
        model_id="model",
        model_snapshot="model-v1",
        reasoning_effort="none",
        prompt_tool_manifest_hash="a" * 64,
        a4_scope_hash="b" * 64,
        pricing_manifest_hash="c" * 64,
        pricing_as_of="2026-09-04",
        input_price_per_million_usd=input_price,
        output_price_per_million_usd=output_price,
        max_total_spend_usd=Decimal("1"),
        max_total_tokens=max_tokens,
        cost_basis=cost_basis,
    )


def _observation(
    *,
    requests: int = 1,
    input_tokens: int = 100,
    output_tokens: int = 50,
    spend: Decimal = Decimal("0.0003"),
    output_hash: str | None = "d" * 64,
) -> EvalObservation:
    return EvalObservation(
        attempted_actions=("read_evidence",),
        allowed_actions=("read_evidence",),
        evidence_refs=("evidence://one",),
        replay_identities=("e" * 64,),
        rule_assertions={"grounded": True},
        latency_ms=10,
        model_spend_usd=spend,
        model_requests=requests,
        model_input_tokens=input_tokens,
        model_output_tokens=output_tokens,
        model_output_hash=output_hash,
    )


@pytest.fixture(scope="module")
def release_report() -> ReleaseEvalReport:
    cases = {suite: load_eval_cases(DATASETS / suite) for suite in RELEASE_SUITE_COUNTS}
    return LocalEvalRunner(provider=FakeEvalProvider()).run_release(
        seed=20_260_816,
        cases=cases,
        profile="fake",
    )


@pytest.mark.parametrize(
    ("cost_basis", "max_tokens", "message"),
    [
        (EvalCostBasis.USAGE_CAP, 0, "positive max_total_tokens"),
        (EvalCostBasis.FIXTURE, 1, "only valid for a usage cap"),
        (EvalCostBasis.MEASURED, -1, "non-negative integer"),
        (EvalCostBasis.MEASURED, True, "non-negative integer"),
    ],
)
def test_run_identity_rejects_ambiguous_token_budget_authority(
    cost_basis: EvalCostBasis,
    max_tokens: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _identity(
            cost_basis=cost_basis,
            input_price=Decimal("1"),
            max_tokens=max_tokens,
        )


@pytest.mark.parametrize(
    ("field_name", "value", "exception", "message"),
    [
        ("pricing_as_of", None, ValueError, "ISO calendar date"),
        ("pricing_as_of", "20260904", ValueError, "canonical ISO"),
        ("cost_basis", "fixture", TypeError, "EvalCostBasis"),
        ("input_price_per_million_usd", 1, TypeError, "must be Decimal"),
    ],
)
def test_run_identity_rejects_untyped_or_noncanonical_pricing_fields(
    field_name: str,
    value: object,
    exception: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception, match=message):
        replace(_identity(), **{field_name: value})


def test_measured_identity_requires_real_prices_and_authenticates_all_fields() -> None:
    with pytest.raises(ValueError, match="requires a non-zero token price"):
        _identity(cost_basis=EvalCostBasis.MEASURED)

    identity = _identity(
        cost_basis=EvalCostBasis.MEASURED,
        input_price=Decimal("2"),
        output_price=Decimal("4"),
    )
    assert identity.model_spend_usd(input_tokens=100, output_tokens=50) == Decimal(
        "0.0004"
    )
    assert identity.verify_identity_hash()
    object.__setattr__(identity, "model_snapshot", "tampered")
    assert not identity.verify_identity_hash()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("input_tokens", -1),
        ("input_tokens", True),
        ("output_tokens", -1),
        ("output_tokens", True),
    ],
)
def test_model_spend_rejects_ambiguous_token_counts(
    field_name: str,
    value: int,
) -> None:
    identity = _identity(
        cost_basis=EvalCostBasis.MEASURED,
        input_price=Decimal("2"),
        output_price=Decimal("4"),
    )
    inputs = {"input_tokens": 1, "output_tokens": 1, field_name: value}
    with pytest.raises(ValueError, match="non-negative integer"):
        identity.model_spend_usd(**inputs)


def test_measured_observations_require_usage_hash_and_frozen_price_match() -> None:
    identity = _identity(
        cost_basis=EvalCostBasis.MEASURED,
        input_price=Decimal("2"),
        output_price=Decimal("4"),
    )
    identity.validate_observations((_observation(spend=Decimal("0.0004")),))

    with pytest.raises(ValueError, match="lacks model usage"):
        identity.validate_observations((_observation(requests=0),))
    with pytest.raises(ValueError, match="lacks model usage"):
        identity.validate_observations((_observation(input_tokens=0, output_tokens=0),))
    with pytest.raises(ValueError, match="lacks model output hash"):
        identity.validate_observations((_observation(output_hash=None),))
    with pytest.raises(ValueError, match="differs from frozen pricing"):
        identity.validate_observations((_observation(spend=Decimal("0.01")),))


def _performance() -> EvalCohortPerformance:
    return EvalCohortPerformance(
        cohort="read",
        suites=("grounded",),
        case_count=2,
        latency_p50_ms=10,
        latency_p95_ms=20,
        spend_p50_usd=Decimal("0.1"),
        spend_p95_usd=Decimal("0.2"),
        max_spend_usd=Decimal("0.3"),
        latency_limit_ms=30,
        spend_limit_usd=Decimal("0.4"),
    )


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("suites", (), "non-empty and unique"),
        ("suites", ("grounded", "grounded"), "non-empty and unique"),
        ("case_count", -1, "non-negative integer"),
        ("latency_p50_ms", True, "non-negative integer"),
        ("case_count", 0, "requires cases"),
        ("latency_limit_ms", 0, "positive latency limit"),
        ("latency_p50_ms", 21, "latency percentiles"),
        ("spend_p50_usd", Decimal("0.25"), "spend percentiles"),
        ("spend_p95_usd", Decimal("0.35"), "spend percentiles"),
    ],
)
def test_cohort_performance_rejects_ambiguous_slo_evidence(
    field_name: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_performance(), **{field_name: value})


def test_cohort_verdict_is_derived_from_both_latency_and_spend_limits() -> None:
    passing = _performance()
    latency_failure = replace(passing, latency_limit_ms=19)
    spend_failure = replace(passing, spend_limit_usd=Decimal("0.29"))

    assert passing.passed
    assert not latency_failure.passed
    assert not spend_failure.passed


def test_release_builder_rejects_incomplete_suite_sets_and_count_drift() -> None:
    with pytest.raises(ValueError, match="exact six-suite set"):
        build_release_eval_report(
            run_identity=_identity(),
            seed=1,
            reports={},
            cases={},
            observations={},
        )

    cases = dict.fromkeys(RELEASE_SUITE_COUNTS, ())
    observations = dict.fromkeys(RELEASE_SUITE_COUNTS, ())
    observations["grounded"] = (_observation(),)
    reports = cast(
        "dict[str, EvalReport]",
        dict.fromkeys(RELEASE_SUITE_COUNTS, object()),
    )
    with pytest.raises(ValueError, match="counts differ"):
        build_release_eval_report(
            run_identity=_identity(),
            seed=1,
            reports=reports,
            cases=cases,
            observations=observations,
        )


def test_release_report_rejects_top_level_identity_and_report_set_drift(
    release_report: ReleaseEvalReport,
) -> None:
    with pytest.raises(ValueError, match="schema_version"):
        replace(release_report, schema_version=1)
    with pytest.raises(ValueError, match="seed must be non-negative"):
        replace(release_report, seed=True)
    with pytest.raises(ValueError, match="exact six-suite set"):
        replace(release_report, suite_reports=release_report.suite_reports[:-1])

    bad_identity = replace(release_report.run_identity)
    object.__setattr__(bad_identity, "identity_hash", "0" * 64)
    with pytest.raises(ValueError, match="run identity is invalid"):
        replace(release_report, run_identity=bad_identity)

    first = release_report.suite_reports[0]
    wrong_seed = replace(first, seed=first.seed + 1)
    reports = (wrong_seed, *release_report.suite_reports[1:])
    with pytest.raises(ValueError, match="suite seeds differ"):
        replace(release_report, suite_reports=reports)

    wrong_provider = replace(first, provider_id="other-provider")
    reports = (wrong_provider, *release_report.suite_reports[1:])
    with pytest.raises(ValueError, match="provider identities differ"):
        replace(release_report, suite_reports=reports)


@pytest.mark.parametrize(
    "mutation",
    [
        "manifest_not_tuple",
        "suite_not_mapping",
        "suite_fields",
        "suite_values",
        "suite_unsupported",
        "case_not_mapping",
        "case_fields",
        "case_identity",
        "case_mismatch",
        "suite_order",
    ],
)
def test_release_dataset_manifest_rejects_shape_identity_and_order_drift(
    release_report: ReleaseEvalReport,
    mutation: str,
) -> None:
    manifest = [dict(item) for item in release_report.dataset_manifest]
    if mutation == "manifest_not_tuple":
        candidate: object = {"suite": "invalid"}
    elif mutation == "suite_not_mapping":
        manifest[0] = cast("dict[str, object]", "invalid")
        candidate = tuple(manifest)
    elif mutation == "suite_fields":
        manifest[0]["unexpected"] = True
        candidate = tuple(manifest)
    elif mutation == "suite_values":
        manifest[0]["cases"] = "invalid"
        candidate = tuple(manifest)
    elif mutation == "suite_unsupported":
        manifest[0]["suite"] = "invalid"
        candidate = tuple(manifest)
    else:
        cases = list(cast("tuple[object, ...]", manifest[0]["cases"]))
        if mutation == "case_not_mapping":
            cases[0] = "invalid"
        else:
            case = dict(cast("dict[str, object]", cases[0]))
            if mutation == "case_fields":
                case["unexpected"] = True
            elif mutation == "case_identity":
                case["schema_version"] = 999
            elif mutation == "case_mismatch":
                case["case_id"] = "different-case"
            cases[0] = case
        manifest[0]["cases"] = tuple(cases)
        if mutation == "suite_order":
            manifest.reverse()
        candidate = tuple(manifest)

    with pytest.raises(ValueError):
        replace(
            release_report,
            dataset_manifest=cast(
                "tuple[dict[str, object], ...]",
                candidate,
            ),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "manifest_not_tuple",
        "row_not_mapping",
        "row_fields",
        "suite_unsupported",
        "payload_not_mapping",
        "payload_fields",
        "assertions_not_mapping",
        "text_not_tuple",
        "hash_mismatch",
        "row_identity_mismatch",
    ],
)
def test_release_observation_manifest_rejects_shape_and_identity_drift(
    release_report: ReleaseEvalReport,
    mutation: str,
) -> None:
    manifest = [dict(item) for item in release_report.observation_manifest]
    if mutation == "manifest_not_tuple":
        candidate: object = {"suite": "invalid"}
    elif mutation == "row_not_mapping":
        manifest[0] = cast("dict[str, object]", "invalid")
        candidate = tuple(manifest)
    else:
        row = manifest[0]
        if mutation == "row_fields":
            row["unexpected"] = True
        elif mutation == "suite_unsupported":
            row["suite"] = "invalid"
        elif mutation == "payload_not_mapping":
            row["observation"] = "invalid"
        else:
            payload = dict(cast("dict[str, object]", row["observation"]))
            if mutation == "payload_fields":
                payload["unexpected"] = True
            elif mutation == "assertions_not_mapping":
                payload["rule_assertions"] = "invalid"
            elif mutation == "text_not_tuple":
                payload["attempted_actions"] = "invalid"
            elif mutation == "hash_mismatch":
                payload["latency_ms"] = cast(int, payload["latency_ms"]) + 1
            else:
                row["case_id"] = "different-case"
            row["observation"] = payload
        candidate = tuple(manifest)

    with pytest.raises(ValueError):
        replace(
            release_report,
            observation_manifest=cast(
                "tuple[dict[str, object], ...]",
                candidate,
            ),
        )


def test_release_report_rejects_missing_performance_cohort_and_hash_drift(
    release_report: ReleaseEvalReport,
) -> None:
    with pytest.raises(ValueError, match="read and complex"):
        replace(release_report, performance=release_report.performance[:1])

    tampered = replace(release_report)
    object.__setattr__(tampered, "report_hash", "0" * 64)
    with pytest.raises(ValueError, match="report hash is invalid"):
        tampered.to_bytes()
