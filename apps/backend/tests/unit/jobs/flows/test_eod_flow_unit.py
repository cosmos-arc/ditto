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

from typing import Any, cast

import pytest
from ditto_application.processes.execution.strategy_run_process import StrategyRunMode
from loguru import logger
from pytest_mock import MockerFixture


def _prefect_runner(entrypoint: Any) -> Any:
    """从 Prefect flow/task 对象提取底层函数。"""
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))


# ---------------------------------------------------------------------------
# 模块路径常量（避免拼写错误）
# ---------------------------------------------------------------------------
EOD_MODULE = "ditto_apps.jobs.flows.eod"


@pytest.mark.unit
def test_alert_failure_log_does_not_serialize_sensitive_exception(
    mocker: MockerFixture,
) -> None:
    """EOD alert containment must not re-log sender exception secrets."""
    from ditto_apps.jobs.flows.eod import _send_alert_safely
    from ditto_platform.services import NotificationLevel

    bot_token = "eod-secret-token:13579"
    sensitive_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    alert_manager = mocker.MagicMock()
    alert_manager.send_alert.side_effect = RuntimeError(
        f"notification failed for {sensitive_url}"
    )
    records: list[object] = []
    sink_id = logger.add(
        lambda message: records.append(message.record),
        level="ERROR",
    )

    try:
        _send_alert_safely(
            alert_manager,
            template="dq_failure",
            context={"trade_date": "2026-07-16"},
            level=NotificationLevel.ERROR,
        )
    finally:
        logger.remove(sink_id)

    serialized_records = repr(records)
    assert bot_token not in serialized_records
    assert sensitive_url not in serialized_records
    assert records
    record = cast(dict[str, object], records[-1])
    extra = record["extra"]
    assert isinstance(extra, dict)
    assert extra == {
        "event": "eod_alert_send_failed",
        "error_code": "EOD_ALERT_SEND_FAILED",
        "error_type": "RuntimeError",
        "template": "dq_failure",
    }


@pytest.fixture(autouse=True)
def _import_eod_flow():
    """确保 eod_flow 模块在 mock 之前被导入。"""
    import ditto_apps.jobs.flows.eod  # noqa: F401


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _mock_strategy_bundle(
    mocker: MockerFixture,
    catalog: Any = None,
    facade: Any = None,
    run_service: Any = None,
    signal_package_publisher: Any = None,
    sizing_context_builder: Any = None,
    trade_date_resolver: Any = None,
) -> Any:
    """构造 create_strategy_bundle 的 mock，返回 StrategyBundle 上下文管理器。"""
    from ditto_apps.registry.contexts.bundle import StrategyBundle

    if signal_package_publisher is not None:
        sizing_context_builder = sizing_context_builder or mocker.MagicMock()
        trade_date_resolver = trade_date_resolver or mocker.MagicMock()
        signal_package_publisher.finalize.side_effect = lambda package: package
        signal_package_publisher.find_staged.return_value = None
    bundle = StrategyBundle(
        strategy_facade=facade or mocker.MagicMock(),
        catalog_service=catalog or mocker.MagicMock(),
        run_service=run_service or mocker.MagicMock(),
        signal_package_publisher=signal_package_publisher,
        sizing_context_builder=sizing_context_builder,
        trade_date_resolver=trade_date_resolver,
    )
    cm = mocker.MagicMock()
    cm.__enter__ = mocker.Mock(return_value=bundle)
    cm.__exit__ = mocker.Mock(return_value=False)
    return cm


def _ready_etf_ingestion() -> dict[str, object]:
    """Return complete ready evidence for tests that exercise later EOD stages."""
    return {
        "trade_date": "2026-04-15",
        "skipped": False,
        "t1_results": {
            "etf_daily": {
                "trade_date": "2026-04-15",
                "status": "success",
                "checksum": "sha256:etf-ready",
                "row_count": 100,
            }
        },
        "dqc_results": {
            "trade_date": "2026-04-15",
            "results_by_dataset": {
                "etf_daily": {
                    "passed": True,
                    "evidence": {
                        "kind": "persisted_ingestion_l1_l2",
                        "trade_date": "2026-04-15",
                        "checksum": "sha256:etf-ready",
                        "row_count": 100,
                    },
                }
            },
        },
        "summary": {
            "success_count": 5,
            "failed_count": 0,
            "skipped_count": 0,
        },
    }


# ===========================================================================
# Test: 非交易日跳过
# ===========================================================================


@pytest.mark.unit
class TestEodFlowNonTradingDay:
    """非交易日应直接返回跳过结果。"""

    def test_skips_on_non_trading_day(self, mocker: MockerFixture) -> None:
        """非交易日时 EOD Flow 返回 skipped=True。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=False)

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(
            trade_date="2026-01-01",
            strategy_id="etf-rotation",
            account_id="paper",
        )

        assert result["skipped"] is True
        assert result["date"] == "2026-01-01"
        assert result["overall_status"] == "skipped"
        # 不应调用子 flow
        assert result["ingestion"] is None
        assert result["materialization"] is None
        assert result["strategies"] == []

    def test_missing_execution_selection_blocks_before_any_side_effect(
        self,
        mocker: MockerFixture,
    ) -> None:
        """缺失策略或账户选择时 fail closed，不得启动摄取。"""
        check_day = mocker.patch(f"{EOD_MODULE}.check_trading_day")
        ingestion = mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value=_ready_etf_ingestion(),
        )

        from ditto_apps.jobs.flows.eod import eod_flow

        result = _prefect_runner(eod_flow)(trade_date="2026-04-15")

        assert result["overall_status"] == "partial"
        assert result["strategies"][0]["status"] == "blocked"
        assert result["strategies"][0]["reason"] == "STRATEGY_SELECTION_REQUIRED"
        check_day.assert_not_called()
        ingestion.assert_not_called()

    def test_prefect_flow_delegates_to_shared_pipeline_runner(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Prefect wrapper 只选择 Prefect adapters，并委托共享业务 runner。"""
        expected = {
            "date": "2026-04-15",
            "skipped": True,
            "overall_status": "skipped",
            "ingestion": None,
            "materialization": None,
            "strategies": [],
        }
        pipeline = mocker.patch(
            f"{EOD_MODULE}.run_eod_pipeline",
            create=True,
            return_value=expected,
        )

        from ditto_apps.jobs.flows.eod import (
            check_trading_day,
            daily_ingestion_flow,
            daily_materialization_flow,
            eod_flow,
        )

        result = _prefect_runner(eod_flow)(
            trade_date="2026-04-15",
            source="tushare",
            strategy_id="alpha",
            account_id="paper",
        )

        assert result is expected
        pipeline.assert_called_once()
        call = pipeline.call_args
        assert call.args == ()
        assert {
            key: value for key, value in call.kwargs.items() if key != "dependencies"
        } == {
            "trade_date": "2026-04-15",
            "source": "tushare",
            "strategy_id": "alpha",
            "account_id": "paper",
            "allow_experimental_data": False,
        }
        dependencies = call.kwargs["dependencies"]
        assert dependencies.check_trading_day is check_trading_day
        assert dependencies.daily_ingestion is daily_ingestion_flow
        assert dependencies.daily_materialization is daily_materialization_flow


