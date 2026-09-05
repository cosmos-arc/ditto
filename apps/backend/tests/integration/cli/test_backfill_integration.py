"""CLI backfill 命令组集成测试.

测试 backfill 命令组的各种子命令：
- backfill metadata (calendar, basic)
- backfill market (stock, etf, index, adj, status)
"""

from pathlib import Path

import pytest
from apps.backend.tests.integration.cli.helpers import assert_cli_result
from ditto_apps.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

# 集成测试串行执行，避免并发副作用
# cli_test: 禁用 observability 自动重置，避免 I/O 冲突
pytestmark = [pytest.mark.integration, pytest.mark.serial, pytest.mark.cli_test]


class TestBackfillMetadata:
    """backfill metadata 子命令测试."""

    def test_backfill_metadata_help(self) -> None:
        """测试 backfill metadata --help."""
        result = runner.invoke(app, ["backfill", "metadata", "--help"])
        assert result.exit_code == 0
        assert "calendar" in result.stdout
        assert "basic" in result.stdout

    def test_backfill_metadata_calendar_help(self) -> None:
        """测试 backfill metadata calendar --help."""
        result = runner.invoke(app, ["backfill", "metadata", "calendar", "--help"])
        assert result.exit_code == 0
        assert "--start" in result.stdout
        assert "--end" in result.stdout

    def test_backfill_metadata_basic_help(self) -> None:
        """测试 backfill metadata basic --help."""
        result = runner.invoke(app, ["backfill", "metadata", "basic", "--help"])
        assert result.exit_code == 0
        assert "资产类型" in result.stdout or "asset" in result.stdout.lower()


class TestBackfillMarket:
    """backfill market 子命令测试."""

    def test_backfill_market_help(self) -> None:
        """测试 backfill market --help."""
        result = runner.invoke(app, ["backfill", "market", "--help"])
        assert result.exit_code == 0
        assert "stock" in result.stdout
        assert "etf" in result.stdout
        assert "index" in result.stdout
        assert "adj" in result.stdout
        assert "status" in result.stdout

    def test_backfill_market_stock_help(self) -> None:
        """测试 backfill market stock --help."""
        result = runner.invoke(app, ["backfill", "market", "stock", "--help"])
        assert result.exit_code == 0
        assert "--start" in result.stdout
        assert "--end" in result.stdout
        assert "--parallel" in result.stdout

    def test_backfill_market_etf_help(self) -> None:
        """测试 backfill market etf --help."""
        result = runner.invoke(app, ["backfill", "market", "etf", "--help"])
        assert result.exit_code == 0
        assert "--start" in result.stdout
        assert "--end" in result.stdout

    def test_backfill_market_index_help(self) -> None:
        """测试 backfill market index --help."""
        result = runner.invoke(app, ["backfill", "market", "index", "--help"])
        assert result.exit_code == 0
        assert "--start" in result.stdout
        assert "--end" in result.stdout

    def test_backfill_market_adj_help(self) -> None:
        """测试 backfill market adj --help."""
        result = runner.invoke(app, ["backfill", "market", "adj", "--help"])
        assert result.exit_code == 0
        assert "--start" in result.stdout
        assert "--end" in result.stdout
        assert "--fund" in result.stdout

    def test_backfill_market_status_help(self) -> None:
        """测试 backfill market status --help."""
        result = runner.invoke(app, ["backfill", "market", "status", "--help"])
        assert result.exit_code == 0
        assert "--start" in result.stdout
        assert "--end" in result.stdout


class TestBackfillMarketStock:
    """backfill market stock 功能测试."""

    def test_backfill_market_stock_with_data_root(self, tmp_path: Path) -> None:
        """测试 backfill market stock 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "backfill",
                "market",
                "stock",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-03",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )

    def test_backfill_market_stock_with_parallel(self, tmp_path: Path) -> None:
        """测试 backfill market stock --parallel."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "backfill",
                "market",
                "stock",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-02",
                "--parallel",
                "2",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )


class TestBackfillMarketETF:
    """backfill market etf 功能测试."""

    def test_backfill_market_etf_with_data_root(self, tmp_path: Path) -> None:
        """测试 backfill market etf 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "backfill",
                "market",
                "etf",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-03",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )

    def test_backfill_market_etf_with_parallel(self, tmp_path: Path) -> None:
        """测试 backfill market etf --parallel."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "backfill",
                "market",
                "etf",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-02",
                "--parallel",
                "2",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )


class TestBackfillMarketAdj:
    """backfill market adj 功能测试."""

    def test_backfill_market_adj_with_data_root(self, tmp_path: Path) -> None:
        """测试 backfill market adj 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "backfill",
                "market",
                "adj",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-03",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )

    def test_backfill_market_adj_fund_with_data_root(self, tmp_path: Path) -> None:
        """测试 backfill market adj --fund 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "backfill",
                "market",
                "adj",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-03",
                "--fund",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )
