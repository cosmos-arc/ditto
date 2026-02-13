"""Market 域摄取命令单元测试."""

from unittest.mock import MagicMock, Mock

import pytest
from ditto_port.cli.commands.ingest import market
from ditto_port.cli.main import app
from pytest_mock import MockerFixture
from typer import Context
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    """创建 CLI 测试运行器."""
    return CliRunner()


@pytest.fixture
def mock_ctx():
    """创建 typer.Context mock."""
    ctx = Mock(spec=Context)
    ctx.obj = {"data_root": "/mock/data", "verbose": False}
    return ctx


@pytest.mark.unit
class TestMarketCommands:
    """Market 命令测试."""

    def test_ingest_market_stock_command_exists(self) -> None:
        """测试 stock 命令存在且可调用."""
        assert hasattr(market, "stock")
        assert callable(market.stock)

    def test_ingest_market_etf_command_exists(self) -> None:
        """测试 etf 命令存在且可调用."""
        assert hasattr(market, "etf")
        assert callable(market.etf)

    def test_ingest_market_index_command_exists(self) -> None:
        """测试 index 命令存在且可调用."""
        assert hasattr(market, "index")
        assert callable(market.index)

    def test_ingest_market_adj_command_exists(self) -> None:
        """测试 adj 命令存在且可调用."""
        assert hasattr(market, "adj")
        assert callable(market.adj)

    def test_ingest_market_status_command_exists(self) -> None:
        """测试 status 命令存在且可调用."""
        assert hasattr(market, "status")
        assert callable(market.status)

    def test_ingest_market_stock_delegates_to_factory(
        self, mocker: MockerFixture, mock_ctx: Mock
    ) -> None:
        """测试 stock 命令委托给工厂函数."""
        mock_impl = mocker.patch.object(market, "_stock_daily_impl")
        market.stock(mock_ctx, "2024-01-02", False)
        mock_impl.assert_called_once_with(mock_ctx, "2024-01-02", False)

    def test_ingest_market_etf_delegates_to_factory(
        self, mocker: MockerFixture, mock_ctx: Mock
    ) -> None:
        """测试 etf 命令委托给工厂函数."""
        mock_impl = mocker.patch.object(market, "_etf_daily_impl")
        market.etf(mock_ctx, "2024-01-02", False)
        mock_impl.assert_called_once_with(mock_ctx, "2024-01-02", False)

    def test_ingest_market_index_delegates_to_factory(
        self, mocker: MockerFixture, mock_ctx: Mock
    ) -> None:
        """测试 index 命令委托给工厂函数."""
        mock_impl = mocker.patch.object(market, "_index_daily_impl")
        market.index(mock_ctx, "2024-01-02", False)
        mock_impl.assert_called_once_with(mock_ctx, "2024-01-02", False)

    def test_ingest_market_adj_stock_delegates_to_factory(
        self, mocker: MockerFixture, mock_ctx: Mock
    ) -> None:
        """测试 adj 命令委托给股票复权因子工厂函数."""
        mock_impl = mocker.patch.object(market, "_adj_factor_impl")
        mock_fund_impl = mocker.patch.object(market, "_fund_adj_impl")
        market.adj(mock_ctx, "2024-01-02", False, fund=False)
        mock_impl.assert_called_once_with(mock_ctx, "2024-01-02", False)
        mock_fund_impl.assert_not_called()

    def test_ingest_market_adj_fund_delegates_to_factory(
        self, mocker: MockerFixture, mock_ctx: Mock
    ) -> None:
        """测试 adj 命令 --fund 选项委托给 ETF/基金复权因子工厂函数."""
        mock_impl = mocker.patch.object(market, "_adj_factor_impl")
        mock_fund_impl = mocker.patch.object(market, "_fund_adj_impl")
        market.adj(mock_ctx, "2024-01-02", False, fund=True)
        mock_fund_impl.assert_called_once_with(mock_ctx, "2024-01-02", False)
        mock_impl.assert_not_called()

    def test_ingest_market_status_delegates_to_factory(
        self, mocker: MockerFixture, mock_ctx: Mock
    ) -> None:
        """测试 status 命令委托给工厂函数."""
        mock_impl = mocker.patch.object(market, "_stock_status_impl")
        market.status(mock_ctx, "2024-01-02", False)
        mock_impl.assert_called_once_with(mock_ctx, "2024-01-02", False)


