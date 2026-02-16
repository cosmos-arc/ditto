"""部署脚本单元测试."""

import pytest
from ditto_port.jobs.flows.deploy import (
    FlowDeploymentConfig,
    _get_flow,
    _get_flow_configs,
    deploy_all_flows,
    list_flows,
)
from pytest_mock import MockerFixture


@pytest.mark.unit
class TestGetFlow:
    """测试 _get_flow 函数."""

    def test_get_flow_returns_known_flow(self):
        """测试获取已知的 flow。"""
        # Note: 在单元测试中，@flow decorator 被 mock，返回原始函数
        flow = _get_flow("daily_ingestion_flow")
        assert callable(flow)
        assert flow.__name__ == "daily_ingestion_flow"

    def test_get_flow_raises_for_unknown_flow(self):
        """测试获取未知 flow 时抛出异常。"""
        with pytest.raises(ValueError, match="Unknown flow"):
            _get_flow("unknown_flow")


@pytest.mark.unit
class TestGetFlowConfigs:
    """测试 _get_flow_configs 函数."""

    def test_get_flow_configs_returns_list(self):
        """测试返回配置列表。"""
        configs = _get_flow_configs()
        assert isinstance(configs, list)
        assert len(configs) == 5

    def test_get_flow_configs_contains_all_flows(self):
        """测试包含所有 flow 配置。"""
        configs = _get_flow_configs()
        deployment_names = [c.deployment_name for c in configs]
        expected = [
            "daily-ingestion-prod",
            "daily-repair-prod",
            "retry-failed-prod",
            "backfill-prod",
            "repair-holes-prod",
        ]
        assert deployment_names == expected

    def test_flow_config_structure(self):
        """测试 FlowDeploymentConfig 结构正确。"""
        configs = _get_flow_configs()
        config = configs[0]
        assert isinstance(config, FlowDeploymentConfig)
        assert callable(config.flow)
        assert isinstance(config.deployment_name, str)
        assert isinstance(config.description, str)
        assert isinstance(config.parameters, dict)
        assert isinstance(config.tags, list)


@pytest.mark.unit
class TestListFlows:
    """测试 list_flows 函数。"""

    # 注意：list_flows 依赖 flow.name 属性，但在单元测试中 @flow 被 mock
    # 因此这些测试需要使用真实 Flow 或 mock flow 对象

    def test_list_flows_returns_dict(self, mocker: MockerFixture):
        """测试返回 flow 名称到描述的映射。"""
        # Arrange - mock flow configs
        mock_get_configs = mocker.patch(
            "ditto_port.jobs.flows.deploy._get_flow_configs"
        )

        # 创建一个简单的对象来替代 Mock，让 name 属性正常工作
        class SimpleFlow:
            name = "test_flow"
            __name__ = "test_flow"

        mock_flow = SimpleFlow()

        mock_config = mocker.Mock()
        mock_config.flow = mock_flow
        mock_config.description = "Test description"
        mock_get_configs.return_value = [mock_config]

        # Act
        flows = list_flows()

        # Assert
        assert isinstance(flows, dict)
        assert "test_flow" in flows

    def test_list_flows_has_descriptions(self, mocker: MockerFixture):
        """测试每个 flow 都有描述。"""
        # Arrange
        mock_get_configs = mocker.patch(
            "ditto_port.jobs.flows.deploy._get_flow_configs"
        )

        # 创建一个简单的对象来替代 Mock，让 name 属性正常工作
        class SimpleFlow:
            name = "test_flow"
            __name__ = "test_flow"

        mock_flow = SimpleFlow()

        mock_config = mocker.Mock()
        mock_config.flow = mock_flow
        mock_config.description = "Test description"
        mock_get_configs.return_value = [mock_config]

        # Act
        flows = list_flows()

        # Assert
        assert flows["test_flow"] == "Test description"


