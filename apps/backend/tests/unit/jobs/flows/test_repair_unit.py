"""Sparse PIT recovery flow adapter tests."""

from __future__ import annotations

from typing import Any

import pytest
from ditto_application.processes.ingestion.sparse_recovery_models import (
    SparsePITComponentRecoveryResult,
    SparsePITReattestationRequest,
    SparsePITReattestationResult,
)
from pytest_mock import MockerFixture


def _prefect_runner(entrypoint: Any) -> Any:
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))


def test_sparse_pit_runner_delegates_to_application_process(
    mocker: MockerFixture,
) -> None:
    from ditto_apps.jobs.flows import repair as repair_module

    application_result = SparsePITReattestationResult(
        dataset="balance_sheet",
        source="tushare",
        signal_date="2026-07-16",
        passed=True,
        component_dates=("2026-06-30",),
        components=(
            SparsePITComponentRecoveryResult(
                trade_date="2026-06-30",
                passed=True,
                checksum="sha256:component",
                row_count=12,
            ),
        ),
        source_snapshot_id="snapshot:tushare:balance_sheet:aggregate",
        source_snapshot_ids=("snapshot:tushare:balance_sheet:2026-06-30",),
        row_count=12,
    )
    bundle = mocker.MagicMock()
    bundle.sparse_pit_reattestation.run.return_value = application_result
    context = mocker.MagicMock()
    context.__enter__.return_value = bundle
    context.__exit__.return_value = None
    create_bundle = mocker.patch.object(
        repair_module,
        "create_ingestion_bundle",
        return_value=context,
    )

    result = repair_module.run_sparse_pit_reattestation(
        dataset="balance_sheet",
        signal_date="2026-07-16",
        source="tushare",
    )

    create_bundle.assert_called_once_with(source="tushare")
    bundle.sparse_pit_reattestation.run.assert_called_once_with(
        SparsePITReattestationRequest(
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-16",
        )
    )
    assert result == application_result.to_dict()


def test_sparse_pit_prefect_flow_uses_plain_runner(mocker: MockerFixture) -> None:
    from ditto_apps.jobs.flows import repair as repair_module

    runner = mocker.patch.object(
        repair_module,
        "run_sparse_pit_reattestation",
        return_value={"passed": True},
    )

    result = _prefect_runner(repair_module.sparse_pit_reattestation_flow)(
        dataset="balance_sheet",
        signal_date="2026-07-16",
        source="tushare",
    )

    assert result == {"passed": True}
    runner.assert_called_once_with(
        dataset="balance_sheet",
        signal_date="2026-07-16",
        source="tushare",
    )


def test_sparse_pit_prefect_flow_fails_when_evidence_does_not_pass(
    mocker: MockerFixture,
) -> None:
    from ditto_apps.jobs.flows import repair as repair_module

    mocker.patch.object(
        repair_module,
        "run_sparse_pit_reattestation",
        return_value={
            "passed": False,
            "error": "SPARSE_REATTEST_COMPONENT_FAILED",
        },
    )

    with pytest.raises(RuntimeError, match="SPARSE_REATTEST_COMPONENT_FAILED"):
        _prefect_runner(repair_module.sparse_pit_reattestation_flow)(
            dataset="balance_sheet",
            signal_date="2026-07-16",
            source="tushare",
        )


def _mock_bundle_context(mocker: MockerFixture, bundle: Any) -> None:
    from ditto_apps.jobs.flows import repair as repair_module

    context = mocker.MagicMock()
    context.__enter__.return_value = bundle
    context.__exit__.return_value = None
    mocker.patch.object(
        repair_module,
        "create_ingestion_bundle",
        return_value=context,
    )


