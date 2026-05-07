"""CLI query 命令组集成测试.

测试 query 命令组的各种子命令：
- query metadata (instruments, instrument)
- query market
- query fundamental
- query capital
- query macro
"""

from pathlib import Path

import pytest
from ditto_apps.cli.main import app
from packages.apps.tests.integration.cli.helpers import assert_cli_result
from typer.testing import CliRunner

runner = CliRunner()

# 集成测试串行执行，避免并发副作用
# cli_test: 禁用 observability 自动重置，避免 I/O 冲突
pytestmark = [pytest.mark.integration, pytest.mark.serial, pytest.mark.cli_test]


class TestQueryMetadata:
    """query metadata 子命令测试."""

    def test_query_metadata_help(self) -> None:
        """测试 query metadata --help."""
        result = runner.invoke(app, ["query", "metadata", "--help"])
        assert result.exit_code == 0
        assert "instruments" in result.stdout
        assert "instrument" in result.stdout

    def test_query_metadata_instruments_help(self) -> None:
        """测试 query metadata instruments --help."""
        result = runner.invoke(app, ["query", "metadata", "instruments", "--help"])
        assert result.exit_code == 0
        assert "--ticker" in result.stdout
        assert "--asset-class" in result.stdout
        assert "--exchange" in result.stdout
        assert "--json" in result.stdout

    def test_query_metadata_instrument_help(self) -> None:
        """测试 query metadata instrument --help."""
        result = runner.invoke(app, ["query", "metadata", "instrument", "--help"])
        assert result.exit_code == 0
        assert "INSTRUMENT-ID" in result.stdout or "标的 ID" in result.stdout


class TestQueryMarket:
    """query market 子命令测试."""

    def test_query_market_help(self) -> None:
        """测试 query market --help."""
        result = runner.invoke(app, ["query", "market", "--help"])
        assert result.exit_code == 0


class TestQueryFundamental:
    """query fundamental 子命令测试."""

    def test_query_fundamental_help(self) -> None:
        """测试 query fundamental --help."""
        result = runner.invoke(app, ["query", "fundamental", "--help"])
        assert result.exit_code == 0


class TestQueryCapital:
    """query capital 子命令测试."""

    def test_query_capital_help(self) -> None:
        """测试 query capital --help."""
        result = runner.invoke(app, ["query", "capital", "--help"])
        assert result.exit_code == 0


class TestQueryMacro:
    """query macro 子命令测试."""

    def test_query_macro_help(self) -> None:
        """测试 query macro --help."""
        result = runner.invoke(app, ["query", "macro", "--help"])
        assert result.exit_code == 0


class TestQueryMetadataInstruments:
    """query metadata instruments 功能测试."""

    def test_query_metadata_instruments_with_data_root(self, tmp_path: Path) -> None:
        """测试 query metadata instruments 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "query", "metadata", "instruments"],
        )
        # 查询命令需要数据库支持，可能因数据库问题失败
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "未找到"),
        )

    def test_query_metadata_instruments_with_ticker(self, tmp_path: Path) -> None:
        """测试 query metadata instruments --ticker."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "query",
                "metadata",
                "instruments",
                "--ticker",
                "600000",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "未找到"),
        )

    def test_query_metadata_instruments_with_asset_class(self, tmp_path: Path) -> None:
        """测试 query metadata instruments --asset-class."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "query",
                "metadata",
                "instruments",
                "--asset-class",
                "stock",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "未找到"),
        )

    def test_query_metadata_instruments_with_json(self, tmp_path: Path) -> None:
        """测试 query metadata instruments --json."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "query",
                "metadata",
                "instruments",
                "--json",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "未找到"),
        )


class TestQueryMetadataInstrument:
    """query metadata instrument 功能测试."""

    def test_query_metadata_instrument_with_data_root(self, tmp_path: Path) -> None:
        """测试 query metadata instrument 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "query", "metadata", "instrument", "1"],
        )
        # 查询命令需要数据库支持，可能因数据库问题或找不到标的而失败
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=("unable to open database file", "未找到"),
        )
