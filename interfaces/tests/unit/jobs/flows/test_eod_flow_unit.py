"""
Unit tests for EOD (End-of-Day) orchestration flow.

测试场景:
1. 非交易日跳过
2. 摄取全部成功 -> 物化 -> 策略运行
3. 摄取有失败 -> 跳过物化和策略
4. 策略运行部分失败（不影响其他策略）
5. 物化失败 -> 策略仍然运行
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_mock import MockerFixture


def _prefect_runner(entrypoint: Any) -> Any:
    """从 Prefect flow/task 对象提取底层函数。"""
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))


# ---------------------------------------------------------------------------
# 模块路径常量（避免拼写错误）
# ---------------------------------------------------------------------------
EOD_MODULE = "ditto_interfaces.jobs.flows.eod"


@pytest.fixture(autouse=True)
def _import_eod_flow():
    """确保 eod_flow 模块在 mock 之前被导入。"""
    import ditto_interfaces.jobs.flows.eod  # noqa: F401


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _mock_strategy_bundle(
    mocker: MockerFixture,
    catalog: Any = None,
    facade: Any = None,
) -> Any:
    """构造 create_strategy_bundle 的 mock，返回 StrategyBundle 上下文管理器。"""
    from ditto_interfaces.registry.contexts.bundle import StrategyBundle

    bundle = StrategyBundle(
        strategy_facade=facade or mocker.MagicMock(),
        catalog_service=catalog or mocker.MagicMock(),
    )
    cm = mocker.MagicMock()
    cm.__enter__ = mocker.Mock(return_value=bundle)
    cm.__exit__ = mocker.Mock(return_value=False)
    return cm


# ===========================================================================
# Test: 非交易日跳过
# ===========================================================================


@pytest.mark.unit
class TestEodFlowNonTradingDay:
    """非交易日应直接返回跳过结果。"""

    def test_skips_on_non_trading_day(self, mocker: MockerFixture) -> None:
        """非交易日时 EOD Flow 返回 skipped=True。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=False)

        from ditto_interfaces.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(trade_date="2026-01-01")

        assert result["skipped"] is True
        assert result["date"] == "2026-01-01"
        assert result["overall_status"] == "skipped"
        # 不应调用子 flow
        assert result["ingestion"] is None
        assert result["materialization"] is None
        assert result["strategies"] == []


# ===========================================================================
# Test: 摄取全部成功 -> 物化 -> 策略运行
# ===========================================================================


