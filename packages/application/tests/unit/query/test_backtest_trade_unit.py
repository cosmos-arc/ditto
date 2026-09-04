"""Tests for BacktestTradeQueryFacade — 从回测产物读取成交明细."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
from ditto_application.queries.backtest_trade import (
    BacktestTradeQueryFacade,
    TradeRecord,
)
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord


def _make_artifact_record(
    run_id: str = "run-001",
    file_path: str = "/data/artifacts/run-001",
    artifact_type: ArtifactKind = ArtifactKind.BACKTEST_REPORT,
) -> StrategyArtifactRecord:
    """构造测试用 StrategyArtifactRecord."""
    return StrategyArtifactRecord(
        artifact_id=f"art-{run_id}",
        strategy_id="strat-001",
        run_id=run_id,
        artifact_type=artifact_type,
        file_path=file_path,
    )


def _sample_trade_df() -> pl.DataFrame:
    """构造样例成交 DataFrame — 列结构匹配 TradeRecord 字段."""
    return pl.DataFrame(
        {
            "trade_date": [
                "2024-01-02",
                "2024-01-05",
                "2024-01-10",
                "2024-01-15",
            ],
            "instrument_id": [100, 200, 100, 300],
            "direction": ["buy", "sell", "buy", "sell"],
            "entry_date": [
                "2024-01-02",
                "2024-01-05",
                "2024-01-10",
                "2024-01-15",
            ],
            "exit_date": [
                "2024-01-05",
                "2024-01-08",
                "2024-01-15",
                "2024-01-20",
            ],
            "entry_price": [10.0, 20.0, 11.0, 30.0],
            "exit_price": [11.0, 19.0, 12.5, 28.0],
            "quantity": [1000, 500, 800, 600],
            "pnl": [990.0, -510.0, 1192.0, -1212.0],
        },
    )


class TestQueryTradesReadsParquet:
    """BacktestTradeQueryFacade.query_trades — 从 parquet 读取成交数据."""

    def test_reads_trade_log_parquet(self, tmp_path: Path) -> None:
        """给定 run_id，查找产物目录并读取 trade_log.parquet."""
        artifact_dir = tmp_path / "run-001"
        artifact_dir.mkdir()
        trade_df = _sample_trade_df()
        trade_df.write_parquet(artifact_dir / "trade_log.parquet")

        record = _make_artifact_record(run_id="run-001", file_path=str(artifact_dir))
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = [record]

        facade = BacktestTradeQueryFacade(artifact_service=service)
        result = facade.query_trades(run_id="run-001")

        assert len(result) == 4
        assert all(isinstance(r, TradeRecord) for r in result)
        service.list_artifacts.assert_called_once()

    def test_reads_current_closed_trade_aggregate_schema(self, tmp_path: Path) -> None:
        """Current engine artifacts expose exit_date/net_pnl without legacy aliases."""
        artifact_dir = tmp_path / "run-current"
        artifact_dir.mkdir()
        pl.DataFrame(
            {
                "trade_id": ["trade-1"],
                "instrument_id": [2001724],
                "direction": ["buy"],
                "entry_date": ["2024-01-02"],
                "exit_date": ["2024-01-05"],
                "entry_price": [92.0],
                "exit_price": [93.0],
                "quantity": [100],
                "gross_pnl": [100.0],
                "fees": [5.0],
                "net_pnl": [95.0],
            }
        ).write_parquet(artifact_dir / "trade_log.parquet")
        record = _make_artifact_record(
            run_id="run-current", file_path=str(artifact_dir)
        )
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = [record]

        result = BacktestTradeQueryFacade(service).query_trades(run_id="run-current")

        assert result == [
            TradeRecord(
                trade_date="2024-01-05",
                instrument_id=2001724,
                direction="buy",
                entry_date="2024-01-02",
                exit_date="2024-01-05",
                entry_price=92.0,
                exit_price=93.0,
                quantity=100,
                pnl=95.0,
            )
        ]

    def test_ignores_open_trade_aggregate_rows(self, tmp_path: Path) -> None:
        """The current engine keeps open positions in trade_log with null exits."""
        artifact_dir = tmp_path / "run-current-open"
        artifact_dir.mkdir()
        pl.DataFrame(
            {
                "trade_id": ["trade-closed", "trade-open"],
                "instrument_id": [2001724, 2001755],
                "direction": ["buy", "buy"],
                "entry_date": ["2024-01-02", "2024-01-03"],
                "exit_date": ["2024-01-05", None],
                "entry_price": [92.0, 3.50],
                "exit_price": [93.0, None],
                "quantity": [100, 1_000],
                "gross_pnl": [100.0, None],
                "fees": [5.0, None],
                "net_pnl": [95.0, None],
            }
        ).write_parquet(artifact_dir / "trade_log.parquet")
        record = _make_artifact_record(
            run_id="run-current-open", file_path=str(artifact_dir)
        )
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = [record]

        result = BacktestTradeQueryFacade(service).query_trades(
            run_id="run-current-open"
        )

        assert len(result) == 1
        assert result[0].trade_date == "2024-01-05"
        assert result[0].instrument_id == 2001724

    def test_returns_empty_when_run_id_not_found(self) -> None:
        """run_id 不存在时返回空列表."""
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = []

        facade = BacktestTradeQueryFacade(artifact_service=service)
        result = facade.query_trades(run_id="nonexistent")

        assert result == []

    def test_uses_backtest_report_artifact_when_replay_proof_exists(
        self,
        tmp_path: Path,
    ) -> None:
        """同一 run 有 replay proof 时仍从 backtest_report 目录读取 trade_log."""
        report_dir = tmp_path / "run-001-report"
        report_dir.mkdir()
        proof_dir = tmp_path / "run-001-proof"
        proof_dir.mkdir()
        _sample_trade_df().write_parquet(report_dir / "trade_log.parquet")

        proof_record = _make_artifact_record(
            run_id="run-001",
            file_path=str(proof_dir),
            artifact_type=ArtifactKind.REPLAY_PROOF,
        )
        report_record = _make_artifact_record(
            run_id="run-001",
            file_path=str(report_dir),
            artifact_type=ArtifactKind.BACKTEST_REPORT,
        )
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = [proof_record, report_record]

        facade = BacktestTradeQueryFacade(artifact_service=service)
        result = facade.query_trades(run_id="run-001")

        assert len(result) == 4


class TestQueryTradesWithDateFilter:
    """BacktestTradeQueryFacade.query_trades — 日期范围过滤."""

    def test_filters_by_start_date(self, tmp_path: Path) -> None:
        """start_date 过滤 exit_date < start_date 的记录."""
        artifact_dir = tmp_path / "run-001"
        artifact_dir.mkdir()
        _sample_trade_df().write_parquet(artifact_dir / "trade_log.parquet")

        record = _make_artifact_record(run_id="run-001", file_path=str(artifact_dir))
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = [record]

        facade = BacktestTradeQueryFacade(artifact_service=service)
        result = facade.query_trades(run_id="run-001", start_date="2024-01-10")

        # exit_date < 2024-01-10 的应被过滤: T001(01-05), T002(01-08)
        # 保留: T003(01-15), T004(01-20)
        assert len(result) == 2
        assert {r.exit_date for r in result} == {"2024-01-15", "2024-01-20"}

    def test_filters_by_end_date(self, tmp_path: Path) -> None:
        """end_date 过滤 entry_date > end_date 的记录."""
        artifact_dir = tmp_path / "run-001"
        artifact_dir.mkdir()
        _sample_trade_df().write_parquet(artifact_dir / "trade_log.parquet")

        record = _make_artifact_record(run_id="run-001", file_path=str(artifact_dir))
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = [record]

        facade = BacktestTradeQueryFacade(artifact_service=service)
        result = facade.query_trades(run_id="run-001", end_date="2024-01-10")

        # entry_date > 2024-01-10 的应被过滤: T004(01-15)
        # entry_date <= 2024-01-10: T001(01-02), T002(01-05), T003(01-10)
        assert len(result) == 3

    def test_filters_by_both_dates(self, tmp_path: Path) -> None:
        """同时指定 start_date 和 end_date."""
        artifact_dir = tmp_path / "run-001"
        artifact_dir.mkdir()
        _sample_trade_df().write_parquet(artifact_dir / "trade_log.parquet")

        record = _make_artifact_record(run_id="run-001", file_path=str(artifact_dir))
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = [record]

        facade = BacktestTradeQueryFacade(artifact_service=service)
        result = facade.query_trades(
            run_id="run-001",
            start_date="2024-01-06",
            end_date="2024-01-12",
        )

        # exit_date >= 2024-01-06 AND entry_date <= 2024-01-12
        # T001: exit 01-05 < 01-06 -> 排除
        # T002: exit 01-08 >= 01-06, entry 01-05 <= 01-12 -> 保留
        # T003: exit 01-15 >= 01-06, entry 01-10 <= 01-12 -> 保留
        # T004: entry 01-15 > 01-12 -> 排除
        assert len(result) == 2
        assert {r.entry_date for r in result} == {"2024-01-05", "2024-01-10"}


class TestQueryTradesWithPagination:
    """BacktestTradeQueryFacade.query_trades — 分页控制."""

    def test_applies_limit(self, tmp_path: Path) -> None:
        """limit 限制返回行数."""
        artifact_dir = tmp_path / "run-001"
        artifact_dir.mkdir()
        _sample_trade_df().write_parquet(artifact_dir / "trade_log.parquet")

        record = _make_artifact_record(run_id="run-001", file_path=str(artifact_dir))
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = [record]

        facade = BacktestTradeQueryFacade(artifact_service=service)
        result = facade.query_trades(run_id="run-001", limit=2)

        assert len(result) == 2

    def test_applies_offset(self, tmp_path: Path) -> None:
        """offset 跳过前 N 行."""
        artifact_dir = tmp_path / "run-001"
        artifact_dir.mkdir()
        _sample_trade_df().write_parquet(artifact_dir / "trade_log.parquet")

        record = _make_artifact_record(run_id="run-001", file_path=str(artifact_dir))
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = [record]

        facade = BacktestTradeQueryFacade(artifact_service=service)
        result = facade.query_trades(run_id="run-001", offset=2)

        assert len(result) == 2

    def test_applies_limit_and_offset(self, tmp_path: Path) -> None:
        """同时使用 limit 和 offset."""
        artifact_dir = tmp_path / "run-001"
        artifact_dir.mkdir()
        _sample_trade_df().write_parquet(artifact_dir / "trade_log.parquet")

        record = _make_artifact_record(run_id="run-001", file_path=str(artifact_dir))
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = [record]

        facade = BacktestTradeQueryFacade(artifact_service=service)
        result = facade.query_trades(run_id="run-001", limit=1, offset=1)

        assert len(result) == 1

    def test_offset_beyond_data_returns_empty(self, tmp_path: Path) -> None:
        """offset 超出数据范围返回空列表."""
        artifact_dir = tmp_path / "run-001"
        artifact_dir.mkdir()
        _sample_trade_df().write_parquet(artifact_dir / "trade_log.parquet")

        record = _make_artifact_record(run_id="run-001", file_path=str(artifact_dir))
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = [record]

        facade = BacktestTradeQueryFacade(artifact_service=service)
        result = facade.query_trades(run_id="run-001", offset=100)

        assert result == []


class TestQueryTradesEdgeCases:
    """BacktestTradeQueryFacade.query_trades — 边界情况."""

    def test_missing_parquet_returns_empty(self, tmp_path: Path) -> None:
        """产物目录存在但 trade_log.parquet 不存在时返回空列表."""
        artifact_dir = tmp_path / "run-001"
        artifact_dir.mkdir()
        # 不创建 trade_log.parquet

        record = _make_artifact_record(run_id="run-001", file_path=str(artifact_dir))
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = [record]

        facade = BacktestTradeQueryFacade(artifact_service=service)
        result = facade.query_trades(run_id="run-001")

        assert result == []

    def test_multiple_artifacts_picks_first(self, tmp_path: Path) -> None:
        """同一 run_id 多个产物记录时使用第一个."""
        dir_a = tmp_path / "run-001-a"
        dir_a.mkdir()
        trade_df = pl.DataFrame(
            {
                "trade_date": ["2024-01-01"],
                "instrument_id": [100],
                "direction": ["buy"],
                "entry_date": ["2024-01-01"],
                "exit_date": ["2024-01-05"],
                "entry_price": [10.0],
                "exit_price": [11.0],
                "quantity": [1000],
                "pnl": [100.0],
            },
        )
        trade_df.write_parquet(dir_a / "trade_log.parquet")

        dir_b = tmp_path / "run-001-b"
        dir_b.mkdir()
        trade_df_b = pl.DataFrame(
            {
                "trade_date": ["2024-02-01"],
                "instrument_id": [200],
                "direction": ["sell"],
                "entry_date": ["2024-02-01"],
                "exit_date": ["2024-02-05"],
                "entry_price": [20.0],
                "exit_price": [19.0],
                "quantity": [500],
                "pnl": [-500.0],
            },
        )
        trade_df_b.write_parquet(dir_b / "trade_log.parquet")

        record_a = _make_artifact_record(run_id="run-001", file_path=str(dir_a))
        record_b = _make_artifact_record(run_id="run-001", file_path=str(dir_b))
        service = MagicMock(spec=["list_artifacts"])
        service.list_artifacts.return_value = [record_a, record_b]

        facade = BacktestTradeQueryFacade(artifact_service=service)
        result = facade.query_trades(run_id="run-001")

        assert len(result) == 1
        assert result[0].instrument_id == 100
