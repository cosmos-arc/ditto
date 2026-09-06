"""Contract tests for the pinned, offline oasdiff wrapper."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from tooling.contracts import oasdiff

_LEGACY_BACKEND_COMMIT = "0b0b61f17df972989de79e212fc1982f05388495"
_LEGACY_BASELINE_SHA256 = (
    "acaf611b4ae849f9adea6c13ea17139103f839ef94caa3a3f167f331a65f8a2e"
)
_HTTP_VALIDATION_ERROR_REF = "#/components/schemas/HTTPValidationError"
_ERROR_RESPONSE_REF = "#/components/schemas/ErrorResponse"
_HTTP_METHODS = frozenset(
    {"delete", "get", "head", "options", "patch", "post", "put", "trace"}
)


def _git(repo: Path, *args: str) -> str:
    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(  # noqa: S603 -- test-only resolved git executable
        [git, *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _legacy_baseline() -> bytes:
    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(  # noqa: S603 -- immutable in-repository fixture
        [
            git,
            "show",
            f"{_LEGACY_BACKEND_COMMIT}:docs/openapi/v1.json",
        ],
        cwd=oasdiff._REPO_ROOT,
        check=True,
        capture_output=True,
    )
    assert hashlib.sha256(result.stdout).hexdigest() == _LEGACY_BASELINE_SHA256
    return result.stdout


def _operation_response_refs(schema: object, *, status: str) -> list[str]:
    assert isinstance(schema, dict)
    paths = schema["paths"]
    assert isinstance(paths, dict)
    refs: list[str] = []
    for path_item in paths.values():
        assert isinstance(path_item, dict)
        for method, operation in path_item.items():
            if method not in _HTTP_METHODS:
                continue
            assert isinstance(operation, dict)
            responses = operation.get("responses", {})
            assert isinstance(responses, dict)
            response = responses.get(status)
            if not isinstance(response, dict):
                continue
            content = response.get("content")
            if not isinstance(content, dict):
                continue
            media_type = content.get("application/json")
            if not isinstance(media_type, dict):
                continue
            response_schema = media_type.get("schema")
            if not isinstance(response_schema, dict):
                continue
            ref = response_schema.get("$ref")
            if isinstance(ref, str):
                refs.append(ref)
    return refs


def test_exact_legacy_validation_erratum_is_narrow_and_auditable() -> None:
    payload = _legacy_baseline()
    before = json.loads(payload)

    prepared = oasdiff.prepare_baseline_contract(payload)

    assert prepared.source_sha256 == _LEGACY_BASELINE_SHA256
    assert prepared.applied_erratum_id == "legacy-runtime-error-envelope-v1"
    assert prepared.corrected_responses == 169
    assert prepared.contract_bytes != payload
    after = json.loads(prepared.contract_bytes)
    assert (
        _operation_response_refs(before, status="422")
        == [_HTTP_VALIDATION_ERROR_REF] * 169
    )
    assert _operation_response_refs(after, status="422") == [_ERROR_RESPONSE_REF] * 169
    before_schemas = before["components"]["schemas"]
    after_schemas = after["components"]["schemas"]
    assert "ErrorResponse" not in before_schemas
    assert "ErrorResponse" in after_schemas
    assert "HTTPValidationError" not in after_schemas
    assert "ValidationError" not in after_schemas
    error_response_bytes = json.dumps(
        after_schemas["ErrorResponse"],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    assert hashlib.sha256(error_response_bytes).hexdigest() == (
        "3cd5c1437465d27460e2efe67c8d9221b364629a12678b2d9204bae71daf2613"
    )
    unchanged_before = dict(before_schemas)
    unchanged_after = dict(after_schemas)
    del unchanged_before["HTTPValidationError"]
    del unchanged_before["ValidationError"]
    del unchanged_after["ErrorResponse"]
    assert unchanged_after == unchanged_before
    audit = prepared.erratum_audit_result()
    assert audit is not None
    assert audit["sourceSha256"] == _LEGACY_BASELINE_SHA256
    assert audit["corrected422Responses"] == 169
    assert audit["effectiveSha256"] == prepared.effective_sha256
    assert "runtime" in str(audit["reason"])


def test_unknown_baseline_hash_is_not_modified() -> None:
    payload = b'{"openapi":"3.1.0","info":{"title":"T","version":"1"},"paths":{}}\n'

    prepared = oasdiff.prepare_baseline_contract(payload)

    assert prepared.contract_bytes == payload
    assert prepared.applied_erratum_id is None
    assert prepared.corrected_responses == 0
    assert prepared.erratum_audit_result() is None


def test_known_legacy_hash_with_structural_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = json.loads(_legacy_baseline())
    del schema["paths"]["/api/v1/agent/approvals"]["get"]["responses"]["422"]
    drifted = json.dumps(schema, sort_keys=True).encode()
    monkeypatch.setattr(
        oasdiff,
        "_payload_sha256",
        lambda _payload: _LEGACY_BASELINE_SHA256,
    )

    with pytest.raises(oasdiff.OasdiffError, match=r"erratum.*169"):
        oasdiff.prepare_baseline_contract(drifted)


def test_known_legacy_hash_with_operation_path_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = json.loads(_legacy_baseline())
    schema["paths"]["/api/v1/drifted-approvals"] = schema["paths"].pop(
        "/api/v1/agent/approvals"
    )
    drifted = json.dumps(schema, sort_keys=True).encode()
    monkeypatch.setattr(
        oasdiff,
        "_payload_sha256",
        lambda _payload: _LEGACY_BASELINE_SHA256,
    )

    with pytest.raises(oasdiff.OasdiffError, match=r"operation-set mismatch"):
        oasdiff.prepare_baseline_contract(drifted)


def test_known_legacy_hash_with_component_schema_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = json.loads(_legacy_baseline())
    schema["components"]["schemas"]["HTTPValidationError"]["title"] = "Drifted"
    drifted = json.dumps(schema, sort_keys=True).encode()
    monkeypatch.setattr(
        oasdiff,
        "_payload_sha256",
        lambda _payload: _LEGACY_BASELINE_SHA256,
    )

    with pytest.raises(oasdiff.OasdiffError, match=r"schema mismatch"):
        oasdiff.prepare_baseline_contract(drifted)


def test_merge_base_without_canonical_contract_is_explicit_no_baseline(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Contract Test")
    _git(tmp_path, "config", "user.email", "contract@example.invalid")
    (tmp_path / "README.md").write_text("initial\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-qm", "initial")

    resolution = oasdiff.resolve_merge_base(
        repo_root=tmp_path,
        base_ref="HEAD",
    )

    assert resolution.status == "no-baseline"
    assert resolution.contract_bytes is None
    assert "contracts/openapi/v1.json" in resolution.reason


def test_merge_base_without_common_ancestor_fails_closed(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Contract Test")
    _git(tmp_path, "config", "user.email", "contract@example.invalid")
    (tmp_path / "base.txt").write_text("base\n", encoding="utf-8")
    _git(tmp_path, "add", "base.txt")
    _git(tmp_path, "commit", "-qm", "base history")
    _git(tmp_path, "tag", "base-history")
    _git(tmp_path, "switch", "--orphan", "unrelated")
    (tmp_path / "unrelated.txt").write_text("unrelated\n", encoding="utf-8")
    _git(tmp_path, "add", "unrelated.txt")
    _git(tmp_path, "commit", "-qm", "unrelated history")

    with pytest.raises(oasdiff.OasdiffError, match="cannot resolve merge base"):
        oasdiff.resolve_merge_base(
            repo_root=tmp_path,
            base_ref="base-history",
        )


def test_merge_base_command_failure_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Contract Test")
    _git(tmp_path, "config", "user.email", "contract@example.invalid")
    (tmp_path / "README.md").write_text("initial\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-qm", "initial")
    original_git = oasdiff._git

    def fail_merge_base(
        repo_root: Path,
        *arguments: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        if arguments and arguments[0] == "merge-base":
            command = ["git", *arguments]
            return subprocess.CompletedProcess(
                command,
                returncode=128,
                stdout=b"",
                stderr=b"fatal: shallow history cannot resolve merge base\n",
            )
        return original_git(repo_root, *arguments, check=check)

    monkeypatch.setattr(oasdiff, "_git", fail_merge_base)

    with pytest.raises(
        oasdiff.OasdiffError,
        match="shallow history cannot resolve merge base",
    ):
        oasdiff.resolve_merge_base(repo_root=tmp_path, base_ref="HEAD")


def test_merge_base_uses_approved_legacy_contract_during_path_migration(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Contract Test")
    _git(tmp_path, "config", "user.email", "contract@example.invalid")
    legacy = tmp_path / "docs/openapi/v1.json"
    legacy.parent.mkdir(parents=True)
    payload = (
        b'{"openapi":"3.1.0","info":{"title":"Legacy","version":"1"},"paths":{}}\n'
    )
    legacy.write_bytes(payload)
    _git(tmp_path, "add", "docs/openapi/v1.json")
    _git(tmp_path, "commit", "-qm", "legacy contract")

    resolution = oasdiff.resolve_merge_base(
        repo_root=tmp_path,
        base_ref="HEAD",
    )

    assert resolution.status == "found"
    assert resolution.contract_bytes == payload
    assert "docs/openapi/v1.json" in resolution.reason


def test_release_uses_approved_legacy_contract_during_path_migration(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Contract Test")
    _git(tmp_path, "config", "user.email", "contract@example.invalid")
    legacy = tmp_path / "docs/openapi/v1.json"
    legacy.parent.mkdir(parents=True)
    payload = (
        b'{"openapi":"3.1.0","info":{"title":"Legacy","version":"1"},"paths":{}}\n'
    )
    legacy.write_bytes(payload)
    _git(tmp_path, "add", "docs/openapi/v1.json")
    _git(tmp_path, "commit", "-qm", "legacy release contract")
    _git(tmp_path, "tag", "v0.9.0")

    resolution = oasdiff.resolve_release(repo_root=tmp_path)

    assert resolution.status == "found"
    assert resolution.ref == "v0.9.0"
    assert resolution.contract_bytes == payload
    assert "docs/openapi/v1.json" in resolution.reason


def test_release_uses_latest_reachable_tag_without_stale_fallback(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Contract Test")
    _git(tmp_path, "config", "user.email", "contract@example.invalid")
    contract = tmp_path / "contracts/openapi/v1.json"
    contract.parent.mkdir(parents=True)
    contract.write_text('{"openapi":"3.1.0"}\n', encoding="utf-8")
    _git(tmp_path, "add", "contracts/openapi/v1.json")
    _git(tmp_path, "commit", "-qm", "release with contract")
    _git(tmp_path, "tag", "v1.0.0")
    contract.unlink()
    _git(tmp_path, "add", "-u")
    _git(tmp_path, "commit", "-qm", "latest release without contract")
    _git(tmp_path, "tag", "v2.0.0")

    resolution = oasdiff.resolve_release(repo_root=tmp_path)

    assert resolution.status == "no-baseline"
    assert resolution.ref == "v2.0.0"
    assert "v2.0.0" in resolution.reason


def test_tampered_checksum_manifest_is_rejected_before_archive(
    tmp_path: Path,
) -> None:
    checksums = tmp_path / "checksums.txt"
    checksums.write_text("not trusted\n", encoding="utf-8")
    expected = hashlib.sha256(b"trusted manifest\n").hexdigest()

    with pytest.raises(oasdiff.SupplyChainError, match=r"checksums\.txt SHA-256"):
        oasdiff.verify_release_archive(
            dist_dir=tmp_path,
            asset_name="oasdiff_1.28.0_linux_amd64.tar.gz",
            expected_manifest_sha256=expected,
        )


def test_release_archive_is_accepted_only_through_trusted_manifest(
    tmp_path: Path,
) -> None:
    asset_name = "oasdiff_1.28.0_linux_amd64.tar.gz"
    archive = tmp_path / asset_name
    archive.write_bytes(b"verified archive payload")
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest_payload = f"{archive_sha}  {asset_name}\n".encode()
    (tmp_path / "checksums.txt").write_bytes(manifest_payload)

    verified = oasdiff.verify_release_archive(
        dist_dir=tmp_path,
        asset_name=asset_name,
        expected_manifest_sha256=hashlib.sha256(manifest_payload).hexdigest(),
    )

    assert verified == archive


def test_breaking_check_fails_on_warnings_without_loading_repo_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = b'{"openapi":"3.1.0","info":{"title":"T","version":"1"},"paths":{}}'
    current = tmp_path / "current.json"
    current.write_bytes(schema)
    resolution = oasdiff.BaselineResolution(
        kind="merge-base",
        status="found",
        ref="main",
        commit="a" * 40,
        reason="test baseline",
        contract_bytes=schema,
    )
    observed: dict[str, object] = {}

    @contextmanager
    def fake_verified_oasdiff(_dist_dir: Path) -> Iterator[Path]:
        yield tmp_path / "oasdiff"

    def fake_run(
        command: list[str],
        **options: object,
    ) -> subprocess.CompletedProcess[bytes]:
        observed["command"] = command
        observed["cwd"] = options["cwd"]
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(oasdiff, "verified_oasdiff", fake_verified_oasdiff)
    monkeypatch.setattr(oasdiff.subprocess, "run", fake_run)

    assert (
        oasdiff.run_breaking_check(
            resolution=resolution,
            current_path=current,
            dist_dir=tmp_path,
        )
        == 0
    )

    command = observed["command"]
    assert isinstance(command, list)
    assert command[command.index("--fail-on") + 1] == "WARN"
    assert observed["cwd"] != oasdiff._REPO_ROOT


def test_breaking_check_compares_the_erratum_normalized_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    legacy = _legacy_baseline()
    current = tmp_path / "current.json"
    current.write_bytes(legacy)
    resolution = oasdiff.BaselineResolution(
        kind="merge-base",
        status="found",
        ref="main",
        commit=_LEGACY_BACKEND_COMMIT,
        reason="legacy baseline",
        contract_bytes=legacy,
    )
    observed: dict[str, bytes] = {}

    @contextmanager
    def fake_verified_oasdiff(_dist_dir: Path) -> Iterator[Path]:
        yield tmp_path / "oasdiff"

    def fake_run(
        command: list[str],
        **_options: object,
    ) -> subprocess.CompletedProcess[bytes]:
        observed["baseline"] = Path(command[2]).read_bytes()
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(oasdiff, "verified_oasdiff", fake_verified_oasdiff)
    monkeypatch.setattr(oasdiff.subprocess, "run", fake_run)

    assert (
        oasdiff.run_breaking_check(
            resolution=resolution,
            current_path=current,
            dist_dir=tmp_path,
        )
        == 0
    )

    compared = json.loads(observed["baseline"])
    assert (
        _operation_response_refs(compared, status="422") == [_ERROR_RESPONSE_REF] * 169
    )
    audit = capsys.readouterr().err
    assert '"event": "openapi-baseline-erratum"' in audit
    assert f'"sourceSha256": "{_LEGACY_BASELINE_SHA256}"' in audit


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Darwin", "arm64", "oasdiff_1.28.0_darwin_all.tar.gz"),
        ("Darwin", "x86_64", "oasdiff_1.28.0_darwin_all.tar.gz"),
        ("Linux", "x86_64", "oasdiff_1.28.0_linux_amd64.tar.gz"),
        ("Linux", "aarch64", "oasdiff_1.28.0_linux_arm64.tar.gz"),
        ("Windows", "AMD64", "oasdiff_1.28.0_windows_amd64.tar.gz"),
    ],
)
def test_release_asset_selection_is_platform_specific(
    system: str,
    machine: str,
    expected: str,
) -> None:
    assert oasdiff.release_asset_name(system=system, machine=machine) == expected
