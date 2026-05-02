"""CLI 按标的摄取命令集成测试.

测试合并到域命令后的按标的摄取功能:
- ingest market stock/etf/index --ticker/--standard-ticker/--instrument-id
- ingest fundamental balance/income/cash-flow/dividend --ticker
- ingest capital valuation/margin --ticker
"""

from pathlib import Path

import pytest
from ditto_apps.cli.main import app
from helpers import assert_cli_result
from typer.testing import CliRunner

runner = CliRunner()

# 集成测试串行执行，避免并发副作用
# cli_test: 禁用 observability 自动重置，避免 I/O 冲突
pytestmark = [pytest.mark.integration, pytest.mark.serial, pytest.mark.cli_test]


class TestIngestMarketInstrumentMode:
    """ingest market 按标的摄取模式测试."""

    def test_ingest_market_stock_help_shows_instrument_options(self) -> None:
        """测试 ingest market stock --help 显示标识符选项."""
        result = runner.invoke(app, ["ingest", "market", "stock", "--help"])
        assert result.exit_code == 0
        assert "--ticker" in result.stdout
        assert "--standard-ticker" in result.stdout
        assert "--instrument-id" in result.stdout
        assert "--start" in result.stdout
        assert "--end" in result.stdout

    def test_ingest_market_stock_by_ticker_help(self) -> None:
        """测试 ingest market stock --ticker 模式帮助信息."""
        result = runner.invoke(app, ["ingest", "market", "stock", "--help"])
        assert result.exit_code == 0
        # 确保文档中有两种模式的说明
        assert "按日期" in result.stdout or "date" in result.stdout.lower()
        assert "按标的" in result.stdout or "ticker" in result.stdout.lower()

    def test_ingest_market_stock_date_and_ticker_mutually_exclusive(self) -> None:
        """测试日期和标识符不能同时指定."""
        result = runner.invoke(
            app,
            [
                "ingest",
                "market",
                "stock",
                "2024-01-15",
                "--ticker",
                "000001",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-31",
            ],
        )
        # 应该报错
        assert result.exit_code != 0 or "不能同时指定" in result.stdout

    def test_ingest_market_stock_ticker_requires_start_end(self) -> None:
        """测试按标的摄取需要同时指定 --start 和 --end."""
        result = runner.invoke(
            app,
            [
                "ingest",
                "market",
                "stock",
                "--ticker",
                "000001",
                "--start",
                "2024-01-01",
            ],
        )
        # 应该报错
        assert result.exit_code != 0 or "--end" in result.stdout

    def test_ingest_market_stock_no_params_error(self) -> None:
        """测试不指定任何参数时报错."""
        result = runner.invoke(app, ["ingest", "market", "stock"])
        # 应该报错
        assert result.exit_code != 0 or "请指定" in result.stdout

    def test_ingest_market_stock_by_ticker_with_data_root(self, tmp_path: Path) -> None:
        """测试 ingest market stock --ticker 使用自定义数据根目录."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "market",
                "stock",
                "--ticker",
                "000001",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-31",
            ],
        )
        # 命令可能因数据源问题失败（无 Tushare token），这是预期的
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=(
                "unable to open database file",
                "Tushare",
                "instrument",
            ),
        )

    @pytest.mark.skip(reason="loguru I/O 冲突, 功能已通过其他测试验证")
    def test_ingest_market_stock_by_standard_ticker(self, tmp_path: Path) -> None:
        """测试 ingest market stock --standard-ticker."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "market",
                "stock",
                "--standard-ticker",
                "000001.XSHE",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-31",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=(
                "unable to open database file",
                "Tushare",
                "instrument",
            ),
        )

    def test_ingest_market_stock_by_instrument_id(self, tmp_path: Path) -> None:
        """测试 ingest market stock --instrument-id."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "market",
                "stock",
                "--instrument-id",
                "1000001",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-31",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=(
                "unable to open database file",
                "Tushare",
                "instrument",
            ),
        )

    def test_ingest_market_etf_by_ticker(self, tmp_path: Path) -> None:
        """测试 ingest market etf --ticker."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "market",
                "etf",
                "--ticker",
                "510300",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-31",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=(
                "unable to open database file",
                "Tushare",
                "instrument",
            ),
        )

    def test_ingest_market_index_by_ticker(self, tmp_path: Path) -> None:
        """测试 ingest market index --ticker."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "market",
                "index",
                "--ticker",
                "000001",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-31",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=(
                "unable to open database file",
                "Tushare",
                "instrument",
            ),
        )

    def test_ingest_market_stock_by_ticker_with_force(self, tmp_path: Path) -> None:
        """测试 ingest market stock --ticker --force."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "market",
                "stock",
                "--ticker",
                "000001",
                "--start",
                "2024-01-01",
                "--end",
                "2024-01-31",
                "--force",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=(
                "unable to open database file",
                "Tushare",
                "instrument",
            ),
        )


