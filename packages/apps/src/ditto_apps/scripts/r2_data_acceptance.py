"""R2 data-product acceptance runner and recoverability helpers."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

import orjson
from ditto_application.processes.ingestion.r2_preflight import (
    ChunkBenchmark,
    ProviderAccessEvidence,
    R2AcceptanceRuntimeEvidence,
    R2IngestionPreflight,
    R2PreflightEvidence,
    R2PreflightReport,
)
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
from pydantic import BaseModel, ConfigDict

from ditto_apps.registry.container import make_app_container

__all__ = [
    "R2AcceptanceReport",
    "R2BackupError",
    "R2BackupReport",
    "R2IdempotencyReport",
    "R2IdempotencySnapshot",
    "R2RestoreReport",
    "create_r2_backup",
    "restore_r2_backup",
    "run_fixture_acceptance",
    "run_live_acceptance",
    "verify_consecutive_idempotency",
    "verify_idempotency_snapshots",
    "write_live_evidence_bundle",
]

_SQLITE_NAME = "metadata.sqlite"
_PAYLOAD_NAME = "payload"
_MANIFEST_NAME = "manifest.json"
_LIVE_SOURCE_SCHEMA = "ditto.r2-live-gate-source"
_LIVE_ARTIFACT_SCHEMA = "ditto.r2-live-gate-artifact"


class R2BackupError(RuntimeError):
    """Raised when combined R2 operational evidence is not recoverable."""


@dataclass(frozen=True, slots=True)
class R2BackupReport:
    """Verified SQLite and payload backup evidence."""

    backup_root: Path
    manifest_path: Path
    sqlite: SQLiteDatabaseReport
    payload: PayloadTreeReport


@dataclass(frozen=True, slots=True)
class R2RestoreReport:
    """Verified SQLite and payload restore evidence."""

    sqlite_destination: Path
    payload_destination: Path
    sqlite: SQLiteDatabaseReport
    payload: PayloadTreeReport


@dataclass(frozen=True, slots=True)
class R2IdempotencySnapshot:
    """Observable durable identities after one acceptance run."""

    durable_identity_count: int
    write_attempt_count: int
    snapshot_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject incomplete or ambiguous idempotency observations."""
        if self.durable_identity_count < 0 or self.write_attempt_count < 0:
            raise ValueError("idempotency counts cannot be negative")
        if len(set(self.snapshot_ids)) != len(self.snapshot_ids):
            raise ValueError("idempotency snapshot identities must be unique")


@dataclass(frozen=True, slots=True)
class R2IdempotencyReport:
    """Evidence that a consecutive second run performed no durable writes."""

    first: R2IdempotencySnapshot
    second: R2IdempotencySnapshot
    second_run_write_attempts: int
    passed: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class R2RecoverabilityReport:
    """Combined backup/restore exercise result."""

    passed: bool
    sqlite_table_row_counts: dict[str, int]
    payload_root_sha256: str | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class R2AcceptanceReport:
    """Machine-readable R2 acceptance result for fixture or live evidence."""

    mode: Literal["fixture", "live"]
    status: Literal[
        "ready",
        "configuration_blocked",
        "performance_blocked",
        "acceptance_failed",
    ]
    checked_at: datetime
    preflight: R2PreflightReport
    recoverability: R2RecoverabilityReport
    idempotency: R2IdempotencyReport | None
    reason_codes: tuple[str, ...]


class _ProviderAccessInput(BaseModel):
    provider_dataset: str
    entitled: bool
    evidence_uri: str
    checked_at: datetime

    model_config = ConfigDict(strict=True, extra="forbid")


class _BenchmarkInput(BaseModel):
    dataset_id: str
    sample_partitions: int
    sample_rows: int
    elapsed_seconds: float
    target_partitions: int
    observed_at: datetime
    evidence_uri: str

    model_config = ConfigDict(strict=True, extra="forbid")


