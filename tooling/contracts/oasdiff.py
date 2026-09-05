"""Run a pinned, checksum-verified, offline oasdiff compatibility check."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from tooling.contracts.generate_web_schema import load_local_schema

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT_RELATIVE_PATH = Path("contracts/openapi/v1.json")
_LEGACY_CONTRACT_RELATIVE_PATH = Path("docs/openapi/v1.json")
_APPROVED_CONTRACT_RELATIVE_PATHS = (
    _CONTRACT_RELATIVE_PATH,
    _LEGACY_CONTRACT_RELATIVE_PATH,
)
_DEFAULT_CURRENT = _REPO_ROOT / _CONTRACT_RELATIVE_PATH
OASDIFF_VERSION = "1.28.0"
OASDIFF_CHECKSUMS_SHA256 = (
    "98d24bf37e5f8d6935765aa3bdd2402c05ca291af236e7825aa4a8bc4f0be589"
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CHECKSUM_FIELD_COUNT = 2
_GIT = shutil.which("git")
_HTTP_METHODS = frozenset(
    {"delete", "get", "head", "options", "patch", "post", "put", "trace"}
)
_LEGACY_VALIDATION_ERRATUM_ID = "legacy-runtime-error-envelope-v1"
_LEGACY_VALIDATION_ERRATUM_REASON = (
    "the legacy FastAPI snapshot auto-documented validation failures as "
    "HTTPValidationError even though the runtime returned ErrorResponse"
)
_LEGACY_VALIDATION_BASELINE_SHA256 = (
    "acaf611b4ae849f9adea6c13ea17139103f839ef94caa3a3f167f331a65f8a2e"
)
_LEGACY_VALIDATION_RESPONSE_COUNT = 169
_LEGACY_VALIDATION_LOCATIONS_SHA256 = (
    "1bebe99f98760842f89f6ba7137c6353e869d51f10d256f96e385e96edb963da"
)
_LEGACY_HTTP_VALIDATION_SCHEMA_SHA256 = (
    "7373c21f1389312367e27e440140ba11d587693c56d8aa27249b36d3f58c10c6"
)
_LEGACY_VALIDATION_ERROR_SCHEMA_SHA256 = (
    "ca285d0c0e64c42844efd2e860edb239e77cc49d87f065c5ccb7d2f55331b862"
)
_HTTP_VALIDATION_ERROR_REF = "#/components/schemas/HTTPValidationError"
_VALIDATION_ERROR_REF = "#/components/schemas/ValidationError"
_ERROR_RESPONSE_REF = "#/components/schemas/ErrorResponse"
_LEGACY_422_RESPONSE: dict[str, object] = {
    "description": "Validation Error",
    "content": {
        "application/json": {
            "schema": {"$ref": _HTTP_VALIDATION_ERROR_REF},
        }
    },
}
_RUNTIME_ERROR_RESPONSE_SCHEMA: dict[str, object] = {
    "description": (
        "Standard error response model for API errors.\n\n"
        "Used for external API responses, so using Pydantic BaseModel "
        "(not frozen dataclass)."
    ),
    "properties": {
        "detail": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "title": "Detail",
        },
        "error": {"title": "Error", "type": "string"},
        "error_code": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "title": "Error Code",
        },
        "request_id": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "title": "Request Id",
        },
        "status_code": {"title": "Status Code", "type": "integer"},
        "success": {
            "const": False,
            "default": False,
            "title": "Success",
            "type": "boolean",
        },
        "timestamp": {
            "anyOf": [{"type": "number"}, {"type": "null"}],
            "title": "Timestamp",
        },
    },
    "required": ["status_code", "error"],
    "title": "ErrorResponse",
    "type": "object",
}


class OasdiffError(RuntimeError):
    """The offline compatibility gate could not execute correctly."""


class SupplyChainError(OasdiffError):
    """Pinned release material failed integrity verification."""


@dataclass(frozen=True)
class BaselineResolution:
    """A found contract baseline or an explicit first-introduction result."""

    kind: Literal["merge-base", "release"]
    status: Literal["found", "no-baseline"]
    ref: str | None
    commit: str | None
    reason: str
    contract_bytes: bytes | None

    def public_result(self) -> dict[str, str | None]:
        """Return stable JSON-safe fields without embedding the contract."""
        return {
            "kind": self.kind,
            "status": self.status,
            "ref": self.ref,
            "commit": self.commit,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PreparedBaseline:
    """Validated baseline bytes plus any narrowly applied historical erratum."""

    contract_bytes: bytes
    source_sha256: str
    effective_sha256: str
    applied_erratum_id: str | None
    corrected_responses: int

    def erratum_audit_result(self) -> dict[str, object] | None:
        """Return deterministic audit evidence when an erratum was applied."""
        if self.applied_erratum_id is None:
            return None
        return {
            "event": "openapi-baseline-erratum",
            "id": self.applied_erratum_id,
            "reason": _LEGACY_VALIDATION_ERRATUM_REASON,
            "sourceSha256": self.source_sha256,
            "effectiveSha256": self.effective_sha256,
            "corrected422Responses": self.corrected_responses,
        }


def _git(
    repo_root: Path,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    if _GIT is None:
        raise OasdiffError("git is required to resolve OpenAPI baselines")
    return subprocess.run(  # noqa: S603 -- resolved git path and argument vector
        [_GIT, *arguments],
        cwd=repo_root,
        check=check,
        capture_output=True,
    )


def _resolve_commit(repo_root: Path, reference: str) -> str:
    if not reference or reference.startswith("-") or "\0" in reference:
        raise OasdiffError(f"unsafe or empty git reference: {reference!r}")
    result = _git(
        repo_root,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{reference}^{{commit}}",
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        raise OasdiffError(f"cannot resolve git reference {reference!r}: {detail}")
    commit = result.stdout.decode().strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit):
        raise OasdiffError(
            f"git returned a non-object id for {reference!r}: {commit!r}"
        )
    return commit


def _contract_at_commit(
    repo_root: Path, commit: str
) -> tuple[Path | None, bytes | None]:
    for relative_path in _APPROVED_CONTRACT_RELATIVE_PATHS:
        object_name = f"{commit}:{relative_path.as_posix()}"
        exists = _git(repo_root, "cat-file", "-e", object_name, check=False)
        if exists.returncode == 0:
            return relative_path, _git(
                repo_root, "cat-file", "blob", object_name
            ).stdout
    return None, None


def resolve_merge_base(*, repo_root: Path, base_ref: str) -> BaselineResolution:
    """Resolve the canonical contract at HEAD's merge base with ``base_ref``."""
    head = _resolve_commit(repo_root, "HEAD")
    base_tip = _resolve_commit(repo_root, base_ref)
    merge_base_result = _git(repo_root, "merge-base", head, base_tip, check=False)
    if merge_base_result.returncode != 0:
        detail = merge_base_result.stderr.decode(errors="replace").strip()
        if not detail:
            detail = "no common ancestor or the available history is incomplete"
        message = (
            f"cannot resolve merge base between HEAD ({head}) and "
            + f"{base_ref!r} ({base_tip}); git merge-base exited "
            + f"{merge_base_result.returncode}: {detail}"
        )
        raise OasdiffError(message)
    commit = merge_base_result.stdout.decode().strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit):
        raise OasdiffError(f"git merge-base returned a non-object id: {commit!r}")
    contract_path, contract = _contract_at_commit(repo_root, commit)
    if contract_path is None or contract is None:
        return BaselineResolution(
            kind="merge-base",
            status="no-baseline",
            ref=base_ref,
            commit=commit,
            reason=(
                f"no approved OpenAPI contract exists at merge base {commit}; checked "
                + ", ".join(
                    path.as_posix() for path in _APPROVED_CONTRACT_RELATIVE_PATHS
                )
            ),
            contract_bytes=None,
        )
    return BaselineResolution(
        kind="merge-base",
        status="found",
        ref=base_ref,
        commit=commit,
        reason=f"merge-base contract found at {contract_path.as_posix()}",
        contract_bytes=contract,
    )


