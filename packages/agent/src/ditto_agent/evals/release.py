"""Content-addressed aggregate release report for the six R5 eval suites."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import cast

from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts._validation import (
    freeze_json,
    nonnegative_decimal,
    normalized_text,
    sha256_hex,
)
from ditto_agent.evals._statistics import nearest_decimal, nearest_rank
from ditto_agent.evals.cases import EvalCase, EvalObservation
from ditto_agent.evals.manifest import release_dataset_manifest
from ditto_agent.evals.report import EvalReport

RELEASE_SUITE_COUNTS: Mapping[str, int] = MappingProxyType(
    {
        "author": 20,
        "campaign": 30,
        "grounded": 41,
        "permission": 20,
        "sandbox": 10,
        "shadow": 10,
    }
)
_READ_SUITES = ("grounded",)
_COMPLEX_SUITES = ("author", "permission", "sandbox", "shadow")
_RELEASE_CASE_COUNT = sum(RELEASE_SUITE_COUNTS.values())
_RELEASE_SCHEMA_VERSION = 2
_SCHEMA_BY_SUITE = MappingProxyType(
    {
        "author": 3,
        "campaign": 4,
        "grounded": 2,
        "permission": 3,
        "sandbox": 4,
        "shadow": 5,
    }
)


class EvalCostBasis(StrEnum):
    """Authority used to derive per-case model spend."""

    FIXTURE = "fixture"
    MEASURED = "token_usage"
    USAGE_CAP = "usage_cap"


@dataclass(frozen=True, slots=True)
class ReleaseEvalRunIdentity:
    """Immutable model, prompt/tool, approval, pricing, and budget identity."""

    provider_id: str
    profile: str
    model_id: str
    model_snapshot: str
    reasoning_effort: str
    prompt_tool_manifest_hash: str
    a4_scope_hash: str
    pricing_manifest_hash: str
    pricing_as_of: str
    input_price_per_million_usd: Decimal
    output_price_per_million_usd: Decimal
    max_total_spend_usd: Decimal
    max_total_tokens: int
    cost_basis: EvalCostBasis
    identity_hash: str = field(init=False)

    def _validate_token_budget(self) -> None:
        value = cast(object, self.max_total_tokens)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("max_total_tokens must be a non-negative integer")
        if self.cost_basis is EvalCostBasis.USAGE_CAP:
            if self.max_total_tokens == 0:
                raise ValueError("usage cap requires a positive max_total_tokens")
        elif self.max_total_tokens != 0:
            raise ValueError("max_total_tokens is only valid for a usage cap")

    def __post_init__(self) -> None:
        """Normalize every release-sensitive field and derive its identity."""
        for name in (
            "provider_id",
            "profile",
            "model_id",
            "model_snapshot",
            "reasoning_effort",
        ):
            object.__setattr__(
                self,
                name,
                normalized_text(getattr(self, name), field=f"eval run {name}"),
            )
        for name in (
            "prompt_tool_manifest_hash",
            "a4_scope_hash",
            "pricing_manifest_hash",
        ):
            object.__setattr__(
                self,
                name,
                sha256_hex(getattr(self, name), field=f"eval run {name}"),
            )
        try:
            parsed_pricing_date = date.fromisoformat(self.pricing_as_of)
        except (TypeError, ValueError) as exc:
            raise ValueError("pricing_as_of must be an ISO calendar date") from exc
        if parsed_pricing_date.isoformat() != self.pricing_as_of:
            raise ValueError("pricing_as_of must be a canonical ISO calendar date")
        if not isinstance(cast(object, self.cost_basis), EvalCostBasis):
            raise TypeError("cost_basis must be an EvalCostBasis")
        for name in (
            "input_price_per_million_usd",
            "output_price_per_million_usd",
            "max_total_spend_usd",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be Decimal")
            nonnegative_decimal(value, field=name)
        if (
            self.cost_basis is EvalCostBasis.MEASURED
            and self.input_price_per_million_usd == 0
            and self.output_price_per_million_usd == 0
        ):
            raise ValueError("token-usage pricing requires a non-zero token price")
        self._validate_token_budget()
        object.__setattr__(
            self, "identity_hash", canonical_sha256(self.identity_payload())
        )

    @classmethod
    def fixture(
        cls,
        *,
        provider_id: str,
        profile: str,
        max_total_spend_usd: Decimal = Decimal("1"),
    ) -> ReleaseEvalRunIdentity:
        """Create an explicit non-live identity for authenticated fixture costs."""
        return cls(
            provider_id=provider_id,
            profile=profile,
            model_id="fixture-observation",
            model_snapshot="fixture-observation-v1",
            reasoning_effort="none",
            prompt_tool_manifest_hash=canonical_sha256(
                {"kind": "fixture", "version": 1, "surface": "release-eval"}
            ),
            a4_scope_hash=canonical_sha256(
                {"approval": "not-applicable", "network_egress": False}
            ),
            pricing_manifest_hash=canonical_sha256(
                {"cost_basis": EvalCostBasis.FIXTURE, "version": 1}
            ),
            pricing_as_of="1970-01-01",
            input_price_per_million_usd=Decimal(0),
            output_price_per_million_usd=Decimal(0),
            max_total_spend_usd=max_total_spend_usd,
            max_total_tokens=0,
            cost_basis=EvalCostBasis.FIXTURE,
        )

    def model_spend_usd(self, *, input_tokens: int, output_tokens: int) -> Decimal:
        """Return conservative uncached-input token spend under frozen prices."""
        for name, value in (
            ("input_tokens", input_tokens),
            ("output_tokens", output_tokens),
        ):
            raw_value = cast(object, value)
            if (
                isinstance(raw_value, bool)
                or not isinstance(raw_value, int)
                or raw_value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer")
        return (
            Decimal(input_tokens) * self.input_price_per_million_usd
            + Decimal(output_tokens) * self.output_price_per_million_usd
        ) / Decimal(1_000_000)

    def validate_observations(
        self,
        observations: tuple[EvalObservation, ...],
    ) -> None:
        """Reject unauthenticated live usage, price drift, or token-cap overrun."""
        if self.cost_basis is EvalCostBasis.FIXTURE:
            return
        total_tokens = 0
        for observation in observations:
            model_tokens = (
                observation.model_input_tokens + observation.model_output_tokens
            )
            if observation.model_requests <= 0 or model_tokens <= 0:
                raise ValueError("live release observation lacks model usage")
            if observation.model_output_hash is None:
                raise ValueError("live release observation lacks model output hash")
            total_tokens += model_tokens
            if self.cost_basis is EvalCostBasis.MEASURED and (
                observation.model_spend_usd
                != self.model_spend_usd(
                    input_tokens=observation.model_input_tokens,
                    output_tokens=observation.model_output_tokens,
                )
            ):
                raise ValueError("release observation cost differs from frozen pricing")
        if self.cost_basis is EvalCostBasis.USAGE_CAP and (
            total_tokens > self.max_total_tokens
        ):
            raise ValueError("release eval exceeds authenticated token cap")

    def identity_payload(self) -> dict[str, object]:
        """Return every field that invalidates inherited release evidence."""
        return {
            "provider_id": self.provider_id,
            "profile": self.profile,
            "model_id": self.model_id,
            "model_snapshot": self.model_snapshot,
            "reasoning_effort": self.reasoning_effort,
            "prompt_tool_manifest_hash": self.prompt_tool_manifest_hash,
            "a4_scope_hash": self.a4_scope_hash,
            "pricing_manifest_hash": self.pricing_manifest_hash,
            "pricing_as_of": self.pricing_as_of,
            "input_price_per_million_usd": self.input_price_per_million_usd,
            "output_price_per_million_usd": self.output_price_per_million_usd,
            "max_total_spend_usd": self.max_total_spend_usd,
            "max_total_tokens": self.max_total_tokens,
            "cost_basis": self.cost_basis,
        }

    def verify_identity_hash(self) -> bool:
        """Recompute the complete run identity."""
        return self.identity_hash == canonical_sha256(self.identity_payload())


def _validated_reports(
    reports: tuple[EvalReport, ...],
    *,
    provider_id: str,
    seed: int,
) -> tuple[EvalReport, ...]:
    ordered = tuple(sorted(reports, key=lambda item: item.suite))
    suite_ids = tuple(item.suite for item in ordered)
    if set(suite_ids) != set(RELEASE_SUITE_COUNTS) or len(suite_ids) != len(
        set(suite_ids)
    ):
        raise ValueError("release eval requires the exact six-suite set")
    if any(item.seed != seed for item in ordered):
        raise ValueError("release eval suite seeds differ")
    if any(item.provider_id != provider_id for item in ordered):
        raise ValueError("release eval provider identities differ")
    return ordered


def _case_manifest_identity(
    case_item: object,
    *,
    suite_name: str,
) -> tuple[str, str, str]:
    if not isinstance(case_item, Mapping):
        raise ValueError("release eval case manifest is invalid")
    case_manifest = cast(Mapping[str, object], case_item)
    if set(case_manifest) != {
        "case_id",
        "schema_version",
        "input_hash",
        "case_hash",
    }:
        raise ValueError("release eval case manifest fields are invalid")
    case_id = case_manifest["case_id"]
    input_hash = case_manifest["input_hash"]
    case_hash = case_manifest["case_hash"]
    if (
        not isinstance(case_id, str)
        or not isinstance(input_hash, str)
        or not isinstance(case_hash, str)
        or case_manifest["schema_version"] != _SCHEMA_BY_SUITE[suite_name]
    ):
        raise ValueError("release eval case identity is invalid")
    return (
        normalized_text(case_id, field="eval case_id"),
        sha256_hex(input_hash, field="eval input_hash"),
        sha256_hex(case_hash, field="eval case_hash"),
    )


def _suite_manifest_name(
    suite_item: object,
    *,
    reports: Mapping[str, EvalReport],
) -> str:
    if not isinstance(suite_item, Mapping):
        raise ValueError("release eval dataset suite manifest is invalid")
    suite_manifest = cast(Mapping[str, object], suite_item)
    if set(suite_manifest) != {"suite", "cases"}:
        raise ValueError("release eval dataset suite fields are invalid")
    suite_value = suite_manifest["suite"]
    case_items = suite_manifest["cases"]
    if not isinstance(suite_value, str) or not isinstance(case_items, tuple):
        raise ValueError("release eval dataset suite values are invalid")
    suite_name = normalized_text(suite_value, field="dataset suite")
    if suite_name not in RELEASE_SUITE_COUNTS:
        raise ValueError("release eval dataset suite is unsupported")
    raw_case_items = cast(tuple[object, ...], case_items)
    case_identities = tuple(
        _case_manifest_identity(item, suite_name=suite_name) for item in raw_case_items
    )
    report_identities = tuple(
        (item.case_id, item.input_hash, item.case_hash)
        for item in reports[suite_name].results
    )
    if case_identities != report_identities:
        raise ValueError("release eval dataset manifest differs from results")
    return suite_name


def _validated_dataset_manifest(
    manifest: tuple[Mapping[str, object], ...],
    *,
    reports: Mapping[str, EvalReport],
) -> tuple[Mapping[str, object], ...]:
    frozen = freeze_json(manifest, field="release eval dataset manifest")
    if not isinstance(frozen, tuple):
        raise ValueError("release eval dataset manifest must be a tuple")
    raw_manifest = cast(tuple[object, ...], frozen)
    suite_names = tuple(
        _suite_manifest_name(item, reports=reports) for item in raw_manifest
    )
    if suite_names != tuple(sorted(RELEASE_SUITE_COUNTS)):
        raise ValueError("release eval dataset manifest suite order is invalid")
    return cast(tuple[Mapping[str, object], ...], raw_manifest)


def _validated_performance(
    performance: tuple[EvalCohortPerformance, ...],
    *,
    observations: Mapping[str, tuple[EvalObservation, ...]],
) -> tuple[EvalCohortPerformance, ...]:
    ordered = tuple(sorted(performance, key=lambda item: item.cohort))
    if {item.cohort for item in ordered} != {"read", "complex"}:
        raise ValueError("release eval requires read and complex SLO cohorts")
    expected = tuple(
        sorted(_cohort_performance(observations), key=lambda item: item.cohort)
    )
    if tuple(item.identity_payload() for item in ordered) != tuple(
        item.identity_payload() for item in expected
    ):
        raise ValueError("release eval performance evidence is inconsistent")
    return ordered


def _text_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"release eval {field} must be a tuple")
    raw_values = cast(tuple[object, ...], value)
    return tuple(normalized_text(cast(str, item), field=field) for item in raw_values)


def _observation_from_payload(payload: object) -> EvalObservation:
    if not isinstance(payload, Mapping):
        raise ValueError("release eval observation payload is invalid")
    values = cast(Mapping[str, object], payload)
    expected = {
        "attempted_actions",
        "allowed_actions",
        "evidence_refs",
        "replay_identities",
        "rule_assertions",
        "latency_ms",
        "model_spend_usd",
        "model_requests",
        "model_input_tokens",
        "model_output_tokens",
    }
    if set(values) not in (expected, expected | {"model_output_hash"}):
        raise ValueError("release eval observation payload fields are invalid")
    assertions = values["rule_assertions"]
    if not isinstance(assertions, Mapping):
        raise ValueError("release eval observation rule assertions are invalid")
    return EvalObservation(
        attempted_actions=_text_tuple(
            values["attempted_actions"], field="attempted action"
        ),
        allowed_actions=_text_tuple(values["allowed_actions"], field="allowed action"),
        evidence_refs=_text_tuple(values["evidence_refs"], field="evidence ref"),
        replay_identities=_text_tuple(
            values["replay_identities"], field="replay identity"
        ),
        rule_assertions=cast(Mapping[str, bool], assertions),
        latency_ms=cast(int, values["latency_ms"]),
        model_spend_usd=cast(Decimal, values["model_spend_usd"]),
        model_requests=cast(int, values["model_requests"]),
        model_input_tokens=cast(int, values["model_input_tokens"]),
        model_output_tokens=cast(int, values["model_output_tokens"]),
        model_output_hash=cast(str | None, values.get("model_output_hash")),
    )


def _validated_observation_manifest(
    manifest: tuple[Mapping[str, object], ...],
    *,
    reports: Mapping[str, EvalReport],
) -> tuple[
    tuple[Mapping[str, object], ...],
    Mapping[str, tuple[EvalObservation, ...]],
]:
    frozen = freeze_json(manifest, field="release eval observation manifest")
    if not isinstance(frozen, tuple):
        raise ValueError("release eval observation manifest must be a tuple")
    rows = cast(tuple[object, ...], frozen)
    actual_identities: list[tuple[str, str, str]] = []
    observations: dict[str, list[EvalObservation]] = {
        suite: [] for suite in RELEASE_SUITE_COUNTS
    }
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("release eval observation manifest row is invalid")
        values = cast(Mapping[str, object], row)
        if set(values) != {
            "suite",
            "case_id",
            "observation_hash",
            "observation",
        }:
            raise ValueError("release eval observation manifest fields are invalid")
        suite = normalized_text(cast(str, values["suite"]), field="suite")
        if suite not in RELEASE_SUITE_COUNTS:
            raise ValueError("release eval observation suite is unsupported")
        case_id = normalized_text(
            cast(str, values["case_id"]), field="observation case_id"
        )
        observation_hash = sha256_hex(
            cast(str, values["observation_hash"]), field="observation_hash"
        )
        observation = _observation_from_payload(values["observation"])
        if observation.observation_hash != observation_hash:
            raise ValueError("release eval observation hash is invalid")
        actual_identities.append((suite, case_id, observation_hash))
        observations[suite].append(observation)
    expected_identities = tuple(
        (suite, result.case_id, result.observation_hash)
        for suite in sorted(RELEASE_SUITE_COUNTS)
        for result in reports[suite].results
    )
    if tuple(actual_identities) != expected_identities:
        raise ValueError("release eval observations differ from suite results")
    return (
        cast(tuple[Mapping[str, object], ...], rows),
        MappingProxyType(
            {suite: tuple(items) for suite, items in observations.items()}
        ),
    )


def _cohort_performance(
    observations: Mapping[str, tuple[EvalObservation, ...]],
) -> tuple[EvalCohortPerformance, ...]:
    read_observations = tuple(
        item for suite in _READ_SUITES for item in observations[suite]
    )
    complex_observations = tuple(
        item for suite in _COMPLEX_SUITES for item in observations[suite]
    )
    return (
        EvalCohortPerformance.from_observations(
            cohort="read",
            suites=_READ_SUITES,
            observations=read_observations,
            latency_limit_ms=30_000,
            spend_limit_usd=Decimal("0.25"),
        ),
        EvalCohortPerformance.from_observations(
            cohort="complex",
            suites=_COMPLEX_SUITES,
            observations=complex_observations,
            latency_limit_ms=60_000,
            spend_limit_usd=Decimal("0.75"),
        ),
    )


@dataclass(frozen=True, slots=True)
class EvalCohortPerformance:
    """Exact P50/P95/cost envelope for one interaction-budget cohort."""

    cohort: str
    suites: tuple[str, ...]
    case_count: int
    latency_p50_ms: int
    latency_p95_ms: int
    spend_p50_usd: Decimal
    spend_p95_usd: Decimal
    max_spend_usd: Decimal
    latency_limit_ms: int
    spend_limit_usd: Decimal
    passed: bool = field(init=False)

    def __post_init__(self) -> None:
        """Validate observations and derive the immutable SLO verdict."""
        object.__setattr__(
            self,
            "cohort",
            normalized_text(self.cohort, field="eval cohort"),
        )
        if not self.suites or len(self.suites) != len(set(self.suites)):
            raise ValueError("eval cohort suites must be non-empty and unique")
        for suite in self.suites:
            normalized_text(suite, field="eval cohort suite")
        for name in (
            "case_count",
            "latency_p50_ms",
            "latency_p95_ms",
            "latency_limit_ms",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.case_count == 0 or self.latency_limit_ms == 0:
            raise ValueError("eval cohort requires cases and a positive latency limit")
        if self.latency_p50_ms > self.latency_p95_ms:
            raise ValueError("eval cohort latency percentiles are inconsistent")
        for name in ("spend_p50_usd", "spend_p95_usd", "max_spend_usd"):
            nonnegative_decimal(getattr(self, name), field=name)
        nonnegative_decimal(self.spend_limit_usd, field="spend_limit_usd")
        if not self.spend_p50_usd <= self.spend_p95_usd <= self.max_spend_usd:
            raise ValueError("eval cohort spend percentiles are inconsistent")
        object.__setattr__(
            self,
            "passed",
            self.latency_p95_ms <= self.latency_limit_ms
            and self.max_spend_usd <= self.spend_limit_usd,
        )

    @classmethod
    def from_observations(
        cls,
        *,
        cohort: str,
        suites: tuple[str, ...],
        observations: tuple[EvalObservation, ...],
        latency_limit_ms: int,
        spend_limit_usd: Decimal,
    ) -> EvalCohortPerformance:
        """Compute deterministic nearest-rank percentiles from provider facts."""
        latencies = tuple(item.latency_ms for item in observations)
        spends = tuple(item.model_spend_usd for item in observations)
        return cls(
            cohort=cohort,
            suites=suites,
            case_count=len(observations),
            latency_p50_ms=nearest_rank(latencies, 50),
            latency_p95_ms=nearest_rank(latencies, 95),
            spend_p50_usd=nearest_decimal(spends, 50),
            spend_p95_usd=nearest_decimal(spends, 95),
            max_spend_usd=max(spends, default=Decimal(0)),
            latency_limit_ms=latency_limit_ms,
            spend_limit_usd=spend_limit_usd,
        )

    def identity_payload(self) -> dict[str, object]:
        """Return every measurement, threshold, and derived verdict."""
        return {
            "cohort": self.cohort,
            "suites": self.suites,
            "case_count": self.case_count,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p95_ms": self.latency_p95_ms,
            "spend_p50_usd": self.spend_p50_usd,
            "spend_p95_usd": self.spend_p95_usd,
            "max_spend_usd": self.max_spend_usd,
            "latency_limit_ms": self.latency_limit_ms,
            "spend_limit_usd": self.spend_limit_usd,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class ReleaseEvalReport:
    """Frozen release dataset/grader identity and all release hard gates."""

    run_identity: ReleaseEvalRunIdentity
    seed: int
    dataset_manifest: tuple[Mapping[str, object], ...]
    observation_manifest: tuple[Mapping[str, object], ...]
    grader_manifest_hash: str
    suite_reports: tuple[EvalReport, ...]
    performance: tuple[EvalCohortPerformance, ...]
    schema_version: int = _RELEASE_SCHEMA_VERSION
    suite: str = field(init=False, default="all")
    case_count: int = field(init=False)
    suite_case_counts: Mapping[str, int] = field(init=False)
    dataset_manifest_hash: str = field(init=False)
    observation_manifest_hash: str = field(init=False)
    total_model_spend_usd: Decimal = field(init=False)
    passed: bool = field(init=False)
    report_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Require the closed suite set and authenticate every aggregate field."""
        if self.schema_version != _RELEASE_SCHEMA_VERSION:
            raise ValueError("release eval schema_version is not supported")
        if not isinstance(
            cast(object, self.run_identity), ReleaseEvalRunIdentity
        ) or not (self.run_identity.verify_identity_hash()):
            raise ValueError("release eval run identity is invalid")
        if isinstance(self.seed, bool) or self.seed < 0:
            raise ValueError("release eval seed must be non-negative")
        supplied_grader_hash = sha256_hex(
            self.grader_manifest_hash, field="grader_manifest_hash"
        )
        reports = _validated_reports(
            self.suite_reports,
            provider_id=self.provider_id,
            seed=self.seed,
        )
        object.__setattr__(self, "suite_reports", reports)
        reports_by_suite = {item.suite: item for item in reports}
        expected_grader_hash = canonical_sha256(
            tuple(
                (suite, reports_by_suite[suite].grader_manifest_hash)
                for suite in sorted(reports_by_suite)
            )
        )
        if supplied_grader_hash != expected_grader_hash:
            raise ValueError("release eval grader manifest hash is inconsistent")
        object.__setattr__(self, "grader_manifest_hash", expected_grader_hash)
        counts = MappingProxyType({item.suite: item.case_count for item in reports})
        object.__setattr__(self, "suite_case_counts", counts)
        object.__setattr__(self, "case_count", sum(counts.values()))
        manifest = _validated_dataset_manifest(
            self.dataset_manifest,
            reports=reports_by_suite,
        )
        object.__setattr__(self, "dataset_manifest", manifest)
        object.__setattr__(self, "dataset_manifest_hash", canonical_sha256(manifest))
        observation_manifest, observations = _validated_observation_manifest(
            self.observation_manifest,
            reports=reports_by_suite,
        )
        object.__setattr__(self, "observation_manifest", observation_manifest)
        object.__setattr__(
            self, "observation_manifest_hash", canonical_sha256(observation_manifest)
        )
        performance = _validated_performance(
            self.performance,
            observations=observations,
        )
        object.__setattr__(self, "performance", performance)
        all_observations = tuple(
            item for suite in sorted(observations) for item in observations[suite]
        )
        self.run_identity.validate_observations(all_observations)
        total_spend = sum(
            (item.model_spend_usd for item in all_observations),
            start=Decimal(0),
        )
        object.__setattr__(self, "total_model_spend_usd", total_spend)
        object.__setattr__(
            self,
            "passed",
            dict(counts) == dict(RELEASE_SUITE_COUNTS)
            and self.case_count == _RELEASE_CASE_COUNT
            and all(item.passed for item in reports)
            and all(item.passed for item in performance)
            and total_spend <= self.run_identity.max_total_spend_usd,
        )
        object.__setattr__(
            self, "report_hash", canonical_sha256(self.identity_payload())
        )

    @property
    def campaign_budget(self) -> dict[str, object]:
        """Record why Campaign is excluded from per-interaction SLO pooling."""
        return {
            "suite": "campaign",
            "case_count": self.suite_case_counts["campaign"],
            "policy": "campaign_authorization_budget",
        }

    @property
    def provider_id(self) -> str:
        """Return the provider identity frozen by the run manifest."""
        return self.run_identity.provider_id

    @property
    def profile(self) -> str:
        """Return the model profile frozen by the run manifest."""
        return self.run_identity.profile

    def identity_payload(self) -> dict[str, object]:
        """Return the complete authenticated release report."""
        return {
            "schema_version": self.schema_version,
            "suite": self.suite,
            "provider_id": self.provider_id,
            "profile": self.profile,
            "run_identity": {
                **self.run_identity.identity_payload(),
                "identity_hash": self.run_identity.identity_hash,
            },
            "seed": self.seed,
            "dataset_manifest": self.dataset_manifest,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "observation_manifest": self.observation_manifest,
            "observation_manifest_hash": self.observation_manifest_hash,
            "grader_manifest_hash": self.grader_manifest_hash,
            "case_count": self.case_count,
            "suite_case_counts": self.suite_case_counts,
            "suite_reports": tuple(
                {**item.identity_payload(), "report_hash": item.report_hash}
                for item in self.suite_reports
            ),
            "performance": tuple(item.identity_payload() for item in self.performance),
            "total_model_spend_usd": self.total_model_spend_usd,
            "campaign_budget": self.campaign_budget,
            "passed": self.passed,
        }

    def verify_report_hash(self) -> bool:
        """Recompute the aggregate report identity."""
        return self.report_hash == canonical_sha256(self.identity_payload())

    def to_bytes(self) -> bytes:
        """Render canonical JSON without wall-clock or environment state."""
        if not self.verify_report_hash():
            raise ValueError("release eval report hash is invalid")
        return canonical_bytes(
            {**self.identity_payload(), "report_hash": self.report_hash}
        )


