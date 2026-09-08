"""Adversarial tests for offline release-cohort verification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from tooling.release.cohort_manifest import (
    ReleaseCoordinates,
    build_cohort_manifest,
    write_cohort_manifest,
)
from tooling.release.cohort_verify import (
    CohortVerificationError,
    main,
    verify_cohort_manifest,
)
from tooling.release.tests.image_fixture import write_image

_VERIFIER_ARTIFACTS = (
    "release-tools/tooling/__init__.py",
    "release-tools/tooling/release/__init__.py",
    "release-tools/tooling/release/cohort_manifest.py",
    "release-tools/tooling/release/cohort_verify.py",
    "release-tools/tooling/release/environment_identity.py",
    "release-tools/verify-cohort.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_write(path: Path, document: dict[str, object]) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _recompute_cohort_id(document: dict[str, object]) -> None:
    unsigned = {key: value for key, value in document.items() if key != "cohort_id"}
    document["cohort_id"] = hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def _portable_cohort(root: Path) -> tuple[Path, dict[str, object]]:
    contract = root / "release-inputs" / "contracts" / "openapi" / "v1.json"
    uv_lock = root / "release-inputs" / "uv.lock"
    bun_lock = root / "release-inputs" / "bun.lock"
    interpreter = root / "release-inputs" / ".python-version"
    source = root / "release-inputs" / "Dockerfile"
    backend = root / "ditto-image.tar"
    web = root / "ditto-web.tar"
    backend_sbom = root / "ditto-backend.spdx.json"
    web_sbom = root / "ditto-web.spdx.json"
    policy = (
        root / "release-inputs" / "contracts" / "cohorts" / "compatibility-policy.json"
    )
    policy_digest = policy.with_suffix(".sha256")
    contract.parent.mkdir(parents=True)
    contract.write_bytes(b'{"openapi":"3.1.0"}\n')
    uv_lock.write_bytes(b"uv-lock\n")
    interpreter.write_text("cpython-3.13.14")
    source.write_text("FROM python@sha256:fixture")
    bun_lock.write_bytes(b"bun-lock\n")
    write_image(backend, root / "release-inputs")
    web.write_bytes(b"immutable-web")
    _canonical_write(
        backend_sbom,
        {
            "SPDXID": "SPDXRef-DOCUMENT",
            "packages": [{"SPDXID": "SPDXRef-Backend", "name": "ditto-backend"}],
            "spdxVersion": "SPDX-2.3",
        },
    )
    _canonical_write(
        web_sbom,
        {
            "SPDXID": "SPDXRef-DOCUMENT",
            "documentDescribes": ["SPDXRef-Ditto-Web-Artifact"],
            "packages": [
                {
                    "SPDXID": "SPDXRef-Ditto-Web-Artifact",
                    "checksums": [
                        {
                            "algorithm": "SHA256",
                            "checksumValue": _sha256(web),
                        }
                    ],
                    "name": "@ditto/web-artifact",
                }
            ],
            "spdxVersion": "SPDX-2.3",
        },
    )
    policy.parent.mkdir(parents=True, exist_ok=True)
    _canonical_write(
        policy,
        {
            "api_contract_version": "v1",
            "current": {"source": "web_build"},
            "previous": [],
            "schema": "ditto.cohort-compatibility-policy",
            "schema_version": 1,
        },
    )
    policy_digest.write_text(
        f"{_sha256(policy)}  compatibility-policy.json\n",
        encoding="utf-8",
    )
    verifier_files: list[Path] = []
    for relative in _VERIFIER_ARTIFACTS:
        verifier_file = root / relative
        verifier_file.parent.mkdir(parents=True, exist_ok=True)
        verifier_file.write_text(f"# {relative}\n")
        verifier_files.append(verifier_file)
    artifacts = (
        contract,
        uv_lock,
        interpreter,
        source,
        bun_lock,
        backend,
        web,
        backend_sbom,
        web_sbom,
        policy,
        policy_digest,
        *verifier_files,
    )
    manifest = build_cohort_manifest(
        workspace_root=root,
        artifact_paths=artifacts,
        backend_artifact_path=backend,
        web_artifact_path=web,
        release=ReleaseCoordinates(
            product_version="1.2.3",
            git_sha="a" * 40,
            api_contract_version="v1",
            api_contract_sha256=_sha256(contract),
            generated_at="2026-09-05T00:00:00Z",
        ),
    )
    manifest_path = root / "release-cohort.json"
    write_cohort_manifest(manifest_path, manifest, artifact_paths=artifacts)
    return manifest_path, json.loads(manifest_path.read_text(encoding="utf-8"))


def _mutate_manifest(
    manifest_path: Path,
    mutation: Callable[[dict[str, object]], None],
    *,
    recompute_id: bool = True,
) -> None:
    document: dict[str, object] = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutation(document)
    if recompute_id:
        _recompute_cohort_id(document)
    _canonical_write(manifest_path, document)


def _artifacts(document: dict[str, object]) -> list[dict[str, object]]:
    value = document["artifacts"]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return value


def _release(document: dict[str, object]) -> dict[str, object]:
    value = document["release"]
    assert isinstance(value, dict)
    return value


def _backend(document: dict[str, object]) -> dict[str, object]:
    value = document["backend_artifact"]
    assert isinstance(value, dict)
    return value


def _web(document: dict[str, object]) -> dict[str, object]:
    value = document["web_artifact"]
    assert isinstance(value, dict)
    return value


def _refresh_artifact_record(
    manifest_path: Path,
    document: dict[str, object],
    relative_path: str,
) -> None:
    artifact = manifest_path.parent / relative_path
    for record in _artifacts(document):
        if record["path"] == relative_path:
            record["sha256"] = _sha256(artifact)
            record["size_bytes"] = artifact.stat().st_size
            _recompute_cohort_id(document)
            _canonical_write(manifest_path, document)
            return
    raise AssertionError(f"missing fixture artifact: {relative_path}")


def test_verifier_accepts_a_self_contained_offline_cohort(tmp_path: Path) -> None:
    manifest_path, expected = _portable_cohort(tmp_path)

    verified = verify_cohort_manifest(
        workspace_root=tmp_path,
        manifest_path=manifest_path,
    )

    assert verified == expected
    assert all(
        not Path(record["path"]).is_absolute() for record in verified["artifacts"]
    )


def test_verifier_requires_both_canonical_sboms(tmp_path: Path) -> None:
    for missing in ("ditto-backend.spdx.json", "ditto-web.spdx.json"):
        root = tmp_path / missing.removesuffix(".spdx.json")
        root.mkdir()
        manifest_path, _ = _portable_cohort(root)

        def drop_sbom(document: dict[str, object], missing: str = missing) -> None:
            records = _artifacts(document)
            records[:] = [record for record in records if record["path"] != missing]

        _mutate_manifest(manifest_path, drop_sbom)
        with pytest.raises(CohortVerificationError, match="SBOM"):
            verify_cohort_manifest(
                workspace_root=root,
                manifest_path=manifest_path,
            )

    root = tmp_path / "noncanonical"
    root.mkdir()
    manifest_path, document = _portable_cohort(root)
    web_sbom = root / "ditto-web.spdx.json"
    web_sbom.write_text(
        json.dumps(json.loads(web_sbom.read_text(encoding="utf-8"))),
        encoding="utf-8",
    )
    _refresh_artifact_record(manifest_path, document, "ditto-web.spdx.json")
    with pytest.raises(CohortVerificationError, match="canonical"):
        verify_cohort_manifest(workspace_root=root, manifest_path=manifest_path)


def test_web_sbom_subject_must_bind_the_web_tar_digest(tmp_path: Path) -> None:
    manifest_path, document = _portable_cohort(tmp_path)
    web_sbom = tmp_path / "ditto-web.spdx.json"
    sbom = json.loads(web_sbom.read_text(encoding="utf-8"))
    sbom["packages"][0]["checksums"][0]["checksumValue"] = "0" * 64
    _canonical_write(web_sbom, sbom)
    _refresh_artifact_record(manifest_path, document, "ditto-web.spdx.json")

    with pytest.raises(CohortVerificationError, match=r"Web SBOM.*digest"):
        verify_cohort_manifest(
            workspace_root=tmp_path,
            manifest_path=manifest_path,
        )


def test_compatibility_policy_and_sidecar_are_required_and_bound(
    tmp_path: Path,
) -> None:
    manifest_path, document = _portable_cohort(tmp_path)
    sidecar_path = "release-inputs/contracts/cohorts/compatibility-policy.sha256"
    sidecar = tmp_path / sidecar_path
    sidecar.write_text(
        f"{'0' * 64}  compatibility-policy.json\n",
        encoding="utf-8",
    )
    _refresh_artifact_record(manifest_path, document, sidecar_path)

    with pytest.raises(CohortVerificationError, match="sidecar"):
        verify_cohort_manifest(
            workspace_root=tmp_path,
            manifest_path=manifest_path,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda document: document.__setitem__("unexpected", True), "fields"),
        (lambda document: document.pop("generated_at"), "fields"),
        (
            lambda document: _release(document).__setitem__("unexpected", True),
            "release fields",
        ),
        (
            lambda document: _release(document).pop("product_version"),
            "release fields",
        ),
        (
            lambda document: _artifacts(document)[0].__setitem__("unexpected", True),
            "artifact.*fields",
        ),
        (
            lambda document: _artifacts(document)[0].pop("size_bytes"),
            "artifact.*fields",
        ),
        (lambda document: document.__setitem__("schema_version", True), "version"),
        (
            lambda document: _release(document).__setitem__(
                "product_version", "v1.2.3"
            ),
            "SemVer",
        ),
        (
            lambda document: _release(document).__setitem__("git_sha", "main"),
            "Git SHA",
        ),
    ],
)
def test_verifier_rejects_non_exact_schema_and_identity(
    tmp_path: Path,
    mutation: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    manifest_path, _ = _portable_cohort(tmp_path)
    _mutate_manifest(manifest_path, mutation)

    with pytest.raises(CohortVerificationError, match=message):
        verify_cohort_manifest(workspace_root=tmp_path, manifest_path=manifest_path)


def test_verifier_rejects_a_false_cohort_id(tmp_path: Path) -> None:
    manifest_path, _ = _portable_cohort(tmp_path)
    _mutate_manifest(
        manifest_path,
        lambda document: document.__setitem__("cohort_id", "0" * 64),
        recompute_id=False,
    )

    with pytest.raises(CohortVerificationError, match="cohort_id"):
        verify_cohort_manifest(workspace_root=tmp_path, manifest_path=manifest_path)


def test_verifier_rejects_backend_or_web_summaries_that_disagree_with_artifacts(
    tmp_path: Path,
) -> None:
    for field, helper in (("backend", _backend), ("Web", _web)):
        cohort_root = tmp_path / field
        cohort_root.mkdir()
        manifest_path, _ = _portable_cohort(cohort_root)
        _mutate_manifest(
            manifest_path,
            lambda document, helper=helper: helper(document).__setitem__(
                "sha256", "0" * 64
            ),
        )

        with pytest.raises(CohortVerificationError, match=f"{field} artifact"):
            verify_cohort_manifest(
                workspace_root=cohort_root,
                manifest_path=manifest_path,
            )


def test_contract_digest_must_bind_the_versioned_contract_artifact(
    tmp_path: Path,
) -> None:
    manifest_path, document = _portable_cohort(tmp_path)
    web_sha = str(_web(document)["sha256"])
    _mutate_manifest(
        manifest_path,
        lambda current: _release(current).__setitem__("api_contract_sha256", web_sha),
    )

    with pytest.raises(CohortVerificationError, match="contract digest"):
        verify_cohort_manifest(workspace_root=tmp_path, manifest_path=manifest_path)


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        ("size", "size"),
        ("sha256", "SHA-256"),
        ("media_type", "media type"),
    ],
)
def test_every_artifact_record_is_recomputed_from_disk(
    tmp_path: Path,
    tamper: str,
    message: str,
) -> None:
    manifest_path, _ = _portable_cohort(tmp_path)
    if tamper == "size":
        (tmp_path / "ditto-web.tar").write_bytes(b"different-size")
    elif tamper == "sha256":
        web = tmp_path / "ditto-web.tar"
        payload = web.read_bytes()
        web.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
    else:
        _mutate_manifest(
            manifest_path,
            lambda document: _artifacts(document)[0].__setitem__(
                "media_type", "application/octet-stream"
            ),
        )

    with pytest.raises(CohortVerificationError, match=message):
        verify_cohort_manifest(workspace_root=tmp_path, manifest_path=manifest_path)


def test_artifact_paths_cannot_escape_or_use_noncanonical_separators(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _portable_cohort(tmp_path)
    outside = tmp_path.parent / "outside.tar"
    outside.write_bytes((tmp_path / "ditto-web.tar").read_bytes())
    try:

        def escape(document: dict[str, object]) -> None:
            path = "../outside.tar"
            _web(document)["path"] = path
            for record in _artifacts(document):
                if record["path"] == "ditto-web.tar":
                    record["path"] = path

        _mutate_manifest(manifest_path, escape)
        with pytest.raises(CohortVerificationError, match=r"relative|escape"):
            verify_cohort_manifest(
                workspace_root=tmp_path,
                manifest_path=manifest_path,
            )
    finally:
        outside.unlink()

    for unsafe_path in (
        "/tmp/ditto-web.tar",
        "C:/ditto-web.tar",
        "dir\\ditto-web.tar",
        "a//b",
    ):
        root = tmp_path / hashlib.sha256(unsafe_path.encode()).hexdigest()[:8]
        root.mkdir()
        candidate, _ = _portable_cohort(root)

        def make_unsafe(document: dict[str, object], path: str = unsafe_path) -> None:
            _web(document)["path"] = path
            for record in _artifacts(document):
                if record["path"] == "ditto-web.tar":
                    record["path"] = path

        _mutate_manifest(candidate, make_unsafe)
        with pytest.raises(CohortVerificationError, match="path"):
            verify_cohort_manifest(workspace_root=root, manifest_path=candidate)


def test_verifier_rejects_symlinks_and_non_regular_files(tmp_path: Path) -> None:
    for kind in ("symlink", "directory"):
        root = tmp_path / kind
        root.mkdir()
        manifest_path, _ = _portable_cohort(root)
        web = root / "ditto-web.tar"
        payload = web.read_bytes()
        web.unlink()
        if kind == "symlink":
            target = root / "web-target.tar"
            target.write_bytes(payload)
            web.symlink_to(target)
            message = "symlink"
        else:
            web.mkdir()
            message = "regular file"

        with pytest.raises(CohortVerificationError, match=message):
            verify_cohort_manifest(
                workspace_root=root,
                manifest_path=manifest_path,
            )


def test_verifier_rejects_a_symlink_in_an_artifact_parent_path(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _portable_cohort(tmp_path)
    openapi = tmp_path / "release-inputs" / "contracts" / "openapi"
    target = openapi.with_name("openapi-target")
    openapi.rename(target)
    openapi.symlink_to(target, target_is_directory=True)

    with pytest.raises(CohortVerificationError, match="symlink"):
        verify_cohort_manifest(workspace_root=tmp_path, manifest_path=manifest_path)


def test_verifier_requires_sorted_unique_records_and_all_release_inputs(
    tmp_path: Path,
) -> None:
    def drop_bun_lock(records: list[dict[str, object]]) -> None:
        records[:] = [
            record for record in records if record["path"] != "release-inputs/bun.lock"
        ]

    for mutation, message in (
        (lambda records: records.reverse(), "sorted"),
        (lambda records: records.append(dict(records[-1])), "duplicate"),
        (drop_bun_lock, "release input"),
    ):
        root = tmp_path / message.replace(" ", "-")
        root.mkdir()
        manifest_path, _ = _portable_cohort(root)
        _mutate_manifest(
            manifest_path,
            lambda document, mutation=mutation: mutation(_artifacts(document)),
        )
        with pytest.raises(CohortVerificationError, match=message):
            verify_cohort_manifest(workspace_root=root, manifest_path=manifest_path)


def test_verifier_requires_its_complete_offline_runtime_to_be_hash_bound(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _portable_cohort(tmp_path)

    def drop_entrypoint(document: dict[str, object]) -> None:
        records = _artifacts(document)
        records[:] = [
            record
            for record in records
            if record["path"] != "release-tools/verify-cohort.py"
        ]

    _mutate_manifest(manifest_path, drop_entrypoint)

    with pytest.raises(CohortVerificationError, match="verifier"):
        verify_cohort_manifest(workspace_root=tmp_path, manifest_path=manifest_path)


def test_verifier_requires_canonical_manifest_bytes(tmp_path: Path) -> None:
    manifest_path, document = _portable_cohort(tmp_path)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CohortVerificationError, match="canonical"):
        verify_cohort_manifest(workspace_root=tmp_path, manifest_path=manifest_path)


def test_cli_verifies_paths_relative_to_an_extracted_cohort(tmp_path: Path) -> None:
    manifest_path, _ = _portable_cohort(tmp_path)

    assert (
        main(["--workspace-root", str(tmp_path), "--manifest", manifest_path.name]) == 0
    )


def test_fixture_media_types_are_platform_deterministic(tmp_path: Path) -> None:
    """Guard the fixed MIME contract shared by generator and verifier."""
    manifest_path, document = _portable_cohort(tmp_path)

    assert manifest_path.is_file()
    by_path = {str(record["path"]): record for record in _artifacts(document)}
    for path in by_path:
        expected = (
            "application/json"
            if path.endswith(".json")
            else "application/x-tar"
            if path.endswith(".tar")
            else "application/octet-stream"
        )
        assert by_path[path]["media_type"] == expected


@pytest.mark.parametrize("name", ["uv.lock", ".python-version", "Dockerfile"])
def test_backend_environment_rejects_rebound_inputs(tmp_path: Path, name: str) -> None:
    manifest_path, document = _portable_cohort(tmp_path)
    relative = "release-inputs/" + name
    with (tmp_path / relative).open("a") as stream:
        stream.write("changed")
    _refresh_artifact_record(manifest_path, document, relative)
    with pytest.raises(CohortVerificationError, match="environment identity"):
        verify_cohort_manifest(workspace_root=tmp_path, manifest_path=manifest_path)
