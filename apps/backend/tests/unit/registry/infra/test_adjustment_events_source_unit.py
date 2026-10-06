"""#515 A3：FuyaoAdjustmentEventsSource dump 陈旧守卫单测."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import polars as pl
import pytest
from ditto_apps.registry.infra import protocol_adapters
from ditto_apps.registry.infra.protocol_adapters import (
    FuyaoAdjustmentEventsSource,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_dump(root: Path, name: str) -> Path:
    dump_dir = root / "fuyao" / "dumps" / "adjustment-factors"
    dump_dir.mkdir(parents=True)
    dump = dump_dir / name
    dump.write_bytes(b"stub")
    return dump


def test_no_dump_raises(tmp_path: Path) -> None:
    source = FuyaoAdjustmentEventsSource(tmp_path)

    with pytest.raises(RuntimeError, match="dump not found"):
        source.fetch_adjustment_events("2026-01-02")


def test_stale_dump_raises(tmp_path: Path) -> None:
    """dump 日期早于目标日必须拒绝：陈旧 dump 过滤后同样零事件，会被
    对账层误读为「无除权事件的正常日」（#515 A3 例行调度前提）."""
    _make_dump(tmp_path, "20260101.parquet")
    source = FuyaoAdjustmentEventsSource(tmp_path)

    with pytest.raises(RuntimeError, match="predates target date"):
        source.fetch_adjustment_events("2026-01-02")


def test_unparseable_dump_name_raises(tmp_path: Path) -> None:
    _make_dump(tmp_path, "latest.parquet")
    source = FuyaoAdjustmentEventsSource(tmp_path)

    with pytest.raises(RuntimeError, match="unexpected name"):
        source.fetch_adjustment_events("2026-01-02")


def test_fresh_dump_filters_target_date(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_dump(tmp_path, "20260102.parquet")
    frame = pl.DataFrame(
        {
            "ticker": ["000001", "000001"],
            "trade_date": [date(2026, 1, 2), date(2026, 1, 1)],
        },
        schema={"ticker": pl.String, "trade_date": pl.Date},
    )
    monkeypatch.setattr(
        protocol_adapters.FuyaoSource,
        "adjustment_factors_frame",
        staticmethod(lambda _dump: frame),
    )
    source = FuyaoAdjustmentEventsSource(tmp_path)

    result = source.fetch_adjustment_events("2026-01-02")

    assert result.height == 1
    assert result["trade_date"].to_list() == [date(2026, 1, 2)]
