"""Fail-closed backup and isolated restore for workstation SQLite stores."""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

import orjson
from ditto_platform.foundation.storage.sqlite_backup import (
    SQLiteBackupError,
    SQLiteDatabaseReport,
    backup_database,
    inspect_database,
    restore_database,
)

type WorkstationDatabaseDomain = Literal["data", "research", "trading", "agent"]

_MANIFEST_NAME = "manifest.json"
_SCHEMA_VERSION = 1


class WorkstationBackupError(RuntimeError):
    """Raised when a complete workstation recovery unit cannot be proven."""


@dataclass(frozen=True, slots=True)
class WorkstationDatabaseSpec:
    """Canonical database location within one runtime root."""

    domain: WorkstationDatabaseDomain
    relative_path: str


@dataclass(frozen=True, slots=True)
class WorkstationDatabaseEvidence:
    """Integrity evidence for one physical SQLite database."""

    domain: WorkstationDatabaseDomain
    relative_path: str
    integrity_check: str
    sha256: str
    size_bytes: int
    table_row_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class WorkstationBackupManifest:
    """Authenticated manifest for the four logical recovery domains."""

    schema_version: int
    databases: tuple[WorkstationDatabaseEvidence, ...]
    manifest_hash: str


WORKSTATION_DATABASES: tuple[WorkstationDatabaseSpec, ...] = (
    WorkstationDatabaseSpec("data", "metadata/metadata.sqlite"),
    WorkstationDatabaseSpec("research", "research/research.sqlite"),
    WorkstationDatabaseSpec("trading", "trading/trading.sqlite"),
    WorkstationDatabaseSpec("agent", "agent/agent.sqlite"),
    WorkstationDatabaseSpec("agent", "agent/agent-presentation.sqlite3"),
    WorkstationDatabaseSpec("agent", "agent-shadow/decision-opinion.sqlite"),
)


def backup_workstation(
    source_root: Path,
    backup_root: Path,
) -> WorkstationBackupManifest:
    """Back up every canonical store into one new authenticated directory."""
    source = source_root.expanduser().resolve(strict=False)
    destination = backup_root.expanduser().resolve(strict=False)
    _validate_new_destination(source, destination)
    if not source.is_dir():
        raise WorkstationBackupError("workstation source root does not exist")

    destination.mkdir(parents=True)
    try:
        evidence: list[WorkstationDatabaseEvidence] = []
        for spec in WORKSTATION_DATABASES:
            report = backup_database(
                source / spec.relative_path,
                destination / spec.relative_path,
            )
            evidence.append(_evidence(spec, report))
        manifest = _build_manifest(tuple(evidence))
        _write_manifest(destination, manifest)
        return verify_workstation_backup(destination)
    except BaseException as exc:
        shutil.rmtree(destination)
        if isinstance(exc, WorkstationBackupError):
            raise
        raise WorkstationBackupError("workstation backup failed") from exc


def verify_workstation_backup(backup_root: Path) -> WorkstationBackupManifest:
    """Authenticate the manifest and every database before restore."""
    root = backup_root.expanduser().resolve(strict=False)
    try:
        manifest = _read_manifest(root / _MANIFEST_NAME)
        expected = _manifest_digest(manifest.databases)
        if manifest.manifest_hash != expected:
            raise WorkstationBackupError("manifest hash mismatch")
        if tuple(
            (item.domain, item.relative_path) for item in manifest.databases
        ) != tuple((item.domain, item.relative_path) for item in WORKSTATION_DATABASES):
            raise WorkstationBackupError("database inventory mismatch")
        for item in manifest.databases:
            report = inspect_database(root / item.relative_path)
            if (
                report.integrity_check != item.integrity_check
                or report.sha256 != item.sha256
                or report.size_bytes != item.size_bytes
                or report.table_row_counts != item.table_row_counts
            ):
                raise WorkstationBackupError(
                    f"database evidence mismatch: {item.relative_path}"
                )
        return manifest
    except (OSError, orjson.JSONDecodeError, SQLiteBackupError) as exc:
        raise WorkstationBackupError("workstation backup verification failed") from exc
    except WorkstationBackupError as exc:
        raise WorkstationBackupError(
            f"workstation backup verification failed: {exc}"
        ) from exc


def restore_workstation(
    backup_root: Path,
    destination_root: Path,
) -> WorkstationBackupManifest:
    """Restore a verified recovery unit into a new isolated runtime root."""
    backup = backup_root.expanduser().resolve(strict=False)
    destination = destination_root.expanduser().resolve(strict=False)
    _validate_new_destination(backup, destination)
    manifest = verify_workstation_backup(backup)
    destination.mkdir(parents=True)
    try:
        for item in manifest.databases:
            restored = restore_database(
                backup / item.relative_path,
                destination / item.relative_path,
            )
            if restored.table_row_counts != item.table_row_counts:
                raise WorkstationBackupError(
                    f"restored logical content mismatch: {item.relative_path}"
                )
        return manifest
    except BaseException as exc:
        shutil.rmtree(destination)
        if isinstance(exc, WorkstationBackupError):
            raise
        raise WorkstationBackupError("workstation restore failed") from exc


