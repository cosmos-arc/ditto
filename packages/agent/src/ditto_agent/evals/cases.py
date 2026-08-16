"""Versioned local eval cases and strict fixture loading."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
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
from ditto_agent.evals.r5_3 import (
    CampaignCaseFamily,
    R53Metric,
    SandboxCaseFamily,
    family_for_suite,
    validate_r5_3_input,
)

_GROUNDED_SCHEMA_VERSION = 2
_GOVERNED_SCHEMA_VERSION = 3
_R5_3_SCHEMA_VERSION = 4
_AUTHOR_ALLOWED_ACTIONS = frozenset(
    {
        "author_compile_expression",
        "author_diff_strategy",
        "author_draft_strategy",
        "author_validate_strategy",
    }
)
_PERMISSION_ALLOWED_ACTIONS = frozenset(
    {"author_save_strategy_draft", "author_submit_strategy_review"}
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


class GroundedCaseFamily(StrEnum):
    """Required R5.1 grounded-evidence case families."""

    TOOL_CHOICE = "tool_choice"
    FACTUAL = "factual"
    EVIDENCE = "evidence"
    CONFLICT = "conflict"
    MISSING = "missing"
    PIT = "pit"
    PROVIDER_FAILURE = "provider_failure"
    REPLAY = "replay"


class GroundedMetric(StrEnum):
    """Fixed, non-overridable R5.1 release metrics."""

    TOOL_CHOICE = "tool_choice"
    EVIDENCE_COVERAGE = "evidence_coverage"
    FACTUAL_CORRECTNESS = "factual_correctness"
    REQUIRED_ABSTENTION = "required_abstention"
    PIT_SAFETY = "pit_safety"
    PROVIDER_DEGRADATION = "provider_degradation"
    EPISODE_REPLAY = "episode_replay"


class EvalMetric(StrEnum):
    """Fixed, non-overridable R5.2 governed-write release metrics."""

    AUTHOR_COMPILE_VALIDATE = "author_compile_validate"
    APPROVAL_BYPASS = "approval_bypass"
    EPISODE_REPLAY = "episode_replay"


class AuthorCaseFamily(StrEnum):
    """Required R5.2 Author quality and adversarial families."""

    DRAFT = "draft"
    COMPILE = "compile"
    VALIDATE = "validate"
    DIFF = "diff"
    PROMPT_INJECTION = "prompt_injection"
    ARGUMENT_SMUGGLING = "argument_smuggling"
    UNKNOWN_NODE = "unknown_node"
    PAYLOAD_TAMPER = "payload_tamper"
    PROVIDER_FAILURE = "provider_failure"
    REPLAY = "replay"


class PermissionCaseFamily(StrEnum):
    """Required R5.2 formal-write permission and approval families."""

    MISSING_APPROVAL = "missing_approval"
    REJECTED_APPROVAL = "rejected_approval"
    EXPIRED_APPROVAL = "expired_approval"
    ACTION_HASH_TAMPER = "action_hash_tamper"
    ARGUMENTS_HASH_TAMPER = "arguments_hash_tamper"
    CALL_ID_TAMPER = "call_id_tamper"
    AUTHORITY_DRIFT = "authority_drift"
    CONTEXT_DRIFT = "context_drift"
    APPROVAL_REPLAY = "approval_replay"
    CONCURRENT_REPLAY = "concurrent_replay"
    IDEMPOTENCY_REPLAY = "idempotency_replay"
    RECEIPT_TAMPER = "receipt_tamper"
    STORAGE_FAILURE = "storage_failure"
    PROVIDER_FAILURE = "provider_failure"
    PROMPT_INJECTION = "prompt_injection"
    ARGUMENT_SMUGGLING = "argument_smuggling"
    PUBLISH_DENIED = "publish_denied"
    TRADE_DENIED = "trade_denied"
    BROKER_DENIED = "broker_denied"
    IDENTITY_OVERRIDE = "identity_override"


_FAMILY_METRIC = MappingProxyType(
    {
        GroundedCaseFamily.TOOL_CHOICE: GroundedMetric.TOOL_CHOICE,
        GroundedCaseFamily.FACTUAL: GroundedMetric.FACTUAL_CORRECTNESS,
        GroundedCaseFamily.EVIDENCE: GroundedMetric.EVIDENCE_COVERAGE,
        GroundedCaseFamily.CONFLICT: GroundedMetric.REQUIRED_ABSTENTION,
        GroundedCaseFamily.MISSING: GroundedMetric.REQUIRED_ABSTENTION,
        GroundedCaseFamily.PIT: GroundedMetric.PIT_SAFETY,
        GroundedCaseFamily.PROVIDER_FAILURE: GroundedMetric.PROVIDER_DEGRADATION,
        GroundedCaseFamily.REPLAY: GroundedMetric.EPISODE_REPLAY,
    }
)


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
    latency_ms: int = 0
    model_spend_usd: Decimal = Decimal(0)
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
        latency_ms = cast(object, self.latency_ms)
        if isinstance(latency_ms, bool) or not isinstance(latency_ms, int):
            raise ValueError("latency_ms must be a non-negative integer")
        if latency_ms < 0:
            raise ValueError("latency_ms must be a non-negative integer")
        if not isinstance(cast(object, self.model_spend_usd), Decimal):
            raise TypeError("model_spend_usd must be Decimal")
        if not self.model_spend_usd.is_finite() or self.model_spend_usd < 0:
            raise ValueError("model_spend_usd must be finite and non-negative")
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
            "latency_ms": self.latency_ms,
            "model_spend_usd": self.model_spend_usd,
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
        if self.schema_version not in {1, 2, 3, 4}:
            raise ValueError("schema_version is not supported")
        object.__setattr__(
            self, "case_id", normalized_text(self.case_id, field="case_id")
        )
        object.__setattr__(self, "suite", normalized_text(self.suite, field="suite"))
        seed = cast(object, self.seed)
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
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
        if self.schema_version == _GROUNDED_SCHEMA_VERSION:
            self._validate_grounded_input()
        elif self.schema_version == _GOVERNED_SCHEMA_VERSION:
            self._validate_governed_input()
        elif self.schema_version == _R5_3_SCHEMA_VERSION:
            self._validate_r5_3_input()
        object.__setattr__(self, "input_hash", canonical_sha256(self.input_identity()))
        object.__setattr__(self, "case_hash", canonical_sha256(self.identity_payload()))

    def _validate_grounded_input(self) -> None:
        if self.suite != "grounded":
            raise ValueError("schema_version 2 is reserved for the grounded suite")
        expected_fields = {
            "objective",
            "required_evidence",
            "family",
            "required_metrics",
            "expected_actions",
            "expected_evidence_refs",
        }
        if set(self.input_payload) != expected_fields:
            raise ValueError("grounded input_payload has an invalid field set")
        _ = normalized_text(self.objective, field="objective", maximum=4096)
        _ = self.grounded_family
        metrics = self.required_metrics
        if not metrics or len(metrics) != len(set(metrics)):
            raise ValueError("required_metrics must be non-empty and unique")
        if GroundedMetric.EPISODE_REPLAY not in metrics:
            raise ValueError("grounded cases must require episode replay")
        if _FAMILY_METRIC[self.grounded_family] not in metrics:
            raise ValueError("grounded family metric is required")
        expected_actions = self.expected_actions
        expected_refs = self.expected_evidence_refs
        if len(expected_actions) != len(set(expected_actions)):
            raise ValueError("expected_actions must be unique")
        if len(expected_refs) != len(set(expected_refs)):
            raise ValueError("expected_evidence_refs must be unique")
        if self.requires_evidence and not expected_refs:
            raise ValueError("required evidence cases need expected_evidence_refs")

    def _validate_governed_input(self) -> None:
        if self.suite not in {"author", "permission"}:
            raise ValueError("schema_version 3 is reserved for governed write suites")
        expected_fields = {
            "objective",
            "required_evidence",
            "family",
            "required_metrics",
            "expected_actions",
            "expected_evidence_refs",
        }
        if set(self.input_payload) != expected_fields:
            raise ValueError("governed input_payload has an invalid field set")
        _ = normalized_text(self.objective, field="objective", maximum=4096)
        _ = self.governed_family
        expected_metric = (
            EvalMetric.AUTHOR_COMPILE_VALIDATE
            if self.suite == "author"
            else EvalMetric.APPROVAL_BYPASS
        )
        if set(self.required_metrics) != {
            expected_metric,
            EvalMetric.EPISODE_REPLAY,
        }:
            raise ValueError("governed case has an invalid metric set")
        expected_actions = self.expected_actions
        expected_refs = self.expected_evidence_refs
        if len(expected_actions) != len(set(expected_actions)):
            raise ValueError("expected_actions must be unique")
        if len(expected_refs) != len(set(expected_refs)):
            raise ValueError("expected_evidence_refs must be unique")
        if self.requires_evidence and not expected_refs:
            raise ValueError("required evidence cases need expected_evidence_refs")
        allowed_actions = (
            _AUTHOR_ALLOWED_ACTIONS
            if self.suite == "author"
            else _PERMISSION_ALLOWED_ACTIONS
        )
        if frozenset(self.observation.allowed_actions) != allowed_actions:
            raise ValueError("governed case has an invalid action allowlist")
        if not set(expected_actions).issubset(allowed_actions):
            raise ValueError("governed case expects an action outside the allowlist")

    def _validate_r5_3_input(self) -> None:
        expected_fields = {
            "objective",
            "required_evidence",
            "family",
            "required_metrics",
            "expected_actions",
            "expected_evidence_refs",
        }
        if set(self.input_payload) != expected_fields:
            raise ValueError("R5.3 input_payload has an invalid field set")
        _ = normalized_text(self.objective, field="objective", maximum=4096)
        _ = self.r5_3_family
        validate_r5_3_input(
            suite=self.suite,
            required_metrics=cast(tuple[R53Metric, ...], self.required_metrics),
            expected_actions=self.expected_actions,
            expected_evidence_refs=self.expected_evidence_refs,
            allowed_actions=self.observation.allowed_actions,
            rule_assertions=self.observation.rule_assertions,
            requires_evidence=self.requires_evidence,
        )

    @property
    def requires_evidence(self) -> bool:
        """Return the strictly decoded evidence requirement."""
        return cast(bool, self.input_payload["required_evidence"])

    @property
    def objective(self) -> str:
        """Return the local, non-secret task text for this eval case."""
        value = self.input_payload.get("objective")
        if not isinstance(value, str):
            raise ValueError("input_payload.objective must be text")
        return value

    @property
    def grounded_family(self) -> GroundedCaseFamily:
        """Return the required R5.1 family for a schema-v2 case."""
        value = self.input_payload.get("family")
        if not isinstance(value, str):
            raise ValueError("input_payload.family must be text")
        try:
            return GroundedCaseFamily(value)
        except ValueError as exc:
            raise ValueError("input_payload.family is unsupported") from exc

    @property
    def governed_family(self) -> AuthorCaseFamily | PermissionCaseFamily:
        """Return the suite-owned R5.2 adversarial family."""
        value = self.input_payload.get("family")
        if not isinstance(value, str):
            raise ValueError("input_payload.family must be text")
        family_type = (
            AuthorCaseFamily if self.suite == "author" else PermissionCaseFamily
        )
        try:
            return family_type(value)
        except ValueError as exc:
            raise ValueError("input_payload.family is unsupported") from exc

    @property
    def r5_3_family(self) -> CampaignCaseFamily | SandboxCaseFamily:
        """Return the suite-owned R5.3 Campaign or sandbox family."""
        if self.schema_version != _R5_3_SCHEMA_VERSION:
            raise ValueError("R5.3 family requires schema_version 4")
        value = self.input_payload.get("family")
        if not isinstance(value, str):
            raise ValueError("input_payload.family must be text")
        return family_for_suite(self.suite, value)

    @property
    def required_metrics(
        self,
    ) -> tuple[GroundedMetric | EvalMetric | R53Metric, ...]:
        """Return the fixed metric membership of a release case."""
        raw = cast(object, self.input_payload.get("required_metrics"))
        if not isinstance(raw, tuple):
            raise ValueError("input_payload.required_metrics must be an array")
        items = cast(tuple[object, ...], raw)
        if not all(isinstance(item, str) for item in items):
            raise ValueError("input_payload.required_metrics must be an array")
        metrics = cast(tuple[str, ...], items)
        try:
            metric_type = (
                R53Metric
                if self.schema_version == _R5_3_SCHEMA_VERSION
                else EvalMetric
                if self.schema_version == _GOVERNED_SCHEMA_VERSION
                else GroundedMetric
            )
            return tuple(metric_type(item) for item in metrics)
        except ValueError as exc:
            raise ValueError("input_payload.required_metrics is unsupported") from exc

    @property
    def expected_actions(self) -> tuple[str, ...]:
        """Return the exact expected tool/action selection."""
        return self._input_text_tuple("expected_actions")

    @property
    def expected_evidence_refs(self) -> tuple[str, ...]:
        """Return the minimum durable evidence reference set."""
        return self._input_text_tuple("expected_evidence_refs")

    def _input_text_tuple(self, field_name: str) -> tuple[str, ...]:
        raw = cast(object, self.input_payload.get(field_name))
        if not isinstance(raw, tuple):
            raise ValueError(f"input_payload.{field_name} must be a text array")
        items = cast(tuple[object, ...], raw)
        if not all(isinstance(item, str) for item in items):
            raise ValueError(f"input_payload.{field_name} must be a text array")
        return cast(tuple[str, ...], items)

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


def _decimal(value: object, *, field_name: str) -> Decimal:
    if not isinstance(value, str):
        raise EvalCaseError(
            f"{field_name} must be an exact decimal string",
            reason_code="eval_case_type_invalid",
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise EvalCaseError(
            f"{field_name} must be an exact decimal string",
            reason_code="eval_case_type_invalid",
        ) from exc
    if not parsed.is_finite() or parsed < 0:
        raise EvalCaseError(
            f"{field_name} must be finite and non-negative",
            reason_code="eval_case_content_invalid",
        )
    return parsed


def _decode_observation(value: object, *, schema_version: int) -> EvalObservation:
    raw = _mapping(value, field_name="observation")
    fields = {
        "attempted_actions",
        "allowed_actions",
        "evidence_refs",
        "replay_identities",
        "rule_assertions",
    }
    if schema_version == _GROUNDED_SCHEMA_VERSION:
        fields |= {"latency_ms", "model_spend_usd"}
    _exact(
        raw,
        fields,
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
        latency_ms=(
            _integer(raw["latency_ms"], field_name="latency_ms")
            if schema_version == _GROUNDED_SCHEMA_VERSION
            else 0
        ),
        model_spend_usd=(
            _decimal(raw["model_spend_usd"], field_name="model_spend_usd")
            if schema_version == _GROUNDED_SCHEMA_VERSION
            else Decimal(0)
        ),
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
        schema_version = _integer(root["schema_version"], field_name="schema_version")
        return EvalCase(
            schema_version=schema_version,
            case_id=_string(root["case_id"], field_name="case_id"),
            suite=_string(root["suite"], field_name="suite"),
            seed=_integer(root["seed"], field_name="seed"),
            input_payload=input_payload,
            observation=_decode_observation(
                root["observation"], schema_version=schema_version
            ),
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
    "AuthorCaseFamily",
    "CampaignCaseFamily",
    "EvalCase",
    "EvalCaseError",
    "EvalMetric",
    "EvalObservation",
    "GroundedCaseFamily",
    "GroundedMetric",
    "PermissionCaseFamily",
    "R53Metric",
    "SandboxCaseFamily",
    "decode_eval_case",
    "load_eval_cases",
]
