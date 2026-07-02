"""Wave 1 catalog 校验脚本单元测试。

纯逻辑测试 (mock payload) 验证 ``wave1_catalog_check`` 的矩阵构建与渲染契约;
e2e 测试跑真实脚本, RED (72 failures) -> GREEN (0 failure) 随 backfill 收敛。
e2e 需先 source scripts/acceptance/wave1_env.sh 指向 backfilled data root。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from scripts.acceptance.rc1_requirements import LAUNCH_DATASETS
from scripts.acceptance.wave1_catalog_check import (
    build_dataset_matrix,
    render_matrix,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve().parent / "wave1_catalog_check.py"
ENV_SCRIPT = Path(__file__).resolve().parent / "wave1_env.sh"
_FILLED_ROW_COUNT = 100


def _make_payload(dataset: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "dataset": dataset,
        "dataset_maturity": "initial-focus",
        "dataset_promotion_status": "ready",
        "catalog_storage_uri": "sqlite:///x.db",
        "catalog_schema_hash": "abc",
        "catalog_row_count": _FILLED_ROW_COUNT,
        "catalog_freshness_status": "fresh",
    }
    base.update(overrides)
    return {"datasets": [base]}


def test_build_matrix_marks_missing_dataset_as_absent() -> None:
    payload = {"datasets": [{"dataset": "other", "dataset_maturity": "stable"}]}

    matrix = build_dataset_matrix(payload, datasets=("stock_daily",))

    row = matrix[0]
    assert row["dataset"] == "stock_daily"
    assert row["present"] is False
    assert row["has_storage_uri"] is False
    assert row["has_schema_hash"] is False
    assert row["row_count"] is None


def test_build_matrix_reflects_filled_catalog_fields() -> None:
    payload = _make_payload("stock_daily")

    matrix = build_dataset_matrix(payload, datasets=("stock_daily",))

    row = matrix[0]
    assert row["present"] is True
    assert row["maturity"] == "initial-focus"
    assert row["promotion_status"] == "ready"
    assert row["freshness"] == "fresh"
    assert row["has_storage_uri"] is True
    assert row["has_schema_hash"] is True
    assert row["row_count"] == _FILLED_ROW_COUNT


def test_build_matrix_covers_all_launch_datasets() -> None:
    matrix = build_dataset_matrix({"datasets": []})

    assert [row["dataset"] for row in matrix] == list(LAUNCH_DATASETS)


def test_render_matrix_includes_every_launch_dataset() -> None:
    rendered = render_matrix(build_dataset_matrix({"datasets": []}))

    for dataset in LAUNCH_DATASETS:
        assert dataset in rendered


def test_script_help_runs_when_executed_directly() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--output" in result.stdout


@pytest.mark.e2e
def test_wave1_catalog_check_passes_after_backfill() -> None:
    """RED->GREEN: Phase 1 完成后 14 数据集 catalog 校验 0 failure。"""

    if not os.environ.get("DITTO_DATA_ROOT") and not os.environ.get("WAVE1_DATA_ROOT"):
        pytest.skip("需先 source wave1_env.sh 指向 backfilled data root")

    result = subprocess.run(
        [
            "bash",
            "-c",
            f"source '{ENV_SCRIPT}' && {sys.executable} '{SCRIPT}'",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"catalog check 未通过 (Phase 1 完成后预期 0 failure):\n{result.stdout[-2000:]}"
    )