def _validate_new_destination(source: Path, destination: Path) -> None:
    if destination.exists():
        raise WorkstationBackupError("destination already exists")
    if (
        source == destination
        or source.is_relative_to(destination)
        or destination.is_relative_to(source)
    ):
        raise WorkstationBackupError("source and destination must not overlap")


def _evidence(
    spec: WorkstationDatabaseSpec,
    report: SQLiteDatabaseReport,
) -> WorkstationDatabaseEvidence:
    return WorkstationDatabaseEvidence(
        domain=spec.domain,
        relative_path=spec.relative_path,
        integrity_check=report.integrity_check,
        sha256=report.sha256,
        size_bytes=report.size_bytes,
        table_row_counts=report.table_row_counts,
    )


def _manifest_payload(
    databases: tuple[WorkstationDatabaseEvidence, ...],
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "databases": [asdict(item) for item in databases],
    }


def _manifest_digest(databases: tuple[WorkstationDatabaseEvidence, ...]) -> str:
    payload = orjson.dumps(_manifest_payload(databases), option=orjson.OPT_SORT_KEYS)
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _build_manifest(
    databases: tuple[WorkstationDatabaseEvidence, ...],
) -> WorkstationBackupManifest:
    return WorkstationBackupManifest(
        schema_version=_SCHEMA_VERSION,
        databases=databases,
        manifest_hash=_manifest_digest(databases),
    )


def _write_manifest(root: Path, manifest: WorkstationBackupManifest) -> None:
    payload = {
        **_manifest_payload(manifest.databases),
        "manifest_hash": manifest.manifest_hash,
    }
    (root / _MANIFEST_NAME).write_bytes(
        orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    )


def _read_manifest(path: Path) -> WorkstationBackupManifest:
    payload = orjson.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise WorkstationBackupError("manifest must be an object")
    raw = cast("Mapping[str, object]", payload)
    if set(raw) != {"schema_version", "databases", "manifest_hash"}:
        raise WorkstationBackupError("manifest keys are invalid")
    if raw["schema_version"] != _SCHEMA_VERSION:
        raise WorkstationBackupError("manifest schema version is invalid")
    raw_databases = raw["databases"]
    if not isinstance(raw_databases, list):
        raise WorkstationBackupError("manifest databases must be a list")
    database_items = cast("list[object]", raw_databases)
    databases = tuple(_parse_evidence(item) for item in database_items)
    manifest_hash = raw["manifest_hash"]
    if not isinstance(manifest_hash, str):
        raise WorkstationBackupError("manifest hash is invalid")
    return WorkstationBackupManifest(
        schema_version=_SCHEMA_VERSION,
        databases=databases,
        manifest_hash=manifest_hash,
    )


def _parse_evidence(value: object) -> WorkstationDatabaseEvidence:
    if not isinstance(value, dict):
        raise WorkstationBackupError("database evidence must be an object")
    raw = cast("Mapping[str, object]", value)
    expected_keys = {
        "domain",
        "relative_path",
        "integrity_check",
        "sha256",
        "size_bytes",
        "table_row_counts",
    }
    if set(raw) != expected_keys:
        raise WorkstationBackupError("database evidence keys are invalid")
    domain = raw["domain"]
    relative_path = raw["relative_path"]
    integrity = raw["integrity_check"]
    sha256 = raw["sha256"]
    size_bytes = raw["size_bytes"]
    row_counts = raw["table_row_counts"]
    if domain not in {"data", "research", "trading", "agent"}:
        raise WorkstationBackupError("database domain is invalid")
    if not all(isinstance(item, str) for item in (relative_path, integrity, sha256)):
        raise WorkstationBackupError("database text evidence is invalid")
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool):
        raise WorkstationBackupError("database size is invalid")
    if not isinstance(row_counts, dict):
        raise WorkstationBackupError("database row counts are invalid")
    row_count_items = cast("Mapping[object, object]", row_counts)
    if not all(
        isinstance(key, str) and isinstance(count, int) and not isinstance(count, bool)
        for key, count in row_count_items.items()
    ):
        raise WorkstationBackupError("database row counts are invalid")
    return WorkstationDatabaseEvidence(
        domain=cast("WorkstationDatabaseDomain", domain),
        relative_path=cast(str, relative_path),
        integrity_check=cast(str, integrity),
        sha256=cast(str, sha256),
        size_bytes=size_bytes,
        table_row_counts=cast("dict[str, int]", row_counts),
    )


__all__ = [
    "WORKSTATION_DATABASES",
    "WorkstationBackupError",
    "WorkstationBackupManifest",
    "WorkstationDatabaseEvidence",
    "WorkstationDatabaseSpec",
    "backup_workstation",
    "restore_workstation",
    "verify_workstation_backup",
]
