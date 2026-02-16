"""CLI ingest 命令组集成测试.

测试 ingest 命令组的各种子命令：
- ingest metadata (calendar, basic)
- ingest market (stock, etf, index, adj, status)
"""

from pathlib import Path

import pytest
from ditto_port.cli.main import app
from typer.testing import CliRunner

from .helpers import assert_cli_result

runner = CliRunner()

# 集成测试串行执行，避免并发副作用
# cli_test: 禁用 observability 自动重置，避免 I/O 冲突
pytestmark = [pytest.mark.integration, pytest.mark.serial, pytest.mark.cli_test]


class TestIngestMetadata:
    """ingest metadata 子命令测试."""

    def test_ingest_metadata_help(self) -> None:
        """测试 ingest metadata --help."""
        result = runner.invoke(app, ["ingest", "metadata", "--help"])
        assert result.exit_code == 0
        assert "calendar" in result.stdout
        assert "basic" in result.stdout

    def test_ingest_metadata_calendar_help(self) -> None:
        """测试 ingest metadata calendar --help."""
        result = runner.invoke(app, ["ingest", "metadata", "calendar", "--help"])
        assert result.exit_code == 0
        assert "交易日期" in result.stdout or "date" in result.stdout.lower()

    def test_ingest_metadata_basic_help(self) -> None:
        """测试 ingest metadata basic --help."""
        result = runner.invoke(app, ["ingest", "metadata", "basic", "--help"])
        assert result.exit_code == 0
        assert "资产类型" in result.stdout or "asset" in result.stdout.lower()


class TestIngestMarket:
    """ingest market 子命令测试."""

    def test_ingest_market_help(self) -> None:
        """测试 ingest market --help."""
        result = runner.invoke(app, ["ingest", "market", "--help"])
        assert result.exit_code == 0
        assert "stock" in result.stdout
        assert "etf" in result.stdout
        assert "index" in result.stdout
        assert "adj" in result.stdout
        assert "status" in result.stdout

    def test_ingest_market_stock_help(self) -> None:
        """测试 ingest market stock --help."""
        result = runner.invoke(app, ["ingest", "market", "stock", "--help"])
        assert result.exit_code == 0
        assert "交易日期" in result.stdout or "date" in result.stdout.lower()

    def test_ingest_market_etf_help(self) -> None:
        """测试 ingest market etf --help."""
        result = runner.invoke(app, ["ingest", "market", "etf", "--help"])
        assert result.exit_code == 0
        assert "交易日期" in result.stdout or "date" in result.stdout.lower()

    def test_ingest_market_index_help(self) -> None:
        """测试 ingest market index --help."""
        result = runner.invoke(app, ["ingest", "market", "index", "--help"])
        assert result.exit_code == 0
        assert "交易日期" in result.stdout or "date" in result.stdout.lower()

    def test_ingest_market_adj_help(self) -> None:
        """测试 ingest market adj --help."""
        result = runner.invoke(app, ["ingest", "market", "adj", "--help"])
        assert result.exit_code == 0
        assert "交易日期" in result.stdout or "date" in result.stdout.lower()
        assert "--fund" in result.stdout

    def test_ingest_market_status_help(self) -> None:
        """测试 ingest market status --help."""
        result = runner.invoke(app, ["ingest", "market", "status", "--help"])
        assert result.exit_code == 0
        assert "交易日期" in result.stdout or "date" in result.stdout.lower()


class TestIngestMarketDaily:
    """ingest market daily 功能测试."""

    def test_ingest_market_stock_invalid_date(self) -> None:
        """测试 ingest market stock 无效日期格式."""
        result = runner.invoke(app, ["ingest", "market", "stock", "2024/01/02"])
        # 无效日期格式应该失败或报错
        assert result.exit_code != 0 or "错误" in result.stdout

    def test_ingest_market_etf_invalid_date(self) -> None:
        """测试 ingest market etf 无效日期格式."""
        result = runner.invoke(app, ["ingest", "market", "etf", "2024/01/02"])
        assert result.exit_code != 0 or "错误" in result.stdout

    def test_ingest_market_stock_with_data_root(self, tmp_path: Path) -> None:
        """测试 ingest market stock 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "ingest", "market", "stock", "2024-01-02"],
        )
        # 命令可能因数据源问题失败（无 Tushare token），这是预期的
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )

    def test_ingest_market_stock_with_force(self, tmp_path: Path) -> None:
        """测试 ingest market stock --force."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "market",
                "stock",
                "2024-01-02",
                "--force",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )

    def test_ingest_market_etf_with_data_root(self, tmp_path: Path) -> None:
        """测试 ingest market etf 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "ingest", "market", "etf", "2024-01-02"],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )

    def test_ingest_market_adj_with_data_root(self, tmp_path: Path) -> None:
        """测试 ingest market adj 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "ingest", "market", "adj", "2024-01-02"],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )

    def test_ingest_market_adj_fund_with_data_root(self, tmp_path: Path) -> None:
        """测试 ingest market adj --fund 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "market",
                "adj",
                "2024-01-02",
                "--fund",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )


class TestIngestMetadataCalendar:
    """ingest metadata calendar 功能测试."""

    def test_ingest_metadata_calendar_with_data_root(self, tmp_path: Path) -> None:
        """测试 ingest metadata calendar 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "metadata",
                "calendar",
                "2024-01-02",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )

    def test_ingest_metadata_calendar_with_force(self, tmp_path: Path) -> None:
        """测试 ingest metadata calendar --force."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "metadata",
                "calendar",
                "2024-01-02",
                "--force",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )


class TestIngestMetadataBasic:
    """ingest metadata basic 功能测试."""

    def test_ingest_metadata_basic_stock(self, tmp_path: Path) -> None:
        """测试 ingest metadata basic stock."""
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "ingest", "metadata", "basic", "stock"],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )

    def test_ingest_metadata_basic_etf(self, tmp_path: Path) -> None:
        """测试 ingest metadata basic etf."""
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "ingest", "metadata", "basic", "etf"],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )

    def test_ingest_metadata_basic_index(self, tmp_path: Path) -> None:
        """测试 ingest metadata basic index."""
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "ingest", "metadata", "basic", "index"],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "Tushare"),
        )

    def test_ingest_metadata_basic_invalid_asset(self, tmp_path: Path) -> None:
        """测试 ingest metadata basic 无效资产类型."""
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "ingest", "metadata", "basic", "invalid"],
        )
        # 应该报错或退出码非零
        assert result.exit_code != 0 or "未知" in result.stdout
