"""Fail-closed edges for the versioned local eval case codec."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import cast

import orjson
import pytest
from ditto_agent.evals.cases import (
    EvalCase,
    EvalCaseError,
    EvalObservation,
    decode_eval_case,
    load_eval_cases,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "evals"
DATASETS = Path(__file__).parents[3] / "src" / "ditto_agent" / "evals" / "datasets"
REPLAY_HASH = "a" * 64


def _observation() -> EvalObservation:
    return EvalObservation(
        attempted_actions=("read_evidence",),
        allowed_actions=("read_evidence",),
        evidence_refs=("evidence://one",),
        replay_identities=(REPLAY_HASH,),
        rule_assertions={"authority_bound": True},
    )


def _fixture_payload(path: Path | None = None) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        orjson.loads((path or FIXTURES / "passing.json").read_bytes()),
    )


def _decode_error(payload: object) -> EvalCaseError:
    with pytest.raises(EvalCaseError) as info:
        decode_eval_case(orjson.dumps(payload))
    return info.value


@pytest.mark.parametrize(
    ("field_name", "value", "exception", "message"),
    [
        ("attempted_actions", ("duplicate", "duplicate"), ValueError, "duplicates"),
        ("replay_identities", (), ValueError, "must not be empty"),
        ("latency_ms", -1, ValueError, "non-negative integer"),
        ("latency_ms", True, ValueError, "non-negative integer"),
        ("model_spend_usd", "0", TypeError, "must be Decimal"),
        ("model_spend_usd", Decimal("NaN"), ValueError, "finite and non-negative"),
        ("model_spend_usd", Decimal("-0.01"), ValueError, "finite and non-negative"),
        ("model_requests", -1, ValueError, "non-negative integer"),
        ("model_input_tokens", True, ValueError, "non-negative integer"),
        ("model_output_tokens", -1, ValueError, "non-negative integer"),
    ],
)
def test_observation_rejects_ambiguous_or_negative_usage_fields(
    field_name: str,
    value: object,
    exception: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception, match=message):
        replace(_observation(), **{field_name: value})


def test_observation_optional_model_hash_is_authenticated() -> None:
    observation = replace(_observation(), model_output_hash="b" * 64)
    assert observation.identity_payload()["model_output_hash"] == "b" * 64
    assert observation.verify_observation_hash()

    object.__setattr__(observation, "model_output_hash", "c" * 64)
    assert not observation.verify_observation_hash()


@pytest.mark.parametrize(
    ("field_name", "value", "exception", "message"),
    [
        ("schema_version", 0, ValueError, "schema_version"),
        ("seed", -1, ValueError, "seed"),
        ("seed", True, ValueError, "seed"),
        ("input_payload", [], TypeError, "must be a mapping"),
        (
            "input_payload",
            {"objective": "x", "required_evidence": 1},
            ValueError,
            "required_evidence",
        ),
        ("observation", "forged", TypeError, "EvalObservation"),
    ],
)
def test_eval_case_rejects_invalid_envelope_fields(
    field_name: str,
    value: object,
    exception: type[Exception],
    message: str,
) -> None:
    case = load_eval_cases(FIXTURES)[0]
    with pytest.raises(exception, match=message):
        replace(case, **{field_name: value})


def test_eval_case_rejects_a_tampered_observation_identity() -> None:
    observation = _observation()
    object.__setattr__(observation, "observation_hash", "0" * 64)

    with pytest.raises(ValueError, match="observation hash"):
        EvalCase(
            schema_version=1,
            case_id="tampered-observation",
            suite="baseline",
            seed=1,
            input_payload={"objective": "Check identity.", "required_evidence": True},
            observation=observation,
        )


def test_case_accessors_reject_forged_payload_types_and_versions() -> None:
    case = load_eval_cases(FIXTURES)[0]
    forged = replace(
        case,
        input_payload={
            "objective": 1,
            "required_evidence": True,
            "family": 1,
            "required_metrics": (),
            "expected_actions": (),
            "expected_evidence_refs": (),
        },
    )
    with pytest.raises(ValueError, match="objective must be text"):
        _ = forged.objective
    with pytest.raises(ValueError, match="family must be text"):
        _ = forged.grounded_family

    unsupported = replace(
        case,
        input_payload={
            "objective": "x",
            "required_evidence": True,
            "family": "not-a-family",
        },
    )
    with pytest.raises(ValueError, match="family is unsupported"):
        _ = unsupported.grounded_family
    with pytest.raises(ValueError, match=r"R5\.3 family requires schema_version 4"):
        _ = unsupported.r5_3_family
    with pytest.raises(ValueError, match="shadow family requires schema_version 5"):
        _ = unsupported.shadow_family

    object.__setattr__(
        unsupported,
        "input_payload",
        MappingProxyType(
            {
                "required_evidence": True,
                "required_metrics": ["episode_replay"],
                "expected_actions": [1],
                "expected_evidence_refs": [1],
            }
        ),
    )
    with pytest.raises(ValueError, match="required_metrics must be an array"):
        _ = unsupported.required_metrics
    with pytest.raises(ValueError, match="expected_actions must be a text array"):
        _ = unsupported.expected_actions
    with pytest.raises(ValueError, match="expected_evidence_refs must be a text array"):
        _ = unsupported.expected_evidence_refs

    object.__setattr__(
        unsupported,
        "input_payload",
        MappingProxyType(
            {
                "required_evidence": True,
                "required_metrics": ("not-a-metric",),
                "expected_actions": (1,),
                "expected_evidence_refs": (1,),
            }
        ),
    )
    with pytest.raises(ValueError, match="required_metrics is unsupported"):
        _ = unsupported.required_metrics
    with pytest.raises(ValueError, match="expected_actions must be a text array"):
        _ = unsupported.expected_actions
    with pytest.raises(ValueError, match="expected_evidence_refs must be a text array"):
        _ = unsupported.expected_evidence_refs


def test_versioned_family_accessors_reject_forged_types_and_values() -> None:
    case = load_eval_cases(FIXTURES)[0]
    for suite in ("author", "permission"):
        object.__setattr__(case, "suite", suite)
        object.__setattr__(
            case,
            "input_payload",
            MappingProxyType({"required_evidence": True, "family": 1}),
        )
        with pytest.raises(ValueError, match="family must be text"):
            _ = case.governed_family
        object.__setattr__(
            case,
            "input_payload",
            MappingProxyType({"required_evidence": True, "family": "not-a-family"}),
        )
        with pytest.raises(ValueError, match="family is unsupported"):
            _ = case.governed_family

    object.__setattr__(case, "schema_version", 4)
    object.__setattr__(
        case,
        "input_payload",
        MappingProxyType({"required_evidence": True, "family": 1}),
    )
    with pytest.raises(ValueError, match="family must be text"):
        _ = case.r5_3_family

    object.__setattr__(case, "schema_version", 5)
    with pytest.raises(ValueError, match="family must be text"):
        _ = case.shadow_family
    object.__setattr__(
        case,
        "input_payload",
        MappingProxyType({"required_evidence": True, "family": "not-a-family"}),
    )
    with pytest.raises(ValueError, match="family is unsupported"):
        _ = case.shadow_family


def test_decoder_rejects_invalid_json_and_non_object_roots() -> None:
    with pytest.raises(EvalCaseError) as malformed:
        decode_eval_case(b"{not-json")
    assert malformed.value.reason_code == "eval_case_json_invalid"

    error = _decode_error([])
    assert error.reason_code == "eval_case_type_invalid"


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        ("schema_bool", "eval_case_type_invalid"),
        ("case_id_number", "eval_case_type_invalid"),
        ("suite_number", "eval_case_type_invalid"),
        ("seed_bool", "eval_case_type_invalid"),
        ("input_not_object", "eval_case_type_invalid"),
        ("observation_not_object", "eval_case_type_invalid"),
        ("actions_not_array", "eval_case_type_invalid"),
        ("action_not_text", "eval_case_type_invalid"),
        ("assertions_not_object", "eval_case_type_invalid"),
        ("assertion_not_bool", "eval_case_type_invalid"),
        ("required_evidence_not_bool", "eval_case_content_invalid"),
        ("replay_empty", "eval_case_content_invalid"),
    ],
)
def test_decoder_reports_stable_reason_codes_for_type_forgery(
    mutation: str,
    reason_code: str,
) -> None:
    payload = _fixture_payload()
    observation = cast("dict[str, object]", payload["observation"])
    input_payload = cast("dict[str, object]", payload["input_payload"])
    if mutation == "schema_bool":
        payload["schema_version"] = True
    elif mutation == "case_id_number":
        payload["case_id"] = 1
    elif mutation == "suite_number":
        payload["suite"] = 1
    elif mutation == "seed_bool":
        payload["seed"] = True
    elif mutation == "input_not_object":
        payload["input_payload"] = []
    elif mutation == "observation_not_object":
        payload["observation"] = []
    elif mutation == "actions_not_array":
        observation["attempted_actions"] = {}
    elif mutation == "action_not_text":
        observation["attempted_actions"] = [1]
    elif mutation == "assertions_not_object":
        observation["rule_assertions"] = []
    elif mutation == "assertion_not_bool":
        observation["rule_assertions"] = {"authority_bound": "yes"}
    elif mutation == "required_evidence_not_bool":
        input_payload["required_evidence"] = 1
    else:
        observation["replay_identities"] = []

    assert _decode_error(payload).reason_code == reason_code


@pytest.mark.parametrize(
    ("value", "reason_code"),
    [
        (1, "eval_case_type_invalid"),
        ("not-a-decimal", "eval_case_type_invalid"),
        ("NaN", "eval_case_content_invalid"),
        ("-0.01", "eval_case_content_invalid"),
    ],
)
def test_grounded_decoder_rejects_inexact_or_invalid_spend(
    value: object,
    reason_code: str,
) -> None:
    payload = _fixture_payload(DATASETS / "grounded" / "01-tool_choice-experiment.json")
    observation = cast("dict[str, object]", payload["observation"])
    observation["model_spend_usd"] = value

    assert _decode_error(payload).reason_code == reason_code


@pytest.mark.parametrize(
    "mutation",
    [
        "invalid_fields",
        "duplicate_metrics",
        "missing_replay_metric",
        "duplicate_actions",
        "duplicate_refs",
        "missing_required_refs",
    ],
)
def test_grounded_cases_reject_ambiguous_release_requirements(mutation: str) -> None:
    payload = _fixture_payload(DATASETS / "grounded" / "01-tool_choice-experiment.json")
    input_payload = cast("dict[str, object]", payload["input_payload"])
    metrics = cast("list[str]", input_payload["required_metrics"])
    actions = cast("list[str]", input_payload["expected_actions"])
    refs = cast("list[str]", input_payload["expected_evidence_refs"])
    if mutation == "invalid_fields":
        input_payload["unexpected"] = True
    elif mutation == "duplicate_metrics":
        metrics.append(metrics[0])
    elif mutation == "missing_replay_metric":
        metrics.remove("episode_replay")
    elif mutation == "duplicate_actions":
        actions.append(actions[0])
    elif mutation == "duplicate_refs":
        refs.append(refs[0])
    else:
        refs.clear()

    assert _decode_error(payload).reason_code == "eval_case_content_invalid"


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_suite",
        "invalid_fields",
        "duplicate_actions",
        "duplicate_refs",
        "missing_required_refs",
        "action_outside_allowlist",
    ],
)
def test_governed_cases_reject_ambiguous_write_requirements(mutation: str) -> None:
    payload = _fixture_payload(DATASETS / "author" / "01-draft-structured.json")
    input_payload = cast("dict[str, object]", payload["input_payload"])
    actions = cast("list[str]", input_payload["expected_actions"])
    refs = cast("list[str]", input_payload["expected_evidence_refs"])
    if mutation == "wrong_suite":
        payload["suite"] = "baseline"
    elif mutation == "invalid_fields":
        input_payload["unexpected"] = True
    elif mutation == "duplicate_actions":
        actions.append(actions[0])
    elif mutation == "duplicate_refs":
        refs.append(refs[0])
    elif mutation == "missing_required_refs":
        refs.clear()
    else:
        actions.append("publish_strategy")

    assert _decode_error(payload).reason_code == "eval_case_content_invalid"


@pytest.mark.parametrize(
    ("relative_path", "mutation"),
    [
        ("campaign/01-manifest-authorization.json", "invalid_fields"),
        ("shadow/01-v3-grounding.json", "invalid_fields"),
        ("shadow/01-v3-grounding.json", "wrong_suite"),
    ],
)
def test_later_eval_versions_keep_their_exact_field_and_suite_ownership(
    relative_path: str,
    mutation: str,
) -> None:
    payload = _fixture_payload(DATASETS / relative_path)
    if mutation == "invalid_fields":
        input_payload = cast("dict[str, object]", payload["input_payload"])
        input_payload["unexpected"] = True
    else:
        payload["suite"] = "baseline"

    assert _decode_error(payload).reason_code == "eval_case_content_invalid"


def test_loader_reports_missing_empty_unreadable_and_duplicate_inputs(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(EvalCaseError) as missing_info:
        load_eval_cases(missing)
    assert missing_info.value.reason_code == "eval_case_directory_missing"

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(EvalCaseError) as empty_info:
        load_eval_cases(empty)
    assert empty_info.value.reason_code == "eval_case_directory_empty"

    unreadable = tmp_path / "unreadable"
    unreadable.mkdir()
    (unreadable / "broken.json").symlink_to(unreadable / "absent.json")
    with pytest.raises(EvalCaseError) as unreadable_info:
        load_eval_cases(unreadable)
    assert unreadable_info.value.reason_code == "eval_case_read_failed"
    assert unreadable_info.value.details == {"filename": "broken.json"}

    duplicate = tmp_path / "duplicate"
    duplicate.mkdir()
    source = (FIXTURES / "passing.json").read_bytes()
    (duplicate / "one.json").write_bytes(source)
    (duplicate / "two.json").write_bytes(source)
    with pytest.raises(EvalCaseError) as duplicate_info:
        load_eval_cases(duplicate)
    assert duplicate_info.value.reason_code == "eval_case_duplicate_id"