# ===========================================================================
# Test: 摄取全部成功 -> 物化 -> 策略运行
# ===========================================================================


@pytest.mark.unit
class TestEodFlowHappyPath:
    """正常流程: 摄取成功 -> 物化 -> 策略运行。"""

    def test_ingestion_is_scoped_from_selected_published_strategy_before_run(
        self,
        mocker: MockerFixture,
    ) -> None:
        """The selected published version must own EOD ingestion scope."""
        from ditto_application.processes.execution.eod_coordinator import (
            EodStrategyRequest,
        )
        from ditto_strategy.models import StrategySpecRecord

        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)
        ingestion = mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value=_ready_etf_ingestion(),
        )
        mocker.patch(
            f"{EOD_MODULE}.daily_materialization_flow",
            return_value={"trade_date": "2026-04-15", "summary": {}},
        )
        request = EodStrategyRequest(
            strategy_id="alpha",
            strategy_version="7",
            required_datasets=("etf_daily",),
        )
        strategy_runner = mocker.patch(
            f"{EOD_MODULE}._run_strategies",
            return_value=(
                [
                    {
                        "strategy_id": "alpha",
                        "strategy_version": "7",
                        "status": "completed",
                    }
                ],
                True,
            ),
        )
        catalog = mocker.MagicMock()
        catalog.get_active_published.return_value = StrategySpecRecord(
            strategy_id="alpha",
            name="Alpha",
            spec_json={"required_datasets": ["etf_daily"]},
            version=7,
        )
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(mocker, catalog=catalog),
        )

        from ditto_apps.jobs.flows.eod import eod_flow

        result = _prefect_runner(eod_flow)(
            trade_date="2026-04-15",
            strategy_id="alpha",
            account_id="paper",
        )

        assert result["overall_status"] == "success"
        ingestion.assert_called_once_with(
            trade_date="2026-04-15",
            source="tushare",
            required_datasets=("etf_daily",),
        )
        strategy_runner.assert_called_once_with(
            "2026-04-15",
            dataset_states=mocker.ANY,
            strategy=request,
            account_id="paper",
            source="tushare",
            allow_experimental_data=False,
        )
        catalog.get_active_published.assert_called_once_with("alpha")

    def test_unknown_strategy_dataset_scope_blocks_before_ingestion(
        self,
        mocker: MockerFixture,
    ) -> None:
        """An invalid published dependency must never reach a data provider."""
        from ditto_strategy.models import StrategySpecRecord

        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)
        ingestion = mocker.patch(f"{EOD_MODULE}.daily_ingestion_flow")
        materialization = mocker.patch(f"{EOD_MODULE}.daily_materialization_flow")
        catalog = mocker.MagicMock()
        catalog.get_active_published.return_value = StrategySpecRecord(
            strategy_id="alpha",
            name="Alpha",
            spec_json={"required_datasets": ["unknown_market_feed"]},
            version=7,
        )
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(mocker, catalog=catalog),
        )
        blocked = {
            "strategy_id": "alpha",
            "strategy_version": "7",
            "status": "blocked",
            "reason": "REQUIRED_DATA_NOT_READY",
        }
        strategy_runner = mocker.patch(
            f"{EOD_MODULE}._run_strategies",
            return_value=([blocked], False),
        )

        from ditto_apps.jobs.flows.eod import eod_flow

        result = _prefect_runner(eod_flow)(
            trade_date="2026-04-15",
            strategy_id="alpha",
            account_id="paper",
        )

        assert result["overall_status"] == "partial"
        assert result["strategies"] == [blocked]
        assert result["ingestion"] is None
        ingestion.assert_not_called()
        materialization.assert_not_called()
        strategy_runner.assert_called_once()

    def test_missing_published_strategy_blocks_before_ingestion(
        self, mocker: MockerFixture
    ) -> None:
        """A missing published selection must not trigger provider side effects."""
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
        mock_catalog.get_active_published.return_value = None
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(mocker, catalog=mock_catalog),
        )

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(
            trade_date="2026-04-15",
            strategy_id="missing-strategy",
            account_id="paper",
        )

        assert result["skipped"] is False
        assert result["overall_status"] == "partial"
        assert result["ingestion"] is None
        assert result["materialization"] is None
        assert result["strategies"][0]["reason"] == "NO_ACTIVE_STRATEGY"

        mock_ingestion.assert_not_called()
        mock_materialization.assert_not_called()

    def test_runs_only_explicitly_selected_published_strategy(
        self,
        mocker: MockerFixture,
    ) -> None:
        """可发布多个研究策略，EOD 仍只运行显式选中的执行策略。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)

        # 摄取成功
        mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value=_ready_etf_ingestion(),
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
        from ditto_strategy.models import StrategySpecRecord

        spec1 = StrategySpecRecord(
            strategy_id="alpha_momentum",
            name="Alpha Momentum",
            spec_json={"required_datasets": ["etf_daily"]},
            version=1,
        )
        spec2 = StrategySpecRecord(
            strategy_id="alpha_mean_revert",
            name="Alpha Mean Revert",
            spec_json={"required_datasets": ["etf_daily"]},
            version=2,
        )
        mock_catalog = mocker.MagicMock()
        mock_catalog.get_active_published.side_effect = {
            "alpha_momentum": spec1,
            "alpha_mean_revert": spec2,
        }.get

        # 模拟 StrategyFacade
        mock_facade = mocker.MagicMock()
        from ditto_application.processes.execution.strategy_run_process import (
            StrategyRunResult,
        )

        mock_facade.run_strategy_for_date_from_catalog.side_effect = [
            StrategyRunResult(
                run_id="run-001",
                trade_date="2026-04-15",
                strategy_id="alpha_momentum",
                target=self._make_target_portfolio("alpha_momentum", "run-001"),
                mode=StrategyRunMode.RESEARCH,
            ),
            StrategyRunResult(
                run_id="run-002",
                trade_date="2026-04-15",
                strategy_id="alpha_mean_revert",
                target=self._make_target_portfolio("alpha_mean_revert", "run-002"),
                mode=StrategyRunMode.RESEARCH,
            ),
        ]
        mock_publisher = mocker.MagicMock()
        mock_publisher.publish.side_effect = [
            mocker.Mock(intents=(mocker.Mock(),), checksum="sha256:first"),
            mocker.Mock(
                intents=(mocker.Mock(), mocker.Mock()),
                checksum="sha256:second",
            ),
        ]

        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(
                mocker,
                catalog=mock_catalog,
                facade=mock_facade,
                signal_package_publisher=mock_publisher,
            ),
        )

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(
            trade_date="2026-04-15",
            strategy_id="alpha_momentum",
            account_id="paper",
        )

        assert result["overall_status"] == "success"
        assert len(result["strategies"]) == 1
        assert result["strategies"][0]["strategy_id"] == "alpha_momentum"
        assert result["strategies"][0]["status"] == "completed"

        mock_catalog.get_active_published.assert_called_once_with("alpha_momentum")
        mock_catalog.list_latest_published.assert_not_called()
        assert mock_facade.run_strategy_for_date_from_catalog.call_count == 1
        assert mock_publisher.publish.call_count == 1

    def test_publishes_signal_package_for_successful_strategy(
        self,
        mocker: MockerFixture,
    ) -> None:
        """成功运行的 published 策略应发布交易信号包并返回发布元数据。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)
        mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value={
                "trade_date": "2026-04-15",
                "skipped": False,
                "t1_results": {
                    "etf_daily": {
                        "trade_date": "2026-04-15",
                        "status": "success",
                        "checksum": "sha256:etf-daily",
                        "row_count": 100,
                    }
                },
                "dqc_results": {
                    "trade_date": "2026-04-15",
                    "results_by_dataset": {
                        "etf_daily": {
                            "passed": True,
                            "evidence": {
                                "kind": "persisted_ingestion_l1_l2",
                                "trade_date": "2026-04-15",
                                "checksum": "sha256:etf-daily",
                                "row_count": 100,
                            },
                        }
                    },
                },
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

        from ditto_application.processes.execution.signal_package_models import (
            SignalPackagePublishRequest,
        )
        from ditto_application.processes.execution.strategy_run_process import (
            StrategyRunResult,
        )
        from ditto_strategy.models import StrategySpecRecord

        spec = StrategySpecRecord(
            strategy_id="alpha_momentum",
            name="Alpha Momentum",
            spec_json={"required_datasets": ["etf_daily"]},
            version=1,
        )
        batch_key = "eod-2026-04-15-alpha_momentum-1"
        target = self._make_target_portfolio("alpha_momentum", batch_key)
        mock_catalog = mocker.MagicMock()
        mock_catalog.get_active_published.return_value = spec
        mock_facade = mocker.MagicMock()
        mock_facade.run_strategy_for_date_from_catalog.return_value = StrategyRunResult(
            run_id=batch_key,
            trade_date="2026-04-15",
            strategy_id="alpha_momentum",
            target=target,
            mode=StrategyRunMode.RECOMMENDATION,
            factor_ids=("signal_value",),
            factor_values={510300: {"signal_value": 0.42}},
            risk_flags=("MAX_POSITION_LIMIT",),
            risk_locked_instruments=(510300,),
        )
        sizing_builder = mocker.MagicMock()
        from ditto_application.processes.execution.manual_sizing import (
            ManualSizingContexts,
            ManualTradeDates,
        )

        sizing_builder.build.return_value = ManualSizingContexts(
            account_id="paper",
            sleeve_id="manual-paper-alpha_momentum",
            contexts={},
        )
        date_resolver = mocker.MagicMock()

        date_resolver.resolve.return_value = ManualTradeDates(
            signal_date="2026-04-15",
            decision_date="2026-04-15",
            intended_trade_date="2026-04-16",
        )
        mock_publisher = mocker.MagicMock()
        mock_publisher.publish.return_value = mocker.Mock(
            outcome="completed",
            artifact_id="signal-package-alpha",
            intents=(mocker.Mock(), mocker.Mock()),
            checksum="sha256:eod-signals",
        )
        run_service = mocker.MagicMock()

        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(
                mocker,
                catalog=mock_catalog,
                facade=mock_facade,
                run_service=run_service,
                signal_package_publisher=mock_publisher,
                sizing_context_builder=sizing_builder,
                trade_date_resolver=date_resolver,
            ),
        )

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(
            trade_date="2026-04-15",
            strategy_id="alpha_momentum",
            account_id="paper",
        )

        kwargs = mock_facade.run_strategy_for_date_from_catalog.call_args.kwargs
        assert kwargs["config"].mode == StrategyRunMode.RECOMMENDATION
        assert kwargs["config"].run_id == batch_key
        assert kwargs["config"].manage_run_lifecycle is False
        assert kwargs["source"] == "tushare"
        assert kwargs["allow_experimental_data"] is False
        mock_catalog.get_active_published.assert_called_once_with("alpha_momentum")
        mock_catalog.list_latest_published.assert_not_called()
        run_service.create_run.assert_called_once()
        run_service.mark_running.assert_called_once_with(batch_key)
        run_service.mark_completed.assert_called_once_with(batch_key)
        run_service.mark_failed.assert_not_called()
        sizing_builder.build.assert_called_once_with(
            account_id="paper",
            strategy_id="alpha_momentum",
            signal_date="2026-04-15",
            instrument_ids=(),
            allow_experimental_data=False,
            risk_locked_instruments=(510300,),
        )
        mock_publisher.publish.assert_called_once_with(
            SignalPackagePublishRequest(
                target=target,
                strategy_version="1",
                account_id="paper",
                sleeve_id="manual-paper-alpha_momentum",
                sizing_contexts={},
                decision_date="2026-04-15",
                intended_trade_date="2026-04-16",
                required_datasets=("etf_daily",),
                required_dataset_states=(
                    {
                        "dataset": "etf_daily",
                        "status": "ready",
                        "snapshot_id": "sha256:etf-daily",
                        "reason": "",
                    },
                ),
                dataset_snapshot_ids={"etf_daily": "sha256:etf-daily"},
                factor_ids=("signal_value",),
                factor_values={510300: {"signal_value": 0.42}},
                risk_flags=("MAX_POSITION_LIMIT",),
                threshold=0.01,
            )
        )
        mock_publisher.finalize.assert_called_once_with(
            mock_publisher.publish.return_value
        )
        assert result["strategies"] == [
            {
                "strategy_id": "alpha_momentum",
                "strategy_version": "1",
                "batch_key": batch_key,
                "status": "completed",
                "required_dataset_states": [
                    {
                        "dataset": "etf_daily",
                        "status": "ready",
                        "snapshot_id": "sha256:etf-daily",
                        "reason": "",
                    }
                ],
                "artifact_id": "signal-package-alpha",
                "checksum": "sha256:eod-signals",
                "reason": "",
                "run_id": batch_key,
            }
        ]

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
        mock_catalog.get_active_published.return_value = None
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(mocker, catalog=mock_catalog),
        )

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(
            trade_date="2026-04-15",
            strategy_id="missing-strategy",
            account_id="paper",
        )

        assert result["strategies"][0]["reason"] == "NO_ACTIVE_STRATEGY"
        assert result["overall_status"] == "partial"

    # -- helper --------------------------------------------------------------

    @staticmethod
    def _make_target_portfolio(
        strategy_id: str = "test",
        run_id: str = "run-001",
    ) -> Any:
        """构造 TargetPortfolio 实例。"""
        from ditto_strategy.alpha.models import TargetPortfolio

        return TargetPortfolio(
            trade_date="2026-04-15",
            strategy_id=strategy_id,
            run_id=run_id,
            positions={},
            cash_target=1.0,
        )