def resolve_release(
    *,
    repo_root: Path,
    release_ref: str | None = None,
) -> BaselineResolution:
    """Resolve an explicit release or the newest reachable ``v*`` contract."""
    if release_ref is not None:
        reference = release_ref
    else:
        tags = _git(
            repo_root,
            "tag",
            "--merged",
            "HEAD",
            "--sort=-version:refname",
            "--list",
            "v[0-9]*",
        )
        reference = next(
            (line for line in tags.stdout.decode().splitlines() if line),
            None,
        )
    if reference is None:
        return BaselineResolution(
            kind="release",
            status="no-baseline",
            ref=None,
            commit=None,
            reason="no reachable v* release tag exists",
            contract_bytes=None,
        )
    commit = _resolve_commit(repo_root, reference)
    contract_path, contract = _contract_at_commit(repo_root, commit)
    if contract_path is not None and contract is not None:
        return BaselineResolution(
            kind="release",
            status="found",
            ref=reference,
            commit=commit,
            reason=f"release contract found at {contract_path.as_posix()}",
            contract_bytes=contract,
        )
    return BaselineResolution(
        kind="release",
        status="no-baseline",
        ref=reference,
        commit=commit,
        reason=(
            f"no approved OpenAPI contract exists at release {reference!r}; checked "
            + ", ".join(path.as_posix() for path in _APPROVED_CONTRACT_RELATIVE_PATHS)
        ),
        contract_bytes=None,
    )


