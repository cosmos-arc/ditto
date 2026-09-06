"""Tests for the checked-in current/previous cohort compatibility policy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tooling.release import compatibility_policy as policy_module
from tooling.release.cohort_manifest import (
    CohortManifest,
    ReleaseCoordinates,
    build_cohort_manifest,
    write_cohort_manifest,
)
from tooling.release.compatibility_policy import (
    CompatibilityPolicyError,
    load_compatibility_policy,
    register_previous_release,
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


def _write_portable_manifest(root: Path) -> tuple[Path, dict[str, str]]:
    contract = root / "release-inputs" / "contracts" / "openapi" / "v1.json"
    contract.parent.mkdir(parents=True)
    contract.write_text("{}\n")
    inputs = [
        contract,
        root / "release-inputs" / "uv.lock",
        root / "release-inputs" / "bun.lock",
    ]
    inputs[1].write_text("pixi\n")
    inputs[2].write_text("bun\n")
    for name in (".python-version", "Dockerfile"):
        path = root / "release-inputs" / name
        path.write_text("fixture")
        inputs.append(path)
    verifier_paths = (
        "release-tools/tooling/__init__.py",
        "release-tools/tooling/release/__init__.py",
        "release-tools/tooling/release/cohort_manifest.py",
        "release-tools/tooling/release/cohort_verify.py",
        "release-tools/verify-cohort.py",
    )
    for relative in verifier_paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {relative}\n")
        inputs.append(target)
    backend = root / "backend.tar"
    web = root / "web.tar"
    backend.write_text("backend\n")
    web.write_text("web\n")
    inputs.extend((backend, web))
    for name, packages in (
        ("ditto-backend.spdx.json", [{"SPDXID": "SPDXRef-Backend", "name": "backend"}]),
        (
            "ditto-web.spdx.json",
            [
                {
                    "SPDXID": "SPDXRef-Ditto-Web-Artifact",
                    "name": "web",
                    "checksums": [
                        {
                            "algorithm": "SHA256",
                            "checksumValue": hashlib.sha256(
                                web.read_bytes()
                            ).hexdigest(),
                        }
                    ],
                }
            ],
        ),
    ):
        sbom = root / name
        sbom.write_text(
            json.dumps(
                {
                    "spdxVersion": "SPDX-2.3",
                    "packages": packages,
                    "documentDescribes": [packages[0]["SPDXID"]],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        inputs.append(sbom)
    policy_root = root / "release-inputs" / "contracts" / "cohorts"
    policy_root.mkdir(parents=True)
    inputs.extend(_write_policy(policy_root, _document()))
    contract_sha256 = hashlib.sha256(contract.read_bytes()).hexdigest()
    identity = _identity(contract_sha256=contract_sha256)
    manifest = build_cohort_manifest(
        workspace_root=root,
        artifact_paths=inputs,
        backend_artifact_path=backend,
        web_artifact_path=web,
        release=ReleaseCoordinates(
            product_version=identity["product_version"],
            git_sha=identity["git_sha"],
            api_contract_version=identity["api_contract_version"],
            api_contract_sha256=identity["api_contract_sha256"],
            generated_at="2026-09-05T00:00:00Z",
        ),
    )
    manifest_path = root / "release-cohort.json"
    write_cohort_manifest(manifest_path, manifest, artifact_paths=inputs)
    return manifest_path, identity


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


def test_release_manifest_can_register_one_real_previous_cohort(
    tmp_path: Path,
) -> None:
    policy, digest = _write_policy(tmp_path, _document())
    cohort_root = tmp_path / "cohort"
    release_manifest, identity = _write_portable_manifest(cohort_root)
    output_policy = tmp_path / "next" / "compatibility-policy.json"
    output_digest = tmp_path / "next" / "compatibility-policy.sha256"

    register_previous_release(
        policy,
        digest,
        release_manifest,
        output_policy,
        output_digest,
    )

    loaded = load_compatibility_policy(output_policy, output_digest)
    assert loaded.previous == (identity,)


def test_registration_rejects_a_release_manifest_with_a_false_cohort_id(
    tmp_path: Path,
) -> None:
    policy, digest = _write_policy(tmp_path, _document())
    cohort_root = tmp_path / "cohort"
    release_manifest, _ = _write_portable_manifest(cohort_root)
    manifest = json.loads(release_manifest.read_text(encoding="utf-8"))
    manifest["cohort_id"] = "0" * 64
    release_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CompatibilityPolicyError, match="cohort_id"):
        register_previous_release(
            policy,
            digest,
            release_manifest,
            tmp_path / "output.json",
            tmp_path / "output.sha256",
        )


def test_registration_fails_closed_when_a_bound_artifact_was_tampered(
    tmp_path: Path,
) -> None:
    policy, digest = _write_policy(tmp_path, _document())
    cohort_root = tmp_path / "cohort"
    cohort_root.mkdir()
    release_manifest, _ = _write_portable_manifest(cohort_root)
    (cohort_root / "web.tar").write_text("tampered\n")

    with pytest.raises(CompatibilityPolicyError, match=r"verification|SHA-256"):
        register_previous_release(
            policy,
            digest,
            release_manifest,
            tmp_path / "output.json",
            tmp_path / "output.sha256",
        )


def test_registration_uses_manifest_parent_or_an_explicit_workspace_root(
    tmp_path: Path,
) -> None:
    policy, digest = _write_policy(tmp_path, _document())
    cohort_root = tmp_path / "cohort"
    release_manifest, identity = _write_portable_manifest(cohort_root)
    nested_manifest = cohort_root / "manifests" / release_manifest.name
    nested_manifest.parent.mkdir()
    release_manifest.replace(nested_manifest)

    with pytest.raises(CompatibilityPolicyError, match="verification"):
        register_previous_release(
            policy,
            digest,
            nested_manifest,
            tmp_path / "default-root.json",
            tmp_path / "default-root.sha256",
        )

    output_policy = tmp_path / "explicit-root.json"
    output_digest = tmp_path / "explicit-root.sha256"
    register_previous_release(
        policy,
        digest,
        nested_manifest,
        output_policy,
        output_digest,
        workspace_root=cohort_root,
    )

    assert load_compatibility_policy(output_policy, output_digest).previous == (
        identity,
    )


def test_registration_uses_the_identity_from_the_verified_manifest_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    policy, digest = _write_policy(tmp_path, _document())
    cohort_root = tmp_path / "cohort"
    release_manifest, verified_identity = _write_portable_manifest(cohort_root)
    replacement = json.loads(release_manifest.read_text(encoding="utf-8"))
    replacement_identity = dict(replacement["release"])
    replacement_identity["product_version"] = "2.0.0"
    replacement_identity["git_sha"] = "c" * 40
    replacement["release"] = replacement_identity
    unsigned = {key: value for key, value in replacement.items() if key != "cohort_id"}
    replacement["cohort_id"] = hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    replacement_payload = (
        json.dumps(replacement, indent=2, sort_keys=True).encode() + b"\n"
    )
    real_verify = policy_module.verify_cohort_manifest

    def verify_then_replace(
        *, workspace_root: Path, manifest_path: Path
    ) -> CohortManifest:
        verified = real_verify(
            workspace_root=workspace_root,
            manifest_path=manifest_path,
        )
        release_manifest.write_bytes(replacement_payload)
        return verified

    monkeypatch.setattr(
        policy_module,
        "verify_cohort_manifest",
        verify_then_replace,
    )
    output_policy = tmp_path / "snapshot-policy.json"
    output_digest = tmp_path / "snapshot-policy.sha256"

    register_previous_release(
        policy,
        digest,
        release_manifest,
        output_policy,
        output_digest,
    )

    assert load_compatibility_policy(output_policy, output_digest).previous == (
        verified_identity,
    )


def test_registration_rejects_boolean_release_schema_version(tmp_path: Path) -> None:
    policy, digest = _write_policy(tmp_path, _document())
    unsigned: dict[str, object] = {
        "schema": "ditto.release-cohort",
        "schema_version": True,
        "generated_at": "2026-09-04T00:00:00Z",
        "release": _identity(),
        "backend_artifact": {"path": "backend", "sha256": "c" * 64},
        "web_artifact": {"path": "web", "sha256": "d" * 64},
        "artifacts": [],
    }
    manifest = {
        **unsigned,
        "cohort_id": hashlib.sha256(
            json.dumps(
                unsigned,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest(),
    }
    release_manifest = tmp_path / "release-cohort.json"
    release_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CompatibilityPolicyError, match="schema"):
        register_previous_release(
            policy,
            digest,
            release_manifest,
            tmp_path / "output.json",
            tmp_path / "output.sha256",
        )