@pytest.mark.unit
class TestDailyRepairCompensationSelection:
    """#623 补偿选择：按真实失败记录发现，禁全注册表每日回补。"""

    @staticmethod
    def _excluded_projection() -> list[dict[str, object]]:
        """RetryManager.compensation_selection 非瞬态投影的真实形状。"""
        return [
            {
                "dataset": "global_index_daily",
                "error_code": "UNKNOWN_ERROR",
                "kind": "permanent",
                "failure_count": 2,
                "oldest_trade_date": "2026-10-28",
                "newest_trade_date": "2026-10-29",
            },
            {
                "dataset": "hk_hold",
                "error_code": "EMPTY_DATA",
                "kind": "source_missing",
                "failure_count": 5,
                "oldest_trade_date": "2026-10-28",
                "newest_trade_date": "2026-10-29",
            },
        ]

    def test_default_discovers_transient_failures_only(
        self, mocker: MockerFixture
    ) -> None:
        """datasets=None：重试=瞬态失败数据集（发现），空洞=消费者关键白名单。"""
        from ditto_apps.jobs.flows import repair as repair_module

        bundle = mocker.MagicMock()
        bundle.retry_manager.compensation_selection.return_value = (
            ["cash_flow", "etf_nav"],
            self._excluded_projection(),
        )
        _mock_bundle_context(mocker, bundle)
        retry_flow = mocker.patch.object(
            repair_module,
            "retry_failed_flow",
            return_value={"retried_count": 0, "success_count": 0},
        )
        holes_flow = mocker.patch.object(
            repair_module,
            "repair_holes_flow",
            return_value={"repaired_count": 0},
        )

        result = _prefect_runner(repair_module.daily_repair_flow)()

        assert [c.kwargs["dataset"] for c in retry_flow.call_args_list] == [
            "cash_flow",
            "etf_nav",
        ]
        assert [c.kwargs["dataset"] for c in holes_flow.call_args_list] == list(
            repair_module.CONSUMER_CRITICAL_HOLE_DATASETS
        )
        summary = result["summary"]
        assert summary["retry_datasets"] == ["cash_flow", "etf_nav"]
        assert summary["holes_datasets"] == list(
            repair_module.CONSUMER_CRITICAL_HOLE_DATASETS
        )
        # 永久/源缺失失败保留原因与补偿范围（人工裁决可见）。
        excluded = summary["excluded_failure_groups"]
        assert [item["dataset"] for item in excluded] == [
            "global_index_daily",
            "hk_hold",
        ]
        assert excluded[0]["kind"] == "permanent"
        assert excluded[1]["kind"] == "source_missing"
        assert excluded[0]["failure_count"] == 2

    def test_default_without_transient_failures_only_scans_critical_holes(
        self, mocker: MockerFixture
    ) -> None:
        """无瞬态失败时不重试任何数据集（非瞬态不自动补偿）。"""
        from ditto_apps.jobs.flows import repair as repair_module

        bundle = mocker.MagicMock()
        bundle.retry_manager.compensation_selection.return_value = ([], [])
        _mock_bundle_context(mocker, bundle)
        retry_flow = mocker.patch.object(
            repair_module,
            "retry_failed_flow",
        )
        holes_flow = mocker.patch.object(
            repair_module,
            "repair_holes_flow",
            return_value={"repaired_count": 0},
        )

        result = _prefect_runner(repair_module.daily_repair_flow)()

        retry_flow.assert_not_called()
        assert len(holes_flow.call_args_list) == len(
            repair_module.CONSUMER_CRITICAL_HOLE_DATASETS
        )
        assert result["summary"]["retry_datasets"] == []

    def test_explicit_datasets_keep_retry_and_holes_on_same_list(
        self, mocker: MockerFixture
    ) -> None:
        """显式 datasets：维持既有手动语义（重试+空洞逐数据集）。"""
        from ditto_apps.jobs.flows import repair as repair_module

        _mock_bundle_context(mocker, mocker.MagicMock())
        retry_flow = mocker.patch.object(
            repair_module,
            "retry_failed_flow",
            return_value={"retried_count": 0, "success_count": 0},
        )
        holes_flow = mocker.patch.object(
            repair_module,
            "repair_holes_flow",
            return_value={"repaired_count": 0},
        )

        result = _prefect_runner(repair_module.daily_repair_flow)(
            datasets=["stock_daily"],
        )

        assert [c.kwargs["dataset"] for c in retry_flow.call_args_list] == [
            "stock_daily"
        ]
        assert [c.kwargs["dataset"] for c in holes_flow.call_args_list] == [
            "stock_daily"
        ]
        assert result["summary"]["retry_datasets"] == ["stock_daily"]
        assert result["summary"]["holes_datasets"] == ["stock_daily"]

    def test_discovered_stale_dataset_does_not_kill_repair(
        self, mocker: MockerFixture
    ) -> None:
        """correctness #623 F2：补偿发现含失效数据集名时逐项隔离。

        ingestion_log 驱动的发现可能返回已改名/移除/权限被撤的数据集；
        单个编排异常不得拖垮整晚修补——消费者关键数据集的空洞扫描
        仍须执行，错误留痕在结果里。
        """
        from ditto_apps.jobs.flows import repair as repair_module

        bundle = mocker.MagicMock()
        bundle.retry_manager.compensation_selection.return_value = (
            ["stale_dataset", "etf_nav"],
            [],
        )
        _mock_bundle_context(mocker, bundle)
        retry_flow = mocker.patch.object(
            repair_module,
            "retry_failed_flow",
            side_effect=[
                ValueError("unknown dataset: stale_dataset"),
                {"retried_count": 1, "success_count": 1},
            ],
        )
        holes_flow = mocker.patch.object(
            repair_module,
            "repair_holes_flow",
            return_value={"repaired_count": 0},
        )

        result = _prefect_runner(repair_module.daily_repair_flow)()

        # 失效数据集失败留痕，其余数据集与空洞扫描继续。
        assert "ValueError" in str(result["retry_result"]["stale_dataset"]["error"])
        assert result["retry_result"]["etf_nav"]["success_count"] == 1
        assert len(holes_flow.call_args_list) == len(
            repair_module.CONSUMER_CRITICAL_HOLE_DATASETS
        )
        assert retry_flow.call_count == 2
