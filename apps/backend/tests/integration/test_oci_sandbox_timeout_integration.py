"""OCI 沙箱进程边界超时用例（自 unit 目录按性质归位 integration，2026-09-27）。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from apps.backend.tests.unit.test_oci_sandbox_process_runner import (
    _command,
    _fake_docker,
    _runner,
)


@pytest.mark.slow  # [6] 参数休眠 6s 天然超集成预算(实测 10s), 进慢车道
@pytest.mark.parametrize("probe_delay_seconds", [0, 6])
@pytest.mark.integration  # 集成性质(真入口/容器/子进程/重数据), 2026-09-27 分层归位
def test_runner_enforces_wall_timeout_and_removes_the_exact_container(
    tmp_path: Path,
    probe_delay_seconds: float,
) -> None:
    executable, cleanup = _fake_docker(
        tmp_path, probe_delay_seconds=probe_delay_seconds
    )
    runner, seccomp = _runner(executable, tmp_path)

    result = runner.run(_command("timeout", seccomp_path=seccomp, timeout=3))
    started = float((tmp_path / "probe.finished").read_text(encoding="ascii"))

    # Inventory has its own timeout. Measure from the real fake-CLI probe
    # completion, retaining runtime startup and exact cleanup in this bound.
    # Eight seconds remains below the fake workload's ten-second sleep.
    assert time.monotonic() - started < 8
    assert result.timed_out is True
    assert cleanup.read_text(encoding="utf-8") == "cleaned"


@pytest.mark.slow  # [6] 参数休眠 6s 天然超集成预算(实测 10s), 进慢车道
@pytest.mark.parametrize("probe_delay_seconds", [0, 6])
@pytest.mark.integration  # 集成性质(真入口/容器/子进程/重数据), 2026-09-27 分层归位
def test_runner_timeout_is_not_extended_by_orphaned_output_pipes(
    tmp_path: Path,
    probe_delay_seconds: float,
) -> None:
    executable, cleanup = _fake_docker(
        tmp_path, probe_delay_seconds=probe_delay_seconds
    )
    runner, seccomp = _runner(executable, tmp_path)

    result = runner.run(_command("orphan-pipe", seccomp_path=seccomp, timeout=3))
    started = float((tmp_path / "probe.finished").read_text(encoding="ascii"))

    # Exclude only the separately bounded inventory probe, not execution or
    # cleanup. Waiting for the orphan's ten-second sleep must still fail.
    assert time.monotonic() - started < 8
    assert result.timed_out is True
    assert cleanup.read_text(encoding="utf-8") == "cleaned"
