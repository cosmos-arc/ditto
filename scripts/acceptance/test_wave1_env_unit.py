"""Wave 1 acceptance env 脚本单元测试。

校验 ``scripts/acceptance/wave1_env.sh`` source 后导出的环境变量字段完整、
路径解析正确。该测试仅校验脚本契约，不依赖真实数据环境。

运行::

    pixi run -e dev pytest scripts/acceptance/test_wave1_env_unit.py --no-cov -q
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve().parent / "wave1_env.sh"

REQUIRED_KEYS = (
    "DITTO_DATA_ROOT",
    "SQLITE_PATH",
    "DUCKDB_PATH",
    "ENVIRONMENT",
    "PYTHONUNBUFFERED",
)


def _source_env(args: list[str] | None = None) -> dict[str, str]:
    """``source wave1_env.sh``（可选位置参数）后导出的环境变量。"""
    arg_str = " ".join(args) if args else ""
    completed = subprocess.run(
        [
            "bash",
            "-c",
            f"unset WAVE1_DATA_ROOT; source '{SCRIPT}' {arg_str} && env -0",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    env: dict[str, str] = {}
    for entry in completed.stdout.split("\0"):
        if not entry:
            continue
        eq = entry.find("=")
        if eq <= 0:
            continue
        env[entry[:eq]] = entry[eq + 1 :]
    return env


def test_wave1_env_exports_required_fields() -> None:
    env = _source_env(["some/relative-root"])

    assert env["ENVIRONMENT"] == "testing"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["DITTO_DATA_ROOT"].endswith("some/relative-root")
    assert env["SQLITE_PATH"] == f"{env['DITTO_DATA_ROOT']}/metadata/metadata.sqlite"
    assert env["DUCKDB_PATH"] == f"{env['DITTO_DATA_ROOT']}/db/ditto.duckdb"


def test_wave1_env_resolves_relative_root_against_pwd() -> None:
    """相对路径 data root 应解析为仓库根下的绝对路径。"""
    env = _source_env([".tmp/ditto-rc1"])

    assert env["DITTO_DATA_ROOT"] == (REPO_ROOT / ".tmp" / "ditto-rc1").as_posix()


def test_wave1_env_defaults_to_tmp_ditto_rc1() -> None:
    """不传参数时默认 data root 为 .tmp/ditto-rc1。"""
    env = _source_env()

    assert env["DITTO_DATA_ROOT"].endswith(".tmp/ditto-rc1")
    assert all(key in env for key in REQUIRED_KEYS)


def test_wave1_env_respects_existing_wave1_data_root() -> None:
    """已导出的 WAVE1_DATA_ROOT 应作为默认值被复用。"""
    completed = subprocess.run(
        [
            "bash",
            "-c",
            f"export WAVE1_DATA_ROOT=predefined/root; source '{SCRIPT}' && env -0",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    env: dict[str, str] = {}
    for entry in completed.stdout.split("\0"):
        if entry and (eq := entry.find("=")) > 0:
            env[entry[:eq]] = entry[eq + 1 :]

    assert env["DITTO_DATA_ROOT"].endswith("predefined/root")
