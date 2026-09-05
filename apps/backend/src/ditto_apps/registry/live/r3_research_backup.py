"""Verified R3 research/governance backup and restore operations."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import orjson
from ditto_platform.foundation.storage.payload_backup import (
    PayloadBackupError,
    PayloadTreeReport,
    backup_payload_tree,
    inspect_payload_tree,
    restore_payload_tree,
)
from ditto_platform.foundation.storage.sqlite_backup import (
    SQLiteBackupError,
    SQLiteDatabaseReport,
    backup_database,
    inspect_database,
    restore_database,
)

from ditto_apps.registry.contexts.r3_recovery import (
    DatabaseSchemaRecoveryEvidence,
    R3DomainRecoveryEvidence,
    R3RecoveryVerificationError,
    R3SchemaRecoveryEvidence,
    capture_r3_domain_evidence,
    inspect_r3_schema_evidence,
    resolve_metadata_database,
    verify_restored_r3_domain,
)

__all__ = [
    "PinnedArtifactBackupReport",
    "R3ResearchBackupError",
    "R3ResearchBackupReport",
    "R3ResearchRestoreReport",
    "R3RestoredVerificationReport",
    "create_r3_research_backup",
    "inspect_r3_research_sources",
    "restore_r3_research_backup",
    "verify_r3_research_backup",
    "verify_restored_r3_research_backup",
]

_SCHEMA = "ditto.r3-research-backup"
_VERSION = 1
_METADATA_NAME = "metadata.sqlite"
_RESEARCH_NAME = "research.sqlite"
_ARTIFACTS_NAME = "artifacts"
_MANIFEST_NAME = "manifest.json"
_MANIFEST_KEYS = frozenset(
    {
        "schema",
        "version",
        "metadata",
        "research",
        "artifacts",
        "pinned_artifacts",
        "schemas",
        "domain",
    }
)
_BACKUP_LAYOUT = frozenset(
    {_METADATA_NAME, _RESEARCH_NAME, _ARTIFACTS_NAME, _MANIFEST_NAME}
)


class R3ResearchBackupError(RuntimeError):
    """Raised when a combined R3 recovery unit cannot be proven complete."""


@dataclass(frozen=True, slots=True)
class PinnedArtifactBackupReport:
    """Exact indexed-file identity captured from the research database."""

    artifact_id: str
    artifact_kind: str
    relative_path: str
    content_hash: str
    byte_size: int
    reproduction_fingerprint: str


@dataclass(frozen=True, slots=True)
class R3ResearchBackupReport:
    """Verified metadata, research, and artifact backup evidence."""

    backup_root: Path
    manifest_path: Path
    metadata: SQLiteDatabaseReport
    research: SQLiteDatabaseReport
    artifacts: PayloadTreeReport
    pinned_artifacts: tuple[PinnedArtifactBackupReport, ...]
    schemas: R3SchemaRecoveryEvidence
    domain: R3DomainRecoveryEvidence


@dataclass(frozen=True, slots=True)
class R3ResearchRestoreReport:
    """Verified canonical destinations created by one restore."""

    destination_root: Path
    metadata_database: Path
    research_database: Path
    artifact_root: Path
    metadata: SQLiteDatabaseReport
    research: SQLiteDatabaseReport
    artifacts: PayloadTreeReport
    pinned_artifacts: tuple[PinnedArtifactBackupReport, ...]
    schemas: R3SchemaRecoveryEvidence
    domain: R3DomainRecoveryEvidence


@dataclass(frozen=True, slots=True)
class R3RestoredVerificationReport:
    """Typed, domain-level proof for an already restored R3 data root."""

    destination_root: Path
    metadata_database: Path
    research_database: Path
    artifact_root: Path
    schemas: R3SchemaRecoveryEvidence
    domain: R3DomainRecoveryEvidence


def inspect_r3_research_sources(
    *,
    data_root: Path,
    sqlite_path: Path | None = None,
) -> R3ResearchBackupReport:
    """Dry-run the canonical R3 source layout without writing a backup."""
    requested_root = data_root.expanduser()
    _reject_requested_symlink(requested_root, "source data root")
    root = requested_root.resolve(strict=False)
    metadata_database = _metadata_database(root, sqlite_path=sqlite_path)
    research_database = root / "research" / _RESEARCH_NAME
    try:
        metadata = inspect_database(metadata_database)
        research = inspect_database(research_database)
        artifacts = inspect_payload_tree(root / "research" / _ARTIFACTS_NAME)
        pinned = _pinned_artifact_reports(
            research_database,
            artifacts,
            include_wal=True,
        )
        schemas = inspect_r3_schema_evidence(
            metadata_database=metadata_database,
            research_database=research_database,
            include_wal=True,
        )
        domain = capture_r3_domain_evidence(
            metadata_database=metadata_database,
            research_database=research_database,
            include_wal=True,
        )
    except (
        OSError,
        PayloadBackupError,
        R3ResearchBackupError,
        R3RecoveryVerificationError,
        SQLiteBackupError,
        sqlite3.Error,
    ) as exc:
        raise R3ResearchBackupError("R3 source inspection failed") from exc
    return R3ResearchBackupReport(
        backup_root=root,
        manifest_path=root / _MANIFEST_NAME,
        metadata=metadata,
        research=research,
        artifacts=artifacts,
        pinned_artifacts=pinned,
        schemas=schemas,
        domain=domain,
    )


def create_r3_research_backup(
    *,
    data_root: Path,
    backup_root: Path,
    sqlite_path: Path | None = None,
) -> R3ResearchBackupReport:
    """Create one canonical, non-overwriting R3 recovery unit."""
    requested_source = data_root.expanduser()
    requested_backup = backup_root.expanduser()
    _reject_requested_symlink(requested_source, "source data root")
    _reject_requested_symlink(requested_backup, "backup root")
    source = requested_source.resolve(strict=False)
    root = requested_backup.resolve(strict=False)
    if _is_within(root, source):
        raise R3ResearchBackupError("backup root must be outside source data root")
    if root.exists():
        raise R3ResearchBackupError("backup root already exists")
    root.parent.mkdir(parents=True, exist_ok=True)
    try:
        root.mkdir()
    except FileExistsError as exc:
        raise R3ResearchBackupError("backup root already exists") from exc

    try:
        metadata_source = _metadata_database(source, sqlite_path=sqlite_path)
        metadata = backup_database(
            metadata_source,
            root / _METADATA_NAME,
        )
        research = backup_database(
            source / "research" / _RESEARCH_NAME,
            root / _RESEARCH_NAME,
        )
        artifacts = backup_payload_tree(
            source / "research" / _ARTIFACTS_NAME,
            root / _ARTIFACTS_NAME,
        )
        pinned = _pinned_artifact_reports(root / _RESEARCH_NAME, artifacts)
        schemas = inspect_r3_schema_evidence(
            metadata_database=root / _METADATA_NAME,
            research_database=root / _RESEARCH_NAME,
            include_wal=False,
        )
        domain = capture_r3_domain_evidence(
            metadata_database=root / _METADATA_NAME,
            research_database=root / _RESEARCH_NAME,
            include_wal=False,
        )
        manifest_path = root / _MANIFEST_NAME
        manifest_path.write_bytes(
            _canonical_json(
                _manifest_record(
                    metadata=metadata,
                    research=research,
                    artifacts=artifacts,
                    pinned_artifacts=pinned,
                    schemas=schemas,
                    domain=domain,
                )
            )
        )
    except (
        OSError,
        PayloadBackupError,
        R3ResearchBackupError,
        R3RecoveryVerificationError,
        SQLiteBackupError,
        sqlite3.Error,
    ) as exc:
        shutil.rmtree(root)
        raise R3ResearchBackupError("combined R3 backup failed") from exc

    return R3ResearchBackupReport(
        backup_root=root,
        manifest_path=manifest_path,
        metadata=metadata,
        research=research,
        artifacts=artifacts,
        pinned_artifacts=pinned,
        schemas=schemas,
        domain=domain,
    )


def verify_r3_research_backup(
    *,
    backup_root: Path,
) -> R3ResearchBackupReport:
    """Verify canonical manifest bytes and every backed logical identity."""
    requested_root = backup_root.expanduser()
    try:
        _validate_backup_layout(requested_root)
        root = requested_root.resolve(strict=False)
        manifest_path = root / _MANIFEST_NAME
        manifest_bytes = manifest_path.read_bytes()
        loaded_manifest = orjson.loads(manifest_bytes)
        if not isinstance(loaded_manifest, dict):
            raise R3ResearchBackupError("invalid R3 backup manifest")
        manifest = cast("dict[str, object]", loaded_manifest)
        if manifest_bytes != _canonical_json(manifest):
            raise R3ResearchBackupError("R3 backup manifest is not canonical JSON")
        if frozenset(manifest) != _MANIFEST_KEYS:
            raise R3ResearchBackupError("invalid R3 backup manifest")
        if manifest.get("schema") != _SCHEMA or manifest.get("version") != _VERSION:
            raise R3ResearchBackupError("unsupported R3 backup manifest")

        metadata = _inspect_standalone_database(root / _METADATA_NAME)
        research = _inspect_standalone_database(root / _RESEARCH_NAME)
        artifacts = inspect_payload_tree(root / _ARTIFACTS_NAME)
        try:
            pinned = _pinned_artifact_reports(root / _RESEARCH_NAME, artifacts)
        except R3ResearchBackupError as exc:
            raise R3ResearchBackupError("backup does not match manifest") from exc
        schemas = inspect_r3_schema_evidence(
            metadata_database=root / _METADATA_NAME,
            research_database=root / _RESEARCH_NAME,
            include_wal=False,
        )
        domain = capture_r3_domain_evidence(
            metadata_database=root / _METADATA_NAME,
            research_database=root / _RESEARCH_NAME,
            include_wal=False,
        )
        actual_manifest = _manifest_record(
            metadata=metadata,
            research=research,
            artifacts=artifacts,
            pinned_artifacts=pinned,
            schemas=schemas,
            domain=domain,
        )
        if manifest != actual_manifest:
            raise R3ResearchBackupError("backup does not match manifest")
    except R3ResearchBackupError:
        raise
    except (
        AttributeError,
        KeyError,
        OSError,
        PayloadBackupError,
        R3RecoveryVerificationError,
        SQLiteBackupError,
        orjson.JSONDecodeError,
        sqlite3.Error,
    ) as exc:
        raise R3ResearchBackupError("invalid R3 backup manifest") from exc

    return R3ResearchBackupReport(
        backup_root=root,
        manifest_path=manifest_path,
        metadata=metadata,
        research=research,
        artifacts=artifacts,
        pinned_artifacts=pinned,
        schemas=schemas,
        domain=domain,
    )


def restore_r3_research_backup(
    *,
    backup_root: Path,
    destination_root: Path,
) -> R3ResearchRestoreReport:
    """Restore one verified unit into a new canonical data root."""
    requested_backup = backup_root.expanduser()
    requested_destination = destination_root.expanduser()
    _reject_requested_symlink(requested_backup, "backup root")
    _reject_requested_symlink(requested_destination, "restore destination")
    backup = requested_backup.resolve(strict=False)
    destination = requested_destination.resolve(strict=False)
    if _is_within(destination, backup):
        raise R3ResearchBackupError("restore destination must be outside backup root")
    if destination.exists():
        raise R3ResearchBackupError("restore destination already exists")
    verified = verify_r3_research_backup(backup_root=requested_backup)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.mkdir()
    except FileExistsError as exc:
        raise R3ResearchBackupError("restore destination already exists") from exc

    metadata_target = _canonical_metadata_database(destination)
    research_target = destination / "research" / _RESEARCH_NAME
    artifact_target = destination / "research" / _ARTIFACTS_NAME
    try:
        metadata = _restore_standalone_database(
            verified.backup_root / _METADATA_NAME,
            metadata_target,
        )
        research = _restore_standalone_database(
            verified.backup_root / _RESEARCH_NAME,
            research_target,
        )
        artifacts = restore_payload_tree(
            verified.backup_root / _ARTIFACTS_NAME,
            artifact_target,
        )
        pinned = _pinned_artifact_reports(research_target, artifacts)
        schemas = inspect_r3_schema_evidence(
            metadata_database=metadata_target,
            research_database=research_target,
            include_wal=False,
        )
        domain = verify_restored_r3_domain(
            data_root=destination,
            metadata_database=metadata_target,
            expected=verified.domain,
        )
        if (
            metadata.table_row_counts != verified.metadata.table_row_counts
            or research.table_row_counts != verified.research.table_row_counts
            or artifacts.root_sha256 != verified.artifacts.root_sha256
            or pinned != verified.pinned_artifacts
            or schemas != verified.schemas
        ):
            raise R3ResearchBackupError(
                "restored R3 logical content does not match backup"
            )
    except (
        OSError,
        PayloadBackupError,
        R3ResearchBackupError,
        R3RecoveryVerificationError,
        SQLiteBackupError,
        sqlite3.Error,
    ) as exc:
        shutil.rmtree(destination)
        if isinstance(exc, R3ResearchBackupError):
            raise
        raise R3ResearchBackupError("combined R3 restore failed") from exc

    return R3ResearchRestoreReport(
        destination_root=destination,
        metadata_database=metadata_target,
        research_database=research_target,
        artifact_root=artifact_target,
        metadata=metadata,
        research=research,
        artifacts=artifacts,
        pinned_artifacts=pinned,
        schemas=schemas,
        domain=domain,
    )


def verify_restored_r3_research_backup(
    *,
    backup_root: Path,
    destination_root: Path,
    sqlite_path: Path | None = None,
) -> R3RestoredVerificationReport:
    """Reopen canonical services and prove an existing restore against its unit."""
    requested_destination = destination_root.expanduser()
    _reject_requested_symlink(requested_destination, "restore destination")
    destination = requested_destination.resolve(strict=False)
    if not destination.is_dir():
        raise R3ResearchBackupError("restored R3 data root does not exist")
    verified = verify_r3_research_backup(backup_root=backup_root)
    metadata_database = _metadata_database(destination, sqlite_path=sqlite_path)
    research_database = destination / "research" / _RESEARCH_NAME
    artifact_root = destination / "research" / _ARTIFACTS_NAME
    try:
        schemas = inspect_r3_schema_evidence(
            metadata_database=metadata_database,
            research_database=research_database,
            include_wal=True,
        )
        if schemas != verified.schemas:
            raise R3ResearchBackupError(
                "restored R3 schema evidence does not match backup"
            )
        domain = verify_restored_r3_domain(
            data_root=destination,
            metadata_database=metadata_database,
            expected=verified.domain,
        )
        artifacts = inspect_payload_tree(artifact_root)
        pinned = _pinned_artifact_reports(
            research_database,
            artifacts,
            include_wal=True,
        )
        if (
            artifacts.root_sha256 != verified.artifacts.root_sha256
            or pinned != verified.pinned_artifacts
        ):
            raise R3ResearchBackupError(
                "restored R3 artifact evidence does not match backup"
            )
    except (
        OSError,
        PayloadBackupError,
        R3RecoveryVerificationError,
        SQLiteBackupError,
        sqlite3.Error,
    ) as exc:
        raise R3ResearchBackupError("restored R3 verification failed") from exc
    return R3RestoredVerificationReport(
        destination_root=destination,
        metadata_database=metadata_database,
        research_database=research_database,
        artifact_root=artifact_root,
        schemas=schemas,
        domain=domain,
    )


def _pinned_artifact_reports(
    research_database: Path,
    artifacts: PayloadTreeReport,
    *,
    include_wal: bool = False,
) -> tuple[PinnedArtifactBackupReport, ...]:
    files = {item.relative_path: item for item in artifacts.files}
    database = research_database.expanduser().resolve(strict=False)
    query = "mode=ro" if include_wal else "mode=ro&immutable=1"
    with sqlite3.connect(
        f"{database.as_uri()}?{query}",
        uri=True,
    ) as connection:
        rows = connection.execute(
            """
            SELECT artifact_id, artifact_kind, relative_path, content_hash,
                   byte_size, reproduction_fingerprint
            FROM research_artifact
            WHERE is_pinned=1
            ORDER BY artifact_id
            """
        ).fetchall()
    if not rows:
        raise R3ResearchBackupError(
            "R3 backup requires at least one pinned indexed artifact"
        )

    reports: list[PinnedArtifactBackupReport] = []
    for row in rows:
        relative_path = str(row[2])
        file_report = files.get(relative_path)
        indexed_hash = f"sha256:{row[3]}"
        if (
            file_report is None
            or file_report.sha256 != indexed_hash
            or file_report.size_bytes != int(row[4])
        ):
            raise R3ResearchBackupError(
                f"pinned artifact bytes do not match index: {row[0]}"
            )
        reports.append(
            PinnedArtifactBackupReport(
                artifact_id=str(row[0]),
                artifact_kind=str(row[1]),
                relative_path=relative_path,
                content_hash=indexed_hash,
                byte_size=int(row[4]),
                reproduction_fingerprint=str(row[5]),
            )
        )
    return tuple(reports)


def _manifest_record(
    *,
    metadata: SQLiteDatabaseReport,
    research: SQLiteDatabaseReport,
    artifacts: PayloadTreeReport,
    pinned_artifacts: tuple[PinnedArtifactBackupReport, ...],
    schemas: R3SchemaRecoveryEvidence,
    domain: R3DomainRecoveryEvidence,
) -> dict[str, object]:
    return {
        "schema": _SCHEMA,
        "version": _VERSION,
        "metadata": _json_record(metadata),
        "research": _json_record(research),
        "artifacts": _json_record(artifacts),
        "pinned_artifacts": [_json_record(item) for item in pinned_artifacts],
        "schemas": _json_record(schemas),
        "domain": _json_record(domain),
    }


def _json_record(
    value: (
        SQLiteDatabaseReport
        | PayloadTreeReport
        | PinnedArtifactBackupReport
        | DatabaseSchemaRecoveryEvidence
        | R3SchemaRecoveryEvidence
        | R3DomainRecoveryEvidence
    ),
) -> object:
    return orjson.loads(orjson.dumps(asdict(value)))


def _canonical_json(value: object) -> bytes:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS)


def _inspect_standalone_database(database: Path) -> SQLiteDatabaseReport:
    """Inspect a sealed backup DB without leaving SQLite-generated sidecars."""
    try:
        return inspect_database(database)
    finally:
        _remove_generated_database_sidecars(database)


def _restore_standalone_database(
    backup: Path,
    destination: Path,
) -> SQLiteDatabaseReport:
    """Restore a sealed DB while preserving the backup unit's fixed layout."""
    try:
        return restore_database(backup, destination)
    finally:
        _remove_generated_database_sidecars(backup)


