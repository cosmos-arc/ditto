"""Compose the approved formal R5 release eval without weakening A4."""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, cast

import orjson
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts._validation import normalized_text, sha256_hex
from ditto_agent.evals.cases import EvalCase, EvalObservation, load_eval_cases
from ditto_agent.evals.manifest import release_dataset_manifest_hash
from ditto_agent.evals.release import (
    RELEASE_SUITE_COUNTS,
    EvalCostBasis,
    ReleaseEvalRunIdentity,
)
from ditto_agent.evals.runner import (
    EvalRunnerError,
    FakeEvalProvider,
    LocalEvalRunner,
    bundled_eval_cases,
    run_live_release,
)

from ditto_apps.registry.agent.release_eval_provider import (
    build_glm_coding_plan_release_eval_provider,
    formal_prompt_tool_manifest_hash,
)

_API_KEY_ENV = "DITTO_AGENT_GLM_VALIDATION_API_KEY"
_PROVIDER = "glm"
_PROVIDER_ID = "glm-coding-plan-responses-v1"
_SCOPE_SCHEMA_VERSION = 2
_SEED = 20_260_816


class FormalReleaseEvalError(RuntimeError):
    """Formal release configuration or runtime identity failed closed."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class _Profile:
    reasoning_effort: str


_PROFILES: Mapping[str, _Profile] = MappingProxyType(
    {
        "balanced": _Profile(
            reasoning_effort="high",
        ),
        "quality": _Profile(
            reasoning_effort="max",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class FormalA4Scope:
    """Minimal content-addressed evidence required before formal data egress."""

    provider: str
    approval_record_hash: str
    provider_data_controls_hash: str
    runnable_dataset_manifest_hash: str
    license_egress_manifest_hash: str
    model_id: str
    model_snapshot: str
    max_total_tokens: int
    scope_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Normalize hashes, require a positive budget, and derive scope identity."""
        for name in (
            "approval_record_hash",
            "provider_data_controls_hash",
            "runnable_dataset_manifest_hash",
            "license_egress_manifest_hash",
        ):
            object.__setattr__(
                self,
                name,
                sha256_hex(getattr(self, name), field=f"formal scope {name}"),
            )
        for name in ("provider", "model_id", "model_snapshot"):
            object.__setattr__(
                self,
                name,
                normalized_text(getattr(self, name), field=f"formal scope {name}"),
            )
        if self.provider != _PROVIDER:
            raise ValueError("formal scope provider must be glm")
        if (
            isinstance(cast(object, self.max_total_tokens), bool)
            or not isinstance(cast(object, self.max_total_tokens), int)
            or self.max_total_tokens <= 0
        ):
            raise ValueError("max_total_tokens must be a positive integer")
        object.__setattr__(self, "scope_hash", canonical_sha256(self.payload()))

    def payload(self) -> dict[str, object]:
        """Return the approval scope that invalidates inherited evidence."""
        return {
            "schema_version": _SCOPE_SCHEMA_VERSION,
            "provider": self.provider,
            "approval_record_hash": self.approval_record_hash,
            "provider_data_controls_hash": self.provider_data_controls_hash,
            "runnable_dataset_manifest_hash": self.runnable_dataset_manifest_hash,
            "license_egress_manifest_hash": self.license_egress_manifest_hash,
            "model_id": self.model_id,
            "model_snapshot": self.model_snapshot,
            "max_total_tokens": self.max_total_tokens,
        }

    @classmethod
    def load(cls, path: Path) -> FormalA4Scope:
        """Decode one exact local scope manifest without accepting extra fields."""
        try:
            decoded: object = orjson.loads(path.read_bytes())
        except (OSError, orjson.JSONDecodeError) as exc:
            raise FormalReleaseEvalError(
                "Formal A4 scope could not be read",
                reason_code="formal_eval_scope_invalid",
            ) from exc
        if not isinstance(decoded, dict):
            raise FormalReleaseEvalError(
                "Formal A4 scope must be an object",
                reason_code="formal_eval_scope_invalid",
            )
        payload = cast(dict[str, object], decoded)
        if "model_snapshot" not in payload:
            raise FormalReleaseEvalError(
                "Formal A4 scope requires an operator-attested model revision",
                reason_code="formal_eval_model_snapshot_missing",
            )
        expected = {
            "schema_version",
            "provider",
            "approval_record_hash",
            "provider_data_controls_hash",
            "runnable_dataset_manifest_hash",
            "license_egress_manifest_hash",
            "model_id",
            "model_snapshot",
            "max_total_tokens",
        }
        if (
            set(payload) != expected
            or payload["schema_version"] != _SCOPE_SCHEMA_VERSION
        ):
            raise FormalReleaseEvalError(
                "Formal A4 scope fields are invalid",
                reason_code="formal_eval_scope_invalid",
            )
        try:
            return cls(
                provider=cast(str, payload["provider"]),
                approval_record_hash=cast(str, payload["approval_record_hash"]),
                provider_data_controls_hash=cast(
                    str, payload["provider_data_controls_hash"]
                ),
                runnable_dataset_manifest_hash=cast(
                    str, payload["runnable_dataset_manifest_hash"]
                ),
                license_egress_manifest_hash=cast(
                    str, payload["license_egress_manifest_hash"]
                ),
                model_id=cast(str, payload["model_id"]),
                model_snapshot=cast(str, payload["model_snapshot"]),
                max_total_tokens=cast(int, payload["max_total_tokens"]),
            )
        except (TypeError, ValueError) as exc:
            raise FormalReleaseEvalError(
                "Formal A4 scope values are invalid",
                reason_code="formal_eval_scope_invalid",
            ) from exc


