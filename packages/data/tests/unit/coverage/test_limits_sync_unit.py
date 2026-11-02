"""覆盖合同 YAML ↔ 运行时蒸馏同步守卫（#628）。

docs/data/coverage-contract.yaml 刷新后必须同步蒸馏
ditto_data/coverage/limits.py，否则本测试响亮失败并指出差异条目。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_data.coverage.limits import (
    COVERAGE_MEASURED_AT,
    DatasetCoverageLimit,
    list_dataset_coverage,
)

_REPO_ROOT = Path(__file__).resolve().parents[5]
_YAML_PATH = _REPO_ROOT / "docs" / "data" / "coverage-contract.yaml"

yaml = pytest.importorskip("yaml")


def _distill_from_yaml() -> dict[str, DatasetCoverageLimit]:
    with _YAML_PATH.open(encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    distilled: dict[str, DatasetCoverageLimit] = {}
    for dataset, entry in doc["datasets"].items():
        measured = entry.get("measured") or {}
        distilled[dataset] = DatasetCoverageLimit(
            dataset=dataset,
            domain=entry.get("domain") or "unknown",
            status=entry.get("status") or "unknown",
            measured_start=measured.get("start"),
            measured_end=measured.get("end"),
            gaps=tuple(entry.get("gaps") or ()),
            notes=entry.get("notes"),
        )
    return distilled


def test_runtime_module_matches_yaml_projection() -> None:
    expected = _distill_from_yaml()
    runtime = {item.dataset: item for item in list_dataset_coverage()}
    assert set(runtime) == set(expected), (
        "coverage-contract.yaml 与 ditto_data/coverage/limits.py 数据集集不一致:"
        f" 仅在 YAML={sorted(set(expected) - set(runtime))};"
        f" 仅在运行时={sorted(set(runtime) - set(expected))}"
    )
    mismatched = sorted(
        dataset for dataset in expected if runtime[dataset] != expected[dataset]
    )
    assert not mismatched, (
        "以下数据集的运行时蒸馏与 coverage-contract.yaml 不一致; "
        f"请同步 ditto_data/coverage/limits.py: {mismatched}"
    )


def test_status_vocabulary_closed() -> None:
    allowed = {"ready", "partial", "empty"}
    bad = [i.dataset for i in list_dataset_coverage() if i.status not in allowed]
    assert not bad, f"未知状态禁止出现(unknown 不允许冒充就绪): {bad}"


def test_measured_at_matches_yaml_meta() -> None:
    with _YAML_PATH.open(encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    raw = str(doc["meta"]["measured_at"])
    assert raw.startswith(COVERAGE_MEASURED_AT.isoformat()), (
        f"运行时 COVERAGE_MEASURED_AT={COVERAGE_MEASURED_AT} 与 YAML "
        f"meta.measured_at={raw} 不一致"
    )
