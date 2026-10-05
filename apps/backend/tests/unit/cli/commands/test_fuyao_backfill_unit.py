"""#439：fuyao backfill-daily-k CLI — dry-run 无写入、重叠冲突报告、执行走正常链路."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_apps.cli.main import app
from ditto_data.models.ingestion import IngestionResult
from pytest_mock import MockerFixture
from typer.testing import CliRunner

CONTAINER_PATH = "ditto_apps.cli.commands.fuyao.make_app_container"
BUNDLE_PATH = "ditto_apps.cli.commands.fuyao.create_ingestion_bundle"
DATES_PATH = "ditto_application.processes.ingestion.date_range.list_ingestion_dates"


def _write_daily_k_dump(data_root: Path) -> Path:
    from ditto_data.sources.fuyao.client import date_to_ms

    dump_dir = data_root / "fuyao" / "dumps" / "daily-k"
    dump_dir.mkdir(parents=True)
    dump = dump_dir / "20251005.parquet"
    pl.DataFrame(
        {
            "thscode": ["600519.SH", "600519.SH", "000001.SZ"],
            "currency": ["CNY"] * 3,
            "interval": ["1d"] * 3,
            "adjusted": ["none"] * 3,
            "date_ms": [
                date_to_ms(date(2025, 8, 18)),
                date_to_ms(date(2025, 8, 19)),
                date_to_ms(date(2025, 8, 19)),
            ],
            "open_price": [10.0, 10.5, 12.0],
            "high_price": [11.0, 11.5, 13.0],
            "low_price": [9.5, 10.0, 11.5],
            "close_price": [10.5, 11.0, 12.5],
            "volume": [100.0, 200.0, 300.0],
            "turnover": [1050.0, 2200.0, 3750.0],
        }
    ).write_parquet(dump)
    return dump


class _FakeContainer:
    def __init__(self, services: dict[Any, Any]) -> None:
        self._services = services

    def get(self, key: Any) -> Any:
        return self._services[key]

    def close(self) -> None:
        pass


def _install_fake_container(
    mocker: MockerFixture,
    data_root: Path,
    existing: pl.DataFrame,
) -> MagicMock:
    from ditto_data.services.market_service import MarketService
    from ditto_data.services.metadata_service import MetadataService

    metadata = MagicMock()
    metadata.instrument.resolve_fuyao_instrument_ids.return_value = {
        "600519.SH": 1,
        "000001.SZ": 2,
    }
    market = MagicMock()
    market.get_stock_bars.return_value = existing
    container = _FakeContainer(
        {
            Path: data_root,
            MetadataService: metadata,
            MarketService: market,
        }
    )
    return mocker.patch(CONTAINER_PATH, return_value=container)


def _existing_bars() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 2],
            "trade_date": [date(2025, 8, 18), date(2025, 8, 19)],
            "knowledge_date": [date(2025, 8, 19), date(2025, 8, 20)],
            "open": [10.0, 12.0],
            "high": [11.0, 13.0],
            "low": [9.5, 11.5],
            "close": [10.5, 99.0],  # 000001 8-19 收盘冲突(12.5 vs 99.0)
            # 除权日口径反例：主源 pre_close 是除权参考价, dump 是原始前收
            "pre_close": [None, 15.0],
            "volume": [1.0, 3.0],
            "amount": [1.05, 3.75],
            "pct_change": [None, None],
        }
    )


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.mark.unit
class TestBackfillDailyKDryRun:
    def test_dry_run_reports_overlap_conflicts_without_write(
        self, runner: CliRunner, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        dump = _write_daily_k_dump(tmp_path)
        _install_fake_container(mocker, tmp_path, _existing_bars())
        mocker.patch(DATES_PATH, return_value=["2025-08-18", "2025-08-19"])
        bundle = MagicMock()
        bundle_ctx = mocker.patch(BUNDLE_PATH)
        bundle_ctx.return_value.__enter__.return_value = bundle

        result = runner.invoke(
            app,
            [
                "fuyao",
                "backfill-daily-k",
                "--start",
                "2025-08-18",
                "--end",
                "2025-08-19",
                "--dump",
                str(dump),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "dump 覆盖: 2025-08-18..2025-08-19" in result.output
        assert "主源重叠行: 2(完全一致 1 / 冲突 1)" in result.output
        # 除权日 pre_close 口径差异(原始前收 vs 除权参考价)如实计入冲突字段
        assert "pre_close" in result.output
        assert "close" in result.output
        assert "dry-run 完成, 未写入任何数据" in result.output
        bundle.coordinator.ingest_range.assert_not_called()


@pytest.mark.unit
class TestBackfillDailyKExecute:
    def test_execute_routes_through_fuyao_bundle_override(
        self, runner: CliRunner, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        dump = _write_daily_k_dump(tmp_path)
        _install_fake_container(mocker, tmp_path, _existing_bars())
        mocker.patch(DATES_PATH, return_value=["2025-08-18", "2025-08-19"])

        captured: dict[str, Any] = {}
        coordinator = MagicMock()
        coordinator.ingest_range.return_value = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2025-08-18",
                status="success",
                row_count=1,
            ),
            IngestionResult(
                dataset="stock_daily",
                trade_date="2025-08-19",
                status="success",
                row_count=2,
            ),
        ]

        @contextmanager
        def fake_bundle(source: str = "tushare", *, market_fetcher_override=None):
            captured["source"] = source
            captured["override"] = market_fetcher_override
            yield MagicMock(coordinator=coordinator)

        mocker.patch(BUNDLE_PATH, side_effect=fake_bundle)

        result = runner.invoke(
            app,
            [
                "fuyao",
                "backfill-daily-k",
                "--start",
                "2025-08-18",
                "--end",
                "2025-08-19",
                "--dump",
                str(dump),
                "--execute",
            ],
        )

        assert result.exit_code == 0, result.output
        assert captured["source"] == "fuyao"
        assert captured["override"] is not None
        coordinator.ingest_range.assert_called_once_with(
            "stock_daily", "2025-08-18", "2025-08-19", force=False
        )
        assert "成功 2" in result.output

    def test_execute_failed_dates_exit_nonzero(
        self, runner: CliRunner, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        dump = _write_daily_k_dump(tmp_path)
        _install_fake_container(mocker, tmp_path, _existing_bars())
        mocker.patch(DATES_PATH, return_value=["2025-08-18"])

        coordinator = MagicMock()
        coordinator.ingest_range.return_value = [
            IngestionResult(
                dataset="stock_daily",
                trade_date="2025-08-18",
                status="failed",
                row_count=0,
                error="write blocked",
            ),
        ]

        @contextmanager
        def fake_bundle(source: str = "tushare", *, market_fetcher_override=None):
            yield MagicMock(coordinator=coordinator)

        mocker.patch(BUNDLE_PATH, side_effect=fake_bundle)

        result = runner.invoke(
            app,
            [
                "fuyao",
                "backfill-daily-k",
                "--start",
                "2025-08-18",
                "--end",
                "2025-08-18",
                "--dump",
                str(dump),
                "--execute",
            ],
        )

        assert result.exit_code == 1
        assert "失败" in result.output
        assert "回填不完整" in result.output


@pytest.mark.unit
class TestBackfillDailyKGuardrails:
    def test_missing_dump_exits_with_hint(
        self, runner: CliRunner, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        _install_fake_container(mocker, tmp_path, pl.DataFrame())

        result = runner.invoke(
            app,
            [
                "fuyao",
                "backfill-daily-k",
                "--start",
                "2025-08-18",
                "--end",
                "2025-08-19",
            ],
        )

        assert result.exit_code == 1
        assert "ditto fuyao dump-daily-k" in result.output

    def test_range_outside_coverage_exits(
        self, runner: CliRunner, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        dump = _write_daily_k_dump(tmp_path)
        _install_fake_container(mocker, tmp_path, pl.DataFrame())
        mocker.patch(DATES_PATH, return_value=[])

        result = runner.invoke(
            app,
            [
                "fuyao",
                "backfill-daily-k",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-31",
                "--dump",
                str(dump),
            ],
        )

        assert result.exit_code == 1
        assert "无交集" in result.output
