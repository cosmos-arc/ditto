"""hk_hold 官方披露发布日表与证据 fixture 一致性（#693）."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from ditto_application.processes.ingestion.hk_hold_disclosure import (
    DISCLOSURE_CALENDAR_HORIZON,
    HK_HOLD_PUBLICATION_DATES,
    hk_hold_quarterly_knowledge_date,
)

_REPO_ROOT = Path(__file__).parents[6]
_FIXTURE_DIR = _REPO_ROOT / "docs" / "evidence" / "hkex-stock-connect-calendar"


def _northbound_open(path: Path) -> dict[date, bool]:
    """官方 CSV → {日期: 北向是否交易}（Northbound 列空白=交易）."""
    days: dict[date, bool] = {}
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
    header = next(i for i, r in enumerate(rows) if r and r[0].strip() == "Date")
    for row in rows[header + 1 :]:
        if not row or not row[0].strip():
            continue
        days[date.fromisoformat(row[0].strip())] = row[4].strip() == ""
    return days


def test_publication_dates_rederive_from_official_csv_fixtures() -> None:
    """表内 2024-12-31 起的发布日必须能从官方 Stock Connect 日历复算——
    表与证据 fixture 不允许悄悄漂移."""
    calendar: dict[date, bool] = {}
    for name in ("2025-calendar_csv_e.csv", "2026-calendar_csv_e.csv"):
        calendar.update(_northbound_open(_FIXTURE_DIR / name))
    table = dict(HK_HOLD_PUBLICATION_DATES)
    for quarter_end, expected in sorted(table.items()):
        if quarter_end < date(2024, 12, 31):
            continue  # 2024 无 CSV，推导依据见模块注释（钉值在下一测试）
        after = sorted(d for d, open_ in calendar.items() if d > quarter_end and open_)
        assert after[4] == expected, f"{quarter_end}: 5th northbound day drift"


def test_2024_entry_is_pinned_to_its_derivation() -> None:
    """2024-09-30 季无官方 CSV：SSE 2024-10 开市 8/9/10/14/15 扣 HKEX
    重阳 10-11 → 第 5 个北向交易日=10-15（推导依据见模块注释）."""
    table = dict(HK_HOLD_PUBLICATION_DATES)
    assert table[date(2024, 9, 30)] == date(2024, 10, 15)


def test_table_is_pit_safe_and_horizon_consistent() -> None:
    for quarter_end, published in HK_HOLD_PUBLICATION_DATES:
        assert published > quarter_end
        assert published <= DISCLOSURE_CALENDAR_HORIZON
    # 官方日内的发布日必然晚于事实日（季末）且不越过日历地平线。
    assert hk_hold_quarterly_knowledge_date(
        date(2026, 9, 30),
        run_date=date(2026, 12, 1),
    ) == date(2026, 10, 14)
    assert hk_hold_quarterly_knowledge_date(
        date(2026, 12, 31),
        run_date=date(2027, 1, 12),
    ) == date(2027, 1, 12)