@pytest.mark.unit
class TestEodFlowHappyPath:
    """正常流程: 摄取成功 -> 物化 -> 策略运行。"""

    def test_full_pipeline_success(self, mocker: MockerFixture) -> None:
        """所有步骤成功时返回 overall_status=success。"""
        # 交易日
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)

        # 摄取成功
        mock_ingestion = mocker.patch(f"{EOD_MODULE}.daily_ingestion_flow")
        mock_ingestion.return_value = {
            "trade_date": "2026-04-15",
            "skipped": False,
            "summary": {
                "success_count": 5,
                "failed_count": 0,
                "skipped_count": 0,
            },
        }

        # 物化成功
        mock_materialization = mocker.patch(f"{EOD_MODULE}.daily_materialization_flow")
        mock_materialization.return_value = {
            "trade_date": "2026-04-15",
            "results": [],
            "summary": {"materialized_count": 3},
        }

        # 策略 bundle mock: 无已发布策略
        mock_catalog = mocker.MagicMock()
        mock_catalog.list_specs.return_value = []
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(mocker, catalog=mock_catalog),
        )

        from ditto_interfaces.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(trade_date="2026-04-15")

        assert result["skipped"] is False
        assert result["overall_status"] == "success"
        assert result["ingestion"]["summary"]["success_count"] == 5
        assert result["ingestion"]["summary"]["failed_count"] == 0
        assert result["materialization"]["summary"]["materialized_count"] == 3
        assert result["strategies"] == []

        # 验证调用顺序
        mock_ingestion.assert_called_once_with(
            trade_date="2026-04-15",
            source="tushare",
        )
        mock_materialization.assert_called_once_with(
            trade_date="2026-04-15",
        )

    def test_runs_published_strategies(self, mocker: MockerFixture) -> None:
        """有已发布策略时应逐一运行。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)

        # 摄取成功
        mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value={
                "trade_date": "2026-04-15",
                "skipped": False,
                "summary": {"success_count": 5, "failed_count": 0, "skipped_count": 0},
            },
        )
        # 物化成功
        mocker.patch(
            f"{EOD_MODULE}.daily_materialization_flow",
            return_value={
                "trade_date": "2026-04-15",
                "results": [],
                "summary": {"materialized_count": 2},
            },
        )

        # 模拟已发布策略
        from ditto_data.models.strategy import StrategySpecRecord

        spec1 = StrategySpecRecord(
            strategy_id="alpha_momentum",
            name="Alpha Momentum",
            spec_json={},
            version=1,
            status="published",
        )
        spec2 = StrategySpecRecord(
            strategy_id="alpha_mean_revert",
            name="Alpha Mean Revert",
            spec_json={},
            version=2,
            status="published",
        )
        spec_draft = StrategySpecRecord(
            strategy_id="alpha_draft",
            name="Alpha Draft",
            spec_json={},
            version=1,
            status="draft",
        )

        mock_catalog = mocker.MagicMock()
        mock_catalog.list_specs.return_value = [spec1, spec2, spec_draft]

        # 模拟 StrategyFacade
        mock_facade = mocker.MagicMock()
        from ditto_app.process.execution.strategy_run_process import StrategyRunResult

        mock_facade.run_strategy_for_date_from_catalog.side_effect = [
            StrategyRunResult(
                run_id="run-001",
                trade_date="2026-04-15",
                strategy_id="alpha_momentum",
                target=self._make_target_portfolio("alpha_momentum", "run-001"),
                mode="research",
            ),
            StrategyRunResult(
                run_id="run-002",
                trade_date="2026-04-15",
                strategy_id="alpha_mean_revert",
                target=self._make_target_portfolio("alpha_mean_revert", "run-002"),
                mode="research",
            ),
        ]

        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(
                mocker, catalog=mock_catalog, facade=mock_facade
            ),
        )

        from ditto_interfaces.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(trade_date="2026-04-15")

        assert result["overall_status"] == "success"
        assert len(result["strategies"]) == 2
        assert result["strategies"][0]["strategy_id"] == "alpha_momentum"
        assert result["strategies"][0]["status"] == "success"
        assert result["strategies"][1]["strategy_id"] == "alpha_mean_revert"
        assert result["strategies"][1]["status"] == "success"

        # 只应运行 published 策略（排除 draft）
        assert mock_facade.run_strategy_for_date_from_catalog.call_count == 2

    def test_no_strategies_to_run(self, mocker: MockerFixture) -> None:
        """无已发布策略时 strategies 列表为空。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)
        mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value={
                "trade_date": "2026-04-15",
                "skipped": False,
                "summary": {"success_count": 5, "failed_count": 0, "skipped_count": 0},
            },
        )
        mocker.patch(
            f"{EOD_MODULE}.daily_materialization_flow",
            return_value={
                "trade_date": "2026-04-15",
                "results": [],
                "summary": {"materialized_count": 0},
            },
        )

        # 无策略
        mock_catalog = mocker.MagicMock()
        mock_catalog.list_specs.return_value = []
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(mocker, catalog=mock_catalog),
        )

        from ditto_interfaces.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(trade_date="2026-04-15")

        assert result["strategies"] == []
        assert result["overall_status"] == "success"

    # -- helper --------------------------------------------------------------

    @staticmethod
    def _make_target_portfolio(
        strategy_id: str = "test",
        run_id: str = "run-001",
    ) -> Any:
        """构造 TargetPortfolio 实例。"""
        from ditto_engine.alpha.models import TargetPortfolio

        return TargetPortfolio(
            trade_date="2026-04-15",
            strategy_id=strategy_id,
            run_id=run_id,
            positions={},
            cash_target=1.0,
        )


# ===========================================================================
# Test: 摄取有失败 -> 跳过物化和策略
# ===========================================================================