def release_asset_name(*, system: str, machine: str) -> str:
    """Return the exact upstream archive name for one supported platform."""
    normalized_machine = machine.lower()
    architecture = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(normalized_machine)
    if architecture is None:
        raise OasdiffError(f"unsupported oasdiff architecture: {machine}")
    if system == "Darwin":
        platform_name, suffix = "darwin_all", "tar.gz"
    elif system == "Linux":
        platform_name, suffix = f"linux_{architecture}", "tar.gz"
    elif system == "Windows":
        platform_name, suffix = f"windows_{architecture}", "zip"
    else:
        raise OasdiffError(f"unsupported oasdiff operating system: {system}")
    return f"oasdiff_{OASDIFF_VERSION}_{platform_name}.{suffix}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _release_checksums(payload: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in payload.splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) != _CHECKSUM_FIELD_COUNT or not _SHA256_PATTERN.fullmatch(
            fields[0]
        ):
            raise SupplyChainError(f"malformed oasdiff checksums.txt line: {line!r}")
        name = fields[1].lstrip("*")
        if name in checksums:
            raise SupplyChainError(f"duplicate oasdiff checksum entry: {name}")
        checksums[name] = fields[0]
    return checksums


def verify_release_archive(
    *,
    dist_dir: Path,
    asset_name: str,
    expected_manifest_sha256: str = OASDIFF_CHECKSUMS_SHA256,
) -> Path:
    """Verify the pinned upstream manifest, then its selected release archive."""
    manifest = dist_dir / "checksums.txt"
    archive = dist_dir / asset_name
    if not manifest.is_file():
        raise SupplyChainError(f"missing pinned oasdiff checksum manifest: {manifest}")
    actual_manifest_sha256 = _sha256(manifest)
    if actual_manifest_sha256 != expected_manifest_sha256:
        raise SupplyChainError(
            "oasdiff checksums.txt SHA-256 mismatch: "
            + f"expected {expected_manifest_sha256}, found {actual_manifest_sha256}"
        )
    checksums = _release_checksums(manifest.read_text(encoding="utf-8"))
    expected_archive_sha256 = checksums.get(asset_name)
    if expected_archive_sha256 is None:
        raise SupplyChainError(
            f"oasdiff checksum manifest has no entry for {asset_name}"
        )
    if not archive.is_file():
        raise SupplyChainError(f"missing pinned oasdiff release archive: {archive}")
    actual_archive_sha256 = _sha256(archive)
    if actual_archive_sha256 != expected_archive_sha256:
        raise SupplyChainError(
            f"oasdiff archive SHA-256 mismatch for {asset_name}: "
            + f"expected {expected_archive_sha256}, found {actual_archive_sha256}"
        )
    return archive


def _read_binary_from_archive(archive: Path) -> tuple[str, bytes]:
    expected_names = {"oasdiff", "oasdiff.exe"}
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, mode="r:gz") as bundle:
            matches = [
                member
                for member in bundle.getmembers()
                if member.isfile() and Path(member.name).name in expected_names
            ]
            if len(matches) != 1:
                raise SupplyChainError(
                    f"oasdiff archive must contain exactly one binary: {archive}"
                )
            stream = bundle.extractfile(matches[0])
            if stream is None:
                raise SupplyChainError(f"cannot read oasdiff binary from {archive}")
            return Path(matches[0].name).name, stream.read()
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as bundle:
            matches = [
                name
                for name in bundle.namelist()
                if Path(name).name in expected_names and not name.endswith("/")
            ]
            if len(matches) != 1:
                raise SupplyChainError(
                    f"oasdiff archive must contain exactly one binary: {archive}"
                )
            return Path(matches[0]).name, bundle.read(matches[0])
    raise SupplyChainError(f"unsupported oasdiff archive format: {archive}")


def _payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        + b"\n"
    )


def _object_sha256(value: object) -> str:
    canonical = _canonical_json_bytes(value).removesuffix(b"\n")
    return hashlib.sha256(canonical).hexdigest()


