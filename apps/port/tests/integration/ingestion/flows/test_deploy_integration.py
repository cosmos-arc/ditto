"""Tests for deploy script (Prefect 3.x)."""

# 测试文件允许函数内导入

import pytest


@pytest.mark.integration
class TestDeployFunctions:
    """Tests for deploy module functions."""

    def test_list_flows(self):
        """Test that list_flows returns all available flows."""
        from ditto_port.jobs.flows.deploy import _get_flow_configs, list_flows

        flows = list_flows()

        # list_flows 应该返回所有配置的 flows
        configs = _get_flow_configs()
        assert len(flows) == len(configs)

        # 每个 flow 都应该有描述
        for flow_name, description in flows.items():
            assert isinstance(flow_name, str)
            assert isinstance(description, str)
            assert len(description) > 0

    def test_deploy_all_flows_exists(self):
        """Test that deploy_all_flows function exists."""
        from ditto_port.jobs.flows.deploy import deploy_all_flows

        assert callable(deploy_all_flows)

    def test_deploy_creates_deployments(self, mocker):
        """Test that deploy creates Prefect deployments using Prefect 3.x API."""
        from ditto_port.jobs.flows.deploy import deploy_all_flows

        # Mock prefect.deploy 函数 (在导入时)
        mock_deploy = mocker.patch("prefect.deploy")
        deploy_all_flows(
            work_pool_name="test-pool",
            image="test-image:latest",
            push=False,
        )

        # 验证 deploy 被调用
        assert mock_deploy.called

    def test_get_flow_configs(self):
        """Test that _get_flow_configs returns correct configurations."""
        from ditto_port.jobs.flows.deploy import _get_flow_configs

        configs = _get_flow_configs()

        # 应该有 5 个 flow 配置 (移除了 dq_batch_check task)
        assert len(configs) == 5

        # 验证每个配置都有必需的字段
        for config in configs:
            assert hasattr(config, "flow")
            assert hasattr(config, "deployment_name")
            assert hasattr(config, "description")
            assert hasattr(config, "parameters")
            assert hasattr(config, "tags")
            assert callable(config.flow)
            assert isinstance(config.deployment_name, str)
            assert isinstance(config.description, str)
            assert isinstance(config.parameters, dict)
            assert isinstance(config.tags, list)

    def test_get_flow(self):
        """Test that _get_flow returns correct flow."""
        from ditto_port.jobs.flows.deploy import _get_flow

        # 测试获取有效的 flow
        # 注意: flow.name 是 Prefect 设置的，可能与内部名称不同
        flow = _get_flow("daily_ingestion_flow")
        assert flow is not None
        assert flow.name == "daily-ingestion"

        # 测试无效的 flow 名称
        with pytest.raises(ValueError, match="Unknown flow"):
            _get_flow("invalid_flow_name")


@pytest.mark.integration
class TestMainFunction:
    """Tests for main function."""

    def test_main_list_command(self, mocker):
        """Test that main with 'list' command lists flows."""
        from ditto_port.jobs.flows.deploy import main as deploy_main

        # Mock sys.argv 和 list_flows
        mocker.patch("sys.argv", ["deploy.py", "list"])
        mock_list = mocker.patch("ditto_port.jobs.flows.deploy.list_flows")

        deploy_main()

        # 应该调用 list_flows
        mock_list.assert_called_once()

    def test_main_default_deploys(self, mocker):
        """Test that main without arguments calls deploy_all_flows."""
        from ditto_port.jobs.flows.deploy import main as deploy_main

        # Mock sys.argv and deploy_all_flows
        mocker.patch("sys.argv", ["deploy.py"])
        mock_deploy = mocker.patch("ditto_port.jobs.flows.deploy.deploy_all_flows")

        deploy_main()

        # Should call deploy_all_flows
        mock_deploy.assert_called_once()
