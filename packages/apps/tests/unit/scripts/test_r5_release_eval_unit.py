from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import orjson
from ditto_agent._canonical import canonical_sha256
from ditto_agent.evals.cases import EvalCase, EvalObservation
from ditto_agent.evals.release import ReleaseEvalRunIdentity
from ditto_apps.registry.agent.release_eval_provider import (
    formal_prompt_tool_manifest_hash,
)
from ditto_apps.scripts.r5_release_eval import main

_DATASET_MANIFEST_HASH = (
    "6cd838cc190354e70c31aa6af94786578073beb1c17f8d98bea7f0ec55335114"
)
_PROMPT_TOOL_MANIFEST_HASH = formal_prompt_tool_manifest_hash()


def _scope(
    path: Path,
    *,
    dataset_manifest_hash: str = _DATASET_MANIFEST_HASH,
    model_snapshot: str | None = "glm-5.3-coding-plan-2026-08-17",
    max_total_tokens: int = 20_000,
) -> None:
    payload: dict[str, object] = {
        "schema_version": 2,
        "provider": "glm",
        "approval_record_hash": "1" * 64,
        "provider_data_controls_hash": "3" * 64,
        "runnable_dataset_manifest_hash": dataset_manifest_hash,
        "license_egress_manifest_hash": "5" * 64,
        "model_id": "glm-5.3",
        "max_total_tokens": max_total_tokens,
    }
    if model_snapshot is not None:
        payload["model_snapshot"] = model_snapshot
    path.write_bytes(orjson.dumps(payload))


