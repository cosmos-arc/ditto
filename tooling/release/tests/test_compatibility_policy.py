"""Tests for the checked-in current/previous cohort compatibility policy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tooling.release.compatibility_policy import (
    CompatibilityPolicyError,
    load_compatibility_policy,
)

ROOT = Path(__file__).resolve().parents[3]


def _identity(
    *,
    version: str = "1.1.0",
    git_sha: str = "a" * 40,
    contract_sha256: str = "b" * 64,
) -> dict[str, str]:
    return {
        "product_version": version,
        "git_sha": git_sha,
        "api_contract_version": "v1",
        "api_contract_sha256": contract_sha256,
    }


def _document(previous: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "api_contract_version": "v1",
        "current": {"source": "web_build"},
        "previous": previous or [],
        "schema": "ditto.cohort-compatibility-policy",
        "schema_version": 1,
    }


def _write_policy(root: Path, document: dict[str, object]) -> tuple[Path, Path]:
    policy = root / "compatibility-policy.json"
    digest = root / "compatibility-policy.sha256"
    payload = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode()
        + b"\n"
    )
    policy.write_bytes(payload)
    digest.write_text(
        f"{hashlib.sha256(payload).hexdigest()}  {policy.name}\n",
        encoding="utf-8",
    )
    return policy, digest


def test_checked_in_policy_is_canonical_valid_and_has_no_fabricated_previous() -> None:
    loaded = load_compatibility_policy(
        ROOT / "contracts" / "cohorts" / "compatibility-policy.json",
        ROOT / "contracts" / "cohorts" / "compatibility-policy.sha256",
    )

    assert loaded.schema_version == 1
    assert loaded.api_contract_version == "v1"
    assert loaded.previous == ()
    assert len(loaded.sha256) == 64


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({**_document(), "schema": "ditto.same-major"}, "schema"),
        ({**_document(), "schema_version": 2}, "schema version"),
        ({**_document(), "api_contract_version": "v2"}, "v1"),
        ({**_document(), "unexpected": True}, "fields"),
        (_document([_identity(git_sha="short")]), "Git SHA"),
        (_document([_identity(contract_sha256="short")]), "contract SHA"),
        (_document([_identity(), _identity(version="1.0.0")]), "at most one"),
    ],
)
def test_policy_rejects_invalid_schema_or_identity(
    tmp_path: Path,
    document: dict[str, object],
    message: str,
) -> None:
    policy, digest = _write_policy(tmp_path, document)

    with pytest.raises(CompatibilityPolicyError, match=message):
        load_compatibility_policy(policy, digest)


def test_policy_rejects_a_stale_or_malformed_digest(tmp_path: Path) -> None:
    policy, digest = _write_policy(tmp_path, _document())
    digest.write_text(f"{'0' * 64}  {policy.name}\n", encoding="utf-8")

    with pytest.raises(CompatibilityPolicyError, match="SHA-256"):
        load_compatibility_policy(policy, digest)
