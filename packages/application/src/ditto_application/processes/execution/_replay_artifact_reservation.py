"""Exclusive, identity-checked artifact directory reservation for replay."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from ditto_application.exceptions import AppProcessError

__all__ = ["ReplayArtifactReservation"]


@dataclass(frozen=True, slots=True)
class ReplayArtifactReservation:
    """A directory this process created and may remove only while still empty."""

    target: Path
    device: int
    inode: int

    @classmethod
    def acquire(
        cls,
        target: Path,
        *,
        original: Path,
    ) -> ReplayArtifactReservation:
        """Create ``target`` atomically without accepting aliases or prior paths."""
        same_dir = target.resolve() == original.resolve()
        if same_dir or target.exists() or target.is_symlink():
            raise AppProcessError(
                "Replay artifact target already exists",
                reason=(
                    "replay_artifact_directory_collision"
                    if same_dir
                    else "replay_artifact_target_exists"
                ),
                original_artifact_dir=str(original),
                replay_artifact_dir=str(target),
            )
        try:
            target.mkdir()
        except FileExistsError as exc:
            raise AppProcessError(
                "Replay artifact target already exists",
                reason="replay_artifact_target_exists",
                replay_artifact_dir=str(target),
            ) from exc
        created = target.stat(follow_symlinks=False)
        if not stat.S_ISDIR(created.st_mode):
            raise AppProcessError(
                "Replay artifact reservation is not a directory",
                reason="replay_artifact_target_exists",
                replay_artifact_dir=str(target),
            )
        return cls(target=target, device=created.st_dev, inode=created.st_ino)

    def matches(self, candidate: Path) -> bool:
        """Return whether an indexed path is the exact directory we reserved."""
        if _absolute(candidate) != _absolute(self.target) or candidate.is_symlink():
            return False
        try:
            current = candidate.stat(follow_symlinks=False)
        except OSError:
            return False
        return (
            stat.S_ISDIR(current.st_mode)
            and current.st_dev == self.device
            and current.st_ino == self.inode
        )

    def cleanup_empty(self) -> None:
        """Remove only our unchanged empty placeholder; never remove artifacts."""
        try:
            current = self.target.stat(follow_symlinks=False)
        except OSError:
            return
        if (
            not stat.S_ISDIR(current.st_mode)
            or current.st_dev != self.device
            or current.st_ino != self.inode
        ):
            return
        try:
            self.target.rmdir()
        except OSError:
            return


def _absolute(path: Path) -> Path:
    return path.resolve(strict=False)
