"""Verified, non-overwriting backup and restore for immutable payload trees."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "PayloadBackupError",
    "PayloadFileReport",
    "PayloadTreeReport",
    "backup_payload_tree",
    "inspect_payload_tree",
    "restore_payload_tree",
]


class PayloadBackupError(RuntimeError):
    """Raised when a payload tree cannot be copied and verified safely."""


@dataclass(frozen=True, slots=True)
class PayloadFileReport:
    """Checksum evidence for one relative payload file."""

    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PayloadTreeReport:
    """Deterministic logical identity for one payload directory."""

    directory_name: str
    file_count: int
    total_bytes: int
    root_sha256: str
    files: tuple[PayloadFileReport, ...]


def inspect_payload_tree(directory: Path) -> PayloadTreeReport:
    """Return deterministic per-file and whole-tree checksum evidence."""
    root = _validated_source(directory)
    files: list[PayloadFileReport] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise PayloadBackupError("payload tree cannot contain symbolic links")
        if not path.is_file():
            continue
        relative_path = path.relative_to(root).as_posix()
        files.append(
            PayloadFileReport(
                relative_path=relative_path,
                size_bytes=path.stat().st_size,
                sha256=_file_sha256(path),
            )
        )
    digest = hashlib.sha256()
    for item in files:
        digest.update(item.relative_path.encode())
        digest.update(b"\0")
        digest.update(str(item.size_bytes).encode())
        digest.update(b"\0")
        digest.update(item.sha256.encode())
        digest.update(b"\n")
    return PayloadTreeReport(
        directory_name=root.name,
        file_count=len(files),
        total_bytes=sum(item.size_bytes for item in files),
        root_sha256=f"sha256:{digest.hexdigest()}",
        files=tuple(files),
    )


def backup_payload_tree(source: Path, destination: Path) -> PayloadTreeReport:
    """Copy and verify a payload tree without overwriting prior evidence."""
    return _copy_payload_tree(source, destination)


def restore_payload_tree(backup: Path, destination: Path) -> PayloadTreeReport:
    """Restore and verify a payload tree into a new destination."""
    return _copy_payload_tree(backup, destination)


def _copy_payload_tree(source: Path, destination: Path) -> PayloadTreeReport:
    source_path = _validated_source(source)
    destination_path = destination.expanduser().resolve(strict=False)
    if destination_path.exists():
        raise PayloadBackupError("destination already exists")
    if destination_path == source_path or destination_path.is_relative_to(source_path):
        raise PayloadBackupError("destination must be outside the source tree")
    source_report = inspect_payload_tree(source_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        destination_path.mkdir()
        created = True
        _copy_payload_directories(source_path, destination_path)
        _copy_payload_files(source_path, destination_path, source_report)
        destination_report = inspect_payload_tree(destination_path)
        if _logical_tree_identity(destination_report) != _logical_tree_identity(
            source_report
        ):
            raise PayloadBackupError("payload tree verification failed")
        return destination_report
    except PayloadBackupError:
        if created:
            shutil.rmtree(destination_path)
        raise
    except OSError as exc:
        if created:
            shutil.rmtree(destination_path)
        raise PayloadBackupError("payload tree copy failed") from exc


def _copy_payload_directories(source: Path, destination: Path) -> None:
    directories = sorted(path for path in source.rglob("*") if path.is_dir())
    for directory in directories:
        if directory.is_symlink():
            raise PayloadBackupError("payload tree cannot contain symbolic links")
        (destination / directory.relative_to(source)).mkdir(
            parents=True,
            exist_ok=True,
        )


def _copy_payload_files(
    source: Path,
    destination: Path,
    report: PayloadTreeReport,
) -> None:
    for item in report.files:
        source_file = source / item.relative_path
        destination_file = destination / item.relative_path
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination_file)


def _validated_source(directory: Path) -> Path:
    expanded = directory.expanduser()
    if expanded.is_symlink():
        raise PayloadBackupError("source payload directory cannot be a symbolic link")
    path = expanded.resolve(strict=False)
    if not path.is_dir():
        raise PayloadBackupError("source payload directory does not exist")
    return path


def _logical_tree_identity(
    report: PayloadTreeReport,
) -> tuple[int, int, str, tuple[PayloadFileReport, ...]]:
    return (
        report.file_count,
        report.total_bytes,
        report.root_sha256,
        report.files,
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
