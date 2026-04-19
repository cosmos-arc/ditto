"""dq_batch_check 任务单元测试."""

from unittest.mock import MagicMock

import pytest
from ditto_app.process.quality.types import L3CheckResult
from pytest_mock import MockerFixture


def _prefect_runner(entrypoint):
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))


def _mock_container(
    mocker: MockerFixture,
    *,
    l3_service: MagicMock | None = None,
    metadata_service: MagicMock | None = None,
    market_service: MagicMock | None = None,
) -> MagicMock:
    """创建 mock container，按类型返回对应 mock 对象."""
    container = mocker.MagicMock()

    def _get_side_effect(cls):
        if cls.__name__ == "QualityPatrolService":
            return l3_service
        if cls.__name__ == "MetadataQueryFacade":
            return metadata_service
        if cls.__name__ == "MarketQueryFacade":
            return market_service
        return MagicMock()

    container.get.side_effect = _get_side_effect
    return container


@pytest.mark.unit
class TestDqBatchCheckKnownErrorHandling:
    """测试已知异常被正确记录到 results_by_dataset."""

    @pytest.mark.asyncio
    async def test_known_error_records_failure_in_results(
        self,
        mocker: MockerFixture,
    ) -> None:
        """
        已知异常(ValueError, TypeError, KeyError, AttributeError)
        应该被记录到 results_by_dataset 中，而不是仅记录日志.

        这是 ENG-003 的修复测试：防止批处理结果"假通过/漏报"。
        """
        # Arrange: Mock 所有依赖
        mock_metadata_service = MagicMock()
        mock_metadata_service.get_last_trading_day.return_value = "2024-01-15"

        mock_l3_service = MagicMock()
        mock_l3_service.check_dataset.side_effect = ValueError("数据格式错误")

        container = _mock_container(
            mocker,
            l3_service=mock_l3_service,
            metadata_service=mock_metadata_service,
        )

        mock_context = mocker.MagicMock()
        mock_context.__enter__.return_value = container
        mock_context.__exit__.return_value = None

        mocker.patch(
            "ditto_interfaces.jobs.tasks.dq_batch.create_prefect_host",
            return_value=mock_context,
        )
        mocker.patch(
            "ditto_interfaces.jobs.tasks.dq_batch._send_dq_alert",
            return_value=None,
        )

        from ditto_interfaces.jobs.tasks.dq_batch import dq_batch_check

        runner = _prefect_runner(dq_batch_check)

        # Act: 执行批处理任务
        result = await runner(
            trade_date="2024-01-15",
            datasets=["stock_daily"],
        )

        # Assert: 验证结果结构
        assert "results_by_dataset" in result
        assert "stock_daily" in result["results_by_dataset"]

        dataset_result = result["results_by_dataset"]["stock_daily"]
        # 关键断言：已知异常也应该被记录为失败
        assert dataset_result["passed"] is False
        assert "error" in dataset_result
        assert "ValueError" in dataset_result["error"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("exception_class", "exception_msg"),
        [
            (ValueError, "值错误"),
            (TypeError, "类型错误"),
            (KeyError, "missing_key"),
            (AttributeError, "属性不存在"),
        ],
    )
    async def test_all_known_errors_recorded(
        self,
        mocker: MockerFixture,
        exception_class: type,
        exception_msg: str,
    ) -> None:
        """
        验证所有已知异常类型都被正确记录.

        Args:
            exception_class: 异常类型
            exception_msg: 异常消息
        """
        # Arrange
        mock_metadata_service = MagicMock()
        mock_metadata_service.get_last_trading_day.return_value = "2024-01-15"

        mock_l3_service = MagicMock()
        mock_l3_service.check_dataset.side_effect = exception_class(exception_msg)

        container = _mock_container(
            mocker,
            l3_service=mock_l3_service,
            metadata_service=mock_metadata_service,
        )

        mock_context = mocker.MagicMock()
        mock_context.__enter__.return_value = container
        mock_context.__exit__.return_value = None

        mocker.patch(
            "ditto_interfaces.jobs.tasks.dq_batch.create_prefect_host",
            return_value=mock_context,
        )
        mocker.patch(
            "ditto_interfaces.jobs.tasks.dq_batch._send_dq_alert",
            return_value=None,
        )

        from ditto_interfaces.jobs.tasks.dq_batch import dq_batch_check

        runner = _prefect_runner(dq_batch_check)

        # Act
        result = await runner(
            trade_date="2024-01-15",
            datasets=["etf_daily"],
        )

        # Assert
        assert "etf_daily" in result["results_by_dataset"]
        dataset_result = result["results_by_dataset"]["etf_daily"]
        assert dataset_result["passed"] is False
        assert "error" in dataset_result

    @pytest.mark.asyncio
    async def test_unknown_error_also_recorded(
        self,
        mocker: MockerFixture,
    ) -> None:
        """
        未知异常也应该被正确记录.

        这是现有行为，确保修复后不影响未知异常的处理。
        """
        # Arrange
        mock_metadata_service = MagicMock()
        mock_metadata_service.get_last_trading_day.return_value = "2024-01-15"

        mock_l3_service = MagicMock()
        mock_l3_service.check_dataset.side_effect = RuntimeError("未知运行时错误")

        container = _mock_container(
            mocker,
            l3_service=mock_l3_service,
            metadata_service=mock_metadata_service,
        )

        mock_context = mocker.MagicMock()
        mock_context.__enter__.return_value = container
        mock_context.__exit__.return_value = None

        mocker.patch(
            "ditto_interfaces.jobs.tasks.dq_batch.create_prefect_host",
            return_value=mock_context,
        )
        mocker.patch(
            "ditto_interfaces.jobs.tasks.dq_batch._send_dq_alert",
            return_value=None,
        )

        from ditto_interfaces.jobs.tasks.dq_batch import dq_batch_check

        runner = _prefect_runner(dq_batch_check)

        # Act
        result = await runner(
            trade_date="2024-01-15",
            datasets=["index_daily"],
        )

        # Assert
        assert "index_daily" in result["results_by_dataset"]
        dataset_result = result["results_by_dataset"]["index_daily"]
        assert dataset_result["passed"] is False
        assert "error" in dataset_result
        assert "RuntimeError" in dataset_result["error"]

    @pytest.mark.asyncio
    async def test_mixed_results_with_some_failures(
        self,
        mocker: MockerFixture,
    ) -> None:
        """
        混合场景：部分数据集成功，部分因已知异常失败.

        验证：
        1. 成功的数据集正常记录
        2. 失败的数据集（已知异常）也正确记录
        """
        # Arrange
        mock_metadata_service = MagicMock()
        mock_metadata_service.get_last_trading_day.return_value = "2024-01-15"

        # 第一个成功，第二个失败
        mock_l3_service = MagicMock()
        mock_l3_service.check_dataset.side_effect = [
            L3CheckResult(
                dataset="stock_daily",
                trade_date="2024-01-15",
                passed=True,
                issue_count=0,
            ),
            ValueError("第二个数据集失败"),
        ]

        container = _mock_container(
            mocker,
            l3_service=mock_l3_service,
            metadata_service=mock_metadata_service,
        )

        mock_context = mocker.MagicMock()
        mock_context.__enter__.return_value = container
        mock_context.__exit__.return_value = None

        mocker.patch(
            "ditto_interfaces.jobs.tasks.dq_batch.create_prefect_host",
            return_value=mock_context,
        )
        mocker.patch(
            "ditto_interfaces.jobs.tasks.dq_batch._send_dq_alert",
            return_value=None,
        )

        from ditto_interfaces.jobs.tasks.dq_batch import dq_batch_check

        runner = _prefect_runner(dq_batch_check)

        # Act
        result = await runner(
            trade_date="2024-01-15",
            datasets=["stock_daily", "etf_daily"],
        )

        # Assert
        assert len(result["results_by_dataset"]) == 2

        # 第一个成功
        assert result["results_by_dataset"]["stock_daily"]["passed"] is True

        # 第二个失败
        assert result["results_by_dataset"]["etf_daily"]["passed"] is False
        assert "error" in result["results_by_dataset"]["etf_daily"]
