"""Unit tests for the r2_data_acceptance runner's replay-robustness helpers."""

from __future__ import annotations

import argparse
from pathlib import Path

from ditto_apps.scripts.r2_data_acceptance import (
    _parser,
    _remove_new_restore,
    _resolve_live_args,
)

Stamp = "20260804T120000Z"


def _args(argv: list[str]) -> argparse.Namespace:
    return _parser().parse_args(argv)


def test_resolve_live_args_makes_all_paths_absolute(tmp_path: Path) -> None:
    rel_output = tmp_path / "r2-report.json"
    args = _args(
        [
            "--mode",
            "live",
            "--evidence",
            str(tmp_path / "evidence.json"),
            "--sqlite-path",
            str(tmp_path / "metadata.sqlite"),
            "--payload-root",
            str(tmp_path / "market"),
            "--backup-root",
            str(tmp_path / "backup"),
            "--restore-root",
            str(tmp_path / "restore"),
            "--output",
            str(rel_output),
        ]
    )

    resolved = _resolve_live_args(args, stamp=Stamp)

    assert resolved.evidence_path == (tmp_path / "evidence.json").resolve()
    assert resolved.sqlite_path == (tmp_path / "metadata.sqlite").resolve()
    assert resolved.payload_root == (tmp_path / "market").resolve()
    assert resolved.output == rel_output.resolve()
    for path in (
        resolved.evidence_path,
        resolved.sqlite_path,
        resolved.payload_root,
        resolved.output,
    ):
        assert path is not None
        assert path.is_absolute()


def test_resolve_live_args_stamps_backup_and_restore_per_run(tmp_path: Path) -> None:
    # Same operator roots across two runs must not collide: each gets a stamped subdir.
    common = [
        "--mode",
        "live",
        "--backup-root",
        str(tmp_path / "backup"),
        "--restore-root",
        str(tmp_path / "restore"),
    ]
    first = _resolve_live_args(_args(common), stamp="20260804T120000Z")
    second = _resolve_live_args(_args(common), stamp="20260804T120001Z")

    assert first.backup_root == (tmp_path / "backup").resolve() / "20260804T120000Z"
    assert second.backup_root == (tmp_path / "backup").resolve() / "20260804T120001Z"
    assert first.backup_root != second.backup_root
    assert first.restore_root == (tmp_path / "restore").resolve() / "20260804T120000Z"
    assert first.restore_root != second.restore_root


def test_resolve_live_args_syncs_sqlite_path_and_data_root_to_env(
    tmp_path: Path,
) -> None:
    args = _args(
        [
            "--mode",
            "live",
            "--sqlite-path",
            str(tmp_path / "live-data" / "metadata" / "metadata.sqlite"),
            "--data-root",
            str(tmp_path / "live-data"),
        ]
    )

    resolved = _resolve_live_args(args, stamp=Stamp)

    assert resolved.env_overrides["SQLITE_PATH"] == str(
        (tmp_path / "live-data" / "metadata" / "metadata.sqlite").resolve()
    )
    assert resolved.env_overrides["DITTO_STATE_ROOT"] == str(
        (tmp_path / "live-data").resolve()
    )


def test_resolve_live_args_leaves_env_empty_without_cli_overrides() -> None:
    args = _args(["--mode", "live"])
    resolved = _resolve_live_args(args, stamp=Stamp)
    assert resolved.env_overrides == {}
    assert resolved.backup_root is None
    assert resolved.restore_root is None
    assert resolved.output is None


def test_remove_new_restore_clears_partial_residue(tmp_path: Path) -> None:
    sqlite_target = tmp_path / "metadata.sqlite"
    sqlite_target.write_bytes(b"db")
    partial = tmp_path / ".metadata.sqlite.abc.partial"
    partial.write_bytes(b"partial")
    partial_journal = tmp_path / ".metadata.sqlite.abc.partial-journal"
    partial_journal.write_bytes(b"journal")
    payload_target = tmp_path / "market"
    (payload_target / "stock").mkdir(parents=True)

    _remove_new_restore(sqlite_target, payload_target)

    assert not sqlite_target.exists()
    assert not partial.exists()
    assert not partial_journal.exists()
    assert not payload_target.exists()
