"""Tests for deploy script."""

# ruff: noqa: PLC0415  # 测试文件允许函数内导入

from unittest.mock import patch

import pytest


@pytest.mark.integration
class TestDeployFunctions:
    """Tests for deploy module functions."""

    def test_list_flows(self):
        """Test that list_flows returns all available flows."""
        from ditto_server.ingestion.flows.deploy import list_flows

        flows = list_flows()

        # Should contain all flows
        assert "daily_ingestion_flow" in flows
        assert "backfill_flow" in flows
        assert "retry_failed_flow" in flows
        assert "repair_holes_flow" in flows
        assert "daily_repair_flow" in flows

        # Should have descriptions
        for flow_name, description in flows.items():
            assert isinstance(flow_name, str)
            assert isinstance(description, str)
            assert len(description) > 0

    def test_deploy_all_flows_exists(self):
        """Test that deploy_all_flows function exists."""
        from ditto_server.ingestion.flows.deploy import deploy_all_flows

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
        from ditto_server.ingestion.flows.deploy import deploy_all_flows

        # TODO: Update to test Prefect 3.x deployment mechanism
        # For now, verify the function exists and is callable
        assert callable(deploy_all_flows)


@pytest.mark.integration
class TestMainFunction:
    """Tests for main function."""

    @patch("sys.argv", ["deploy.py", "list"])
    def test_main_list_command(self):
        """Test that main with 'list' command lists flows."""
        from ditto_server.ingestion.flows.deploy import main as deploy_main

        # Mock print
        with patch("builtins.print") as mock_print:
            deploy_main()

        # Should have printed flows
        assert mock_print.called

    @patch("ditto_server.ingestion.flows.deploy.deploy_all_flows")
    @patch("sys.argv", ["deploy.py"])
    def test_main_default_deploys(self, mock_deploy):
        """Test that main without arguments deploys all flows."""
        from ditto_server.ingestion.flows.deploy import main as deploy_main

        deploy_main()

        # Should call deploy_all_flows
        mock_deploy.assert_called_once()