def _remove_generated_database_sidecars(database: Path) -> None:
    for suffix in ("-wal", "-shm"):
        database.with_name(f"{database.name}{suffix}").unlink(missing_ok=True)


def _validate_backup_layout(root: Path) -> None:
    if root.is_symlink():
        raise R3ResearchBackupError("backup layout cannot contain symbolic links")
    if not root.is_dir():
        raise R3ResearchBackupError("R3 backup root does not exist")
    entries = tuple(root.iterdir())
    if any(path.is_symlink() for path in root.rglob("*")):
        raise R3ResearchBackupError("backup layout cannot contain symbolic links")
    if frozenset(path.name for path in entries) != _BACKUP_LAYOUT:
        raise R3ResearchBackupError("R3 backup layout does not match schema")
    regular_files = (
        root / _METADATA_NAME,
        root / _RESEARCH_NAME,
        root / _MANIFEST_NAME,
    )
    if (
        any(not path.is_file() for path in regular_files)
        or not (root / _ARTIFACTS_NAME).is_dir()
    ):
        raise R3ResearchBackupError("R3 backup layout contains invalid entry types")


def _metadata_database(
    data_root: Path,
    *,
    sqlite_path: Path | None,
) -> Path:
    """Return the DataStoreSettings-resolved metadata database path."""
    return resolve_metadata_database(data_root, sqlite_path=sqlite_path)