class _InjectedLiveProvider:
    provider_id = "glm-coding-plan-responses-v1"

    def __init__(self, identity: ReleaseEvalRunIdentity) -> None:
        self.run_identity_hash = identity.identity_hash
        self.model_snapshot = identity.model_snapshot
        self._identity = identity
        self.calls = 0

    async def observe(self, case: EvalCase) -> EvalObservation:
        self.calls += 1
        fixture = case.observation
        input_tokens = 100
        output_tokens = 20
        return EvalObservation(
            attempted_actions=fixture.attempted_actions,
            allowed_actions=fixture.allowed_actions,
            evidence_refs=fixture.evidence_refs,
            replay_identities=fixture.replay_identities,
            rule_assertions=fixture.rule_assertions,
            latency_ms=fixture.latency_ms,
            model_spend_usd=self._identity.model_spend_usd(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
            model_requests=1,
            model_input_tokens=input_tokens,
            model_output_tokens=output_tokens,
            model_output_hash=canonical_sha256(
                {"case_id": case.case_id, "output": "injected"}
            ),
        )


def test_formal_cli_does_not_read_scope_or_secret_without_a4(tmp_path: Path) -> None:
    class GuardedEnvironment(dict[str, str]):
        def get(self, key: str, default: str | None = None) -> str | None:
            if key.startswith("DITTO_AGENT_GLM_"):
                raise AssertionError("credential read before A4")
            return super().get(key, default)

    output = tmp_path / "not-run.json"
    missing_scope = tmp_path / "must-not-be-read.json"

    exit_code = main(
        (
            "--profile",
            "balanced",
            "--scope",
            str(missing_scope),
            "--prompt-tool-manifest-hash",
            _PROMPT_TOOL_MANIFEST_HASH,
            "--output",
            str(output),
        ),
        environment=GuardedEnvironment(),
    )

    payload = orjson.loads(output.read_bytes())
    assert exit_code == 5
    assert payload["reason_code"] == "a4_approval_required"
    assert payload["prohibited_actions_observed"]["api_key_read"] is False


def test_formal_cli_rejects_missing_coding_plan_credential_before_provider_call(
    tmp_path: Path,
) -> None:
    scope = tmp_path / "scope.json"
    output = tmp_path / "failed.json"
    _scope(scope)

    exit_code = main(
        (
            "--profile",
            "balanced",
            "--approval-a4",
            "--scope",
            str(scope),
            "--prompt-tool-manifest-hash",
            _PROMPT_TOOL_MANIFEST_HASH,
            "--output",
            str(output),
        ),
        environment={},
    )

    payload = orjson.loads(output.read_bytes())
    assert exit_code == 1
    assert payload["reason_code"] == "formal_eval_credential_missing"


def test_formal_cli_rejects_missing_stable_model_snapshot_before_secret_read(
    tmp_path: Path,
) -> None:
    class GuardedEnvironment(dict[str, str]):
        def get(self, key: str, default: str | None = None) -> str | None:
            if key.startswith("DITTO_AGENT_GLM_"):
                raise AssertionError("credential read before model snapshot validation")
            return super().get(key, default)

    scope = tmp_path / "scope-without-model-snapshot.json"
    output = tmp_path / "failed.json"
    _scope(scope, model_snapshot=None)

    exit_code = main(
        (
            "--profile",
            "balanced",
            "--approval-a4",
            "--scope",
            str(scope),
            "--prompt-tool-manifest-hash",
            _PROMPT_TOOL_MANIFEST_HASH,
            "--output",
            str(output),
        ),
        environment=GuardedEnvironment(),
        provider_builder=lambda identity, api_key: _InjectedLiveProvider(identity),
    )

    payload = orjson.loads(output.read_bytes())
    assert exit_code == 1
    assert payload["reason_code"] == "formal_eval_model_snapshot_missing"


def test_formal_cli_rejects_rolling_model_id_as_snapshot_before_secret_read(
    tmp_path: Path,
) -> None:
    class GuardedEnvironment(dict[str, str]):
        def get(self, key: str, default: str | None = None) -> str | None:
            if key.startswith("DITTO_AGENT_GLM_"):
                raise AssertionError("credential read before model snapshot validation")
            return super().get(key, default)

    scope = tmp_path / "scope-with-rolling-model-id.json"
    output = tmp_path / "failed.json"
    _scope(scope, model_snapshot="glm-5.3")

    exit_code = main(
        (
            "--profile",
            "balanced",
            "--approval-a4",
            "--scope",
            str(scope),
            "--prompt-tool-manifest-hash",
            _PROMPT_TOOL_MANIFEST_HASH,
            "--output",
            str(output),
        ),
        environment=GuardedEnvironment(),
        provider_builder=lambda identity, api_key: _InjectedLiveProvider(identity),
    )

    payload = orjson.loads(output.read_bytes())
    assert exit_code == 1
    assert payload["reason_code"] == "formal_eval_model_snapshot_unstable"


def test_formal_cli_rejects_prompt_tool_manifest_drift_before_secret_read(
    tmp_path: Path,
) -> None:
    class GuardedEnvironment(dict[str, str]):
        def get(self, key: str, default: str | None = None) -> str | None:
            if key.startswith("DITTO_AGENT_GLM_"):
                raise AssertionError("credential read before prompt/tool validation")
            return super().get(key, default)

    scope = tmp_path / "scope.json"
    output = tmp_path / "failed.json"
    _scope(scope)

    exit_code = main(
        (
            "--profile",
            "balanced",
            "--approval-a4",
            "--scope",
            str(scope),
            "--prompt-tool-manifest-hash",
            "6" * 64,
            "--output",
            str(output),
        ),
        environment=GuardedEnvironment(),
    )

    payload = orjson.loads(output.read_bytes())
    assert exit_code == 1
    assert payload["reason_code"] == "formal_eval_prompt_tool_manifest_mismatch"


def test_formal_cli_runs_120_cases_with_frozen_identity_and_token_budget(
    tmp_path: Path,
) -> None:
    scope = tmp_path / "scope.json"
    output = tmp_path / "balanced.json"
    _scope(scope)
    providers: list[_InjectedLiveProvider] = []

    def builder(
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> _InjectedLiveProvider:
        assert api_key == "plan-secret"
        provider = _InjectedLiveProvider(identity)
        providers.append(provider)
        return provider

    exit_code = main(
        (
            "--profile",
            "balanced",
            "--approval-a4",
            "--scope",
            str(scope),
            "--prompt-tool-manifest-hash",
            _PROMPT_TOOL_MANIFEST_HASH,
            "--output",
            str(output),
        ),
        environment={
            "DITTO_AGENT_GLM_VALIDATION_API_KEY": "plan-secret",
        },
        provider_builder=builder,
    )

    raw = output.read_text()
    payload = orjson.loads(raw)
    assert exit_code == 0
    assert providers[0].calls == 120
    assert payload["passed"] is True
    assert payload["case_count"] == 120
    assert payload["provider_id"] == "glm-coding-plan-responses-v1"
    assert payload["run_identity"]["model_id"] == "glm-5.3"
    assert payload["run_identity"]["model_snapshot"] == "glm-5.3-coding-plan-2026-08-17"
    assert payload["run_identity"]["reasoning_effort"] == "high"
    assert payload["run_identity"]["cost_basis"] == "usage_cap"
    assert payload["run_identity"]["input_price_per_million_usd"] == "0"
    assert payload["run_identity"]["output_price_per_million_usd"] == "0"
    assert payload["total_model_spend_usd"] == "0"
    assert "plan-secret" not in raw


def test_formal_cli_stops_when_total_token_budget_is_exceeded(
    tmp_path: Path,
) -> None:
    scope = tmp_path / "scope.json"
    output = tmp_path / "failed.json"
    _scope(scope, max_total_tokens=100)
    providers: list[_InjectedLiveProvider] = []

    def builder(
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> _InjectedLiveProvider:
        del api_key
        provider = _InjectedLiveProvider(identity)
        providers.append(provider)
        return provider

    exit_code = main(
        (
            "--profile",
            "balanced",
            "--approval-a4",
            "--scope",
            str(scope),
            "--prompt-tool-manifest-hash",
            _PROMPT_TOOL_MANIFEST_HASH,
            "--output",
            str(output),
        ),
        environment={"DITTO_AGENT_GLM_VALIDATION_API_KEY": "plan-secret"},
        provider_builder=builder,
    )

    payload = orjson.loads(output.read_bytes())
    assert exit_code == 1
    assert payload["reason_code"] == "eval_live_total_tokens_exceeded"
    assert providers[0].calls == 1


def test_formal_cli_rejects_provider_model_snapshot_drift_before_first_case(
    tmp_path: Path,
) -> None:
    scope = tmp_path / "scope.json"
    output = tmp_path / "failed.json"
    _scope(scope)
    providers: list[_InjectedLiveProvider] = []

    def builder(
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> _InjectedLiveProvider:
        del api_key
        provider = _InjectedLiveProvider(identity)
        provider.model_snapshot = "glm-5.3-different-snapshot"
        providers.append(provider)
        return provider

    exit_code = main(
        (
            "--profile",
            "balanced",
            "--approval-a4",
            "--scope",
            str(scope),
            "--prompt-tool-manifest-hash",
            _PROMPT_TOOL_MANIFEST_HASH,
            "--output",
            str(output),
        ),
        environment={
            "DITTO_AGENT_GLM_VALIDATION_API_KEY": "plan-secret",
        },
        provider_builder=builder,
    )

    payload = orjson.loads(output.read_bytes())
    assert exit_code == 1
    assert payload["reason_code"] == "formal_eval_provider_model_snapshot_mismatch"
    assert providers[0].calls == 0


def test_formal_cli_rejects_nonpositive_token_budget_before_secret_read(
    tmp_path: Path,
) -> None:
    class GuardedEnvironment(dict[str, str]):
        def get(self, key: str, default: str | None = None) -> str | None:
            if key.startswith("DITTO_AGENT_GLM_"):
                raise AssertionError("credential read before token budget validation")
            return super().get(key, default)

    scope = tmp_path / "scope.json"
    output = tmp_path / "failed.json"
    _scope(scope, max_total_tokens=0)
    builds = 0

    def builder(
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> _InjectedLiveProvider:
        nonlocal builds
        del api_key
        builds += 1
        return _InjectedLiveProvider(identity)

    exit_code = main(
        (
            "--profile",
            "quality",
            "--approval-a4",
            "--scope",
            str(scope),
            "--prompt-tool-manifest-hash",
            _PROMPT_TOOL_MANIFEST_HASH,
            "--output",
            str(output),
        ),
        environment=GuardedEnvironment(),
        provider_builder=builder,
    )

    payload: Mapping[str, object] = orjson.loads(output.read_bytes())
    assert exit_code == 1
    assert payload["reason_code"] == "formal_eval_scope_invalid"
    assert builds == 0


def test_formal_cli_rejects_dataset_scope_drift_before_secret_read(
    tmp_path: Path,
) -> None:
    class GuardedEnvironment(dict[str, str]):
        def get(self, key: str, default: str | None = None) -> str | None:
            if key.startswith("DITTO_AGENT_GLM_"):
                raise AssertionError("credential read before dataset scope validation")
            return super().get(key, default)

    scope = tmp_path / "scope.json"
    output = tmp_path / "failed.json"
    _scope(scope, dataset_manifest_hash="4" * 64)

    def builder(
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> _InjectedLiveProvider:
        del api_key
        return _InjectedLiveProvider(identity)

    exit_code = main(
        (
            "--profile",
            "balanced",
            "--approval-a4",
            "--scope",
            str(scope),
            "--prompt-tool-manifest-hash",
            _PROMPT_TOOL_MANIFEST_HASH,
            "--output",
            str(output),
        ),
        environment=GuardedEnvironment(),
        provider_builder=builder,
    )

    payload = orjson.loads(output.read_bytes())
    assert exit_code == 1
    assert payload["reason_code"] == "formal_eval_dataset_scope_mismatch"