class _SnapshotInput(BaseModel):
    durable_identity_count: int
    write_attempt_count: int
    snapshot_ids: tuple[str, ...]

    model_config = ConfigDict(strict=True, extra="forbid")


class _LiveEvidenceInput(BaseModel):
    provider_access: tuple[_ProviderAccessInput, ...] = ()
    benchmarks: tuple[_BenchmarkInput, ...] = ()
    incremental_elapsed_seconds: float | None = None
    workbench_query_seconds: float | None = None
    first_run: _SnapshotInput | None = None
    second_run: _SnapshotInput | None = None

    model_config = ConfigDict(strict=True, extra="forbid")


def verify_consecutive_idempotency(
    *,
    run: Callable[[], None],
    observe: Callable[[], R2IdempotencySnapshot],
) -> R2IdempotencyReport:
    """Run the same bounded operation twice and compare durable evidence."""
    run()
    first = observe()
    run()
    second = observe()
    return verify_idempotency_snapshots(first, second)


def verify_idempotency_snapshots(
    first: R2IdempotencySnapshot,
    second: R2IdempotencySnapshot,
) -> R2IdempotencyReport:
    """Assess two already captured run observations with the same gate."""
    second_writes = second.write_attempt_count - first.write_attempt_count
    if second_writes < 0:
        raise ValueError("idempotency write attempt count cannot decrease")
    reasons: list[str] = []
    if second_writes:
        reasons.append("second_run_wrote_durable_state")
    if second.durable_identity_count != first.durable_identity_count:
        reasons.append("durable_identity_count_changed")
    if second.snapshot_ids != first.snapshot_ids:
        reasons.append("snapshot_identity_changed")
    return R2IdempotencyReport(
        first=first,
        second=second,
        second_run_write_attempts=second_writes,
        passed=not reasons,
        reason_codes=tuple(reasons),
    )


def run_fixture_acceptance(
    *,
    checked_at: datetime | None = None,
) -> R2AcceptanceReport:
    """Run deterministic preflight, recovery, and idempotency fixtures."""
    now = checked_at or datetime.now(UTC)
    preflight = R2IngestionPreflight().run_fixture(checked_at=now)
    recoverability = _fixture_recoverability()
    idempotency = _fixture_idempotency()
    return _acceptance_report(
        mode="fixture",
        checked_at=now,
        preflight=preflight,
        recoverability=recoverability,
        idempotency=idempotency,
    )


def run_live_acceptance(
    *,
    evidence_path: Path | None,
    sqlite_path: Path | None = None,
    payload_root: Path | None = None,
    backup_root: Path | None = None,
    restore_root: Path | None = None,
    checked_at: datetime | None = None,
) -> R2AcceptanceReport:
    """Assess live non-secret evidence and optionally exercise backup/restore."""
    now = checked_at or datetime.now(UTC)
    evidence = _read_live_evidence(evidence_path)
    container = make_app_container()
    try:
        runtime = container.get(R2AcceptanceRuntimeEvidence)
    finally:
        container.close()
    access = tuple(
        ProviderAccessEvidence(
            provider_dataset=item.provider_dataset,
            credential_configured=(
                credential_configured := item.provider_dataset.partition(":")[0]
                in runtime.credential_sources
            ),
            entitled=item.entitled and credential_configured,
            evidence_uri=item.evidence_uri,
            checked_at=item.checked_at,
        )
        for item in evidence.provider_access
    )
    benchmarks = tuple(
        ChunkBenchmark(**item.model_dump()) for item in evidence.benchmarks
    )
    preflight = R2IngestionPreflight().run(
        R2PreflightEvidence(
            provider_access=access,
            license_records=runtime.license_records,
            certifications=runtime.certifications,
            benchmarks=benchmarks,
            incremental_elapsed_seconds=evidence.incremental_elapsed_seconds,
            workbench_query_seconds=evidence.workbench_query_seconds,
            as_of=now.date(),
            checked_at=now,
        )
    )
    recoverability = _live_recoverability(
        sqlite_path=sqlite_path,
        payload_root=payload_root,
        backup_root=backup_root,
        restore_root=restore_root,
    )
    idempotency = _live_idempotency(evidence)
    return _acceptance_report(
        mode="live",
        checked_at=now,
        preflight=preflight,
        recoverability=recoverability,
        idempotency=idempotency,
    )


