"""Self-contained plan-preimage verification for persisted preflight detail."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import cast

from ditto_application.processes.execution.replay_context_inputs import (
    decode_replay_context_inputs,
)
from ditto_application.processes.experiments._baseline_runtime_evidence import (
    decode_baseline_runtime_evidence,
)
from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.processes.experiments.planning_probes import (
    is_canonical_content_hash,
)

__all__ = ["validate_plan_preimage"]

_PLAN_PREIMAGE_KEYS_V1 = {
    "schema_version",
    "launch_spec_hash",
    "gate_payload_hashes",
    "fold_payload_hashes",
    "research_cycle_id",
    "research_cycle_hash",
    "request_hash",
    "snapshot_evidence",
    "dataset_requirements",
    "validation",
    "validation_authority",
    "work_plan_hash",
    "node_registry_manifest_hash",
    "factor_registry_manifest_hash",
    "factor_binding_hashes",
    "baseline_ref",
    "baseline_descriptor_hash",
    "baseline_registry_manifest_hash",
    "baseline_exact_strategy_hash",
    "baseline_runtime",
    "executor_candidates",
    "certification",
    "preflight_hash",
}
_PLAN_PREIMAGE_KEYS_V2 = _PLAN_PREIMAGE_KEYS_V1 | {"context_input_refs"}


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise experiment_process_error(f"{field_name} must be an object")
    return cast("dict[str, object]", value)


def _list(value: object, field_name: str) -> list[object]:
    if type(value) is not list:
        raise experiment_process_error(f"{field_name} must be a list")
    return cast("list[object]", value)


def _string(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise experiment_process_error(f"{field_name} must be a string")
    return value


def _integer(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise experiment_process_error(f"{field_name} must be an integer")
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash_list(value: object, field_name: str) -> list[object]:
    values = _list(value, field_name)
    if not values or not all(is_canonical_content_hash(item) for item in values):
        raise experiment_process_error(
            f"{field_name} must contain canonical content hashes"
        )
    return values


def _same_json(left: object, right: object) -> bool:
    return _canonical_json(left) == _canonical_json(right)


def _verify_links(
    plan_preimage: Mapping[str, object],
    preflight: Mapping[str, object],
) -> None:
    validation = _mapping(preflight.get("validation"), "validation")
    work = _mapping(preflight.get("work"), "work")
    executor = _mapping(preflight.get("executor"), "executor")
    authority = _mapping(preflight.get("authority"), "authority")
    identities = _mapping(preflight.get("identities"), "identities")
    certification = _mapping(
        identities.get("certification"), "identities.certification"
    )
    checks = _list(preflight.get("checks"), "preflight.checks")
    counts = _mapping(preflight.get("counts"), "preflight.counts")
    gate_hashes = _list(
        plan_preimage.get("gate_payload_hashes"),
        "plan_preimage.gate_payload_hashes",
    )
    fold_hashes = _list(
        plan_preimage.get("fold_payload_hashes"),
        "plan_preimage.fold_payload_hashes",
    )
    authority_preimage = _mapping(
        plan_preimage.get("validation_authority"),
        "plan_preimage.validation_authority",
    )
    expected_authority = {
        key: authority.get(key)
        for key in (
            "payload_hash",
            "runtime_evidence_hash",
            "universe_membership_hash",
            "membership_projection_hash",
            "requires_pit_universe",
            "dataset_bindings",
        )
    }
    expected_certification = {
        key: certification.get(key)
        for key in (
            "profile",
            "required_from",
            "required_to",
            "report_ids",
            "reason_codes",
        )
    }
    links_match = (
        plan_preimage.get("research_cycle_id") == identities.get("research_cycle_id")
        and plan_preimage.get("research_cycle_hash")
        == identities.get("research_cycle_hash")
        and plan_preimage.get("request_hash") == identities.get("request_hash")
        and _same_json(
            plan_preimage.get("snapshot_evidence"),
            certification.get("snapshot_evidence"),
        )
        and _same_json(
            plan_preimage.get("dataset_requirements"),
            identities.get("dataset_requirements"),
        )
        and _same_json(plan_preimage.get("validation"), validation.get("plan"))
        and _same_json(authority_preimage, expected_authority)
        and plan_preimage.get("work_plan_hash") == work.get("plan_hash")
        and plan_preimage.get("node_registry_manifest_hash")
        == executor.get("node_registry_manifest_hash")
        and plan_preimage.get("factor_registry_manifest_hash")
        == executor.get("factor_registry_manifest_hash")
        and _same_json(
            plan_preimage.get("factor_binding_hashes"),
            executor.get("factor_binding_hashes"),
        )
        and plan_preimage.get("baseline_ref") == executor.get("baseline_ref")
        and plan_preimage.get("baseline_descriptor_hash")
        == executor.get("baseline_descriptor_hash")
        and plan_preimage.get("baseline_registry_manifest_hash")
        == executor.get("baseline_registry_manifest_hash")
        and plan_preimage.get("baseline_exact_strategy_hash")
        == executor.get("baseline_exact_strategy_hash")
        and _same_json(
            plan_preimage.get("baseline_runtime"),
            executor.get("baseline_runtime"),
        )
        and _same_json(
            plan_preimage.get("executor_candidates"), executor.get("candidates")
        )
        and _same_json(plan_preimage.get("certification"), expected_certification)
        and len(gate_hashes) == len(checks)
        and len(fold_hashes)
        == _integer(counts.get("planned_fold_count"), "counts.planned_fold_count")
    )
    if not links_match:
        raise experiment_process_error(
            "detail.plan_preimage does not match persisted preflight"
        )


def validate_plan_preimage(
    value: object,
    *,
    plan_hash: str,
    preflight_hash: str,
    preflight: Mapping[str, object],
) -> None:
    """Validate the preimage content address and every persisted cross-link."""
    payload = _mapping(value, "detail.plan_preimage")
    schema_version = _integer(
        payload.get("schema_version"), "plan_preimage.schema_version"
    )
    expected_keys = (
        _PLAN_PREIMAGE_KEYS_V1 if schema_version == 1 else _PLAN_PREIMAGE_KEYS_V2
    )
    if schema_version not in {1, 2} or set(payload) != expected_keys:
        raise experiment_process_error("detail.plan_preimage has an invalid shape")
    if (
        hashlib.sha256(_canonical_json(payload)).hexdigest() != plan_hash
        or _string(payload.get("preflight_hash"), "plan_preimage.preflight_hash")
        != preflight_hash
        or not is_canonical_content_hash(payload.get("launch_spec_hash"))
        or not is_canonical_content_hash(payload.get("research_cycle_hash"))
        or not is_canonical_content_hash(payload.get("request_hash"))
        or not is_canonical_content_hash(payload.get("work_plan_hash"))
        or not is_canonical_content_hash(payload.get("node_registry_manifest_hash"))
        or not is_canonical_content_hash(payload.get("factor_registry_manifest_hash"))
        or not is_canonical_content_hash(payload.get("baseline_descriptor_hash"))
        or not is_canonical_content_hash(payload.get("baseline_registry_manifest_hash"))
        or (
            payload.get("baseline_exact_strategy_hash") is not None
            and not is_canonical_content_hash(
                payload.get("baseline_exact_strategy_hash")
            )
        )
    ):
        raise experiment_process_error(
            "detail.plan_preimage content identity is invalid"
        )
    _string(payload.get("research_cycle_id"), "plan_preimage.research_cycle_id")
    _string(payload.get("baseline_ref"), "plan_preimage.baseline_ref")
    baseline_runtime = decode_baseline_runtime_evidence(payload.get("baseline_runtime"))
    if (
        payload.get("baseline_exact_strategy_hash") is None
        and baseline_runtime is not None
    ) or (
        payload.get("baseline_exact_strategy_hash") is not None
        and baseline_runtime is None
    ):
        raise experiment_process_error(
            "plan_preimage baseline runtime identity is incomplete"
        )
    _hash_list(payload.get("gate_payload_hashes"), "plan_preimage.gate_payload_hashes")
    _hash_list(payload.get("fold_payload_hashes"), "plan_preimage.fold_payload_hashes")
    decode_replay_context_inputs(payload.get("context_input_refs", []))
    factor_binding_hashes = _list(
        payload.get("factor_binding_hashes"),
        "plan_preimage.factor_binding_hashes",
    )
    if any(not is_canonical_content_hash(item) for item in factor_binding_hashes):
        raise experiment_process_error(
            "plan_preimage.factor_binding_hashes must contain canonical hashes"
        )
    _verify_links(payload, preflight)
