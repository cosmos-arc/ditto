"""Strategy CLI 命令单元测试."""

from unittest.mock import MagicMock, Mock

import pytest
from ditto_app.process.execution.backtest_process import BacktestServiceConfig
from ditto_app.process.execution.strategy_run_process import (
    StrategyRunMode,
    StrategyRunServiceConfig,
)
from ditto_interfaces.cli.main import app
from pytest_mock import MockerFixture
from typer.testing import CliRunner

CREATE_BUNDLE_PATH = "ditto_interfaces.cli.commands.strategy.create_strategy_bundle"


@pytest.fixture
def runner() -> CliRunner:
    """创建 CLI 测试运行器。"""
    return CliRunner()


@pytest.mark.unit
class TestStrategyCommandHelp:
    """Strategy 命令帮助测试。"""

    def test_strategy_group_help_exists(self, runner: CliRunner) -> None:
        """测试 strategy 命令组存在。"""
        result = runner.invoke(app, ["strategy", "--help"])
        assert result.exit_code == 0
        assert "策略" in result.output

    def test_strategy_research_help_exists(self, runner: CliRunner) -> None:
        """测试 strategy research 命令存在。"""
        result = runner.invoke(app, ["strategy", "research", "--help"])
        assert result.exit_code == 0
        assert "research" in result.output

    def test_strategy_recommend_help_exists(self, runner: CliRunner) -> None:
        """测试 strategy recommend 命令存在。"""
        result = runner.invoke(app, ["strategy", "recommend", "--help"])
        assert result.exit_code == 0
        assert "recommend" in result.output

    def test_strategy_backtest_help_exists(self, runner: CliRunner) -> None:
        """测试 strategy backtest 命令存在。"""
        result = runner.invoke(app, ["strategy", "backtest", "--help"])
        assert result.exit_code == 0
        assert "backtest" in result.output


@pytest.mark.unit
class TestStrategyCommandIntegration:
    """Strategy 命令集成测试。"""

    def test_strategy_research_delegates_to_facade(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试 research 命令委托给 facade。"""
        mock_facade = MagicMock()
        mock_facade.run_strategy_for_date_from_catalog.return_value = Mock(
            run_id="run-research-1"
        )
        mock_create_bundle = mocker.patch(CREATE_BUNDLE_PATH)
        mock_create_bundle.return_value.__enter__.return_value = Mock(
            strategy_facade=mock_facade
        )

        result = runner.invoke(
            app,
            ["strategy", "research", "alpha.strategy", "2024-01-02", "--version", "3"],
        )

        assert result.exit_code == 0
        kwargs = mock_facade.run_strategy_for_date_from_catalog.call_args.kwargs
        config = kwargs["config"]
        assert isinstance(config, StrategyRunServiceConfig)
        assert config.strategy_id == "alpha.strategy"
        assert config.mode == StrategyRunMode.RESEARCH
        assert kwargs["trade_date"] == "2024-01-02"
        assert kwargs["version"] == 3
        assert kwargs["source"] == "tushare"
        assert "run-research-1" in result.output

    def test_strategy_recommend_delegates_to_facade(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试 recommend 命令委托给 facade。"""
        mock_facade = MagicMock()
        mock_facade.run_strategy_for_date_from_catalog.return_value = Mock(
            run_id="run-recommend-1"
        )
        mock_create_bundle = mocker.patch(CREATE_BUNDLE_PATH)
        mock_create_bundle.return_value.__enter__.return_value = Mock(
            strategy_facade=mock_facade
        )

        result = runner.invoke(
            app,
            ["strategy", "recommend", "alpha.strategy", "2024-01-02"],
        )

        assert result.exit_code == 0
        kwargs = mock_facade.run_strategy_for_date_from_catalog.call_args.kwargs
        config = kwargs["config"]
        assert isinstance(config, StrategyRunServiceConfig)
        assert config.strategy_id == "alpha.strategy"
        assert config.mode == StrategyRunMode.RECOMMENDATION
        assert kwargs["trade_date"] == "2024-01-02"
        assert kwargs["version"] is None
        assert kwargs["source"] == "tushare"
        assert "run-recommend-1" in result.output

    def test_strategy_backtest_delegates_to_facade(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试 backtest 命令委托给 facade。"""
        mock_facade = MagicMock()
        mock_facade.run_backtest_from_catalog.return_value = Mock(
            run_id="run-backtest-1",
            final_nav=1_050_000.0,
            period=("2024-01-02", "2024-01-31"),
        )
        mock_create_bundle = mocker.patch(CREATE_BUNDLE_PATH)
        mock_create_bundle.return_value.__enter__.return_value = Mock(
            strategy_facade=mock_facade
        )

        result = runner.invoke(
            app,
            [
                "strategy",
                "backtest",
                "alpha.strategy",
                "2024-01-02",
                "2024-01-31",
                "--initial-cash",
                "2000000",
            ],
        )

        assert result.exit_code == 0
        kwargs = mock_facade.run_backtest_from_catalog.call_args.kwargs
        config = kwargs["config"]
        assert isinstance(config, BacktestServiceConfig)
        assert config.strategy_id == "alpha.strategy"
        assert config.start_date == "2024-01-02"
        assert config.end_date == "2024-01-31"
        assert config.initial_cash == 2_000_000.0
        assert kwargs["version"] is None
        assert kwargs["source"] == "tushare"
        assert "run-backtest-1" in result.output
        assert "1050000.0" in result.output
