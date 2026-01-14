"""Tests for deploy script."""

# 测试文件允许函数内导入

import pytest


@pytest.mark.integration
class TestDeployFunctions:
    """Tests for deploy module functions."""

    def test_list_flows(self):
        """Test that list_flows returns all available flows."""
        from ditto_port.jobs.flows.deploy import _DEPLOYMENT_CONFIGS, list_flows

        flows = list_flows()

        # list_flows 应该与 _DEPLOYMENT_CONFIGS 一致
        # 每个 flow_name 都应该有对应的部署配置
        for flow_name, _description in flows.items():
            # 找到对应的配置
            config_found = any(
                cfg.flow_name == flow_name
                or (cfg.is_task and cfg.flow_name == flow_name)
                for cfg in _DEPLOYMENT_CONFIGS
            )
            assert config_found, f"Flow '{flow_name}' 没有对应的部署配置"

        # 每个 _DEPLOYMENT_CONFIGS 中的 flow 都应该在 list_flows 中
        for config in _DEPLOYMENT_CONFIGS:
            assert config.flow_name in flows, (
                f"部署配置中的 flow '{config.flow_name}' 不在 list_flows 中"
            )

        # Should have descriptions
        for flow_name, description in flows.items():
            assert isinstance(flow_name, str)
            assert isinstance(description, str)
            assert len(description) > 0

    def test_deploy_all_flows_exists(self):
        """Test that deploy_all_flows function exists."""
        from ditto_port.jobs.flows.deploy import deploy_all_flows

        assert callable(deploy_all_flows)

    @pytest.mark.skip(
        reason="Prefect 3.x removed Deployment API. "
        "Needs update to new deployment mechanism.",
    )
    def test_deploy_creates_deployments(self):
        """Test that deploy creates Prefect deployments.

        Note: Prefect 3.x removed the Deployment API. This test needs to be
        updated to use the new flow.serve(), flow.deploy(), or prefect deploy CLI.
        """
        from ditto_port.jobs.flows.deploy import deploy_all_flows

        # TODO: Update to test Prefect 3.x deployment mechanism
        # For now, verify the function exists and is callable
        assert callable(deploy_all_flows)


@pytest.mark.integration
class TestMainFunction:
    """Tests for main function."""

    def test_main_list_command(self, mocker):
        """Test that main with 'list' command lists flows."""
        from ditto_port.jobs.flows.deploy import main as deploy_main

        # Mock sys.argv and print
        mocker.patch("sys.argv", ["deploy.py", "list"])
        mock_print = mocker.patch("builtins.print")

        deploy_main()

        # Should have printed flows
        assert mock_print.called

    def test_main_default_deploys(self, mocker):
        """Test that main without arguments deploys all flows."""
        from ditto_port.jobs.flows.deploy import main as deploy_main

        # Mock sys.argv and deploy_all_flows
        mocker.patch("sys.argv", ["deploy.py"])
        mock_deploy = mocker.patch("ditto_port.jobs.flows.deploy.deploy_all_flows")

        deploy_main()

        # Should call deploy_all_flows
        mock_deploy.assert_called_once()
