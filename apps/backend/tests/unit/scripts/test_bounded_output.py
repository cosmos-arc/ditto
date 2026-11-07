"""实际子进程的大输出与非零退出均保持可观察。"""

import subprocess
import sys
import time
from pathlib import Path

import pytest
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


def test_existing_oversized_logs_are_bounded_on_start(tmp_path: Path) -> None:
    for name in ("worker.log", "worker.log.1", "worker.log.8"):
        (tmp_path / name).write_bytes(b"x" * 65536)
    evidence = tmp_path / "worker.log.payload"
    evidence.write_bytes(b"keep")
    assert (
        run(
            [sys.executable, "-c", "print('fresh')"],
            tmp_path / "worker.log",
            max_bytes=8192,
            backups=2,
        )
        == 0
    )
    logs = [tmp_path / "worker.log", *tmp_path.glob("worker.log.[0-9]*")]
    assert len(logs) <= 3
    assert all(path.stat().st_size <= 8192 for path in logs)
    assert evidence.read_bytes() == b"keep"


@pytest.mark.slow
def test_stop_is_bounded_when_child_ignores_term(tmp_path: Path) -> None:
    log = tmp_path / "worker.log"
    with subprocess.Popen(  # noqa: S603 - fixed local test argv
        [
            sys.executable,
            "-m",
            "ditto_apps.scripts.bounded_output",
            "--log",
            str(log),
            "--",
            sys.executable,
            "-u",
            "-c",
            "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            + "print('ready'); time.sleep(60)",
        ]
    ) as worker:
        deadline = time.monotonic() + 10
        while not (log.exists() and "ready" in log.read_text()):
            if time.monotonic() > deadline:
                worker.kill()
                raise AssertionError("worker failed to start")
            time.sleep(0.05)
        worker.terminate()
        assert worker.wait(timeout=15) != 0
