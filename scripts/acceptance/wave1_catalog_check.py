"""Wave 1 catalog evidence 全量校验。

跑 ``ditto ops status --json`` + ``validate_maturity_status`` 校验 launch
数据集, 输出 per-dataset 矩阵与 failure 清单, 退出码反映 ok。
供 Phase 1.4 RED/GREEN 迭代: backfill/promotion 前后重跑, 观察 failures 收敛。

用法: source scripts/acceptance/wave1_env.sh 后执行
    pixi run -e dev python scripts/acceptance/wave1_catalog_check.py [--output FILE]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import orjson

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.acceptance.rc1_requirements import (  # noqa: E402
    LAUNCH_DATASETS,
    validate_maturity_status,
)

_STDERR_TAIL = 2000


def _dataset_rows(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """从 ops status payload 提取 dataset -> row 映射。"""
    rows = payload.get("datasets")
    if not isinstance(rows, list):
        rows = payload.get("ingestion_status")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("dataset")): row
        for row in rows
        if isinstance(row, dict) and row.get("dataset") is not None
    }


def build_dataset_matrix(
    payload: dict[str, Any],
    *,
    datasets: tuple[str, ...] = LAUNCH_DATASETS,
) -> list[dict[str, Any]]:
    """构建 per-dataset 校验矩阵（人类可读 + 机读）。"""
    rows_by_dataset = _dataset_rows(payload)
    matrix: list[dict[str, Any]] = []
    for dataset in datasets:
        row = rows_by_dataset.get(dataset, {})
        row_count = row.get("catalog_row_count")
        matrix.append(
            {
                "dataset": dataset,
                "present": bool(row),
                "maturity": str(row.get("dataset_maturity") or ""),
                "promotion_status": str(row.get("dataset_promotion_status") or ""),
                "freshness": str(row.get("catalog_freshness_status") or ""),
                "has_storage_uri": bool(row.get("catalog_storage_uri")),
                "has_schema_hash": bool(row.get("catalog_schema_hash")),
                "row_count": row_count if row_count is not None else None,
            }
        )
    return matrix


def render_matrix(matrix: list[dict[str, Any]]) -> str:
    """渲染人类可读的矩阵表。"""
    header = (
        f"{'dataset':<22} {'maturity':<16} {'promotion':<16} "
        f"{'freshness':<16} {'storage':<8} {'schema':<8} {'rows':>8}"
    )
    lines = [header, "-" * len(header)]
    for row in matrix:
        lines.append(
            f"{row['dataset']:<22} {row['maturity']:<16} "
            f"{row['promotion_status']:<16} {row['freshness']:<16} "
            f"{'yes' if row['has_storage_uri'] else 'no':<8} "
            f"{'yes' if row['has_schema_hash'] else 'no':<8} "
            f"{row['row_count'] if row['row_count'] is not None else '-':>8}"
        )
    return "\n".join(lines)


def _fetch_ops_status() -> dict[str, Any]:
    """跑 ``ditto ops status --json`` 返回 payload。"""
    completed = subprocess.run(
        [sys.executable, "-m", "ditto_apps.cli.main", "ops", "status", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"ops status --json 退出码 {completed.returncode}:\n"
            f"{completed.stderr[-_STDERR_TAIL:]}"
        )
    try:
        return orjson.loads(completed.stdout)
    except orjson.JSONDecodeError as exc:
        raise RuntimeError(
            f"ops status stdout 非合法 JSON: {exc}\n{completed.stdout[-_STDERR_TAIL:]}"
        ) from exc


def main() -> int:
    """跑 ops status、校验 launch 数据集、输出矩阵与 failure 清单。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSON 报告输出路径 (可选)",
    )
    args = parser.parse_args()

    payload = _fetch_ops_status()
    validation = validate_maturity_status(payload)
    matrix = build_dataset_matrix(payload)

    print(render_matrix(matrix))
    print("")
    print(f"校验结果: ok={validation.ok} failures={len(validation.failures)}")
    if validation.failures:
        print("\n失败清单:")
        for failure in validation.failures:
            print(f"  - {failure}")

    if args.output is not None:
        report = {
            "ok": validation.ok,
            "failure_count": len(validation.failures),
            "failures": list(validation.failures),
            "matrix": matrix,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(
            orjson.dumps(report, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
        )

    return 0 if validation.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
