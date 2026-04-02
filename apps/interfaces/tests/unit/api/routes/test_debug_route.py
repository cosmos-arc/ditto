"""测试调试路由条件注册."""

import pytest
from ditto_infra.foundation.config.environment import get_environment
from ditto_interfaces.main import app


class TestDebugRouteConditionallyRegistered:
    """测试调试路由的条件注册逻辑."""

    def test_debug_route_registration_matches_environment(self):
        """调试路由注册状态与环境匹配."""
        env = get_environment()
        routes = [route.path for route in app.routes]
        debug_route_exists = "/api/v1/logs/test" in routes

        if env.is_production:
            assert not debug_route_exists, "生产环境不应注册调试路由"
        else:
            assert debug_route_exists, "非生产环境应注册调试路由"

    def test_debug_route_path_exists_in_dev(self):
        """非生产环境检查路由路径."""
        env = get_environment()
        if env.is_production:
            pytest.skip("生产环境跳过此测试")

        routes = [route.path for route in app.routes]
        assert "/api/v1/logs/test" in routes

    @pytest.mark.asyncio
    async def test_debug_route_returns_test_logs_in_dev(self):
        """非生产环境调用 /logs/test 返回正常."""
        env = get_environment()
        if env.is_production:
            pytest.skip("生产环境跳过此测试")

        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/logs/test")

            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Test logs generated"