class FormalLiveEvalProvider(Protocol):
    """Apps-composed live scenario executor bound to one exact run identity."""

    provider_id: str
    run_identity_hash: str
    model_snapshot: str

    async def observe(self, case: EvalCase) -> EvalObservation:
        """Execute one approved scenario and return host-authenticated facts."""
        ...


type FormalProviderBuilder = Callable[
    [ReleaseEvalRunIdentity, str], FormalLiveEvalProvider
]


def build_formal_run_identity(
    *,
    profile_name: str,
    scope: FormalA4Scope,
    prompt_tool_manifest_hash: str,
) -> ReleaseEvalRunIdentity:
    """Freeze model, prompt/tool, A4, pricing, and budget for one formal run."""
    profile_name = normalized_text(profile_name, field="formal eval profile")
    try:
        profile = _PROFILES[profile_name]
    except KeyError as exc:
        raise ValueError("formal eval profile is unsupported") from exc
    if scope.model_snapshot == scope.model_id:
        raise FormalReleaseEvalError(
            "Formal model revision must differ from the rolling model ID",
            reason_code="formal_eval_model_snapshot_unstable",
        )
    return ReleaseEvalRunIdentity(
        provider_id=_PROVIDER_ID,
        profile=profile_name,
        model_id=scope.model_id,
        model_snapshot=scope.model_snapshot,
        reasoning_effort=profile.reasoning_effort,
        prompt_tool_manifest_hash=prompt_tool_manifest_hash,
        a4_scope_hash=scope.scope_hash,
        pricing_manifest_hash=canonical_sha256(
            {
                "cost_basis": EvalCostBasis.USAGE_CAP,
                "max_total_tokens": scope.max_total_tokens,
                "version": 1,
            }
        ),
        pricing_as_of="1970-01-01",
        input_price_per_million_usd=Decimal(0),
        output_price_per_million_usd=Decimal(0),
        max_total_spend_usd=Decimal(0),
        max_total_tokens=scope.max_total_tokens,
        cost_basis=EvalCostBasis.USAGE_CAP,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run approved formal R5 evals")
    parser.add_argument("--profile", choices=tuple(_PROFILES), required=True)
    parser.add_argument("--approval-a4", action="store_true")
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--prompt-tool-manifest-hash", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _not_run_payload(*, profile: str, reason_code: str) -> bytes:
    return canonical_bytes(
        {
            "schema_version": 1,
            "status": "not_run",
            "approval_gate": "A4",
            "reason_code": reason_code,
            "provider": _PROVIDER,
            "profile": profile,
            "release_gate_passed": False,
            "prohibited_actions_observed": {
                "api_key_read": False,
                "live_endpoint_called": False,
                "model_cost_incurred": False,
                "model_data_exported": False,
            },
        }
    )


def _failed_payload(*, profile: str, error: Exception) -> bytes:
    return canonical_bytes(
        {
            "schema_version": 1,
            "status": "failed",
            "reason_code": (
                error.reason_code
                if isinstance(error, (FormalReleaseEvalError, EvalRunnerError))
                else "formal_release_eval_failed"
            ),
            "failure_type": type(error).__name__,
            "provider": _PROVIDER,
            "profile": profile,
            "release_gate_passed": False,
        }
    )


def _bundled_cases() -> dict[str, tuple[EvalCase, ...]]:
    cases: dict[str, tuple[EvalCase, ...]] = {}
    for suite in RELEASE_SUITE_COUNTS:
        _seed, dataset_path = bundled_eval_cases(suite)
        cases[suite] = load_eval_cases(dataset_path)
    return cases


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] = os.environ,
    provider_builder: FormalProviderBuilder | None = None,
) -> int:
    """Run only after all local scope and composition checks pass."""
    arguments = _parser().parse_args(argv)
    profile_name = str(arguments.profile)
    output = Path(arguments.output)
    if not bool(arguments.approval_a4):
        output.write_bytes(
            _not_run_payload(
                profile=profile_name,
                reason_code="a4_approval_required",
            )
        )
        return 5
    try:
        scope = FormalA4Scope.load(Path(arguments.scope))
        prompt_tool_manifest_hash = str(arguments.prompt_tool_manifest_hash)
        if prompt_tool_manifest_hash != formal_prompt_tool_manifest_hash():
            raise FormalReleaseEvalError(
                "Formal prompt/tool manifest differs from the runnable provider",
                reason_code="formal_eval_prompt_tool_manifest_mismatch",
            )
        identity = build_formal_run_identity(
            profile_name=profile_name,
            scope=scope,
            prompt_tool_manifest_hash=prompt_tool_manifest_hash,
        )
        cases = _bundled_cases()
        LocalEvalRunner(provider=FakeEvalProvider()).preflight_release_cases(
            cases=cases,
            seed=_SEED,
        )
        if release_dataset_manifest_hash(cases) != scope.runnable_dataset_manifest_hash:
            raise FormalReleaseEvalError(
                "Release dataset differs from the approved A4 scope",
                reason_code="formal_eval_dataset_scope_mismatch",
            )
        api_key = environment.get(_API_KEY_ENV)
        if api_key is None or not api_key.strip() or api_key != api_key.strip():
            raise FormalReleaseEvalError(
                "Formal GLM credentials are missing",
                reason_code="formal_eval_credential_missing",
            )
        builder = provider_builder or build_glm_coding_plan_release_eval_provider
        provider = builder(identity, api_key)
        if provider.run_identity_hash != identity.identity_hash:
            raise FormalReleaseEvalError(
                "Live provider is not bound to the exact run identity",
                reason_code="formal_eval_provider_identity_mismatch",
            )
        if provider.model_snapshot != identity.model_snapshot:
            raise FormalReleaseEvalError(
                "Live provider bound a different A4 model revision",
                reason_code="formal_eval_provider_model_snapshot_mismatch",
            )
        report = asyncio.run(
            run_live_release(
                provider=provider,
                run_identity=identity,
                seed=_SEED,
                cases=cases,
            )
        )
    except Exception as exc:
        output.write_bytes(_failed_payload(profile=profile_name, error=exc))
        return 1
    output.write_bytes(report.to_bytes())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FormalA4Scope",
    "FormalLiveEvalProvider",
    "FormalReleaseEvalError",
    "build_formal_run_identity",
    "main",
]