@pytest.mark.unit
class TestEodFlowIngestionFailure:
    """摄取失败时应跳过物化和策略，返回 partial 状态。"""

    def test_skips_downstream_on_ingestion_failure(self, mocker: MockerFixture) -> None:
        """摄取有失败时跳过物化和策略，但发送告警。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)

        # 摄取有失败
        mock_ingestion = mocker.patch(f"{EOD_MODULE}.daily_ingestion_flow")
        mock_ingestion.return_value = {
            "trade_date": "2026-04-15",
            "skipped": False,
            "summary": {
                "success_count": 3,
                "failed_count": 2,
                "skipped_count": 0,
            },
        }

        # 物化不应被调用
        mock_materialization = mocker.patch(f"{EOD_MODULE}.daily_materialization_flow")

        # 摄取失败需要 AlertManager（通过 make_app_container 获取）
        mock_alert_manager = mocker.MagicMock()
        mock_container = mocker.MagicMock()
        mock_container.close = mocker.Mock()
        mock_container.get.return_value = mock_alert_manager
        mocker.patch(f"{EOD_MODULE}.make_app_container", return_value=mock_container)

        from ditto_interfaces.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(trade_date="2026-04-15")

        assert result["skipped"] is False
        assert result["overall_status"] == "partial"
        assert result["ingestion"]["summary"]["failed_count"] == 2
        assert result["materialization"] is None
        assert result["strategies"] == []

        # 物化不应被调用
        mock_materialization.assert_not_called()
        # 告警应被发送
        mock_alert_manager.send_alert.assert_called_once()

    def test_sends_alert_on_ingestion_failure(self, mocker: MockerFixture) -> None:
        """摄取失败时应发送告警通知。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)

        mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value={
                "trade_date": "2026-04-15",
                "skipped": False,
                "summary": {
                    "success_count": 1,
                    "failed_count": 1,
                    "skipped_count": 0,
                },
            },
        )
        mocker.patch(f"{EOD_MODULE}.daily_materialization_flow")

        # 模拟 AlertManager
        mock_alert_manager = mocker.MagicMock()
        mock_alert_manager.send_alert.return_value = {"email": True}
        mock_container = mocker.MagicMock()
        mock_container.close = mocker.Mock()
        mock_container.get.return_value = mock_alert_manager
        mocker.patch(f"{EOD_MODULE}.make_app_container", return_value=mock_container)

        from ditto_interfaces.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        runner(trade_date="2026-04-15")

        # 注意: 告警通知是在摄取失败场景中通过 make_app_container 获取的
        # 这里验证告警逻辑是否被触发
        mock_alert_manager.send_alert.assert_called_once()
        call_kwargs = mock_alert_manager.send_alert.call_args
        assert call_kwargs.kwargs["template"] == "eod_ingestion_failure"


# ===========================================================================
# Test: 策略运行部分失败
# ===========================================================================


@pytest.mark.unit
class TestEodFlowStrategyPartialFailure:
    """策略运行部分失败时不应影响其他策略。"""

    def test_strategy_failure_does_not_block_others(
        self,
        mocker: MockerFixture,
    ) -> None:
        """单个策略失败不影响其他策略运行。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)

        mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value={
                "trade_date": "2026-04-15",
                "skipped": False,
                "summary": {"success_count": 5, "failed_count": 0, "skipped_count": 0},
            },
        )
        mocker.patch(
            f"{EOD_MODULE}.daily_materialization_flow",
            return_value={
                "trade_date": "2026-04-15",
                "results": [],
                "summary": {"materialized_count": 2},
            },
        )

        # 两个已发布策略
        from ditto_data.models.strategy import StrategySpecRecord

        spec1 = StrategySpecRecord(
            strategy_id="alpha_good",
            name="Alpha Good",
            spec_json={},
            version=1,
            status="published",
        )
        spec2 = StrategySpecRecord(
            strategy_id="alpha_bad",
            name="Alpha Bad",
            spec_json={},
            version=1,
            status="published",
        )

        mock_catalog = mocker.MagicMock()
        mock_catalog.list_specs.return_value = [spec1, spec2]

        mock_facade = mocker.MagicMock()
        from ditto_app.process.execution.strategy_run_process import StrategyRunResult
        from ditto_engine.alpha.models import TargetPortfolio

        # 第一个成功，第二个失败
        mock_facade.run_strategy_for_date_from_catalog.side_effect = [
            StrategyRunResult(
                run_id="run-good",
                trade_date="2026-04-15",
                strategy_id="alpha_good",
                target=TargetPortfolio(
                    trade_date="2026-04-15",
                    strategy_id="alpha_good",
                    run_id="run-good",
                    positions={},
                    cash_target=1.0,
                ),
                mode="research",
            ),
            RuntimeError("策略计算失败"),
        ]

        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(
                mocker, catalog=mock_catalog, facade=mock_facade
            ),
        )

        from ditto_interfaces.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(trade_date="2026-04-15")

        # 整体应为 partial
        assert result["overall_status"] == "partial"
        assert len(result["strategies"]) == 2
        assert result["strategies"][0]["strategy_id"] == "alpha_good"
        assert result["strategies"][0]["status"] == "success"
        assert result["strategies"][1]["strategy_id"] == "alpha_bad"
        assert result["strategies"][1]["status"] == "failed"
        assert "RuntimeError" in result["strategies"][1]["error"]

        # 两个策略都应被调用
        assert mock_facade.run_strategy_for_date_from_catalog.call_count == 2


# ===========================================================================
# Test: 物化失败 -> 策略仍然运行
# ===========================================================================


@pytest.mark.unit
class TestEodFlowMaterializationFailure:
    """物化失败时策略仍应运行（策略依赖摄取数据，不依赖物化结果）。"""

    def test_strategy_runs_after_materialization_failure(
        self,
        mocker: MockerFixture,
    ) -> None:
        """物化失败后策略仍然执行。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)

        mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value={
                "trade_date": "2026-04-15",
                "skipped": False,
                "summary": {"success_count": 5, "failed_count": 0, "skipped_count": 0},
            },
        )

        # 物化抛出异常
        mock_materialization = mocker.patch(f"{EOD_MODULE}.daily_materialization_flow")
        mock_materialization.side_effect = RuntimeError("物化服务不可用")

        # 模拟已发布策略
        from ditto_data.models.strategy import StrategySpecRecord

        spec = StrategySpecRecord(
            strategy_id="alpha_test",
            name="Alpha Test",
            spec_json={},
            version=1,
            status="published",
        )

        mock_catalog = mocker.MagicMock()
        mock_catalog.list_specs.return_value = [spec]

        mock_facade = mocker.MagicMock()
        from ditto_app.process.execution.strategy_run_process import StrategyRunResult
        from ditto_engine.alpha.models import TargetPortfolio

        mock_facade.run_strategy_for_date_from_catalog.return_value = StrategyRunResult(
            run_id="run-test",
            trade_date="2026-04-15",
            strategy_id="alpha_test",
            target=TargetPortfolio(
                trade_date="2026-04-15",
                strategy_id="alpha_test",
                run_id="run-test",
                positions={},
                cash_target=1.0,
            ),
            mode="research",
        )

        # 策略 bundle mock
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(
                mocker, catalog=mock_catalog, facade=mock_facade
            ),
        )

        # AlertManager 仍通过 make_app_container 获取
        mock_alert_manager = mocker.MagicMock()
        mock_alert_manager.send_alert.return_value = {"email": True}
        mock_container = mocker.MagicMock()
        mock_container.close = mocker.Mock()
        mock_container.get.return_value = mock_alert_manager
        mocker.patch(f"{EOD_MODULE}.make_app_container", return_value=mock_container)

        from ditto_interfaces.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(trade_date="2026-04-15")

        # 策略应成功运行
        assert len(result["strategies"]) == 1
        assert result["strategies"][0]["status"] == "success"

        # 物化结果应记录失败
        assert result["materialization"] is not None
        assert result["materialization"]["status"] == "failed"

        # 整体应为 partial（物化失败）
        assert result["overall_status"] == "partial"

        # 应发送物化失败告警
        mock_alert_manager.send_alert.assert_called_once()
        call_kwargs = mock_alert_manager.send_alert.call_args
        assert call_kwargs.kwargs["template"] == "eod_materialization_failure"