def _fixture_recoverability() -> R2RecoverabilityReport:
    with TemporaryDirectory(prefix="ditto-r2-acceptance-") as temporary_name:
        root = Path(temporary_name)
        database = root / "runtime" / _SQLITE_NAME
        database.parent.mkdir(parents=True)
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE fixture_evidence (identity TEXT PRIMARY KEY)"
            )
            connection.execute("INSERT INTO fixture_evidence VALUES ('r2')")
            connection.commit()
        payload = root / "runtime" / _PAYLOAD_NAME
        payload.mkdir()
        (payload / "fixture.parquet").write_bytes(b"PAR1-r2-fixture")
        backup = create_r2_backup(
            sqlite_source=database,
            payload_source=payload,
            backup_root=root / "backup",
        )
        restored = restore_r2_backup(
            backup_root=backup.backup_root,
            sqlite_destination=root / "restore" / _SQLITE_NAME,
            payload_destination=root / "restore" / _PAYLOAD_NAME,
        )
        passed = (
            restored.sqlite.table_row_counts == backup.sqlite.table_row_counts
            and restored.payload.root_sha256 == backup.payload.root_sha256
        )
        return R2RecoverabilityReport(
            passed=passed,
            sqlite_table_row_counts=restored.sqlite.table_row_counts,
            payload_root_sha256=restored.payload.root_sha256,
            reason_codes=() if passed else ("restore_evidence_mismatch",),
        )


def _fixture_idempotency() -> R2IdempotencyReport:
    payloads: set[str] = set()
    snapshots: set[str] = set()
    write_attempts = 0

    def run() -> None:
        nonlocal write_attempts
        if "fixture-chunk" in payloads:
            return
        write_attempts += 1
        payloads.add("fixture-chunk")
        snapshots.add("snapshot:fixture:sha256:payload")

    def observe() -> R2IdempotencySnapshot:
        return R2IdempotencySnapshot(
            durable_identity_count=len(payloads),
            write_attempt_count=write_attempts,
            snapshot_ids=tuple(sorted(snapshots)),
        )

    return verify_consecutive_idempotency(run=run, observe=observe)


def _read_live_evidence(path: Path | None) -> _LiveEvidenceInput:
    if path is None:
        return _LiveEvidenceInput()
    try:
        return _LiveEvidenceInput.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ValueError("invalid live acceptance evidence") from exc


def _live_recoverability(
    *,
    sqlite_path: Path | None,
    payload_root: Path | None,
    backup_root: Path | None,
    restore_root: Path | None,
) -> R2RecoverabilityReport:
    if None in {sqlite_path, payload_root, backup_root, restore_root}:
        return R2RecoverabilityReport(
            passed=False,
            sqlite_table_row_counts={},
            payload_root_sha256=None,
            reason_codes=("recoverability_evidence_missing",),
        )
    sqlite_source = _required_path(sqlite_path)
    payload_source = _required_path(payload_root)
    backup_destination = _required_path(backup_root)
    restore_destination = _required_path(restore_root)
    try:
        backup = create_r2_backup(
            sqlite_source=sqlite_source,
            payload_source=payload_source,
            backup_root=backup_destination,
        )
        restored = restore_r2_backup(
            backup_root=backup.backup_root,
            sqlite_destination=restore_destination / _SQLITE_NAME,
            payload_destination=restore_destination / _PAYLOAD_NAME,
        )
    except R2BackupError:
        return R2RecoverabilityReport(
            passed=False,
            sqlite_table_row_counts={},
            payload_root_sha256=None,
            reason_codes=("recoverability_exercise_failed",),
        )
    return R2RecoverabilityReport(
        passed=True,
        sqlite_table_row_counts=restored.sqlite.table_row_counts,
        payload_root_sha256=restored.payload.root_sha256,
        reason_codes=(),
    )


