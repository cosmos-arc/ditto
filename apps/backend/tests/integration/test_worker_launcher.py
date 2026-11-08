"""The versioned launcher controls logging in real flows and their children."""

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from prefect.settings import get_current_settings


@pytest.mark.slow
@pytest.mark.parametrize("diagnostic", [False, True])
def test_worker_launcher_logging(
    tmp_path: Path, prefect_test_session: None, diagnostic: bool
) -> None:
    del prefect_test_session
    repo = Path(__file__).resolve().parents[4]
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    launcher = scripts / "start-prefect-worker.sh"
    shutil.copyfile(repo / "scripts/start-prefect-worker.sh", launcher)
    binaries = tmp_path / ".venv/bin"
    binaries.mkdir(parents=True)
    python = binaries / "python"
    python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
    python.chmod(0o755)
    # Replace only the long-lived worker CLI; execute a real Prefect flow and
    # lazy application logging in its child, without API observability setup.
    prefect = binaries / "prefect"
    prefect.write_text(
        f"#!{sys.executable}\n"
        "import subprocess, sys\n"
        "from prefect import flow\n"
        "from ditto_platform.foundation import logger\n"
        "@flow\n"
        "def probe():\n"
        "    logger.debug('worker-debug-probe')\n"
        "    logger.info('worker-info-probe')\n"
        "    logger.error('worker-error-probe')\n"
        "    subprocess.run([sys.executable, '-c', "
        '"from ditto_platform.foundation import logger; '
        "logger.debug('child-debug-probe'); "
        "logger.info('child-info-probe'); "
        "logger.error('child-error-probe')\"], check=True)\n"
        "probe()\n"
    )
    prefect.chmod(0o755)
    env = os.environ.copy()
    for key in ("LOGURU_LEVEL", "PREFECT_LOGGING_LEVEL"):
        env.pop(key, None)
    env.update(
        PREFECT_API_URL=str(get_current_settings().api.url),
        DITTO_CONFIG_ROOT=str(tmp_path),
        DITTO_STATE_ROOT=str(tmp_path / "data"),
        DITTO_CACHE_ROOT=str(tmp_path / "cache"),
    )
    if diagnostic:
        env["LOGURU_LEVEL"] = "DEBUG"
    subprocess.run(  # noqa: S603 - isolated, fixed local launcher
        ["/bin/sh", str(launcher)], env=env, check=True, timeout=60
    )
    output = (tmp_path / "cache/prefect-worker/worker.log").read_text()
    assert "Finished in state Completed" in output
    for prefix in ("worker", "child"):
        assert f"{prefix}-info-probe" in output
        assert f"{prefix}-error-probe" in output
        assert (f"{prefix}-debug-probe" in output) is diagnostic
