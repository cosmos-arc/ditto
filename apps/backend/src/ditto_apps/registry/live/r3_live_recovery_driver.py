"""Isolated R3 live backup/restore acceptance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from ditto_apps.registry.live.r3_live_evidence_store import (
    sha256_file,
    write_addressed,
)
from ditto_apps.registry.live.r3_research_backup import (
    create_r3_research_backup,
    restore_r3_research_backup,
    verify_r3_research_backup,
    verify_restored_r3_research_backup,
)

__all__ = ["LiveBackupRestoreResult", "run_live_backup_restore"]


@dataclass(frozen=True, slots=True)
class LiveBackupRestoreResult:
    """Hash and domain parity for one isolated production-shaped recovery unit."""

    schema: str
    generated_at: str
    backup_root: str
    restore_root: str
    backup_manifest_hash: str
    metadata_hash_matches: bool
    research_hash_matches: bool
    artifact_hash_matches: bool
    domain_matches: bool


def run_live_backup_restore(
    *,
    data_root: Path,
    evidence_root: Path,
    backup_root: Path,
    restore_root: Path,
) -> LiveBackupRestoreResult:
    """Create or re-verify one non-overwriting live backup and restored root."""
    source = data_root.expanduser().resolve(strict=True)
    backup_target = backup_root.expanduser().resolve(strict=False)
    restore_target = restore_root.expanduser().resolve(strict=False)
    if backup_target.exists() != restore_target.exists():
        raise ValueError("live recovery roots are only partially populated")
    if not backup_target.exists():
        backup = create_r3_research_backup(
            data_root=source,
            backup_root=backup_target,
        )
        restore = restore_r3_research_backup(
            backup_root=backup_target,
            destination_root=restore_target,
        )
        verified_restore = None
    else:
        backup = verify_r3_research_backup(backup_root=backup_target)
        verified_restore = verify_restored_r3_research_backup(
            backup_root=backup_target,
            destination_root=restore_target,
        )
        restore = None
    verified_backup = verify_r3_research_backup(backup_root=backup_target)
    verified = verify_restored_r3_research_backup(
        backup_root=backup_target,
        destination_root=restore_target,
    )
    metadata_matches = backup.metadata.sha256 == verified_backup.metadata.sha256 and (
        restore is None or restore.metadata.sha256 == verified_backup.metadata.sha256
    )
    research_matches = backup.research.sha256 == verified_backup.research.sha256 and (
        restore is None or restore.research.sha256 == verified_backup.research.sha256
    )
    artifact_matches = (
        backup.artifacts.root_sha256 == verified_backup.artifacts.root_sha256
        and (
            restore is None
            or restore.artifacts.root_sha256 == verified_backup.artifacts.root_sha256
        )
    )
    domain_matches = verified.domain == verified_backup.domain
    if restore is None and verified_restore is not None:
        domain_matches = domain_matches and verified_restore.domain == verified.domain
    result = LiveBackupRestoreResult(
        schema="ditto.r3-live-backup-restore.v1",
        generated_at=datetime.now(UTC).isoformat(),
        backup_root=str(backup_target),
        restore_root=str(restore_target),
        backup_manifest_hash=sha256_file(verified_backup.manifest_path),
        metadata_hash_matches=metadata_matches,
        research_hash_matches=research_matches,
        artifact_hash_matches=artifact_matches,
        domain_matches=domain_matches,
    )
    write_addressed(
        evidence_root=evidence_root.expanduser().resolve(strict=True),
        category="recovery",
        payload=asdict(result),
    )
    return result
