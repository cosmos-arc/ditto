"""例行 fuyao dump 刷新任务的失败隔离契约（#617）."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_apps.jobs.tasks import fuyao_dump as fuyao_dump_module
from ditto_apps.jobs.tasks.fuyao_dump import run_fuyao_adjustment_factors_dump
from ditto_apps.registry.fuyao_dump import (
    FuyaoDumpDownload,
    FuyaoSourceUnconfiguredError,
)
from pytest_mock import MockerFixture


@pytest.mark.unit
def test_success_returns_stats(mocker: MockerFixture) -> None:
    """成功路径：固定键形状 + 统计字段回填."""
    mocker.patch.object(
        fuyao_dump_module,
        "download_fuyao_dump",
        return_value=FuyaoDumpDownload(
            kind="adjustment-factors",
            path=Path("/data/fuyao/dumps/adjustment-factors/20261026.parquet"),
            rows=12_345,
            tickers=5_580,
            duplicate_keys=0,
            date_range=None,
        ),
    )

    result = run_fuyao_adjustment_factors_dump()

    assert result == {
        "kind": "adjustment-factors",
        "status": "success",
        "path": "/data/fuyao/dumps/adjustment-factors/20261026.parquet",
        "rows": 12_345,
        "tickers": 5_580,
        "duplicate_keys": 0,
        "identities_registered": 0,
        "identities_unresolved": 0,
        "error": None,
    }


@pytest.mark.unit
def test_unconfigured_source_skips(mocker: MockerFixture) -> None:
    """辅源未配置（FUYAO_API_KEY 缺失）显式 skipped，不拖垮例行链."""
    mocker.patch.object(
        fuyao_dump_module,
        "download_fuyao_dump",
        side_effect=FuyaoSourceUnconfiguredError("fuyao 未配置: set FUYAO_API_KEY"),
    )

    result = run_fuyao_adjustment_factors_dump()

    assert result["status"] == "skipped"
    assert result["path"] is None
    assert "FUYAO_API_KEY" in str(result["error"])


@pytest.mark.unit
def test_download_failure_degrades_to_failed(mocker: MockerFixture) -> None:
    """下载异常显式 failed 留痕（对账将按既有语义降级），不抛出."""
    mocker.patch.object(
        fuyao_dump_module,
        "download_fuyao_dump",
        side_effect=RuntimeError("network down"),
    )

    result = run_fuyao_adjustment_factors_dump()

    assert result["status"] == "failed"
    assert result["error"] == "RuntimeError: network down"
    assert result["rows"] is None


@pytest.mark.unit
def test_result_keys_stable_across_statuses(mocker: MockerFixture) -> None:
    """三种结局的键集合一致（例行链/汇报消费方不分支键存在性）."""
    mocker.patch.object(
        fuyao_dump_module,
        "download_fuyao_dump",
        side_effect=RuntimeError("boom"),
    )
    failed = run_fuyao_adjustment_factors_dump()
    mocker.patch.object(
        fuyao_dump_module,
        "download_fuyao_dump",
        side_effect=FuyaoSourceUnconfiguredError("set FUYAO_API_KEY"),
    )
    skipped = run_fuyao_adjustment_factors_dump()

    assert set(failed) == set(skipped)
    assert set(failed) == {
        "kind",
        "status",
        "path",
        "rows",
        "tickers",
        "duplicate_keys",
        "identities_registered",
        "identities_unresolved",
        "error",
    }