# ===========================================================================
# Test: 返回值结构
# ===========================================================================


@pytest.mark.unit
class TestEodFlowReturnValueStructure:
    """验证返回值结构。"""

    def test_return_value_keys_on_success(self, mocker: MockerFixture) -> None:
        """成功时应包含所有必要键。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)
        mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value={
                "trade_date": "2026-04-15",
                "skipped": False,
                "summary": {"success_count": 5, "failed_count": 0, "skipped_count": 0},
            },
        )
        mocker.patch(
            f"{EOD_MODULE}.daily_materialization_flow",
            return_value={
                "trade_date": "2026-04-15",
                "results": [],
                "summary": {"materialized_count": 0},
            },
        )

        mock_catalog = mocker.MagicMock()
        mock_catalog.list_specs.return_value = []
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(mocker, catalog=mock_catalog),
        )

        from ditto_interfaces.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(trade_date="2026-04-15")

        assert "date" in result
        assert "skipped" in result
        assert "overall_status" in result
        assert "ingestion" in result
        assert "materialization" in result
        assert "strategies" in result

    def test_return_value_keys_on_skip(self, mocker: MockerFixture) -> None:
        """跳过时应包含所有必要键。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=False)

        from ditto_interfaces.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(trade_date="2026-01-01")

        assert "date" in result
        assert "skipped" in result
        assert "overall_status" in result
        assert "ingestion" in result
        assert "materialization" in result
        assert "strategies" in result

    def test_overall_status_is_success_when_all_pass(
        self,
        mocker: MockerFixture,
    ) -> None:
        """所有步骤成功时 overall_status 为 success。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)
        mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value={
                "trade_date": "2026-04-15",
                "skipped": False,
                "summary": {"success_count": 5, "failed_count": 0, "skipped_count": 0},
            },
        )
        mocker.patch(
            f"{EOD_MODULE}.daily_materialization_flow",
            return_value={
                "trade_date": "2026-04-15",
                "results": [],
                "summary": {"materialized_count": 0},
            },
        )

        mock_catalog = mocker.MagicMock()
        mock_catalog.list_specs.return_value = []
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(mocker, catalog=mock_catalog),
        )

        from ditto_interfaces.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(trade_date="2026-04-15")

        assert result["overall_status"] == "success"