@pytest.mark.unit
class TestMarketCommandIntegration:
    """Market 命令集成测试（通过 CLI Runner）."""

    def test_ingest_market_stock_success(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试摄取股票日行情."""
        mock_executor = MagicMock()
        mock_executor.ingest_daily.return_value = {
            "dataset": "stock_daily",
            "trade_date": "2024-01-02",
            "status": "success",
            "row_count": 4000,
            "message": "成功",
            "error": None,
        }
        # Mock at factory level where create_executor is imported
        mock_create_exec = mocker.patch(
            "ditto_port.cli.commands.factory.create_executor"
        )
        mock_create_exec.return_value.__enter__.return_value = mock_executor

        result = runner.invoke(app, ["ingest", "market", "stock", "2024-01-02"])
        assert result.exit_code == 0

    def test_ingest_market_adj_success(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试摄取复权因子."""
        mock_executor = MagicMock()
        mock_executor.ingest_daily.return_value = {
            "dataset": "adj_factor",
            "trade_date": "2024-01-02",
            "status": "success",
            "row_count": 4000,
            "message": "成功",
            "error": None,
        }
        # Mock at factory level where create_executor is imported
        mock_create_exec = mocker.patch(
            "ditto_port.cli.commands.factory.create_executor"
        )
        mock_create_exec.return_value.__enter__.return_value = mock_executor

        result = runner.invoke(app, ["ingest", "market", "adj", "2024-01-02"])
        assert result.exit_code == 0

    def test_ingest_market_adj_fund_success(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试摄取 ETF/基金复权因子."""
        mock_executor = MagicMock()
        mock_executor.ingest_daily.return_value = {
            "dataset": "fund_adj",
            "trade_date": "2024-01-02",
            "status": "success",
            "row_count": 500,
            "message": "成功",
            "error": None,
        }
        # Mock at factory level where create_executor is imported
        mock_create_exec = mocker.patch(
            "ditto_port.cli.commands.factory.create_executor"
        )
        mock_create_exec.return_value.__enter__.return_value = mock_executor

        result = runner.invoke(app, ["ingest", "market", "adj", "2024-01-02", "--fund"])
        assert result.exit_code == 0

    @pytest.mark.skip(
        reason="Flaky: reset_observability fixture 与 CliRunner I/O 流冲突"
    )
    def test_ingest_market_stock_help(self, runner: CliRunner) -> None:
        """测试 stock 命令帮助."""
        result = runner.invoke(app, ["ingest", "market", "stock", "--help"])
        assert result.exit_code == 0
        assert "股票日行情" in result.output

    def test_ingest_market_adj_help(self, runner: CliRunner) -> None:
        """测试 adj 命令帮助."""
        result = runner.invoke(app, ["ingest", "market", "adj", "--help"])
        assert result.exit_code == 0
        assert "复权因子" in result.output

    def test_ingest_market_index_success(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试摄取指数日行情."""
        mock_executor = MagicMock()
        mock_executor.ingest_daily.return_value = {
            "dataset": "index_daily",
            "trade_date": "2024-01-02",
            "status": "success",
            "row_count": 1000,
            "message": "成功",
            "error": None,
        }
        # Mock at factory level where create_executor is imported
        mock_create_exec = mocker.patch(
            "ditto_port.cli.commands.factory.create_executor"
        )
        mock_create_exec.return_value.__enter__.return_value = mock_executor

        result = runner.invoke(app, ["ingest", "market", "index", "2024-01-02"])
        assert result.exit_code == 0

    def test_ingest_market_etf_success(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试摄取 ETF 日行情."""
        mock_executor = MagicMock()
        mock_executor.ingest_daily.return_value = {
            "dataset": "etf_daily",
            "trade_date": "2024-01-02",
            "status": "success",
            "row_count": 800,
            "message": "成功",
            "error": None,
        }
        # Mock at factory level where create_executor is imported
        mock_create_exec = mocker.patch(
            "ditto_port.cli.commands.factory.create_executor"
        )
        mock_create_exec.return_value.__enter__.return_value = mock_executor

        result = runner.invoke(app, ["ingest", "market", "etf", "2024-01-02"])
        assert result.exit_code == 0

    def test_ingest_market_status_success(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试摄取股票状态."""
        mock_executor = MagicMock()
        mock_executor.ingest_daily.return_value = {
            "dataset": "stock_status",
            "trade_date": "2024-01-02",
            "status": "success",
            "row_count": 5000,
            "message": "成功",
            "error": None,
        }
        # Mock at factory level where create_executor is imported
        mock_create_exec = mocker.patch(
            "ditto_port.cli.commands.factory.create_executor"
        )
        mock_create_exec.return_value.__enter__.return_value = mock_executor

        result = runner.invoke(app, ["ingest", "market", "status", "2024-01-02"])
        assert result.exit_code == 0
