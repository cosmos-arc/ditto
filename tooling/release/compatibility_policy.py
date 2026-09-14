"""Validate the checked-in current/previous cohort policy consumed by the Web build."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

__all__ = [
    "CompatibilityPolicy",
    "CompatibilityPolicyError",
    "load_compatibility_policy",
    "main",
]

POLICY_SCHEMA = "ditto.cohort-compatibility-policy"
POLICY_SCHEMA_VERSION = 1
SUPPORTED_API_CONTRACT_VERSION = "v1"
_POLICY_FIELDS = frozenset(
    {
        "api_contract_version",
        "current",
        "previous",
        "schema",
        "schema_version",
    }
)
_IDENTITY_FIELDS = frozenset(
    {
        "product_version",
        "git_sha",
        "api_contract_version",
        "api_contract_sha256",
    }
)
_SEMVER = re.compile(
    r"^(?:0|[1-9][0-9]*)\."
    + r"(?:0|[1-9][0-9]*)\."
    + r"(?:0|[1-9][0-9]*)"
    + r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    + r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    + r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CompatibilityPolicyError(ValueError):
    """Raised when compatibility evidence is malformed or unverifiable."""


class CohortIdentity(TypedDict):
    """Exact backend identity allowed by one Web artifact."""

    product_version: str
    git_sha: str
    api_contract_version: str
    api_contract_sha256: str


class CurrentSource(TypedDict):
    """Non-self-referential source for the current release identity."""

    source: str


class PolicyDocument(TypedDict):
    """Canonical checked-in compatibility policy document."""

    api_contract_version: str
    current: CurrentSource
    previous: list[CohortIdentity]
    schema: str
    schema_version: int


@dataclass(frozen=True, slots=True)
class CompatibilityPolicy:
    """Validated policy plus its checked-in byte identity."""

    schema_version: int
    api_contract_version: str
    previous: tuple[CohortIdentity, ...]
    sha256: str
    document: PolicyDocument


def load_compatibility_policy(
    policy_path: Path,
    digest_path: Path,
) -> CompatibilityPolicy:
    """Load a canonical policy only when its sidecar proves the exact bytes."""
    payload = _read_regular_file(policy_path, label="compatibility policy")
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    digest_payload = _read_regular_file(digest_path, label="policy digest")
    expected_declaration = f"{actual_sha256}  {policy_path.name}\n".encode()
    if digest_payload != expected_declaration:
        raise CompatibilityPolicyError(
            "compatibility policy SHA-256 sidecar is malformed or stale"
        )

    document = _parse_policy_document(payload)
    if payload != _canonical_policy_bytes(document):
        raise CompatibilityPolicyError(
            "compatibility policy must use canonical sorted JSON with one LF"
        )
    return CompatibilityPolicy(
        schema_version=document["schema_version"],
        api_contract_version=document["api_contract_version"],
        previous=tuple(document["previous"]),
        sha256=actual_sha256,
        document=document,
    )


def _parse_policy_document(payload: bytes) -> PolicyDocument:
    raw = _load_json_object(payload, label="compatibility policy")
    _require_exact_fields(raw, _POLICY_FIELDS, label="compatibility policy")
    if raw["schema"] != POLICY_SCHEMA:
        raise CompatibilityPolicyError("compatibility policy schema is invalid")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise CompatibilityPolicyError("compatibility policy schema version must be 1")
    if raw["api_contract_version"] != SUPPORTED_API_CONTRACT_VERSION:
        raise CompatibilityPolicyError("compatibility policy supports only v1")

    current = _object(raw["current"], label="current source")
    _require_exact_fields(current, frozenset({"source"}), label="current source")
    if current["source"] != "web_build":
        raise CompatibilityPolicyError("current source must be web_build")

    previous_value = raw["previous"]
    if not isinstance(previous_value, list):
        raise CompatibilityPolicyError("previous cohorts must be a JSON array")
    if len(previous_value) > 1:
        raise CompatibilityPolicyError(
            "compatibility policy allows at most one previous cohort"
        )
    previous = [
        _cohort_identity(value, label="previous cohort") for value in previous_value
    ]
    return {
        "api_contract_version": SUPPORTED_API_CONTRACT_VERSION,
        "current": {"source": "web_build"},
        "previous": previous,
        "schema": POLICY_SCHEMA,
        "schema_version": POLICY_SCHEMA_VERSION,
    }


def _cohort_identity(value: object, *, label: str) -> CohortIdentity:
    raw = _object(value, label=label)
    _require_exact_fields(raw, _IDENTITY_FIELDS, label=label)
    product_version = _string(raw, "product_version", label=label)
    git_sha = _string(raw, "git_sha", label=label)
    api_contract_version = _string(raw, "api_contract_version", label=label)
    contract_sha256 = _string(raw, "api_contract_sha256", label=label)
    if _SEMVER.fullmatch(product_version) is None:
        raise CompatibilityPolicyError(f"{label} product version must be SemVer")
    if _GIT_SHA.fullmatch(git_sha) is None:
        raise CompatibilityPolicyError(
            f"{label} Git SHA must be a full lowercase 40-character hash"
        )
    if api_contract_version != SUPPORTED_API_CONTRACT_VERSION:
        raise CompatibilityPolicyError(f"{label} API contract version must be v1")
    if _SHA256.fullmatch(contract_sha256) is None:
        raise CompatibilityPolicyError(
            f"{label} contract SHA-256 must be a full lowercase 64-character hash"
        )
    return {
        "product_version": product_version,
        "git_sha": git_sha,
        "api_contract_version": api_contract_version,
        "api_contract_sha256": contract_sha256,
    }


def _load_json_object(payload: bytes, *, label: str) -> dict[str, object]:
    try:
        value = cast(object, json.loads(payload))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CompatibilityPolicyError(f"{label} is not valid JSON") from error
    return _object(value, label=label)


def _object(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CompatibilityPolicyError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _string(raw: Mapping[str, object], field: str, *, label: str) -> str:
    value = raw[field]
    if not isinstance(value, str):
        raise CompatibilityPolicyError(f"{label} {field} must be a string")
    return value


def _require_exact_fields(
    raw: Mapping[str, object], expected: frozenset[str], *, label: str
) -> None:
    actual = set(raw)
    if actual != expected:
        expected_fields = sorted(expected)
        actual_fields = sorted(actual)
        message = (
            f"{label} fields are invalid: "
            f"expected={expected_fields}, actual={actual_fields}"
        )
        raise CompatibilityPolicyError(message)


def _read_regular_file(path: Path, *, label: str) -> bytes:
    if path.is_symlink():
        raise CompatibilityPolicyError(f"{label} cannot be a symlink")
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as error:
        raise CompatibilityPolicyError(f"{label} is unavailable: {path}") from error
    if not resolved.is_file():
        raise CompatibilityPolicyError(f"{label} must be a regular file")
    try:
        return resolved.read_bytes()
    except OSError as error:
        raise CompatibilityPolicyError(f"could not read {label}: {path}") from error


def _canonical_policy_bytes(document: PolicyDocument) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode()
        + b"\n"
    )


def _parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy",
        type=Path,
        default=root / "contracts" / "cohorts" / "compatibility-policy.json",
    )
    parser.add_argument(
        "--digest",
        type=Path,
        default=root / "contracts" / "cohorts" / "compatibility-policy.sha256",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the checked-in compatibility policy and its digest sidecar."""
    arguments = _parser().parse_args(argv)
    load_compatibility_policy(arguments.policy, arguments.digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
