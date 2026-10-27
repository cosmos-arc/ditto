"""#617：共享 fuyao dump 编排 — 北京日命名、统计、未配置显式失败."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_apps.registry import fuyao_dump as fuyao_dump_module
from ditto_apps.registry.fuyao_dump import (
    FuyaoSourceUnconfiguredError,
    download_fuyao_dump,
    dump_dest,
)
from ditto_data.sources.fuyao.client import date_to_ms
from pytest_mock import MockerFixture


def test_dump_dest_uses_beijing_calendar_date(time_machine) -> None:
    """dump 文件名用北京日期：北京 00:00-07:59（UTC 前一日）生成的当日
    dump 不得被陈旧守卫按 UTC 名误判（#515 correctness F4，自 CLI 迁入）."""
    # 北京 2026-01-02 00:30 = UTC 2026-01-01 16:30；UTC 命名会得 20260101
    time_machine.move_to("2026-01-01 16:30:00+00:00", tick=False)

    dest = dump_dest(Path("/data"), "adjustment-factors")

    assert dest.name == "20260102.parquet"
    assert dest == Path("/data/fuyao/dumps/adjustment-factors/20260102.parquet")


class _FakeFuyaoSource:
    """把预置帧写到目标路径的最小源替身."""

    def __init__(self, frame: pl.DataFrame) -> None:
        self._frame = frame
        self.calls: list[tuple[str, Path]] = []

    def download_market_dump(self, kind: str, dest: Path) -> Path:
        self.calls.append((kind, dest))
        # 复刻真源契约：目标父目录由下载方创建
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._frame.write_parquet(dest)
        return dest


def _container(
    mocker: MockerFixture,
    source: Any,
    data_root: Path,
) -> MagicMock:
    """容器替身：FuyaoSource|None 键 → source，Path 键 → data_root."""
    container = MagicMock()
    fuyao_key = fuyao_dump_module.FuyaoSource | None
    container.get.side_effect = lambda key: source if key == fuyao_key else data_root
    mocker.patch.object(fuyao_dump_module, "make_app_container", return_value=container)
    return container


@pytest.mark.unit
def test_download_adjustment_factors_returns_stats(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """成功路径：落盘目标在北京日命名路径，行数/标的/重复键统计正确."""
    frame = pl.DataFrame(
        {
            "thscode": ["600519.SH", "600519.SH", "000001.SZ"],
            "ex_date_ms": [1000, 2000, 1000],
        }
    )
    source = _FakeFuyaoSource(frame)
    _container(mocker, source, tmp_path)

    outcome = download_fuyao_dump("adjustment-factors")

    assert outcome.rows == 3
    assert outcome.tickers == 2
    # (600519.SH, 1000) 与 (000001.SZ, 1000) 各自唯一、(600519.SH, 2000)
    # 无重复对 → 主键无重复
    assert outcome.duplicate_keys == 0
    assert outcome.date_range is None
    assert outcome.path.parent == tmp_path / "fuyao" / "dumps" / "adjustment-factors"
    assert outcome.path.name.endswith(".parquet")
    assert source.calls == [("adjustment-factors", outcome.path)]
    assert outcome.path.exists()


@pytest.mark.unit
def test_download_counts_duplicate_keys(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """主键重复只统计不拒绝（不可变快照保留上游原样）."""
    frame = pl.DataFrame(
        {
            "thscode": ["600519.SH", "600519.SH", "600519.SH"],
            "ex_date_ms": [1000, 1000, 2000],
        }
    )
    _container(mocker, _FakeFuyaoSource(frame), tmp_path)

    outcome = download_fuyao_dump("adjustment-factors")

    assert outcome.rows == 3
    assert outcome.duplicate_keys == 1


@pytest.mark.unit
def test_download_daily_k_stats_use_beijing_calendar_dates(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """daily-k 日期覆盖按北京日界取（date_ms 是北京零点毫秒戳）."""
    frame = pl.DataFrame(
        {
            "thscode": ["600519.SH", "600519.SH"],
            "date_ms": [
                date_to_ms(date(2025, 8, 18)),
                date_to_ms(date(2025, 8, 19)),
            ],
        }
    )
    _container(mocker, _FakeFuyaoSource(frame), tmp_path)

    outcome = download_fuyao_dump("daily-k")

    assert outcome.date_range == (date(2025, 8, 18), date(2025, 8, 19))


@pytest.mark.unit
def test_unconfigured_source_raises_explicitly(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """源未配置显式失败（不静默跳过），消息含配置指引."""
    _container(mocker, None, tmp_path)

    with pytest.raises(FuyaoSourceUnconfiguredError, match="FUYAO_API_KEY"):
        download_fuyao_dump("adjustment-factors")


@pytest.mark.unit
def test_container_closed_after_download(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """容器在成功与失败路径都必须关闭（组合根生命周期）."""
    frame = pl.DataFrame({"thscode": ["600519.SH"], "ex_date_ms": [1000]})
    container = _container(mocker, _FakeFuyaoSource(frame), tmp_path)
    download_fuyao_dump("adjustment-factors")
    assert container.close.call_count == 1

    class _BoomSource(_FakeFuyaoSource):
        def download_market_dump(self, kind: str, dest: Path) -> Path:
            raise RuntimeError("network down")

    failing = _container(mocker, _BoomSource(frame), tmp_path)
    with pytest.raises(RuntimeError, match="network down"):
        download_fuyao_dump("adjustment-factors")
    assert failing.close.call_count == 1