def _required_path(value: Path | None) -> Path:
    if value is None:
        raise ValueError("required acceptance path is missing")
    return value


def _live_idempotency(
    evidence: _LiveEvidenceInput,
) -> R2IdempotencyReport | None:
    if evidence.first_run is None or evidence.second_run is None:
        return None
    first = R2IdempotencySnapshot(**evidence.first_run.model_dump())
    second = R2IdempotencySnapshot(**evidence.second_run.model_dump())
    return verify_idempotency_snapshots(first, second)


def _acceptance_report(
    *,
    mode: Literal["fixture", "live"],
    checked_at: datetime,
    preflight: R2PreflightReport,
    recoverability: R2RecoverabilityReport,
    idempotency: R2IdempotencyReport | None,
) -> R2AcceptanceReport:
    reasons = list(preflight.reason_codes)
    reasons.extend(recoverability.reason_codes)
    if idempotency is None:
        reasons.append("idempotency_evidence_missing")
    else:
        reasons.extend(idempotency.reason_codes)
    if preflight.status != "ready":
        status = preflight.status
    elif not recoverability.passed or idempotency is None or not idempotency.passed:
        status = "acceptance_failed"
    else:
        status = "ready"
    return R2AcceptanceReport(
        mode=mode,
        status=status,
        checked_at=checked_at,
        preflight=preflight,
        recoverability=recoverability,
        idempotency=idempotency,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def _canonical_json(value: object) -> bytes:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json(value))