def build_release_eval_report(
    *,
    run_identity: ReleaseEvalRunIdentity,
    seed: int,
    reports: Mapping[str, EvalReport],
    cases: Mapping[str, tuple[EvalCase, ...]],
    observations: Mapping[str, tuple[EvalObservation, ...]],
) -> ReleaseEvalReport:
    """Bind suite reports to the exact versioned dataset and SLO observations."""
    suite_ids = set(RELEASE_SUITE_COUNTS)
    if (
        set(reports) != suite_ids
        or set(cases) != suite_ids
        or set(observations) != suite_ids
    ):
        raise ValueError("release eval inputs require the exact six-suite set")
    for suite in suite_ids:
        if len(cases[suite]) != len(observations[suite]):
            raise ValueError("release eval case and observation counts differ")
    dataset_manifest = release_dataset_manifest(cases)
    grader_manifest = tuple(
        (suite, reports[suite].grader_manifest_hash) for suite in sorted(suite_ids)
    )
    observation_manifest = tuple(
        {
            "suite": suite,
            "case_id": case.case_id,
            "observation_hash": observation.observation_hash,
            "observation": observation.identity_payload(),
        }
        for suite in sorted(suite_ids)
        for case, observation in zip(
            sorted(cases[suite], key=lambda item: item.case_id),
            observations[suite],
            strict=True,
        )
    )
    return ReleaseEvalReport(
        run_identity=run_identity,
        seed=seed,
        dataset_manifest=dataset_manifest,
        observation_manifest=observation_manifest,
        grader_manifest_hash=canonical_sha256(grader_manifest),
        suite_reports=tuple(reports.values()),
        performance=_cohort_performance(observations),
    )


__all__ = [
    "RELEASE_SUITE_COUNTS",
    "EvalCohortPerformance",
    "EvalCostBasis",
    "ReleaseEvalReport",
    "ReleaseEvalRunIdentity",
    "build_release_eval_report",
]