def _as_object_mapping(value: object, *, location: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise OasdiffError(f"legacy OpenAPI erratum expected an object at {location}")
    return cast("dict[str, object]", value)


def _child_mapping(
    parent: dict[str, object],
    key: str,
    *,
    location: str,
) -> dict[str, object]:
    try:
        value = parent[key]
    except KeyError as error:
        raise OasdiffError(
            f"legacy OpenAPI erratum expected {location}.{key}"
        ) from error
    return _as_object_mapping(value, location=f"{location}.{key}")


def _reference_locations(
    value: object,
    *,
    reference: str,
    location: tuple[str | int, ...] = (),
) -> list[tuple[str | int, ...]]:
    matches: list[tuple[str | int, ...]] = []
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        for key, child in mapping.items():
            if not isinstance(key, str):
                raise OasdiffError(
                    "legacy OpenAPI erratum encountered a non-string object key"
                )
            child_location = (*location, key)
            if key == "$ref" and child == reference:
                matches.append(child_location)
            matches.extend(
                _reference_locations(
                    child,
                    reference=reference,
                    location=child_location,
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(
                _reference_locations(
                    child,
                    reference=reference,
                    location=(*location, index),
                )
            )
    return matches


def _operation_response(
    operation: dict[str, object],
    *,
    status_code: str,
    location: str,
) -> dict[str, object] | None:
    responses_value = operation.get("responses")
    if not isinstance(responses_value, dict):
        return None
    response_value = cast("dict[str, object]", responses_value).get(status_code)
    if response_value is None:
        return None
    return _as_object_mapping(
        response_value,
        location=f"{location}.responses.{status_code}",
    )


def _application_json_schema_ref(response: dict[str, object]) -> object:
    content = response.get("content")
    if not isinstance(content, dict):
        return None
    media_type = cast("dict[str, object]", content).get("application/json")
    if not isinstance(media_type, dict):
        return None
    response_schema = cast("dict[str, object]", media_type).get("schema")
    if not isinstance(response_schema, dict):
        return None
    return cast("dict[str, object]", response_schema).get("$ref")


def _legacy_validation_locations(
    schema: dict[str, object],
) -> list[tuple[str, str]]:
    paths = _child_mapping(schema, "paths", location="root")
    locations: list[tuple[str, str]] = []
    for path, path_item_value in paths.items():
        path_item = _as_object_mapping(
            path_item_value,
            location=f"paths[{path!r}]",
        )
        for method, operation_value in path_item.items():
            if method not in _HTTP_METHODS:
                continue
            operation = _as_object_mapping(
                operation_value,
                location=f"paths[{path!r}].{method}",
            )
            response = _operation_response(
                operation,
                status_code="422",
                location=f"paths[{path!r}].{method}",
            )
            if (
                response is None
                or _application_json_schema_ref(response) != _HTTP_VALIDATION_ERROR_REF
            ):
                continue
            if response != _LEGACY_422_RESPONSE:
                raise OasdiffError(
                    "legacy OpenAPI erratum found a non-canonical 422 response at "
                    + f"{method.upper()} {path}"
                )
            locations.append((path, method))
    return sorted(locations)


def _validate_legacy_validation_erratum(
    schema: dict[str, object],
) -> list[tuple[str, str]]:
    locations = _legacy_validation_locations(schema)
    if len(locations) != _LEGACY_VALIDATION_RESPONSE_COUNT:
        raise OasdiffError(
            "legacy OpenAPI erratum expected exactly "
            + f"{_LEGACY_VALIDATION_RESPONSE_COUNT} canonical 422 responses, "
            + f"found {len(locations)}"
        )
    locations_sha256 = _object_sha256(locations)
    if locations_sha256 != _LEGACY_VALIDATION_LOCATIONS_SHA256:
        raise OasdiffError(
            "legacy OpenAPI erratum 422 operation-set mismatch: expected SHA-256 "
            + f"{_LEGACY_VALIDATION_LOCATIONS_SHA256}, found {locations_sha256}"
        )

    components = _child_mapping(schema, "components", location="root")
    schemas = _child_mapping(components, "schemas", location="components")
    if "ErrorResponse" in schemas:
        raise OasdiffError(
            "legacy OpenAPI erratum refuses to overwrite an existing ErrorResponse"
        )
    http_validation_schema = schemas.get("HTTPValidationError")
    validation_error_schema = schemas.get("ValidationError")
    if _object_sha256(http_validation_schema) != _LEGACY_HTTP_VALIDATION_SCHEMA_SHA256:
        raise OasdiffError("legacy OpenAPI erratum HTTPValidationError schema mismatch")
    if (
        _object_sha256(validation_error_schema)
        != _LEGACY_VALIDATION_ERROR_SCHEMA_SHA256
    ):
        raise OasdiffError("legacy OpenAPI erratum ValidationError schema mismatch")

    expected_http_locations = {
        (
            "paths",
            path,
            method,
            "responses",
            "422",
            "content",
            "application/json",
            "schema",
            "$ref",
        )
        for path, method in locations
    }
    actual_http_locations = set(
        _reference_locations(schema, reference=_HTTP_VALIDATION_ERROR_REF)
    )
    if actual_http_locations != expected_http_locations:
        raise OasdiffError(
            "legacy OpenAPI erratum HTTPValidationError reference-set mismatch"
        )
    expected_validation_location = {
        (
            "components",
            "schemas",
            "HTTPValidationError",
            "properties",
            "detail",
            "items",
            "$ref",
        )
    }
    actual_validation_locations = set(
        _reference_locations(schema, reference=_VALIDATION_ERROR_REF)
    )
    if actual_validation_locations != expected_validation_location:
        raise OasdiffError(
            "legacy OpenAPI erratum ValidationError reference-set mismatch"
        )
    return locations


def _apply_legacy_validation_erratum(
    schema: dict[str, object],
    locations: list[tuple[str, str]],
) -> bytes:
    normalized = copy.deepcopy(schema)
    paths = _child_mapping(normalized, "paths", location="root")
    for path, method in locations:
        path_item = _child_mapping(paths, path, location="paths")
        operation = _child_mapping(path_item, method, location=f"paths[{path!r}]")
        responses = _child_mapping(
            operation,
            "responses",
            location=f"paths[{path!r}].{method}",
        )
        response = _child_mapping(
            responses,
            "422",
            location=f"paths[{path!r}].{method}.responses",
        )
        content = _child_mapping(
            response,
            "content",
            location=f"paths[{path!r}].{method}.responses.422",
        )
        media_type = _child_mapping(
            content,
            "application/json",
            location=f"paths[{path!r}].{method}.responses.422.content",
        )
        response_schema = _child_mapping(
            media_type,
            "schema",
            location=(
                f"paths[{path!r}].{method}.responses.422.content.application/json"
            ),
        )
        response_schema["$ref"] = _ERROR_RESPONSE_REF

    components = _child_mapping(normalized, "components", location="root")
    schemas = _child_mapping(components, "schemas", location="components")
    del schemas["HTTPValidationError"]
    del schemas["ValidationError"]
    schemas["ErrorResponse"] = copy.deepcopy(_RUNTIME_ERROR_RESPONSE_SCHEMA)
    if _reference_locations(normalized, reference=_HTTP_VALIDATION_ERROR_REF):
        raise OasdiffError(
            "legacy OpenAPI erratum left an HTTPValidationError reference behind"
        )
    if _reference_locations(normalized, reference=_VALIDATION_ERROR_REF):
        raise OasdiffError(
            "legacy OpenAPI erratum left a ValidationError reference behind"
        )
    return _canonical_json_bytes(normalized)


def prepare_baseline_contract(payload: bytes) -> PreparedBaseline:
    """Apply only the hash-bound legacy runtime-envelope correction, if eligible."""
    source_sha256 = _payload_sha256(payload)
    if source_sha256 != _LEGACY_VALIDATION_BASELINE_SHA256:
        return PreparedBaseline(
            contract_bytes=payload,
            source_sha256=source_sha256,
            effective_sha256=source_sha256,
            applied_erratum_id=None,
            corrected_responses=0,
        )
    try:
        loaded: object = json.loads(payload)
    except json.JSONDecodeError as error:
        raise OasdiffError(
            f"legacy OpenAPI erratum baseline is invalid JSON: {error}"
        ) from error
    schema = _as_object_mapping(loaded, location="root")
    locations = _validate_legacy_validation_erratum(schema)
    corrected = _apply_legacy_validation_erratum(schema, locations)
    return PreparedBaseline(
        contract_bytes=corrected,
        source_sha256=source_sha256,
        effective_sha256=_payload_sha256(corrected),
        applied_erratum_id=_LEGACY_VALIDATION_ERRATUM_ID,
        corrected_responses=len(locations),
    )


@contextmanager
def verified_oasdiff(dist_dir: Path) -> Iterator[Path]:
    """Yield the verified pinned binary from a temporary extraction directory."""
    asset_name = release_asset_name(
        system=platform.system(), machine=platform.machine()
    )
    archive = verify_release_archive(dist_dir=dist_dir, asset_name=asset_name)
    binary_name, binary_payload = _read_binary_from_archive(archive)
    with tempfile.TemporaryDirectory(prefix="ditto-oasdiff-") as directory:
        binary = Path(directory) / binary_name
        binary.write_bytes(binary_payload)
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
        version = subprocess.run(  # noqa: S603 -- binary came from verified archive
            [str(binary), "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        version_output = f"{version.stdout}\n{version.stderr}"
        if version.returncode != 0 or OASDIFF_VERSION not in version_output:
            raise SupplyChainError(
                f"verified archive did not report oasdiff {OASDIFF_VERSION}: "
                + version_output.strip()
            )
        yield binary


def _validate_baseline_json(payload: bytes) -> None:
    with tempfile.TemporaryDirectory(prefix="ditto-oasdiff-input-") as directory:
        path = Path(directory) / "baseline.json"
        path.write_bytes(payload)
        load_local_schema(path)


def run_breaking_check(
    *,
    resolution: BaselineResolution,
    current_path: Path,
    dist_dir: Path,
) -> int:
    """Run ``oasdiff breaking`` on local files after all integrity checks."""
    if resolution.status != "found" or resolution.contract_bytes is None:
        raise OasdiffError("cannot run oasdiff without a found baseline")
    load_local_schema(current_path)
    _validate_baseline_json(resolution.contract_bytes)
    prepared = prepare_baseline_contract(resolution.contract_bytes)
    _validate_baseline_json(prepared.contract_bytes)
    erratum_audit = prepared.erratum_audit_result()
    if erratum_audit is not None:
        sys.stderr.write(json.dumps(erratum_audit, sort_keys=True) + "\n")
    with tempfile.TemporaryDirectory(prefix="ditto-oasdiff-baseline-") as directory:
        baseline = Path(directory) / "v1.json"
        baseline.write_bytes(prepared.contract_bytes)
        with verified_oasdiff(dist_dir) as binary:
            result = subprocess.run(  # noqa: S603 -- binary came from verified archive
                [
                    str(binary),
                    "breaking",
                    str(baseline),
                    str(current_path.resolve(strict=True)),
                    "--fail-on",
                    "WARN",
                    "--format",
                    "text",
                ],
                # Avoid implicitly loading a repository-level oasdiff config
                # that could weaken this fixed compatibility policy.
                cwd=baseline.parent,
                check=False,
            )
    return result.returncode


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", choices=("merge-base", "release"), required=True)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--release-ref")
    parser.add_argument("--current", type=Path, default=_DEFAULT_CURRENT)
    parser.add_argument(
        "--dist-dir",
        type=Path,
        help=(
            "directory containing upstream checksums.txt and the pinned release "
            "archive; "
            "defaults to DITTO_OASDIFF_DIST_DIR"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Resolve one baseline, report absence, or run the pinned checker."""
    arguments = _parser().parse_args(argv)
    try:
        if arguments.baseline == "merge-base":
            resolution = resolve_merge_base(
                repo_root=_REPO_ROOT,
                base_ref=arguments.base_ref,
            )
        else:
            resolution = resolve_release(
                repo_root=_REPO_ROOT,
                release_ref=arguments.release_ref,
            )
        sys.stdout.write(json.dumps(resolution.public_result(), sort_keys=True) + "\n")
        if resolution.status == "no-baseline":
            return 0
        dist_dir = arguments.dist_dir
        if dist_dir is None:
            configured = os.environ.get("DITTO_OASDIFF_DIST_DIR")
            if not configured:
                asset = release_asset_name(
                    system=platform.system(),
                    machine=platform.machine(),
                )
                raise OasdiffError(
                    "".join(
                        (
                            "oasdiff baseline exists, but no offline distribution ",
                            "directory was provided. Set DITTO_OASDIFF_DIST_DIR to a ",
                            "directory containing the official ",
                            f"v{OASDIFF_VERSION} checksums.txt and {asset}. ",
                            "This wrapper intentionally never downloads tools.",
                        )
                    )
                )
            dist_dir = Path(configured)
        return run_breaking_check(
            resolution=resolution,
            current_path=arguments.current,
            dist_dir=dist_dir.resolve(),
        )
    except (OasdiffError, OSError, subprocess.SubprocessError) as error:
        sys.stderr.write(f"{error}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
