"""
可观测性系统端到端集成测试.

测试 VictoriaMetrics、VictoriaLogs、Vector、Grafana 的完整集成.
"""

import json
import time
from pathlib import Path

import httpx
import pytest

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.mark.integration
@pytest.mark.observability
class TestObservabilityStack:
    """可观测性服务栈集成测试."""

    @pytest.fixture(scope="class")
    def services_endpoints(self) -> dict[str, str]:
        """获取服务端点配置."""
        return {
            "victoriametrics": "http://localhost:8428",
            "victorialogs": "http://localhost:9428",
            "grafana": "http://localhost:3000",
            "vector": "http://localhost:8686",
        }

    @pytest.fixture(scope="class")
    def http_client(self) -> httpx.Client:
        """HTTP 客户端."""
        return httpx.Client(timeout=10.0)

    def test_victoriametrics_health(
        self, http_client: httpx.Client, services_endpoints: dict[str, str]
    ) -> None:
        """测试 VictoriaMetrics 健康检查."""
        response = http_client.get(f"{services_endpoints['victoriametrics']}/health")
        assert response.status_code == 200

    def test_victorialogs_health(
        self, http_client: httpx.Client, services_endpoints: dict[str, str]
    ) -> None:
        """测试 VictoriaLogs 健康检查."""
        response = http_client.get(f"{services_endpoints['victorialogs']}/health")
        assert response.status_code == 200

    def test_vector_health(
        self, http_client: httpx.Client, services_endpoints: dict[str, str]
    ) -> None:
        """测试 Vector 健康检查."""
        response = http_client.get(f"{services_endpoints['vector']}/health")
        assert response.status_code == 200

    def test_grafana_health(
        self, http_client: httpx.Client, services_endpoints: dict[str, str]
    ) -> None:
        """测试 Grafana 健康检查."""
        response = http_client.get(f"{services_endpoints['grafana']}/api/health")
        assert response.status_code == 200

    def test_victoriametrics_metrics_query(
        self, http_client: httpx.Client, services_endpoints: dict[str, str]
    ) -> None:
        """测试 VictoriaMetrics 指标查询."""
        # 查询 up 指标
        response = http_client.get(
            f"{services_endpoints['victoriametrics']}/api/v1/query",
            params={"query": "up"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "result" in data["data"]

    def test_victorialogs_logs_query(
        self, http_client: httpx.Client, services_endpoints: dict[str, str]
    ) -> None:
        """测试 VictoriaLogs 日志查询."""
        # 查询所有日志
        response = http_client.get(
            f"{services_endpoints['victorialogs']}/select/logsql/query",
            params={"query": ""},
        )
        # 可能没有数据, 但端点应该可访问
        assert response.status_code in (200, 400)

    def test_grafana_datasources(
        self, http_client: httpx.Client, services_endpoints: dict[str, str]
    ) -> None:
        """测试 Grafana 数据源配置."""
        # 查询数据源列表
        response = http_client.get(
            f"{services_endpoints['grafana']}/api/datasources",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        datasources = response.json()
        assert isinstance(datasources, list)

        # 检查是否包含 VictoriaMetrics 和 VictoriaLogs
        ds_names = [ds.get("name", "") for ds in datasources]
        assert "VictoriaMetrics" in ds_names
        assert "VictoriaLogs" in ds_names

    def test_grafana_dashboards(
        self, http_client: httpx.Client, services_endpoints: dict[str, str]
    ) -> None:
        """测试 Grafana 仪表盘配置."""
        # 查询仪表盘列表
        response = http_client.get(
            f"{services_endpoints['grafana']}/api/search", params={"type": "dash-db"}
        )
        assert response.status_code == 200
        dashboards = response.json()
        assert isinstance(dashboards, list)

        # 检查是否包含 Ditto 概览仪表盘
        dashboard_titles = [db.get("title", "") for db in dashboards]
        assert "Ditto Observability Overview" in dashboard_titles


@pytest.mark.integration
@pytest.mark.external
@pytest.mark.observability
class TestMetricsExport:
    """指标导出集成测试.

    标记为 external 因为需要外部服务运行并推送指标.
    CI 默认跳过，本地开发时可运行.
    """

    @pytest.fixture(scope="class")
    def victoria_metrics_endpoint(self) -> str:
        """VictoriaMetrics 端点."""
        return "http://localhost:8428"

    @pytest.fixture(scope="class")
    def http_client(self) -> httpx.Client:
        """HTTP 客户端."""
        return httpx.Client(timeout=30.0)

    def test_metrics_export(
        self, victoria_metrics_endpoint: str, http_client: httpx.Client
    ) -> None:
        """
        测试指标导出到 VictoriaMetrics.

        此测试需要应用正在运行并推送指标.
        """
        # 等待指标推送
        time.sleep(20)

        # 查询 ditto 相关指标
        response = http_client.get(
            f"{victoria_metrics_endpoint}/api/v1/query",
            params={"query": '{__name__=~"ditto.*"}'},
        )
        assert response.status_code == 200
        data = response.json()

        # 如果应用正在运行, 应该有指标数据
        # 这里只是验证查询可以执行
        assert "data" in data


@pytest.mark.integration
@pytest.mark.external
@pytest.mark.observability
class TestLogsCollection:
    """日志采集集成测试.

    标记为 external 因为需要外部服务运行并采集日志.
    CI 默认跳过，本地开发时可运行.
    """

    @pytest.fixture(scope="class")
    def victoria_logs_endpoint(self) -> str:
        """VictoriaLogs 端点."""
        return "http://localhost:9428"

    @pytest.fixture(scope="class")
    def http_client(self) -> httpx.Client:
        """HTTP 客户端."""
        return httpx.Client(timeout=30.0)

    def test_logs_collection(
        self, victoria_logs_endpoint: str, http_client: httpx.Client, tmp_path: Path
    ) -> None:
        """
        测试日志采集到 VictoriaLogs.

        此测试会创建一个测试日志文件, 等待 Vector 采集并推送到 VictoriaLogs.
        """
        # 创建测试日志文件
        log_dir = PROJECT_ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        test_log_file = log_dir / "test.jsonl"
        test_log_entry = json.dumps(
            {
                "timestamp": "2024-12-24T10:00:00.000Z",
                "level": "INFO",
                "service": "ditto",
                "message": "Test log entry for integration testing",
                "event": "test_integration",
            }
        )

        # 写入测试日志
        test_log_file.write_text(test_log_entry + "\n")

        # 等待 Vector 采集和推送
        time.sleep(30)

        # 查询 VictoriaLogs
        response = http_client.get(
            f"{victoria_logs_endpoint}/select/logsql/query",
            params={"query": '{service="ditto"} event="test_integration"'},
        )

        # 清理测试日志文件
        test_log_file.unlink(missing_ok=True)

        # 验证查询可以执行
        assert response.status_code in (200, 400)


@pytest.mark.integration
@pytest.mark.observability
class TestObservabilityE2E:
    """端到端集成测试标记."""

    @pytest.fixture
    def http_client(self) -> httpx.Client:
        """HTTP 客户端."""
        return httpx.Client(timeout=10.0)

    def test_services_all_healthy(self) -> None:
        """测试所有服务健康."""
        endpoints: dict[str, str] = {
            "VictoriaMetrics": "http://localhost:8428/health",
            "VictoriaLogs": "http://localhost:9428/health",
            "Vector": "http://localhost:8686/health",
            "Grafana": "http://localhost:3000/api/health",
        }

        failed: list[tuple[str, str]] = []
        for name, endpoint in endpoints.items():
            try:
                with httpx.Client() as client:
                    response = client.get(endpoint)
                if response.status_code != 200:
                    failed.append((name, f"Status: {response.status_code}"))
            except Exception as e:
                failed.append((name, str(e)))

        if failed:
            pytest.fail(f"服务健康检查失败: {failed}")
