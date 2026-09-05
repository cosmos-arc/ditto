"""Workstation four-domain backup CLI contract."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ditto_apps.cli.commands.workstation_recovery import app
from ditto_apps.operations.workstation_backup import WorkstationBackupManifest
from typer.testing import CliRunner


def _manifest() -> WorkstationBackupManifest:
    return WorkstationBackupManifest(
        schema_version=1,
        databases=(),
        manifest_hash="sha256:evidence",
    )


def test_workstation_backup_verify_and_restore_commands(monkeypatch) -> None:
    calls: list[tuple[str, Path, Path | None]] = []
    manifest = _manifest()

    monkeypatch.setattr(
        "ditto_apps.cli.commands.workstation_recovery.backup_workstation",
        lambda source, destination: (
            calls.append(("backup", source, destination)) or manifest
        ),
    )
    monkeypatch.setattr(
        "ditto_apps.cli.commands.workstation_recovery.verify_workstation_backup",
        lambda backup: calls.append(("verify", backup, None)) or manifest,
    )
    monkeypatch.setattr(
        "ditto_apps.cli.commands.workstation_recovery.restore_workstation",
        lambda backup, destination: (
            calls.append(("restore", backup, destination))
            or replace(manifest, manifest_hash="sha256:restored")
        ),
    )
    runner = CliRunner()

    backup = runner.invoke(
        app,
        ["backup", "--source-root", "/runtime", "--destination", "/backup"],
    )
    verify = runner.invoke(app, ["verify", "--backup-root", "/backup"])
    restore = runner.invoke(
        app,
        [
            "restore",
            "--backup-root",
            "/backup",
            "--destination-root",
            "/restored",
        ],
    )

    assert backup.exit_code == verify.exit_code == restore.exit_code == 0
    assert calls == [
        ("backup", Path("/runtime"), Path("/backup")),
        ("verify", Path("/backup"), None),
        ("restore", Path("/backup"), Path("/restored")),
    ]
    assert '"status": "completed"' in backup.stdout
    assert '"manifest_hash": "sha256:evidence"' in verify.stdout
    assert '"manifest_hash": "sha256:restored"' in restore.stdout


def test_workstation_backup_command_fails_closed(monkeypatch) -> None:
    def fail(_source: Path, _destination: Path) -> WorkstationBackupManifest:
        from ditto_apps.operations.workstation_backup import WorkstationBackupError

        raise WorkstationBackupError("database evidence mismatch")

    monkeypatch.setattr(
        "ditto_apps.cli.commands.workstation_recovery.backup_workstation", fail
    )

    result = CliRunner().invoke(
        app,
        ["backup", "--source-root", "/runtime", "--destination", "/backup"],
    )

    assert result.exit_code == 1
    assert '"reason": "WORKSTATION_BACKUP_FAILED"' in result.stdout
    assert "database evidence mismatch" in result.stdout
