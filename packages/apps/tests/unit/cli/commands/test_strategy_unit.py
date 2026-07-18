"""Strategy CLI 命令单元测试."""

from unittest.mock import MagicMock, Mock

import orjson
import pytest
from ditto_application.processes.execution.backtest_process import (
    BacktestCatalogRequestConfig,
)
from ditto_application.processes.execution.strategy_run_process import (
    StrategyRunMode,
    StrategyRunServiceConfig,
)
from ditto_application.processes.strategy.seed_bootstrap import (
    SeedBootstrapResult,
    SeedBootstrapStatus,
)
from ditto_apps.cli.main import app
from pytest_mock import MockerFixture
from typer.testing import CliRunner

CREATE_BUNDLE_PATH = "ditto_apps.cli.commands.strategy.create_strategy_bundle"


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

    def test_strategy_publish_signals_help_exists(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["strategy", "publish-signals", "--help"])
        assert result.exit_code == 0
        assert "publish-signals" in result.output

    def test_strategy_bootstrap_seeds_help_exists(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["strategy", "bootstrap-seeds", "--help"])
        assert result.exit_code == 0
        assert "bootstrap-seeds" in result.output


@pytest.mark.unit
class TestStrategyCommandIntegration:
    """Strategy 命令集成测试。"""

    def test_strategy_bootstrap_seeds_outputs_structured_lifecycle_summary(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        seed_bootstrap = Mock()
        seed_bootstrap.run.return_value = (
            SeedBootstrapResult(
                strategy_id="new.seed",
                status=SeedBootstrapStatus.PUBLISHED,
                version=1,
                created=True,
                published=True,
            ),
            SeedBootstrapResult(
                strategy_id="draft.seed",
                status=SeedBootstrapStatus.PUBLISHED,
                version=2,
                published=True,
            ),
            SeedBootstrapResult(
                strategy_id="stable.seed",
                status=SeedBootstrapStatus.UNCHANGED,
                version=3,
            ),
        )
        mock_create_bundle = mocker.patch(CREATE_BUNDLE_PATH)
        mock_create_bundle.return_value.__enter__.return_value = Mock(
            seed_bootstrap=seed_bootstrap
        )

        result = runner.invoke(app, ["strategy", "bootstrap-seeds"])

        assert result.exit_code == 0
        assert orjson.loads(result.output) == {
            "summary": {
                "created": 1,
                "published": 2,
                "unchanged": 1,
                "conflict": 0,
            },
            "results": [
                {
                    "strategy_id": "new.seed",
                    "status": "published",
                    "version": 1,
                    "created": True,
                    "published": True,
                    "differences": [],
                },
                {
                    "strategy_id": "draft.seed",
                    "status": "published",
                    "version": 2,
                    "created": False,
                    "published": True,
                    "differences": [],
                },
                {
                    "strategy_id": "stable.seed",
                    "status": "unchanged",
                    "version": 3,
                    "created": False,
                    "published": False,
                    "differences": [],
                },
            ],
        }

    def test_strategy_bootstrap_seeds_idempotent_result_exits_zero(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        seed_bootstrap = Mock()
        seed_bootstrap.run.return_value = (
            SeedBootstrapResult(
                strategy_id="stable.seed",
                status=SeedBootstrapStatus.UNCHANGED,
                version=3,
            ),
        )
        mock_create_bundle = mocker.patch(CREATE_BUNDLE_PATH)
        mock_create_bundle.return_value.__enter__.return_value = Mock(
            seed_bootstrap=seed_bootstrap
        )

        result = runner.invoke(app, ["strategy", "bootstrap-seeds"])

        assert result.exit_code == 0
        assert orjson.loads(result.output)["summary"] == {
            "created": 0,
            "published": 0,
            "unchanged": 1,
            "conflict": 0,
        }

    def test_strategy_bootstrap_seeds_conflict_outputs_json_and_exits_one(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        seed_bootstrap = Mock()
        seed_bootstrap.run.return_value = (
            SeedBootstrapResult(
                strategy_id="conflicting.seed",
                status=SeedBootstrapStatus.CONFLICT,
                version=7,
                differences=("name", "spec_json"),
            ),
        )
        mock_create_bundle = mocker.patch(CREATE_BUNDLE_PATH)
        mock_create_bundle.return_value.__enter__.return_value = Mock(
            seed_bootstrap=seed_bootstrap
        )

        result = runner.invoke(app, ["strategy", "bootstrap-seeds"])

        assert result.exit_code == 1
        payload = orjson.loads(result.output)
        assert payload["summary"] == {
            "created": 0,
            "published": 0,
            "unchanged": 0,
            "conflict": 1,
        }
        assert payload["results"][0]["differences"] == ["name", "spec_json"]

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

    def test_strategy_research_allows_experimental_data_when_explicit(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """research 命令显式传递 experimental 数据 opt-in。"""
        mock_facade = MagicMock()
        mock_facade.run_strategy_for_date_from_catalog.return_value = Mock(
            run_id="run-research-exp"
        )
        mock_create_bundle = mocker.patch(CREATE_BUNDLE_PATH)
        mock_create_bundle.return_value.__enter__.return_value = Mock(
            strategy_facade=mock_facade
        )

        result = runner.invoke(
            app,
            [
                "strategy",
                "research",
                "stock.strategy",
                "2024-01-02",
                "--allow-experimental-data",
            ],
        )

        assert result.exit_code == 0
        kwargs = mock_facade.run_strategy_for_date_from_catalog.call_args.kwargs
        assert kwargs["allow_experimental_data"] is True

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

    def test_strategy_publish_signals_fails_closed_before_opening_bundle(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        mock_create_bundle = mocker.patch(CREATE_BUNDLE_PATH)

        result = runner.invoke(
            app,
            [
                "strategy",
                "publish-signals",
                "stock-selection",
                "2026-01-30",
                "--account-id",
                "paper-a",
                "--dataset-snapshot",
                "stock_daily=sha256:stock",
                "--factor",
                "quality_roe",
            ],
        )

        mock_create_bundle.assert_not_called()
        assert result.exit_code == 2
        assert "已停用" in result.output
        assert "未写入信号包" in result.output
        assert (
            "ditto ops run-eod --signal-date 2026-01-30 "
            "--strategy-id stock-selection --account-id paper-a" in result.output
        )

    def test_strategy_publish_signals_legacy_syntax_shows_account_migration(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        mock_create_bundle = mocker.patch(CREATE_BUNDLE_PATH)

        result = runner.invoke(
            app,
            [
                "strategy",
                "publish-signals",
                "stock-selection",
                "2026-01-30",
                "--dataset-snapshot",
                "stock_daily=sha256:stock",
            ],
        )

        mock_create_bundle.assert_not_called()
        assert result.exit_code == 2
        assert "已停用" in result.output
        assert (
            "ditto ops run-eod --signal-date 2026-01-30 "
            "--strategy-id stock-selection --account-id ACCOUNT_ID" in result.output
        )

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
        assert isinstance(config, BacktestCatalogRequestConfig)
        assert config.strategy_id == "alpha.strategy"
        assert config.start_date == "2024-01-02"
        assert config.end_date == "2024-01-31"
        assert config.initial_cash == 2_000_000.0
        assert kwargs["version"] is None
        assert kwargs["source"] == "tushare"
        assert "run-backtest-1" in result.output
        assert "1050000.0" in result.output

    def test_strategy_backtest_allows_experimental_data_when_explicit(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """backtest 命令通过 BacktestServiceOptions 显式传递 maturity opt-in。"""
        mock_facade = MagicMock()
        mock_facade.run_backtest_from_catalog.return_value = Mock(
            run_id="run-backtest-exp",
            final_nav=1_010_000.0,
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
                "stock.strategy",
                "2024-01-02",
                "2024-01-31",
                "--allow-experimental-data",
            ],
        )

        assert result.exit_code == 0
        kwargs = mock_facade.run_backtest_from_catalog.call_args.kwargs
        options = kwargs["options"]
        assert options.allow_experimental_data is True