def _canonical_metadata_database(data_root: Path) -> Path:
    """Return the canonical target inside a newly restored data root."""
    return data_root / "metadata" / _METADATA_NAME


def _reject_requested_symlink(path: Path, label: str) -> None:
    """Reject both live and dangling symlinks before path resolution."""
    if path.is_symlink():
        raise R3ResearchBackupError(f"{label} cannot be a symbolic link")


def _is_within(path: Path, parent: Path) -> bool:
    """Return whether ``path`` equals or descends from ``parent``."""
    return path == parent or path.is_relative_to(parent)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    dry_run = subparsers.add_parser("dry-run")
    dry_run.add_argument("--data-root", type=Path, required=True)
    dry_run.add_argument("--sqlite-path", type=Path)

    backup = subparsers.add_parser("backup")
    backup.add_argument("--data-root", type=Path, required=True)
    backup.add_argument("--backup-root", type=Path, required=True)
    backup.add_argument("--sqlite-path", type=Path)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--backup-root", type=Path, required=True)

    restore = subparsers.add_parser("restore")
    restore.add_argument("--backup-root", type=Path, required=True)
    restore.add_argument("--destination-root", type=Path, required=True)

    verify_restored = subparsers.add_parser("verify-restored")
    verify_restored.add_argument("--backup-root", type=Path, required=True)
    verify_restored.add_argument("--destination-root", type=Path, required=True)
    verify_restored.add_argument("--sqlite-path", type=Path)
    return parser


