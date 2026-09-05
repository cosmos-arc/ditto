"""Four-domain workstation backup and isolated restore commands."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import typer

from ditto_apps.cli.utils.output import output_json_dict
from ditto_apps.operations.workstation_backup import (
    WorkstationBackupError,
    backup_workstation,
    restore_workstation,
    verify_workstation_backup,
)

app = typer.Typer(help="工作站四域备份、验证与隔离恢复")


def _fail(reason: str, error: WorkstationBackupError) -> None:
    output_json_dict({"status": "failed", "reason": reason, "detail": str(error)})
    raise typer.Exit(1)


@app.command("backup")
def backup(
    source_root: Path = typer.Option(..., "--source-root", help="活动运行时根目录"),
    destination: Path = typer.Option(
        ..., "--destination", help="新建且不与源目录重叠的备份目录"
    ),
) -> None:
    """Atomically capture every data, research, trading, and Agent store."""
    try:
        manifest = backup_workstation(source_root, destination)
    except WorkstationBackupError as error:
        _fail("WORKSTATION_BACKUP_FAILED", error)
        return
    output_json_dict({"status": "completed", **asdict(manifest)})


@app.command("verify")
def verify(
    backup_root: Path = typer.Option(..., "--backup-root", help="备份目录"),
) -> None:
    """Authenticate one complete recovery unit without mutating it."""
    try:
        manifest = verify_workstation_backup(backup_root)
    except WorkstationBackupError as error:
        _fail("WORKSTATION_VERIFY_FAILED", error)
        return
    output_json_dict({"status": "completed", **asdict(manifest)})


@app.command("restore")
def restore(
    backup_root: Path = typer.Option(..., "--backup-root", help="已验证备份目录"),
    destination_root: Path = typer.Option(
        ..., "--destination-root", help="全新且隔离的恢复运行时目录"
    ),
) -> None:
    """Restore all stores into a new root; never overwrite an active runtime."""
    try:
        manifest = restore_workstation(backup_root, destination_root)
    except WorkstationBackupError as error:
        _fail("WORKSTATION_RESTORE_FAILED", error)
        return
    output_json_dict({"status": "completed", **asdict(manifest)})