# ===========================================================================
# Test: 摄取有失败 -> 跳过物化并持久化策略 outcome
# ===========================================================================


@pytest.mark.unit
class TestEodFlowIngestionFailure:
    """摄取失败时跳过物化，但策略 outcome 必须可查询。"""

    def test_persists_blocked_outcome_without_dataset_evidence(
        self,
        mocker: MockerFixture,
    ) -> None:
        """缺少逐数据集证据时仍由 coordinator 持久化 blocked run。"""
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

        from ditto_strategy.models import StrategySpecRecord

        spec = StrategySpecRecord(
            strategy_id="alpha",
            name="Alpha",
            spec_json={"required_datasets": ["etf_daily"]},
            version=1,
        )
        catalog = mocker.MagicMock()
        catalog.get_active_published.return_value = spec
        facade = mocker.MagicMock()
        run_service = mocker.MagicMock()
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(
                mocker,
                catalog=catalog,
                facade=facade,
                run_service=run_service,
            ),
        )

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(
            trade_date="2026-04-15",
            strategy_id="alpha",
            account_id="paper",
        )

        assert result["skipped"] is False
        assert result["overall_status"] == "partial"
        assert result["ingestion"]["summary"]["failed_count"] == 2
        assert result["materialization"] is None
        assert result["strategies"] == [
            {
                "strategy_id": "alpha",
                "strategy_version": "1",
                "batch_key": "eod-2026-04-15-alpha-1",
                "status": "blocked",
                "required_dataset_states": [
                    {
                        "dataset": "etf_daily",
                        "status": "unknown",
                        "snapshot_id": None,
                        "reason": "",
                    }
                ],
                "artifact_id": None,
                "checksum": None,
                "reason": "REQUIRED_DATA_NOT_READY",
                "run_id": "eod-2026-04-15-alpha-1",
            }
        ]

        # 物化不应被调用
        mock_materialization.assert_not_called()
        # 告警应被发送
        mock_alert_manager.send_alert.assert_called_once()
        facade.run_strategy_for_date_from_catalog.assert_not_called()
        run_service.create_run.assert_called_once()
        run_service.mark_pending_failed.assert_called_once_with(
            "eod-2026-04-15-alpha-1",
            "blocked:REQUIRED_DATA_NOT_READY",
        )

    def test_dataset_readiness_fails_closed_without_snapshot_and_distinguishes_dq(
        self,
    ) -> None:
        """ready ingestion 仍需 snapshot；ingestion 与 DQ failure reason 必须稳定。"""
        from ditto_apps.jobs.flows.eod import _dataset_states_from_ingestion

        states = _dataset_states_from_ingestion(
            {
                "trade_date": "2026-04-15",
                "t1_results": {
                    "etf_daily": {
                        "trade_date": "2026-04-15",
                        "status": "success",
                        "checksum": None,
                    },
                    "stock_daily": {
                        "trade_date": "2026-04-15",
                        "status": "failed",
                        "error": "network",
                    },
                    "adj_factor": {
                        "trade_date": "2026-04-15",
                        "status": "success",
                        "checksum": "sha256:adj",
                    },
                    "fund_daily": {
                        "trade_date": "2026-04-15",
                        "status": "success",
                        "checksum": "sha256:fund",
                    },
                },
                "dqc_results": {
                    "trade_date": "2026-04-15",
                    "results_by_dataset": {
                        "etf_daily": {"passed": True},
                        "stock_daily": {"passed": False},
                        "adj_factor": {"passed": False, "error": "null ratio"},
                    },
                },
            },
            signal_date="2026-04-15",
        )

        assert (states["etf_daily"].status, states["etf_daily"].reason) == (
            "unknown",
            "SNAPSHOT_ID_MISSING",
        )
        assert (states["stock_daily"].status, states["stock_daily"].reason) == (
            "missing",
            "INGESTION_FAILED: network",
        )
        assert (states["adj_factor"].status, states["adj_factor"].reason) == (
            "dq_failed",
            "DQ_FAILED: null ratio",
        )
        assert (states["fund_daily"].status, states["fund_daily"].reason) == (
            "unknown",
            "DQ_EVIDENCE_MISSING",
        )

    @pytest.mark.parametrize("passed", [None, 1, "true", {}])
    def test_dataset_readiness_rejects_non_authoritative_dq_passed(
        self,
        passed: object,
    ) -> None:
        """只有 DQ 的真实 bool True 才能成为 ready 证据。"""
        from ditto_apps.jobs.flows.eod import _dataset_states_from_ingestion

        dq_row = {} if passed == {} else {"passed": passed}
        states = _dataset_states_from_ingestion(
            {
                "trade_date": "2026-04-15",
                "t1_results": {
                    "etf_daily": {
                        "trade_date": "2026-04-15",
                        "status": "success",
                        "checksum": "sha256:etf",
                    }
                },
                "dqc_results": {
                    "trade_date": "2026-04-15",
                    "results_by_dataset": {"etf_daily": dq_row},
                },
            },
            signal_date="2026-04-15",
        )

        assert states["etf_daily"].status == "unknown"
        assert states["etf_daily"].reason == "DQ_EVIDENCE_INVALID"

    @pytest.mark.parametrize(
        ("dq_evidence", "expected_reason"),
        [
            (None, "DQ_SNAPSHOT_EVIDENCE_MISSING"),
            (
                {
                    "kind": "persisted_ingestion_l1_l2",
                    "trade_date": "2026-04-15",
                    "checksum": "sha256:other",
                    "row_count": 100,
                },
                "DQ_CHECKSUM_MISMATCH",
            ),
            (
                {
                    "kind": "persisted_ingestion_l1_l2",
                    "trade_date": "2026-04-15",
                    "checksum": "sha256:etf",
                    "row_count": 99,
                },
                "DQ_ROW_COUNT_MISMATCH",
            ),
        ],
    )
    def test_dataset_readiness_rejects_unbound_dq_snapshot_evidence(
        self,
        dq_evidence: dict[str, object] | None,
        expected_reason: str,
    ) -> None:
        """DQ pass must be cryptographically bound to the persisted producer row."""
        from ditto_apps.jobs.flows.eod import _dataset_states_from_ingestion

        dq_row: dict[str, object] = {"passed": True}
        if dq_evidence is not None:
            dq_row["evidence"] = dq_evidence
        states = _dataset_states_from_ingestion(
            {
                "trade_date": "2026-04-15",
                "t1_results": {
                    "etf_daily": {
                        "trade_date": "2026-04-15",
                        "status": "success",
                        "checksum": "sha256:etf",
                        "row_count": 100,
                    }
                },
                "dqc_results": {
                    "trade_date": "2026-04-15",
                    "results_by_dataset": {"etf_daily": dq_row},
                },
            },
            signal_date="2026-04-15",
        )

        assert states["etf_daily"].status == "unknown"
        assert states["etf_daily"].reason == expected_reason

    def test_dataset_readiness_accepts_exact_dq_snapshot_evidence(self) -> None:
        """Matching date, checksum, and row count form authoritative ready evidence."""
        from ditto_apps.jobs.flows.eod import _dataset_states_from_ingestion

        states = _dataset_states_from_ingestion(
            {
                "trade_date": "2026-04-15",
                "t1_results": {
                    "etf_daily": {
                        "trade_date": "2026-04-15",
                        "status": "success",
                        "checksum": "sha256:etf",
                        "row_count": 100,
                    }
                },
                "dqc_results": {
                    "trade_date": "2026-04-15",
                    "results_by_dataset": {
                        "etf_daily": {
                            "passed": True,
                            "evidence": {
                                "kind": "persisted_ingestion_l1_l2",
                                "trade_date": "2026-04-15",
                                "checksum": "sha256:etf",
                                "row_count": 100,
                            },
                        }
                    },
                },
            },
            signal_date="2026-04-15",
        )

        assert states["etf_daily"].status == "ready"
        assert states["etf_daily"].reason == ""

    def test_dataset_readiness_accepts_matching_explicit_asof_evidence(self) -> None:
        """Sparse PIT evidence binds its effective date and aggregate snapshot."""
        from ditto_application.catalog_freshness import (
            aggregate_source_snapshot_ids,
        )
        from ditto_apps.jobs.flows.eod import _dataset_states_from_ingestion

        snapshot_id = aggregate_source_snapshot_ids(("snapshot:a", "snapshot:b"))
        assert snapshot_id is not None
        evidence = {
            "kind": "persisted_asof_catalog_snapshot",
            "source": "tushare",
            "signal_date": "2026-07-16",
            "checked_at": "2026-07-16T20:00:00+00:00",
            "effective_partition_date": "2026-07-01",
            "source_snapshot_id": snapshot_id,
            "source_snapshot_ids": ["snapshot:a", "snapshot:b"],
            "row_count": 125,
            "freshness_sla_hours": 1080,
        }
        states = _dataset_states_from_ingestion(
            {
                "trade_date": "2026-07-16",
                "t1_results": {
                    "balance_sheet": {
                        "trade_date": "2026-07-16",
                        "status": "success",
                        "checksum": None,
                        "row_count": 0,
                        "snapshot_evidence": evidence,
                    }
                },
                "dqc_results": {
                    "trade_date": "2026-07-16",
                    "results_by_dataset": {
                        "balance_sheet": {"passed": True, "evidence": evidence}
                    },
                },
            },
            signal_date="2026-07-16",
        )

        assert states["balance_sheet"].status == "ready"
        assert states["balance_sheet"].snapshot_id == snapshot_id
        assert states["balance_sheet"].reason == ""

    def test_dataset_readiness_rejects_evidence_for_other_signal_date(self) -> None:
        """摄取或 DQ 日期不是目标 signal date 时不得复用为 ready。"""
        from ditto_apps.jobs.flows.eod import _dataset_states_from_ingestion

        states = _dataset_states_from_ingestion(
            {
                "trade_date": "2026-04-14",
                "t1_results": {
                    "etf_daily": {
                        "trade_date": "2026-04-14",
                        "status": "success",
                        "checksum": "sha256:etf",
                    }
                },
                "dqc_results": {
                    "trade_date": "2026-04-14",
                    "results_by_dataset": {"etf_daily": {"passed": True}},
                },
            },
            signal_date="2026-04-15",
        )

        assert states["etf_daily"].status == "stale"
        assert states["etf_daily"].reason == ("INGESTION_DATE_MISMATCH:2026-04-14")

    def test_dataset_readiness_rejects_dq_for_other_signal_date(self) -> None:
        """行情日期正确但 DQ 日期不一致时仍必须 fail closed。"""
        from ditto_apps.jobs.flows.eod import _dataset_states_from_ingestion

        states = _dataset_states_from_ingestion(
            {
                "trade_date": "2026-04-15",
                "t1_results": {
                    "etf_daily": {
                        "trade_date": "2026-04-15",
                        "status": "success",
                        "checksum": "sha256:etf",
                    }
                },
                "dqc_results": {
                    "trade_date": "2026-04-14",
                    "results_by_dataset": {"etf_daily": {"passed": True}},
                },
            },
            signal_date="2026-04-15",
        )

        assert states["etf_daily"].status == "unknown"
        assert states["etf_daily"].reason == "DQ_DATE_MISMATCH:2026-04-14"

    def test_eod_request_reuses_legacy_deserializer_fallback_and_invalid_spec_blocks(
        self,
    ) -> None:
        """旧 spec 走模板迁移；无法反序列化的 record 用未知依赖 fail closed。"""
        from ditto_apps.jobs.flows.eod import _eod_request
        from ditto_strategy.models import StrategySpecRecord

        legacy = StrategySpecRecord(
            strategy_id="legacy-etf",
            name="Legacy ETF",
            version=2,
            spec_json={
                "template": "etf_rotation",
                "universe": "csi_etf_broad",
                "asset_class": "etf",
            },
        )
        with pytest.warns(UserWarning, match="missing required_datasets"):
            request = _eod_request(legacy)

        assert request.required_datasets == ("etf_daily",)
        invalid = _eod_request(
            StrategySpecRecord(
                strategy_id="invalid",
                name="Invalid",
                version=1,
                spec_json={},
            )
        )
        assert invalid.required_datasets == ("__invalid_strategy_spec__",)

    def test_sends_alert_on_ingestion_failure(self, mocker: MockerFixture) -> None:
        """摄取失败时应发送告警通知。"""
        from ditto_application.processes.execution.eod_coordinator import (
            EodStrategyRequest,
        )

        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)
        strategy = EodStrategyRequest(
            strategy_id="alpha",
            strategy_version="1",
            required_datasets=("etf_daily",),
        )
        mocker.patch(
            f"{EOD_MODULE}._resolve_published_eod_request",
            return_value=strategy,
        )

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
        strategy_runner = mocker.patch(
            f"{EOD_MODULE}._run_strategies",
            return_value=([], False),
        )

        # 模拟 AlertManager
        mock_alert_manager = mocker.MagicMock()
        mock_alert_manager.send_alert.return_value = {"email": True}
        mock_container = mocker.MagicMock()
        mock_container.close = mocker.Mock()
        mock_container.get.return_value = mock_alert_manager
        mocker.patch(f"{EOD_MODULE}.make_app_container", return_value=mock_container)

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        runner(
            trade_date="2026-04-15",
            strategy_id="alpha",
            account_id="paper",
        )

        # 注意: 告警通知是在摄取失败场景中通过 make_app_container 获取的
        # 这里验证告警逻辑是否被触发
        mock_alert_manager.send_alert.assert_called_once()
        call_kwargs = mock_alert_manager.send_alert.call_args
        assert call_kwargs.kwargs["template"] == "eod_ingestion_failure"
        strategy_runner.assert_called_once_with(
            "2026-04-15",
            dataset_states={},
            strategy=strategy,
            account_id="paper",
            source="tushare",
            allow_experimental_data=False,
        )

    def test_unrelated_ingestion_failure_only_blocks_dependent_strategy(
        self,
        mocker: MockerFixture,
    ) -> None:
        """有逐数据集证据时，EOD 必须让 coordinator 独立判断每个策略。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)
        mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value={
                "trade_date": "2026-04-15",
                "skipped": False,
                "t0_results": {},
                "t1_results": {
                    "etf_daily": {
                        "dataset": "etf_daily",
                        "trade_date": "2026-04-15",
                        "status": "success",
                        "checksum": "sha256:etf-snapshot",
                        "row_count": 100,
                    },
                    "stock_daily": {
                        "dataset": "stock_daily",
                        "trade_date": "2026-04-15",
                        "status": "failed",
                        "error": "provider unavailable",
                    },
                },
                "dqc_results": {
                    "trade_date": "2026-04-15",
                    "results_by_dataset": {
                        "etf_daily": {
                            "passed": True,
                            "evidence": {
                                "kind": "persisted_ingestion_l1_l2",
                                "trade_date": "2026-04-15",
                                "checksum": "sha256:etf-snapshot",
                                "row_count": 100,
                            },
                        },
                        "stock_daily": {"passed": False},
                    },
                },
                "summary": {
                    "success_count": 1,
                    "failed_count": 1,
                    "skipped_count": 0,
                },
            },
        )
        mock_materialization = mocker.patch(f"{EOD_MODULE}.daily_materialization_flow")

        from ditto_application.processes.execution.signal_package import SignalPackage
        from ditto_application.processes.execution.strategy_run_process import (
            StrategyRunResult,
        )
        from ditto_strategy.alpha.models import TargetPortfolio
        from ditto_strategy.models import StrategySpecRecord

        etf_spec = StrategySpecRecord(
            strategy_id="etf-ready",
            name="ETF Ready",
            spec_json={"required_datasets": ["etf_daily"]},
            version=1,
        )
        catalog = mocker.MagicMock()
        catalog.get_active_published.return_value = etf_spec
        target = TargetPortfolio(
            trade_date="2026-04-15",
            strategy_id="etf-ready",
            run_id="eod-2026-04-15-etf-ready-1",
            positions={},
            cash_target=1.0,
        )
        facade = mocker.MagicMock()
        facade.run_strategy_for_date_from_catalog.return_value = StrategyRunResult(
            run_id=target.run_id,
            trade_date="2026-04-15",
            strategy_id="etf-ready",
            target=target,
            mode=StrategyRunMode.RECOMMENDATION,
        )
        publisher = mocker.MagicMock()
        publisher.publish.return_value = SignalPackage(
            run_id=target.run_id,
            strategy_id="etf-ready",
            signal_date="2026-04-15",
            intents=(),
            dataset_snapshot_ids={"etf_daily": "sha256:etf-snapshot"},
            factor_ids=(),
            risk_flags=(),
            factor_values={},
            selection_reasons={},
            checksum="sha256:package",
            artifact_id="signal-package-etf-ready",
            outcome="no_rebalance",
            no_rebalance=True,
        )
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(
                mocker,
                catalog=catalog,
                facade=facade,
                signal_package_publisher=publisher,
            ),
        )
        alert_manager = mocker.MagicMock()
        container = mocker.MagicMock()
        container.get.return_value = alert_manager
        mocker.patch(f"{EOD_MODULE}.make_app_container", return_value=container)

        from ditto_apps.jobs.flows.eod import eod_flow

        result = _prefect_runner(eod_flow)(
            trade_date="2026-04-15",
            strategy_id="etf-ready",
            account_id="paper",
        )

        assert [item["status"] for item in result["strategies"]] == ["no_rebalance"]
        assert result["strategies"][0]["required_dataset_states"] == [
            {
                "dataset": "etf_daily",
                "status": "ready",
                "snapshot_id": "sha256:etf-snapshot",
                "reason": "",
            }
        ]
        run_config = facade.run_strategy_for_date_from_catalog.call_args.kwargs[
            "config"
        ]
        assert run_config.run_id == "eod-2026-04-15-etf-ready-1"
        publish_call = publisher.publish.call_args
        assert publish_call.kwargs == {}
        assert len(publish_call.args) == 1
        publish_request = publish_call.args[0]
        assert publish_request.target == target
        assert publish_request.required_datasets == ("etf_daily",)
        assert publish_request.dataset_snapshot_ids == {
            "etf_daily": "sha256:etf-snapshot"
        }
        catalog.get_active_published.assert_called_once_with("etf-ready")
        catalog.list_latest_published.assert_not_called()
        mock_materialization.assert_not_called()


# ===========================================================================
# Test: 策略运行部分失败
# ===========================================================================


@pytest.mark.unit
class TestEodFlowStrategyPartialFailure:
    """策略运行部分失败时不应影响其他策略。"""

    def test_missing_publisher_marks_signal_publish_skipped(
        self,
        mocker: MockerFixture,
    ) -> None:
        """publisher 未配置时不阻断策略运行，但整体状态降级为 partial。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)
        mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value=_ready_etf_ingestion(),
        )
        mocker.patch(
            f"{EOD_MODULE}.daily_materialization_flow",
            return_value={
                "trade_date": "2026-04-15",
                "results": [],
                "summary": {"materialized_count": 2},
            },
        )

        from ditto_application.processes.execution.strategy_run_process import (
            StrategyRunResult,
        )
        from ditto_strategy.models import StrategySpecRecord

        spec = StrategySpecRecord(
            strategy_id="alpha_no_publisher",
            name="Alpha No Publisher",
            spec_json={"required_datasets": ["etf_daily"]},
            version=1,
        )
        mock_catalog = mocker.MagicMock()
        mock_catalog.get_active_published.return_value = spec
        mock_facade = mocker.MagicMock()
        mock_facade.run_strategy_for_date_from_catalog.return_value = StrategyRunResult(
            run_id="run-no-publisher",
            trade_date="2026-04-15",
            strategy_id="alpha_no_publisher",
            target=self._make_target_portfolio(
                "alpha_no_publisher",
                "run-no-publisher",
            ),
            mode=StrategyRunMode.RECOMMENDATION,
        )
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(
                mocker,
                catalog=mock_catalog,
                facade=mock_facade,
                signal_package_publisher=None,
            ),
        )

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(
            trade_date="2026-04-15",
            strategy_id="alpha_no_publisher",
            account_id="paper",
        )

        assert result["overall_status"] == "partial"
        assert result["strategies"][0]["strategy_id"] == "alpha_no_publisher"
        assert result["strategies"][0]["status"] == "failed"
        assert result["strategies"][0]["reason"] == "SIGNAL_PACKAGE_PUBLISH_FAILED"

    def test_strategy_failure_does_not_block_others(
        self,
        mocker: MockerFixture,
    ) -> None:
        """单个策略失败不影响其他策略运行。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)

        mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value=_ready_etf_ingestion(),
        )
        mocker.patch(
            f"{EOD_MODULE}.daily_materialization_flow",
            return_value={
                "trade_date": "2026-04-15",
                "results": [],
                "summary": {"materialized_count": 2},
            },
        )

        from ditto_strategy.models import StrategySpecRecord

        spec = StrategySpecRecord(
            strategy_id="alpha_bad",
            name="Alpha Bad",
            spec_json={"required_datasets": ["etf_daily"]},
            version=1,
        )

        mock_catalog = mocker.MagicMock()
        mock_catalog.get_active_published.return_value = spec

        mock_facade = mocker.MagicMock()
        mock_facade.run_strategy_for_date_from_catalog.side_effect = RuntimeError(
            "策略计算失败"
        )

        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(
                mocker, catalog=mock_catalog, facade=mock_facade
            ),
        )

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(
            trade_date="2026-04-15",
            strategy_id="alpha_bad",
            account_id="paper",
        )

        # 整体应为 partial
        assert result["overall_status"] == "partial"
        assert len(result["strategies"]) == 1
        assert result["strategies"][0]["strategy_id"] == "alpha_bad"
        assert result["strategies"][0]["status"] == "failed"
        assert result["strategies"][0]["error"] == "STRATEGY_EXECUTION_FAILED"

        assert mock_facade.run_strategy_for_date_from_catalog.call_count == 1

    def test_publish_failure_does_not_block_other_strategies(
        self,
        mocker: MockerFixture,
    ) -> None:
        """单个策略 publish 失败时其他策略仍可发布成功。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=True)
        mocker.patch(
            f"{EOD_MODULE}.daily_ingestion_flow",
            return_value=_ready_etf_ingestion(),
        )
        mocker.patch(
            f"{EOD_MODULE}.daily_materialization_flow",
            return_value={
                "trade_date": "2026-04-15",
                "results": [],
                "summary": {"materialized_count": 2},
            },
        )

        from ditto_application.processes.execution.strategy_run_process import (
            StrategyRunResult,
        )
        from ditto_strategy.models import StrategySpecRecord

        spec_bad = StrategySpecRecord(
            strategy_id="alpha_bad_publish",
            name="Alpha Bad Publish",
            spec_json={"required_datasets": ["etf_daily"]},
            version=1,
        )
        target_bad = self._make_target_portfolio("alpha_bad_publish", "run-bad")
        mock_catalog = mocker.MagicMock()
        mock_catalog.get_active_published.return_value = spec_bad
        mock_facade = mocker.MagicMock()
        mock_facade.run_strategy_for_date_from_catalog.return_value = StrategyRunResult(
            run_id="run-bad",
            trade_date="2026-04-15",
            strategy_id="alpha_bad_publish",
            target=target_bad,
            mode=StrategyRunMode.RECOMMENDATION,
        )
        mock_publisher = mocker.MagicMock()
        mock_publisher.publish.side_effect = RuntimeError("intent store unavailable")
        run_service = mocker.MagicMock()
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(
                mocker,
                catalog=mock_catalog,
                facade=mock_facade,
                run_service=run_service,
                signal_package_publisher=mock_publisher,
            ),
        )

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(
            trade_date="2026-04-15",
            strategy_id="alpha_bad_publish",
            account_id="paper",
        )

        assert result["overall_status"] == "partial"
        assert result["strategies"][0]["strategy_id"] == "alpha_bad_publish"
        assert result["strategies"][0]["status"] == "failed"
        assert result["strategies"][0]["error"] == "SIGNAL_PACKAGE_PUBLISH_FAILED"
        assert len(result["strategies"]) == 1
        assert mock_publisher.publish.call_count == 1
        batch_key = "eod-2026-04-15-alpha_bad_publish-1"
        run_service.mark_running.assert_called_once_with(batch_key)
        run_service.mark_completed.assert_not_called()
        run_service.mark_failed.assert_called_once_with(
            batch_key,
            "failed:SIGNAL_PACKAGE_PUBLISH_FAILED",
        )

    @staticmethod
    def _make_target_portfolio(
        strategy_id: str = "test",
        run_id: str = "run-001",
    ) -> Any:
        """构造 TargetPortfolio 实例。"""
        from ditto_strategy.alpha.models import TargetPortfolio

        return TargetPortfolio(
            trade_date="2026-04-15",
            strategy_id=strategy_id,
            run_id=run_id,
            positions={},
            cash_target=1.0,
        )


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
            return_value=_ready_etf_ingestion(),
        )

        # 物化抛出异常
        mock_materialization = mocker.patch(f"{EOD_MODULE}.daily_materialization_flow")
        mock_materialization.side_effect = RuntimeError("物化服务不可用")

        # 模拟已发布策略
        from ditto_strategy.models import StrategySpecRecord

        spec = StrategySpecRecord(
            strategy_id="alpha_test",
            name="Alpha Test",
            spec_json={"required_datasets": ["etf_daily"]},
            version=1,
        )

        mock_catalog = mocker.MagicMock()
        mock_catalog.get_active_published.return_value = spec

        mock_facade = mocker.MagicMock()
        from ditto_application.processes.execution.strategy_run_process import (
            StrategyRunResult,
        )
        from ditto_strategy.alpha.models import TargetPortfolio

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
            mode=StrategyRunMode.RESEARCH,
        )
        mock_publisher = mocker.MagicMock()
        mock_publisher.publish.return_value = mocker.Mock(
            outcome="no_rebalance",
            intents=(),
            checksum="sha256:no-rebalance",
            artifact_id="signal-package-alpha-test",
        )

        # 策略 bundle mock
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(
                mocker,
                catalog=mock_catalog,
                facade=mock_facade,
                signal_package_publisher=mock_publisher,
            ),
        )

        # AlertManager 仍通过 make_app_container 获取
        mock_alert_manager = mocker.MagicMock()
        mock_alert_manager.send_alert.return_value = {"email": True}
        mock_container = mocker.MagicMock()
        mock_container.close = mocker.Mock()
        mock_container.get.return_value = mock_alert_manager
        mocker.patch(f"{EOD_MODULE}.make_app_container", return_value=mock_container)

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(
            trade_date="2026-04-15",
            strategy_id="alpha_test",
            account_id="paper",
        )

        # 策略应成功运行
        assert len(result["strategies"]) == 1
        assert result["strategies"][0]["status"] == "no_rebalance"

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
        mock_catalog.get_active_published.return_value = None
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(mocker, catalog=mock_catalog),
        )

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(
            trade_date="2026-04-15",
            strategy_id="missing-strategy",
            account_id="paper",
        )

        assert "date" in result
        assert "skipped" in result
        assert "overall_status" in result
        assert "ingestion" in result
        assert "materialization" in result
        assert "strategies" in result

    def test_return_value_keys_on_skip(self, mocker: MockerFixture) -> None:
        """跳过时应包含所有必要键。"""
        mocker.patch(f"{EOD_MODULE}.check_trading_day", return_value=False)

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(
            trade_date="2026-01-01",
            strategy_id="alpha",
            account_id="paper",
        )

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
        mock_catalog.get_active_published.return_value = None
        mocker.patch(
            f"{EOD_MODULE}.create_strategy_bundle",
            return_value=_mock_strategy_bundle(mocker, catalog=mock_catalog),
        )

        from ditto_apps.jobs.flows.eod import eod_flow

        runner = _prefect_runner(eod_flow)
        result = runner(
            trade_date="2026-04-15",
            strategy_id="missing-strategy",
            account_id="paper",
        )

        assert result["overall_status"] == "partial"
        assert result["strategies"][0]["reason"] == "NO_ACTIVE_STRATEGY"