def _path_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError


def _write_report(
    report: (
        R3ResearchBackupReport | R3ResearchRestoreReport | R3RestoredVerificationReport
    ),
) -> None:
    sys.stdout.write(
        orjson.dumps(
            asdict(report),
            default=_path_default,
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        ).decode()
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    """Run one explicit, fail-closed R3 recovery operation."""
    args = _parser().parse_args(argv)
    try:
        if args.operation == "dry-run":
            report = inspect_r3_research_sources(
                data_root=cast("Path", args.data_root),
                sqlite_path=cast("Path | None", args.sqlite_path),
            )
        elif args.operation == "backup":
            report = create_r3_research_backup(
                data_root=cast("Path", args.data_root),
                backup_root=cast("Path", args.backup_root),
                sqlite_path=cast("Path | None", args.sqlite_path),
            )
        elif args.operation == "verify":
            report = verify_r3_research_backup(
                backup_root=cast("Path", args.backup_root)
            )
        elif args.operation == "restore":
            report = restore_r3_research_backup(
                backup_root=cast("Path", args.backup_root),
                destination_root=cast("Path", args.destination_root),
            )
        else:
            report = verify_restored_r3_research_backup(
                backup_root=cast("Path", args.backup_root),
                destination_root=cast("Path", args.destination_root),
                sqlite_path=cast("Path | None", args.sqlite_path),
            )
    except R3ResearchBackupError as exc:
        sys.stderr.write(f"R3 research backup operation failed: {exc}\n")
        return 2
    _write_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
