"""ops SQLite 备份、验证与恢复命令。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ditto_apps.cli.commands.ops import app
from typer.testing import CliRunner


def _seed_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE packages (artifact_id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO packages VALUES ('artifact-r1')")


def test_sqlite_backup_verify_and_restore_commands(tmp_path: Path) -> None:
    source = tmp_path / "metadata.sqlite"
    backup = tmp_path / "r1-backup.sqlite"
    restored = tmp_path / "restore-root" / "metadata.sqlite"
    _seed_database(source)
    runner = CliRunner()

    backup_result = runner.invoke(
        app,
        ["backup-sqlite", "--source", str(source), "--destination", str(backup)],
    )
    verify_result = runner.invoke(
        app,
        ["verify-sqlite", "--database", str(backup)],
    )
    restore_result = runner.invoke(
        app,
        ["restore-sqlite", "--backup", str(backup), "--destination", str(restored)],
    )

    assert backup_result.exit_code == 0, backup_result.exception
    assert verify_result.exit_code == 0, verify_result.exception
    assert restore_result.exit_code == 0, restore_result.exception
    assert '"integrity_check": "ok"' in backup_result.stdout
    assert '"packages": 1' in verify_result.stdout
    assert '"integrity_check": "ok"' in restore_result.stdout
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT artifact_id FROM packages").fetchone() == (
            "artifact-r1",
        )


def test_sqlite_backup_command_fails_closed_without_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "metadata.sqlite"
    destination = tmp_path / "operator-evidence.sqlite"
    _seed_database(source)
    destination.write_bytes(b"preserve me")

    result = CliRunner().invoke(
        app,
        [
            "backup-sqlite",
            "--source",
            str(source),
            "--destination",
            str(destination),
        ],
    )

    assert result.exit_code == 1
    assert '"reason": "SQLITE_BACKUP_FAILED"' in result.stdout
    assert "destination already exists" in result.stdout
    assert destination.read_bytes() == b"preserve me"
