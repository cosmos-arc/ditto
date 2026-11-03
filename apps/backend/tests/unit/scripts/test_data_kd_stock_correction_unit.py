"""data_kd_stock_correction 单元测试（#658 批次2）.

锁定三类语义：scan 只读盘点（下一交易日策略/季度观察锚/无锚拒绝动）、
apply 新版本行映射与账本原因行、fail-closed 防御（可知时间必须晚于事实日）。
写入端口以 stub 注入——SqliteTableWriter/ParquetStore 的冲突键语义由
data 包既有测试覆盖，此处只锁工具自身的映射与证据逻辑。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl
from ditto_apps.scripts.data_kd_stock_correction import (
    _MARGIN_COLUMNS,
    _MARGIN_SCHEMA,
    KD_CORRECTION_SOURCE,
    apply_dataset,
    scan_dataset,
)
from ditto_data.storage.capital.specs import MARGIN_TRADING_SPEC

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_margin_columns_mirror_authoritative_spec() -> None:
    """脚本列清单镜像 MARGIN_TRADING_SPEC（写入端口真源）——防漂移对拍."""
    assert MARGIN_TRADING_SPEC.all_columns == _MARGIN_COLUMNS
    assert set(_MARGIN_SCHEMA) == set(MARGIN_TRADING_SPEC.all_columns)


# 覆盖国庆长假与普通周末的日历片段：08-16（周五，日频制度段末日）→
# 08-19（周一，季度制度段起点）；09-30（节前）→10-08（节后首个交易日）；
# 11-01（周五）→11-04（周一）。
_CALENDAR: list[tuple[str, bool]] = [
    ("2024-08-16", True),
    ("2024-08-19", True),
    ("2024-09-27", True),
    ("2024-09-30", True),
    ("2024-10-01", False),
    ("2024-10-02", False),
    ("2024-10-03", False),
    ("2024-10-04", False),
    ("2024-10-05", False),
    ("2024-10-06", False),
    ("2024-10-07", False),
    ("2024-10-08", True),
    ("2024-10-09", True),
    ("2024-11-01", True),
    ("2024-11-04", True),
]


def _make_db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "metadata.sqlite")
    conn.execute(
        "CREATE TABLE trading_calendar (trade_date TEXT PRIMARY KEY, is_open BOOLEAN)"
    )
    conn.executemany("INSERT INTO trading_calendar VALUES (?, ?)", _CALENDAR)
    conn.execute(
        """
        CREATE TABLE margin_trading (
            instrument_id INTEGER NOT NULL,
            trade_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            margin_buy_balance REAL,
            short_sell_balance REAL,
            margin_buy_amount REAL,
            short_sell_volume REAL,
            PRIMARY KEY (instrument_id, trade_date, effective_from)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE provider_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            source TEXT NOT NULL,
            request_start TEXT NOT NULL,
            request_end TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn


def _insert_margin(
    conn: sqlite3.Connection,
    *,
    instrument_id: int,
    trade_date: str,
    knowledge_date: str,
) -> None:
    conn.execute(
        "INSERT INTO margin_trading VALUES (?, ?, ?, ?, NULL, 1.0, 1.0, 1.0, 1.0)",
        (instrument_id, trade_date, knowledge_date, knowledge_date),
    )


def _write_hk_hold_year(tmp_path: Path, rows: list[dict[str, Any]]) -> None:
    target = tmp_path / "capital" / "hk_hold"
    target.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(
        {
            "source_ticker": [r["source_ticker"] for r in rows],
            "trade_date": [date.fromisoformat(r["trade_date"]) for r in rows],
            "knowledge_date": [date.fromisoformat(r["knowledge_date"]) for r in rows],
            "vol": [1.0 for _ in rows],
            "ratio": [1.0 for _ in rows],
            "exchange": ["SZ" for _ in rows],
            "instrument_id": [r["instrument_id"] for r in rows],
            "source": ["tushare" for _ in rows],
        }
    )
    df.write_parquet(target / "2024.parquet")


@dataclass
class _StubCapitalStore:
    margin_frames: list[pl.DataFrame] = field(default_factory=list)
    hk_hold_frames: list[pl.DataFrame] = field(default_factory=list)
    hsgt_frames: list[pl.DataFrame] = field(default_factory=list)

    def save_margin_trading(self, df: pl.DataFrame, on_duplicate: Any = None) -> int:
        self.margin_frames.append(df)
        return df.height

    def save_hk_hold(
        self, df: pl.DataFrame, year: int, on_duplicate: Any = None
    ) -> int:
        self.hk_hold_frames.append(df)
        return df.height

    def save_hsgt_top10(
        self, df: pl.DataFrame, year: int, on_duplicate: Any = None
    ) -> int:
        self.hsgt_frames.append(df)
        return df.height


@dataclass
class _StubLogStore:
    logs: list[Any] = field(default_factory=list)

    def save_log(self, log: Any) -> Any:
        self.logs.append(log)
        return log


class TestScanMargin:
    def test_friday_and_pre_holiday_rows_flagged(self, tmp_path: Path) -> None:
        conn = _make_db(tmp_path)
        # 09-30（节前）：旧 kd=10-01 自然日，期望 10-08。
        _insert_margin(
            conn, instrument_id=1, trade_date="2024-09-30", knowledge_date="2024-10-01"
        )
        # 11-01（周五）：旧 kd=11-02 周六，期望 11-04。
        _insert_margin(
            conn, instrument_id=1, trade_date="2024-11-01", knowledge_date="2024-11-02"
        )
        # 10-08（周二）：旧 kd=10-09 恰等于下一交易日，无需纠正。
        _insert_margin(
            conn, instrument_id=1, trade_date="2024-10-08", knowledge_date="2024-10-09"
        )
        conn.commit()

        impacts = scan_dataset("margin_trading", conn=conn, data_root=tmp_path)
        assert [
            (i.trade_date, i.old_knowledge_date, i.new_knowledge_date) for i in impacts
        ] == [
            ("2024-09-30", "2024-10-01", "2024-10-08"),
            ("2024-11-01", "2024-11-02", "2024-11-04"),
        ]
        assert all(i.status == "correct" for i in impacts)

    def test_expected_version_present_needs_no_action(self, tmp_path: Path) -> None:
        conn = _make_db(tmp_path)
        # 周五行已有 B1 校准版本（kd=周一）：旧版本保留、无需再写。
        _insert_margin(
            conn, instrument_id=1, trade_date="2024-11-01", knowledge_date="2024-11-02"
        )
        _insert_margin(
            conn, instrument_id=1, trade_date="2024-11-01", knowledge_date="2024-11-04"
        )
        conn.commit()

        impacts = scan_dataset("margin_trading", conn=conn, data_root=tmp_path)
        assert impacts == []


class TestScanHkHold:
    def test_daily_era_flagged_quarterly_anchored_to_observation(
        self,
        tmp_path: Path,
    ) -> None:
        conn = _make_db(tmp_path)
        conn.execute(
            "INSERT INTO provider_snapshots VALUES "
            "('s1', 'hk_hold', 'tushare', '2024-09-16', '2024-09-30', 3000, "
            "'2026-11-01T08:00:00')"
        )
        conn.commit()
        _write_hk_hold_year(
            tmp_path,
            [
                # 日频段周五：期望下一交易日 11-04。
                {
                    "source_ticker": "000001.SZ",
                    "instrument_id": 1,
                    "trade_date": "2024-08-16",
                    "knowledge_date": "2024-08-17",
                },
                # 季度段（>=2024-08-19）：期望观察锚 2026-11-01。
                {
                    "source_ticker": "000001.SZ",
                    "instrument_id": 1,
                    "trade_date": "2024-09-30",
                    "knowledge_date": "2024-10-01",
                },
            ],
        )

        impacts = scan_dataset("hk_hold", conn=conn, data_root=tmp_path)
        by_date = {i.trade_date: i for i in impacts}
        assert by_date["2024-08-16"].new_knowledge_date == "2024-08-19"
        assert by_date["2024-08-16"].anchor == "next_trading_day"
        assert by_date["2024-09-30"].new_knowledge_date == "2026-11-01"
        assert by_date["2024-09-30"].anchor == "observation_snapshot"

    def test_quarterly_without_observation_evidence_is_unanchorable(
        self,
        tmp_path: Path,
    ) -> None:
        conn = _make_db(tmp_path)
        _write_hk_hold_year(
            tmp_path,
            [
                {
                    "source_ticker": "000001.SZ",
                    "instrument_id": 1,
                    "trade_date": "2024-09-30",
                    "knowledge_date": "2024-10-01",
                },
            ],
        )

        impacts = scan_dataset("hk_hold", conn=conn, data_root=tmp_path)
        assert len(impacts) == 1
        assert impacts[0].status == "unanchorable"
        assert impacts[0].new_knowledge_date == "?"


class TestApply:
    def test_margin_apply_writes_new_version_and_ledger(
        self,
        tmp_path: Path,
    ) -> None:
        conn = _make_db(tmp_path)
        _insert_margin(
            conn, instrument_id=7, trade_date="2024-11-01", knowledge_date="2024-11-02"
        )
        conn.commit()
        impacts = scan_dataset("margin_trading", conn=conn, data_root=tmp_path)
        store, logs = _StubCapitalStore(), _StubLogStore()

        result = apply_dataset(
            "margin_trading",
            impacts,
            conn=conn,
            data_root=tmp_path,
            capital_store=store,
            log_store=logs,
            run_at=datetime(2026, 11, 4, 3, 0, tzinfo=_SHANGHAI),
        )

        assert result["dates_corrected"] == 1
        assert result["rows_written"] == 1
        frame = store.margin_frames[0]
        assert frame["knowledge_date"].to_list() == [date(2024, 11, 4)]
        assert frame["effective_from"].to_list() == [date(2024, 11, 4)]
        assert frame["instrument_id"].to_list() == [7]
        assert len(logs.logs) == 1
        log = logs.logs[0]
        assert log.dataset == "margin_trading"
        assert log.source == KD_CORRECTION_SOURCE
        assert log.trade_date == "2024-11-01"
        assert log.rows == 1

    def test_hk_hold_apply_maps_quarterly_rows_by_old_knowledge(
        self,
        tmp_path: Path,
    ) -> None:
        conn = _make_db(tmp_path)
        conn.execute(
            "INSERT INTO provider_snapshots VALUES "
            "('s1', 'hk_hold', 'tushare', '2024-09-16', '2024-09-30', 3000, "
            "'2026-11-01T08:00:00')"
        )
        conn.commit()
        _write_hk_hold_year(
            tmp_path,
            [
                {
                    "source_ticker": "000001.SZ",
                    "instrument_id": 1,
                    "trade_date": "2024-09-30",
                    "knowledge_date": "2024-10-01",
                },
                # 已是期望版本的行不被重复映射。
                {
                    "source_ticker": "000002.SZ",
                    "instrument_id": 2,
                    "trade_date": "2024-09-30",
                    "knowledge_date": "2026-11-01",
                },
            ],
        )
        impacts = scan_dataset("hk_hold", conn=conn, data_root=tmp_path)
        store, logs = _StubCapitalStore(), _StubLogStore()

        result = apply_dataset(
            "hk_hold",
            impacts,
            conn=conn,
            data_root=tmp_path,
            capital_store=store,
            log_store=logs,
            run_at=datetime(2026, 11, 4, 3, 0, tzinfo=_SHANGHAI),
        )

        assert result["rows_written"] == 1
        frame = store.hk_hold_frames[0]
        assert frame["source_ticker"].to_list() == ["000001.SZ"]
        assert frame["knowledge_date"].to_list() == [date(2026, 11, 1)]

    def test_unanchorable_rows_are_not_written(self, tmp_path: Path) -> None:
        conn = _make_db(tmp_path)
        _write_hk_hold_year(
            tmp_path,
            [
                {
                    "source_ticker": "000001.SZ",
                    "instrument_id": 1,
                    "trade_date": "2024-09-30",
                    "knowledge_date": "2024-10-01",
                },
            ],
        )
        impacts = scan_dataset("hk_hold", conn=conn, data_root=tmp_path)
        store, logs = _StubCapitalStore(), _StubLogStore()

        result = apply_dataset(
            "hk_hold",
            impacts,
            conn=conn,
            data_root=tmp_path,
            capital_store=store,
            log_store=logs,
            run_at=datetime(2026, 11, 4, 3, 0, tzinfo=_SHANGHAI),
        )

        assert result["dates_corrected"] == 0
        assert store.hk_hold_frames == []
        assert logs.logs == []

    def test_refuses_to_write_knowledge_before_trade(self) -> None:
        import pytest
        from ditto_apps.scripts.data_kd_stock_correction import (
            _assert_knowledge_after_trade,
        )

        frame = pl.DataFrame(
            {
                "trade_date": [date(2024, 11, 1)],
                "knowledge_date": [date(2024, 10, 31)],
            }
        )
        with pytest.raises(ValueError, match="not after trade_date"):
            _assert_knowledge_after_trade(frame, dataset="margin_trading")