def _content_entry(path: Path, *, root: Path) -> dict[str, str]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def write_live_evidence_bundle(
    *,
    report: R2AcceptanceReport,
    output: Path,
    source_manifest: Path,
) -> None:
    """Write one redacted report and four exact evidence groups for Task 11."""
    if report.mode != "live":
        raise ValueError("R2 live evidence bundle requires a live report")
    root = source_manifest.parent.resolve(strict=False)
    if output.parent.resolve(strict=False) != root:
        raise ValueError("R2 report and source manifest must share one directory")
    evidence_root = root / "r2-live-evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, tuple[Path, object]] = {
        "provider_entitlement": (
            evidence_root / "provider-entitlement.json",
            {
                "schema": _LIVE_ARTIFACT_SCHEMA,
                "version": 1,
                "kind": "provider_entitlement",
                "checked_at": report.checked_at,
                "contract_count": report.preflight.contract_count,
                "products": report.preflight.products,
                "reason_codes": report.preflight.reason_codes,
            },
        ),
        "performance": (
            evidence_root / "performance.json",
            {
                "schema": _LIVE_ARTIFACT_SCHEMA,
                "version": 1,
                "kind": "performance",
                "checked_at": report.checked_at,
                "performance": report.preflight.performance,
            },
        ),
        "recoverability": (
            evidence_root / "recoverability.json",
            {
                "schema": _LIVE_ARTIFACT_SCHEMA,
                "version": 1,
                "kind": "recoverability",
                "checked_at": report.checked_at,
                "recoverability": report.recoverability,
            },
        ),
        "idempotency": (
            evidence_root / "idempotency.json",
            {
                "schema": _LIVE_ARTIFACT_SCHEMA,
                "version": 1,
                "kind": "idempotency",
                "checked_at": report.checked_at,
                "idempotency": report.idempotency,
            },
        ),
    }
    _write_json(output, asdict(report))
    for path, value in artifacts.values():
        _write_json(path, value)
    _write_json(
        source_manifest,
        {
            "schema": _LIVE_SOURCE_SCHEMA,
            "version": 1,
            "report": _content_entry(output, root=root),
            "groups": {
                kind: [_content_entry(path, root=root)]
                for kind, (path, _) in artifacts.items()
            },
        },
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--sqlite-path", type=Path)
    parser.add_argument("--payload-root", type=Path)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--restore-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--data-root", type=Path)
    return parser


def _resolve_path(value: Path | None) -> Path | None:
    return None if value is None else value.expanduser().resolve(strict=False)


def _run_stamp(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%SZ")


@dataclass(frozen=True, slots=True)
class _ResolvedLiveArgs:
    evidence_path: Path | None
    sqlite_path: Path | None
    payload_root: Path | None
    backup_root: Path | None
    restore_root: Path | None
    output: Path | None
    source_manifest: Path | None
    env_overrides: dict[str, str]


def _resolve_live_args(
    args: argparse.Namespace,
    *,
    stamp: str,
) -> _ResolvedLiveArgs:
    """
    Resolve live-run paths to absolute + derive env overrides + per-run roots.

    Mirrors sibling runners (``r2_live_certification``/``r3_live_snapshot_builder``)
    which resolve paths in ``main``. Fixes:

    - relative ``--output`` crashing ``write_live_evidence_bundle``'s
      ``path.relative_to(root)`` (one relative, one absolute);
    - ``--sqlite-path`` being disconnected from the runtime pool, which reads
      ``SQLITE_PATH``/``DITTO_DATA_ROOT`` env via ``load_data_store_settings``;
    - replay colliding with the non-overwrite backup/restore contract by
      stamping a unique subdir per run (the contract itself stays intact).
    """
    data_root = _resolve_path(getattr(args, "data_root", None))
    sqlite_path = _resolve_path(args.sqlite_path)
    env_overrides: dict[str, str] = {}
    if data_root is not None:
        env_overrides["DITTO_DATA_ROOT"] = str(data_root)
    if sqlite_path is not None:
        env_overrides["SQLITE_PATH"] = str(sqlite_path)
    backup_root = _resolve_path(args.backup_root)
    restore_root = _resolve_path(args.restore_root)
    if backup_root is not None:
        backup_root = backup_root / stamp
    if restore_root is not None:
        restore_root = restore_root / stamp
    output = _resolve_path(args.output)
    source_manifest = _resolve_path(args.source_manifest)
    return _ResolvedLiveArgs(
        evidence_path=_resolve_path(args.evidence),
        sqlite_path=sqlite_path,
        payload_root=_resolve_path(args.payload_root),
        backup_root=backup_root,
        restore_root=restore_root,
        output=output,
        source_manifest=source_manifest,
        env_overrides=env_overrides,
    )


def main(argv: list[str] | None = None) -> int:
    """Run acceptance without ever serializing credential material."""
    args = _parser().parse_args(argv)
    if args.mode == "fixture":
        report = run_fixture_acceptance()
    else:
        resolved = _resolve_live_args(args, stamp=_run_stamp(datetime.now(UTC)))
        if resolved.env_overrides:
            os.environ.update(resolved.env_overrides)
        report = run_live_acceptance(
            evidence_path=resolved.evidence_path,
            sqlite_path=resolved.sqlite_path,
            payload_root=resolved.payload_root,
            backup_root=resolved.backup_root,
            restore_root=resolved.restore_root,
        )
        if resolved.output is not None:
            source_manifest = resolved.source_manifest or resolved.output.with_name(
                f"{resolved.output.stem}.manifest{resolved.output.suffix}"
            )
            write_live_evidence_bundle(
                report=report,
                output=resolved.output,
                source_manifest=source_manifest,
            )
    sys.stdout.write(
        orjson.dumps(
            asdict(report),
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        ).decode()
        + "\n"
    )
    return 0 if report.status == "ready" else 2


def create_r2_backup(
    *,
    sqlite_source: Path,
    payload_source: Path,
    backup_root: Path,
) -> R2BackupReport:
    """Create one non-overwriting backup unit for metadata and payloads."""
    root = backup_root.expanduser().resolve(strict=False)
    if root.exists():
        raise R2BackupError("backup root already exists")
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir()
    try:
        sqlite_report = backup_database(sqlite_source, root / _SQLITE_NAME)
        payload_report = backup_payload_tree(payload_source, root / _PAYLOAD_NAME)
        manifest_path = root / _MANIFEST_NAME
        manifest_path.write_bytes(
            orjson.dumps(
                {
                    "version": 1,
                    "sqlite": asdict(sqlite_report),
                    "payload": asdict(payload_report),
                },
                option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
            )
        )
    except (OSError, PayloadBackupError, SQLiteBackupError) as exc:
        shutil.rmtree(root)
        raise R2BackupError("combined R2 backup failed") from exc
    return R2BackupReport(
        backup_root=root,
        manifest_path=manifest_path,
        sqlite=sqlite_report,
        payload=payload_report,
    )


def restore_r2_backup(
    *,
    backup_root: Path,
    sqlite_destination: Path,
    payload_destination: Path,
) -> R2RestoreReport:
    """Verify a backup manifest and restore both stores into new targets."""
    root = backup_root.expanduser().resolve(strict=False)
    sqlite_target = sqlite_destination.expanduser().resolve(strict=False)
    payload_target = payload_destination.expanduser().resolve(strict=False)
    if sqlite_target.exists() or payload_target.exists():
        raise R2BackupError("restore destination already exists")
    try:
        expected_sqlite, expected_payload = _verified_manifest(root)
        sqlite_report = restore_database(root / _SQLITE_NAME, sqlite_target)
        payload_report = restore_payload_tree(root / _PAYLOAD_NAME, payload_target)
        if sqlite_report.table_row_counts != expected_sqlite.table_row_counts:
            raise R2BackupError("restored SQLite logical content does not match backup")
        if payload_report.root_sha256 != expected_payload.root_sha256:
            raise R2BackupError("restored payload content does not match backup")
    except R2BackupError:
        _remove_new_restore(sqlite_target, payload_target)
        raise
    except (OSError, PayloadBackupError, SQLiteBackupError) as exc:
        _remove_new_restore(sqlite_target, payload_target)
        raise R2BackupError("combined R2 restore failed") from exc
    return R2RestoreReport(
        sqlite_destination=sqlite_target,
        payload_destination=payload_target,
        sqlite=sqlite_report,
        payload=payload_report,
    )


def _verified_manifest(
    root: Path,
) -> tuple[SQLiteDatabaseReport, PayloadTreeReport]:
    manifest_path = root / _MANIFEST_NAME
    try:
        manifest = orjson.loads(manifest_path.read_bytes())
        if manifest.get("version") != 1:
            raise R2BackupError("unsupported R2 backup manifest")
        sqlite_report = inspect_database(root / _SQLITE_NAME)
        payload_report = inspect_payload_tree(root / _PAYLOAD_NAME)
        if manifest.get("sqlite") != _json_record(sqlite_report):
            raise R2BackupError("SQLite backup does not match manifest")
        if manifest.get("payload") != _json_record(payload_report):
            raise R2BackupError("payload backup does not match manifest")
    except R2BackupError:
        raise
    except (AttributeError, KeyError, OSError, orjson.JSONDecodeError) as exc:
        raise R2BackupError("invalid R2 backup manifest") from exc
    return sqlite_report, payload_report


def _json_record(
    value: SQLiteDatabaseReport | PayloadTreeReport,
) -> object:
    return orjson.loads(orjson.dumps(asdict(value)))


def _remove_new_restore(sqlite_target: Path, payload_target: Path) -> None:
    sqlite_target.unlink(missing_ok=True)
    for partial in sqlite_target.parent.glob(f".{sqlite_target.name}*.partial*"):
        partial.unlink(missing_ok=True)
    if payload_target.exists():
        shutil.rmtree(payload_target)


if __name__ == "__main__":
    raise SystemExit(main())
