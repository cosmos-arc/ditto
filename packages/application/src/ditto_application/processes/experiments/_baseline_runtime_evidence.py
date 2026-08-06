"""Canonical codec helpers for exact-strategy baseline runtime evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.processes.experiments.planning_probes import (
    BaselineRuntimeExecutorEvidence,
    is_canonical_content_hash,
)

__all__ = [
    "BASELINE_RUNTIME_EVIDENCE_KEYS",
    "baseline_runtime_payload",
    "decode_baseline_runtime_evidence",
    "is_valid_baseline_runtime_evidence",
]

BASELINE_RUNTIME_EVIDENCE_KEYS = frozenset(
    {
        "base_spec_hash",
        "resolved_spec_hash",
        "parameter_hash",
        "pipeline_execution_hash",
        "compiled_factor_set_hash",
        "max_lookback_sessions",
        "node_registry_manifest_hash",
        "factor_registry_manifest_hash",
        "factor_binding_hashes",
    }
)


def is_valid_baseline_runtime_evidence(value: object) -> bool:
    """Return whether an exact typed value contains only canonical identities."""
    if type(value) is not BaselineRuntimeExecutorEvidence:
        return False
    evidence = value
    scalar_hashes = (
        evidence.base_spec_hash,
        evidence.resolved_spec_hash,
        evidence.parameter_hash,
        evidence.pipeline_execution_hash,
        evidence.compiled_factor_set_hash,
        evidence.node_registry_manifest_hash,
        evidence.factor_registry_manifest_hash,
    )
    return (
        all(is_canonical_content_hash(item) for item in scalar_hashes)
        and type(evidence.max_lookback_sessions) is int
        and evidence.max_lookback_sessions >= 0
        and type(evidence.factor_binding_hashes) is tuple
        and all(
            is_canonical_content_hash(item) for item in evidence.factor_binding_hashes
        )
        and len(set(evidence.factor_binding_hashes))
        == len(evidence.factor_binding_hashes)
    )


def baseline_runtime_payload(
    value: BaselineRuntimeExecutorEvidence | None,
) -> Mapping[str, object] | None:
    """Serialize a validated exact baseline identity without adding defaults."""
    if value is None:
        return None
    if not is_valid_baseline_runtime_evidence(value):
        raise experiment_process_error("baseline runtime evidence is invalid")
    return {
        "base_spec_hash": value.base_spec_hash,
        "resolved_spec_hash": value.resolved_spec_hash,
        "parameter_hash": value.parameter_hash,
        "pipeline_execution_hash": value.pipeline_execution_hash,
        "compiled_factor_set_hash": value.compiled_factor_set_hash,
        "max_lookback_sessions": value.max_lookback_sessions,
        "node_registry_manifest_hash": value.node_registry_manifest_hash,
        "factor_registry_manifest_hash": value.factor_registry_manifest_hash,
        "factor_binding_hashes": list(value.factor_binding_hashes),
    }


def decode_baseline_runtime_evidence(
    value: object,
) -> BaselineRuntimeExecutorEvidence | None:
    """Decode an optional persisted identity with exact shape and hash checks."""
    if value is None:
        return None
    if type(value) is not dict:
        raise experiment_process_error("baseline runtime evidence must be an object")
    payload = cast("dict[str, object]", value)
    if set(payload) != set(BASELINE_RUNTIME_EVIDENCE_KEYS):
        raise experiment_process_error("baseline runtime evidence has an invalid shape")
    factor_hashes = payload.get("factor_binding_hashes")
    if type(factor_hashes) is not list:
        raise experiment_process_error(
            "baseline runtime factor bindings must be an array"
        )
    raw_factor_hashes = cast("list[object]", factor_hashes)
    scalar_names = tuple(
        name
        for name in BASELINE_RUNTIME_EVIDENCE_KEYS
        if name not in {"factor_binding_hashes", "max_lookback_sessions"}
    )
    if any(
        not is_canonical_content_hash(payload.get(name)) for name in scalar_names
    ) or any(not is_canonical_content_hash(item) for item in raw_factor_hashes):
        raise experiment_process_error("baseline runtime identity hash is invalid")
    max_lookback = payload.get("max_lookback_sessions")
    if type(max_lookback) is not int or max_lookback < 0:
        raise experiment_process_error(
            "baseline runtime max lookback must be a nonnegative integer"
        )
    evidence = BaselineRuntimeExecutorEvidence(
        base_spec_hash=cast("str", payload.get("base_spec_hash")),
        resolved_spec_hash=cast("str", payload.get("resolved_spec_hash")),
        parameter_hash=cast("str", payload.get("parameter_hash")),
        pipeline_execution_hash=cast("str", payload.get("pipeline_execution_hash")),
        compiled_factor_set_hash=cast("str", payload.get("compiled_factor_set_hash")),
        max_lookback_sessions=max_lookback,
        node_registry_manifest_hash=cast(
            "str", payload.get("node_registry_manifest_hash")
        ),
        factor_registry_manifest_hash=cast(
            "str", payload.get("factor_registry_manifest_hash")
        ),
        factor_binding_hashes=tuple(cast("list[str]", raw_factor_hashes)),
    )
    if not is_valid_baseline_runtime_evidence(evidence):
        raise experiment_process_error("baseline runtime identity hash is invalid")
    return evidence
