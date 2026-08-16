"""Versioned local eval cases and strict fixture loading."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import cast

import orjson

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import (
    freeze_json,
    normalized_text,
    sha256_hex,
)


class EvalCaseError(ValueError):
    """A local eval fixture failed strict decoding or identity validation."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = MappingProxyType(dict(details or {}))


def _unique_texts(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(
        normalized_text(value, field=f"{field_name} item") for value in values
    )
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return tuple(sorted(normalized))


def _frozen_mapping(
    value: Mapping[str, object], *, field_name: str
) -> Mapping[str, object]:
    frozen = freeze_json(value, field=field_name)
    if not isinstance(frozen, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return cast(Mapping[str, object], frozen)


@dataclass(frozen=True, slots=True)
class EvalObservation:
    """Provider-neutral facts inspected only by deterministic host graders."""

    attempted_actions: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    replay_identities: tuple[str, ...]
    rule_assertions: Mapping[str, bool]
    observation_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Normalize all unordered fields and derive the observation identity."""
        object.__setattr__(
            self,
            "attempted_actions",
            _unique_texts(self.attempted_actions, field_name="attempted_actions"),
        )
        object.__setattr__(
            self,
            "allowed_actions",
            _unique_texts(self.allowed_actions, field_name="allowed_actions"),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _unique_texts(self.evidence_refs, field_name="evidence_refs"),
        )
        replay_identities = tuple(
            sha256_hex(value, field="replay identity")
            for value in self.replay_identities
        )
        if not replay_identities:
            raise ValueError("replay_identities must not be empty")
        object.__setattr__(self, "replay_identities", replay_identities)
        assertions: dict[str, bool] = {}
        for name, passed in self.rule_assertions.items():
            normalized_name = normalized_text(name, field="rule assertion name")
            if not isinstance(cast(object, passed), bool):
                raise TypeError("rule assertion values must be bool")
            if normalized_name in assertions:
                raise ValueError("rule assertion names must be unique")
            assertions[normalized_name] = passed
        object.__setattr__(
            self,
            "rule_assertions",
            MappingProxyType(dict(sorted(assertions.items()))),
        )
        object.__setattr__(
            self, "observation_hash", canonical_sha256(self.identity_payload())
        )

    def identity_payload(self) -> dict[str, object]:
        """Return every observed fact authenticated by the observation hash."""
        return {
            "attempted_actions": self.attempted_actions,
            "allowed_actions": self.allowed_actions,
            "evidence_refs": self.evidence_refs,
            "replay_identities": self.replay_identities,
            "rule_assertions": self.rule_assertions,
        }

    def verify_observation_hash(self) -> bool:
        """Recompute the observation identity."""
        return self.observation_hash == canonical_sha256(self.identity_payload())


@dataclass(frozen=True, slots=True)
class EvalCase:
    """One immutable local eval input plus its Fake-provider observation."""

    schema_version: int
    case_id: str
    suite: str
    seed: int
    input_payload: Mapping[str, object]
    observation: EvalObservation
    input_hash: str = field(init=False)
    case_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate versioned case fields and derive stable input/case hashes."""
        if self.schema_version != 1:
            raise ValueError("schema_version is not supported")
        object.__setattr__(
            self, "case_id", normalized_text(self.case_id, field="case_id")
        )
        object.__setattr__(self, "suite", normalized_text(self.suite, field="suite"))
        if isinstance(self.seed, bool) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        object.__setattr__(
            self,
            "input_payload",
            _frozen_mapping(self.input_payload, field_name="input_payload"),
        )
        required = self.input_payload.get("required_evidence")
        if not isinstance(cast(object, required), bool):
            raise ValueError("input_payload.required_evidence must be bool")
        if not isinstance(cast(object, self.observation), EvalObservation):
            raise TypeError("observation must be an EvalObservation")
        if not self.observation.verify_observation_hash():
            raise ValueError("observation hash is invalid")
        object.__setattr__(self, "input_hash", canonical_sha256(self.input_identity()))
        object.__setattr__(self, "case_hash", canonical_sha256(self.identity_payload()))

    @property
    def requires_evidence(self) -> bool:
        """Return the strictly decoded evidence requirement."""
        return cast(bool, self.input_payload["required_evidence"])

    def input_identity(self) -> dict[str, object]:
        """Return case inputs independently traceable from observations."""
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "suite": self.suite,
            "seed": self.seed,
            "input_payload": self.input_payload,
        }

    def identity_payload(self) -> dict[str, object]:
        """Return the complete case artifact identity."""
        return {
            **self.input_identity(),
            "input_hash": self.input_hash,
            "observation": {
                **self.observation.identity_payload(),
                "observation_hash": self.observation.observation_hash,
            },
        }

    def verify_hashes(self) -> bool:
        """Verify input, observation, and complete case identities."""
        return (
            self.observation.verify_observation_hash()
            and self.input_hash == canonical_sha256(self.input_identity())
            and self.case_hash == canonical_sha256(self.identity_payload())
        )


def _mapping(value: object, *, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise EvalCaseError(
            f"{field_name} must be an object",
            reason_code="eval_case_type_invalid",
        )
    raw = cast(dict[object, object], value)
    result: dict[str, object] = {}
    for key, item in raw.items():
        if not isinstance(key, str):
            raise EvalCaseError(
                f"{field_name} keys must be strings",
                reason_code="eval_case_type_invalid",
            )
        result[key] = item
    return result


def _exact(mapping: dict[str, object], keys: set[str], *, field_name: str) -> None:
    if set(mapping) != keys:
        raise EvalCaseError(
            f"{field_name} has an invalid field set",
            reason_code="eval_case_fields_invalid",
        )


def _string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise EvalCaseError(
            f"{field_name} must be a string",
            reason_code="eval_case_type_invalid",
        )
    return value


def _integer(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvalCaseError(
            f"{field_name} must be an integer",
            reason_code="eval_case_type_invalid",
        )
    return value


def _items(value: object, *, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise EvalCaseError(
            f"{field_name} must be an array",
            reason_code="eval_case_type_invalid",
        )
    return tuple(cast(list[object], value))


def _strings(value: object, *, field_name: str) -> tuple[str, ...]:
    return tuple(
        _string(item, field_name=f"{field_name} item")
        for item in _items(value, field_name=field_name)
    )


def _decode_observation(value: object) -> EvalObservation:
    raw = _mapping(value, field_name="observation")
    _exact(
        raw,
        {
            "attempted_actions",
            "allowed_actions",
            "evidence_refs",
            "replay_identities",
            "rule_assertions",
        },
        field_name="observation",
    )
    assertions_raw = _mapping(raw["rule_assertions"], field_name="rule_assertions")
    assertions: dict[str, bool] = {}
    for name, passed in assertions_raw.items():
        if not isinstance(passed, bool):
            raise EvalCaseError(
                "rule assertion values must be bool",
                reason_code="eval_case_type_invalid",
            )
        assertions[name] = passed
    return EvalObservation(
        attempted_actions=_strings(
            raw["attempted_actions"], field_name="attempted_actions"
        ),
        allowed_actions=_strings(raw["allowed_actions"], field_name="allowed_actions"),
        evidence_refs=_strings(raw["evidence_refs"], field_name="evidence_refs"),
        replay_identities=_strings(
            raw["replay_identities"], field_name="replay_identities"
        ),
        rule_assertions=assertions,
    )


def decode_eval_case(payload: bytes) -> EvalCase:
    """Strictly decode one versioned JSON eval fixture."""
    try:
        root = _mapping(cast(object, orjson.loads(payload)), field_name="eval case")
    except orjson.JSONDecodeError as exc:
        raise EvalCaseError(
            "Eval case is not valid JSON",
            reason_code="eval_case_json_invalid",
        ) from exc
    _exact(
        root,
        {
            "schema_version",
            "case_id",
            "suite",
            "seed",
            "input_payload",
            "observation",
        },
        field_name="eval case",
    )
    input_payload = _mapping(root["input_payload"], field_name="input_payload")
    try:
        return EvalCase(
            schema_version=_integer(
                root["schema_version"], field_name="schema_version"
            ),
            case_id=_string(root["case_id"], field_name="case_id"),
            suite=_string(root["suite"], field_name="suite"),
            seed=_integer(root["seed"], field_name="seed"),
            input_payload=input_payload,
            observation=_decode_observation(root["observation"]),
        )
    except EvalCaseError:
        raise
    except (TypeError, ValueError) as exc:
        raise EvalCaseError(
            "Eval case content is invalid",
            reason_code="eval_case_content_invalid",
        ) from exc


def load_eval_cases(directory: Path) -> tuple[EvalCase, ...]:
    """Load all JSON fixtures in stable case-ID order with duplicate fencing."""
    if not directory.is_dir():
        raise EvalCaseError(
            "Eval case directory does not exist",
            reason_code="eval_case_directory_missing",
        )
    cases: list[EvalCase] = []
    for path in sorted(directory.glob("*.json")):
        try:
            cases.append(decode_eval_case(path.read_bytes()))
        except OSError as exc:
            raise EvalCaseError(
                "Eval case file could not be read",
                reason_code="eval_case_read_failed",
                details={"filename": path.name},
            ) from exc
    if not cases:
        raise EvalCaseError(
            "Eval case directory is empty",
            reason_code="eval_case_directory_empty",
        )
    case_ids = tuple(case.case_id for case in cases)
    if len(case_ids) != len(set(case_ids)):
        raise EvalCaseError(
            "Eval case IDs must be unique",
            reason_code="eval_case_duplicate_id",
        )
    return tuple(sorted(cases, key=lambda case: case.case_id))


__all__ = [
    "EvalCase",
    "EvalCaseError",
    "EvalObservation",
    "decode_eval_case",
    "load_eval_cases",
]