class TestIngestFundamentalInstrumentMode:
    """ingest fundamental 按标的摄取模式测试."""

    def test_ingest_fundamental_balance_help_shows_instrument_options(self) -> None:
        """测试 ingest fundamental balance --help 显示标识符选项."""
        result = runner.invoke(app, ["ingest", "fundamental", "balance", "--help"])
        assert result.exit_code == 0
        assert "--ticker" in result.stdout
        assert "--standard-ticker" in result.stdout
        assert "--instrument-id" in result.stdout

    def test_ingest_fundamental_balance_by_ticker(self, tmp_path: Path) -> None:
        """测试 ingest fundamental balance --ticker."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "fundamental",
                "balance",
                "--ticker",
                "000001",
                "--start",
                "2024-01-01",
                "--end",
                "2024-06-30",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=(
                "unable to open database file",
                "Tushare",
                "instrument",
            ),
        )

    def test_ingest_fundamental_income_by_ticker(self, tmp_path: Path) -> None:
        """测试 ingest fundamental income --ticker."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "fundamental",
                "income",
                "--ticker",
                "000001",
                "--start",
                "2024-01-01",
                "--end",
                "2024-06-30",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=(
                "unable to open database file",
                "Tushare",
                "instrument",
            ),
        )

    def test_ingest_fundamental_cash_flow_by_ticker(self, tmp_path: Path) -> None:
        """测试 ingest fundamental cash-flow --ticker."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "fundamental",
                "cash-flow",
                "--ticker",
                "000001",
                "--start",
                "2024-01-01",
                "--end",
                "2024-06-30",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=(
                "unable to open database file",
                "Tushare",
                "instrument",
            ),
        )

    def test_ingest_fundamental_dividend_by_ticker(self, tmp_path: Path) -> None:
        """测试 ingest fundamental dividend --ticker."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "fundamental",
                "dividend",
                "--ticker",
                "000001",
                "--start",
                "2024-01-01",
                "--end",
                "2024-06-30",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=(
                "unable to open database file",
                "Tushare",
                "instrument",
            ),
        )


class TestIngestCapitalInstrumentMode:
    """ingest capital 按标的摄取模式测试."""

    def test_ingest_capital_valuation_help_shows_instrument_options(self) -> None:
        """测试 ingest capital valuation --help 显示标识符选项."""
        result = runner.invoke(app, ["ingest", "capital", "valuation", "--help"])
        assert result.exit_code == 0
        assert "--ticker" in result.stdout
        assert "--standard-ticker" in result.stdout
        assert "--instrument-id" in result.stdout

    def test_ingest_capital_valuation_by_ticker(self, tmp_path: Path) -> None:
        """测试 ingest capital valuation --ticker."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "capital",
                "valuation",
                "--ticker",
                "000001",
                "--start",
                "2024-01-01",
                "--end",
                "2024-06-30",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=(
                "unable to open database file",
                "Tushare",
                "instrument",
            ),
        )

    def test_ingest_capital_margin_by_ticker(self, tmp_path: Path) -> None:
        """测试 ingest capital margin --ticker."""
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
                "ingest",
                "capital",
                "margin",
                "--ticker",
                "000001",
                "--start",
                "2024-01-01",
                "--end",
                "2024-06-30",
            ],
        )
        assert_cli_result(
            result,
            allowed_exit_codes=(0, 1),
            allowed_error_patterns=(
                "unable to open database file",
                "Tushare",
                "instrument",
            ),
        )


class TestTickerCommandRemoved:
    """验证独立 ticker 命令已移除."""

    def test_ingest_ticker_command_not_found(self) -> None:
        """测试 ingest ticker 命令不再存在."""
        result = runner.invoke(app, ["ingest", "ticker", "--help"])
        # 应该报错或显示命令不存在
        assert result.exit_code != 0 or "No such command" in result.stdout
