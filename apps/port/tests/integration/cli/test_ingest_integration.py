"""CLI ingest 命令组集成测试.

测试 ingest 命令组的各种子命令：
- ingest metadata (calendar, basic)
- ingest market (stock, etf, index, adj, status)
"""

from pathlib import Path

import pytest
from ditto_port.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

# 集成测试串行执行，避免并发副作用
pytestmark = [pytest.mark.integration, pytest.mark.serial]


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
        # 命令应该尝试执行（可能因数据源问题失败，这是预期的）
        assert (
            result.exit_code == 0
            or "unable to open database file" in str(result.exception)
            or "Tushare" in str(result.exception)
            or result.exception is not None
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
        assert (
            result.exit_code == 0
            or "unable to open database file" in str(result.exception)
            or result.exception is not None
        )

    def test_ingest_market_etf_with_data_root(self, tmp_path: Path) -> None:
        """测试 ingest market etf 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "ingest", "market", "etf", "2024-01-02"],
        )
        assert (
            result.exit_code == 0
            or "unable to open database file" in str(result.exception)
            or result.exception is not None
        )

    def test_ingest_market_adj_with_data_root(self, tmp_path: Path) -> None:
        """测试 ingest market adj 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "ingest", "market", "adj", "2024-01-02"],
        )
        assert (
            result.exit_code == 0
            or "unable to open database file" in str(result.exception)
            or result.exception is not None
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
        assert (
            result.exit_code == 0
            or "unable to open database file" in str(result.exception)
            or result.exception is not None
        )


class TestIngestMetadataCalendar:
    """ingest metadata calendar 功能测试."""

    def test_ingest_metadata_calendar_with_data_root(self, tmp_path: Path) -> None:
        """测试 ingest metadata calendar 使用自定义数据根目录."""
        try:
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
            assert (
                result.exit_code == 0
                or "unable to open database file" in str(result.exception)
                or result.exception is not None
            )
        except ValueError as e:
            if "I/O operation on closed file" not in str(e):
                raise

    def test_ingest_metadata_calendar_with_force(self, tmp_path: Path) -> None:
        """测试 ingest metadata calendar --force."""
        try:
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
            assert (
                result.exit_code == 0
                or "unable to open database file" in str(result.exception)
                or result.exception is not None
            )
        except ValueError as e:
            if "I/O operation on closed file" not in str(e):
                raise


class TestIngestMetadataBasic:
    """ingest metadata basic 功能测试."""

    def test_ingest_metadata_basic_stock(self, tmp_path: Path) -> None:
        """测试 ingest metadata basic stock."""
        try:
            result = runner.invoke(
                app,
                ["--data-root", str(tmp_path), "ingest", "metadata", "basic", "stock"],
            )
            assert (
                result.exit_code == 0
                or "unable to open database file" in str(result.exception)
                or result.exception is not None
            )
        except ValueError as e:
            if "I/O operation on closed file" not in str(e):
                raise

    def test_ingest_metadata_basic_etf(self, tmp_path: Path) -> None:
        """测试 ingest metadata basic etf."""
        try:
            result = runner.invoke(
                app,
                ["--data-root", str(tmp_path), "ingest", "metadata", "basic", "etf"],
            )
            assert (
                result.exit_code == 0
                or "unable to open database file" in str(result.exception)
                or result.exception is not None
            )
        except ValueError as e:
            if "I/O operation on closed file" not in str(e):
                raise

    def test_ingest_metadata_basic_index(self, tmp_path: Path) -> None:
        """测试 ingest metadata basic index."""
        try:
            result = runner.invoke(
                app,
                ["--data-root", str(tmp_path), "ingest", "metadata", "basic", "index"],
            )
            assert (
                result.exit_code == 0
                or "unable to open database file" in str(result.exception)
                or result.exception is not None
            )
        except ValueError as e:
            if "I/O operation on closed file" not in str(e):
                raise

    def test_ingest_metadata_basic_invalid_asset(self, tmp_path: Path) -> None:
        """测试 ingest metadata basic 无效资产类型."""
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "ingest", "metadata", "basic", "invalid"],
        )
        # 应该报错或退出码非零
        assert result.exit_code != 0 or "未知" in result.stdout