@pytest.mark.unit
class TestDeployAllFlows:
    """测试 deploy_all_flows 函数。"""

    def test_deploy_all_flows_calls_deploy(self, mocker: MockerFixture):
        """测试调用 prefect.deploy。"""
        # Arrange - mock flow configs with callable flows
        mock_deploy = mocker.patch("ditto_port.jobs.flows.deploy.deploy")
        mock_get_configs = mocker.patch(
            "ditto_port.jobs.flows.deploy._get_flow_configs"
        )
        mock_flow = mocker.Mock()
        mock_deployment = mocker.Mock()
        mock_flow.to_deployment.return_value = mock_deployment

        mock_config = mocker.Mock()
        mock_config.flow.return_value = mock_flow
        mock_config.deployment_name = "test-deployment"
        mock_config.description = "Test description"
        mock_config.tags = ["test"]
        mock_config.parameters = {}

        mock_get_configs.return_value = [mock_config]

        # Act
        deploy_all_flows(work_pool_name="test-pool")

        # Assert
        mock_deploy.assert_called_once()
        call_args = mock_deploy.call_args
        assert call_args.kwargs["work_pool_name"] == "test-pool"

    def test_deploy_all_flows_with_image(self, mocker: MockerFixture):
        """测试使用自定义镜像。"""
        # Arrange
        mock_deploy = mocker.patch("ditto_port.jobs.flows.deploy.deploy")
        mock_get_configs = mocker.patch(
            "ditto_port.jobs.flows.deploy._get_flow_configs"
        )
        mock_flow = mocker.Mock()
        mock_deployment = mocker.Mock()
        mock_flow.to_deployment.return_value = mock_deployment

        mock_config = mocker.Mock()
        mock_config.flow.return_value = mock_flow
        mock_get_configs.return_value = [mock_config]

        # Act
        deploy_all_flows(work_pool_name="test-pool", image="test-image:latest")

        # Assert
        call_args = mock_deploy.call_args
        assert call_args.kwargs["image"] == "test-image:latest"

    def test_deploy_all_flows_with_push(self, mocker: MockerFixture):
        """测试 push 参数。"""
        # Arrange
        mock_deploy = mocker.patch("ditto_port.jobs.flows.deploy.deploy")
        mock_get_configs = mocker.patch(
            "ditto_port.jobs.flows.deploy._get_flow_configs"
        )
        mock_flow = mocker.Mock()
        mock_deployment = mocker.Mock()
        mock_flow.to_deployment.return_value = mock_deployment

        mock_config = mocker.Mock()
        mock_config.flow.return_value = mock_flow
        mock_get_configs.return_value = [mock_config]

        # Act
        deploy_all_flows(work_pool_name="test-pool", push=True)

        # Assert
        call_args = mock_deploy.call_args
        assert call_args.kwargs["push"] is True


@pytest.mark.unit
class TestMain:
    """测试 main 函数。"""

    def test_main_list_command(self, mocker: MockerFixture):
        """测试 list 命令。"""
        # Arrange
        import sys

        original_argv = sys.argv
        sys.argv = ["deploy", "list"]
        mock_list_flows = mocker.patch("ditto_port.jobs.flows.deploy.list_flows")
        mocker.patch("ditto_port.jobs.flows.deploy.logger")
        mock_list_flows.return_value = {
            "flow1": "description1",
            "flow2": "description2",
        }

        try:
            # Act
            from ditto_port.jobs.flows import deploy

            deploy.main()
        finally:
            sys.argv = original_argv

        # Assert
        mock_list_flows.assert_called_once()

    def test_main_deploy_command(self, mocker: MockerFixture):
        """测试默认部署命令。"""
        # Arrange
        import sys

        original_argv = sys.argv
        sys.argv = ["deploy"]
        mock_deploy = mocker.patch("ditto_port.jobs.flows.deploy.deploy_all_flows")

        try:
            # Act
            from ditto_port.jobs.flows import deploy

            deploy.main()
        finally:
            sys.argv = original_argv

        # Assert
        mock_deploy.assert_called_once()


@pytest.mark.unit
class TestFlowDeploymentContracts:
    """Flow 部署参数契约测试."""

    def test_backfill_uses_config_not_backfill_config(self) -> None:
        """backfill_flow 参数名应为 config，而非 backfill_config."""
        configs = _get_flow_configs()

        backfill_config = next(
            (c for c in configs if c.deployment_name == "backfill-prod"),
            None,
        )
        assert backfill_config is not None

        # 参数名必须是 "config"，匹配 backfill_flow 签名
        assert "config" in backfill_config.parameters
        assert "backfill_config" not in backfill_config.parameters
