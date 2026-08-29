"""Validation helpers for frozen R5 release-evaluation evidence."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

import orjson
from ditto_agent._canonical import canonical_sha256

from ditto_apps.registry.agent.release_eval_provider import (
    formal_prompt_tool_manifest_hash,
)
from ditto_apps.scripts import _r5_agent_release_contract as _release_contract
from ditto_apps.scripts.r5_release_eval import FormalA4Scope, FormalReleaseEvalError

_SHA256_HEX_LENGTH = 64
_LIVE_REASONING = {"balanced": "high", "quality": "max"}
_LIVE_IDENTITY_FIELDS = {
    "a4_scope_hash",
    "cost_basis",
    "identity_hash",
    "input_price_per_million_usd",
    "max_total_spend_usd",
    "max_total_tokens",
    "model_id",
    "model_snapshot",
    "output_price_per_million_usd",
    "pricing_as_of",
    "pricing_manifest_hash",
    "profile",
    "prompt_tool_manifest_hash",
    "provider_id",
    "reasoning_effort",
}


def _string_mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return cast(Mapping[str, object], value)


def _object_list(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return cast(list[object], value)


def _read_mapping(path: Path) -> Mapping[str, object]:
    decoded: object = orjson.loads(path.read_bytes())
    mapping = _string_mapping(decoded)
    if mapping is None:
        raise ValueError("release evidence must be a JSON object")
    return mapping


def _cohort_performance_valid(
    item: Mapping[str, object],
    *,
    suites: tuple[str, ...],
    count: int,
    latency_limit: int,
    spend_limit: Decimal,
) -> bool:
    raw_suites = _object_list(item.get("suites"))
    if raw_suites is None or not all(isinstance(suite, str) for suite in raw_suites):
        return False
    try:
        p95 = int(cast(int, item.get("latency_p95_ms")))
        maximum = Decimal(cast(str, item.get("max_spend_usd")))
        observed_limit = Decimal(cast(str, item.get("spend_limit_usd")))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return (
        tuple(cast(str, suite) for suite in raw_suites) == suites
        and item.get("case_count") == count
        and item.get("latency_limit_ms") == latency_limit
        and observed_limit == spend_limit
        and p95 <= latency_limit
        and maximum <= spend_limit
        and item.get("passed") is True
    )


def performance_valid(payload: Mapping[str, object]) -> bool:
    """Verify the frozen cohort latency and fixture-spend evidence."""
    performance = _object_list(payload.get("performance"))
    if performance is None:
        return False
    cohorts: dict[str, Mapping[str, object]] = {}
    for raw_item in performance:
        item = _string_mapping(raw_item)
        if item is None or not isinstance(item.get("cohort"), str):
            return False
        cohorts[cast(str, item["cohort"])] = item
    expected = {
        "read": (("grounded",), 30, 30_000, Decimal("0.25")),
        "complex": (
            ("author", "permission", "sandbox", "shadow"),
            60,
            60_000,
            Decimal("0.75"),
        ),
    }
    return (
        set(cohorts) == set(expected)
        and all(
            _cohort_performance_valid(
                cohorts[cohort],
                suites=suites,
                count=count,
                latency_limit=latency_limit,
                spend_limit=spend_limit,
            )
            for cohort, (suites, count, latency_limit, spend_limit) in expected.items()
        )
        and payload.get("campaign_budget")
        == {
            "case_count": 30,
            "policy": "campaign_authorization_budget",
            "suite": "campaign",
        }
    )


def run_identity_and_spend_valid(
    payload: Mapping[str, object],
    *,
    provider_id: str,
    frozen_identity_hash: str,
) -> bool:
    """Verify the fake run identity, authenticated usage, and total budget."""
    run_identity = _string_mapping(payload.get("run_identity"))
    manifest = _object_list(payload.get("observation_manifest"))
    expected_identity_fields = {
        "a4_scope_hash",
        "cost_basis",
        "identity_hash",
        "input_price_per_million_usd",
        "max_total_spend_usd",
        "max_total_tokens",
        "model_id",
        "model_snapshot",
        "output_price_per_million_usd",
        "pricing_as_of",
        "pricing_manifest_hash",
        "profile",
        "prompt_tool_manifest_hash",
        "provider_id",
        "reasoning_effort",
    }
    if (
        run_identity is None
        or manifest is None
        or set(run_identity) != expected_identity_fields
        or run_identity.get("provider_id") != provider_id
        or run_identity.get("profile") != "fake"
        or run_identity.get("cost_basis") != "fixture"
        or run_identity.get("max_total_tokens") != 0
        or run_identity.get("identity_hash") != frozen_identity_hash
    ):
        return False
    supplied_identity_hash = run_identity.get("identity_hash")
    identity_payload = {
        key: value for key, value in run_identity.items() if key != "identity_hash"
    }
    if supplied_identity_hash != canonical_sha256(identity_payload):
        return False
    try:
        max_total_spend = Decimal(str(run_identity["max_total_spend_usd"]))
        supplied_total = Decimal(str(payload.get("total_model_spend_usd")))
        observed_total = Decimal(0)
        for raw_row in manifest:
            row = _string_mapping(raw_row)
            observation = (
                None if row is None else _string_mapping(row.get("observation"))
            )
            if observation is None:
                return False
            for usage_field in (
                "model_requests",
                "model_input_tokens",
                "model_output_tokens",
            ):
                usage = observation.get(usage_field)
                if isinstance(usage, bool) or not isinstance(usage, int) or usage < 0:
                    return False
            observed_total += Decimal(str(observation.get("model_spend_usd")))
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return False
    return supplied_total == observed_total and supplied_total <= max_total_spend


def _sha256_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _validated_live_identity(
    run_identity: Mapping[str, object],
) -> tuple[Mapping[str, object], int] | None:
    supplied_identity_hash = run_identity.get("identity_hash")
    identity_payload = {
        key: value for key, value in run_identity.items() if key != "identity_hash"
    }
    model_id = run_identity.get("model_id")
    model_snapshot = run_identity.get("model_snapshot")
    max_total_tokens = run_identity.get("max_total_tokens")
    valid = (
        _sha256_text(supplied_identity_hash)
        and supplied_identity_hash == canonical_sha256(identity_payload)
        and all(
            _sha256_text(run_identity.get(field))
            for field in (
                "a4_scope_hash",
                "pricing_manifest_hash",
                "prompt_tool_manifest_hash",
            )
        )
        and isinstance(model_id, str)
        and bool(model_id.strip())
        and isinstance(model_snapshot, str)
        and bool(model_snapshot.strip())
        and model_snapshot != model_id
        and not isinstance(max_total_tokens, bool)
        and isinstance(max_total_tokens, int)
        and max_total_tokens > 0
        and run_identity.get("pricing_manifest_hash")
        == canonical_sha256(
            {
                "cost_basis": "usage_cap",
                "max_total_tokens": max_total_tokens,
                "version": 1,
            }
        )
    )
    if not valid:
        return None
    return run_identity, cast(int, max_total_tokens)


def _observed_live_tokens(manifest: list[object]) -> int | None:
    total_tokens = 0
    try:
        for raw_row in manifest:
            row = _string_mapping(raw_row)
            observation = (
                None if row is None else _string_mapping(row.get("observation"))
            )
            if observation is None:
                return None
            requests = observation.get("model_requests")
            input_tokens = observation.get("model_input_tokens")
            output_tokens = observation.get("model_output_tokens")
            valid = (
                not isinstance(requests, bool)
                and isinstance(requests, int)
                and requests > 0
                and not isinstance(input_tokens, bool)
                and isinstance(input_tokens, int)
                and input_tokens >= 0
                and not isinstance(output_tokens, bool)
                and isinstance(output_tokens, int)
                and output_tokens >= 0
                and input_tokens + output_tokens > 0
                and Decimal(str(observation.get("model_spend_usd"))) == 0
                and _sha256_text(observation.get("model_output_hash"))
            )
            if not valid:
                return None
            total_tokens += cast(int, input_tokens) + cast(int, output_tokens)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return total_tokens


def live_usage_identity_valid(
    payload: Mapping[str, object],
    *,
    provider_id: str,
    profile: str,
) -> bool:
    """Verify one GLM usage-capped run identity and authenticated total usage."""
    run_identity = _string_mapping(payload.get("run_identity"))
    manifest = _object_list(payload.get("observation_manifest"))
    if (
        run_identity is None
        or manifest is None
        or set(run_identity) != _LIVE_IDENTITY_FIELDS
        or run_identity.get("provider_id") != provider_id
        or run_identity.get("profile") != profile
        or run_identity.get("cost_basis") != "usage_cap"
        or run_identity.get("reasoning_effort") != _LIVE_REASONING.get(profile)
        or run_identity.get("pricing_as_of") != "1970-01-01"
    ):
        return False
    validated_identity = _validated_live_identity(run_identity)
    if validated_identity is None:
        return False
    try:
        currency_is_unmeasured = (
            all(
                Decimal(str(run_identity[field])) == 0
                for field in (
                    "input_price_per_million_usd",
                    "output_price_per_million_usd",
                    "max_total_spend_usd",
                )
            )
            and Decimal(str(payload.get("total_model_spend_usd"))) == 0
        )
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return False
    observed_tokens = _observed_live_tokens(manifest)
    return (
        currency_is_unmeasured
        and observed_tokens is not None
        and observed_tokens <= validated_identity[1]
    )


def approved_live_identity_valid(
    payload: Mapping[str, object],
    *,
    repo_root: Path,
) -> bool:
    """Bind one live report to the frozen A4 scope, materials, and prompt."""
    scope_path = repo_root / "docs/evidence/r5/preflight/glm-coding-plan-a4-scope.json"
    try:
        scope = FormalA4Scope.load(scope_path)
        materials = _read_mapping(
            repo_root / "docs/evidence/r5/preflight/glm-coding-plan-a4-materials.json"
        )
    except FormalReleaseEvalError:
        return False
    except (OSError, ValueError, orjson.JSONDecodeError):
        return False
    material_fields = {
        "approval_record": "approval_record_hash",
        "provider_data_controls": "provider_data_controls_hash",
        "license_egress_manifest": "license_egress_manifest_hash",
    }
    if (
        set(materials) != {"schema_version", *material_fields}
        or materials.get("schema_version") != 1
    ):
        return False
    for section_name, scope_field in material_fields.items():
        section = _string_mapping(materials.get(section_name))
        if section is None or canonical_sha256(section) != getattr(scope, scope_field):
            return False
    run_identity = _string_mapping(payload.get("run_identity"))
    prompt_tool_hash = formal_prompt_tool_manifest_hash()
    return (
        run_identity is not None
        and scope.scope_hash == _release_contract.FROZEN_GLM_A4_SCOPE_HASH
        and prompt_tool_hash == _release_contract.FROZEN_GLM_PROMPT_TOOL_MANIFEST_HASH
        and scope.runnable_dataset_manifest_hash
        == _release_contract.FROZEN_FAKE_IDENTITIES["dataset_manifest_hash"]
        and run_identity.get("a4_scope_hash") == scope.scope_hash
        and run_identity.get("model_id") == scope.model_id
        and run_identity.get("model_snapshot") == scope.model_snapshot
        and run_identity.get("max_total_tokens") == scope.max_total_tokens
        and run_identity.get("prompt_tool_manifest_hash") == prompt_tool_hash
    )


__all__ = [
    "approved_live_identity_valid",
    "live_usage_identity_valid",
    "performance_valid",
    "run_identity_and_spend_valid",
]
