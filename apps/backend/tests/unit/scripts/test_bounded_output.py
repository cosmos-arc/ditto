"""实际子进程的大输出与非零退出均保持可观察。"""

import sys
from pathlib import Path

from ditto_apps.scripts.bounded_output import run


def test_output_rotates_and_preserves_exit(tmp_path: Path) -> None:
    result = run(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('x' * 100000); sys.exit(7)",
        ],
        tmp_path / "worker.log",
        max_bytes=8192,
        backups=2,
    )
    assert result == 7
    files = list(tmp_path.glob("worker.log*"))
    assert len(files) == 3
    assert sum(path.stat().st_size for path in files) <= 3 * 8192
