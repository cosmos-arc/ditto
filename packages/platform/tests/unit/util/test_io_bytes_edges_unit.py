"""Non-fsync atomic byte-write edge."""

from __future__ import annotations

from pathlib import Path

from ditto_platform.foundation.util.io import atomic_bytes_write


def test_atomic_bytes_write_can_skip_fsync(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "evidence.bin"

    atomic_bytes_write(b"evidence", target, fsync=False)

    assert target.read_bytes() == b"evidence"
    assert not target.with_suffix(".bin.tmp").exists()
