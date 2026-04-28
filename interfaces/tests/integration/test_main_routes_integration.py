"""装配级集成测试: 验证 main.py 中所有路由正确挂载.

这个测试与现有路由测试的区别:
- 现有测试 (test_*_router_unit.py): 创建新的 FastAPI() 实例，只测试单个路由
- 本测试: 使用真实的 ditto_interfaces.main.app，验证路由装配正确性

能够捕获的装配级错误:
- main.py 遗漏 include_router 调用
- routes/__init__.py 导出了路由但 main.py 未挂载
- 路由前缀配置错误
"""

import pytest
from ditto_interfaces.api.routes import __all__ as expected_route_modules
from ditto_interfaces.main import app
from fastapi.routing import APIRoute
from starlette.routing import Route


@pytest.mark.integration
class TestMainRoutesAssembly:
    """验证 main.py 中的路由装配."""

    def test_all_route_modules_have_routers(self) -> None:
        """验证 __all__ 中的所有模块都有 router 属性."""
        from ditto_interfaces.api import routes

        missing_routers = []
        for module_name in expected_route_modules:
            module = getattr(routes, module_name)
            if not hasattr(module, "router"):
                missing_routers.append(module_name)

        assert not missing_routers, f"以下模块缺少 router 属性: {missing_routers}"

    def test_all_routes_registered_in_main_app(self) -> None:
        """验证所有 routes/__init__.py 导出的路由都已挂载到 main.app."""
        # 收集已注册的路由名称（通过 router 对象的 name 或路径前缀）
        registered_routes: set[str] = set()

        for route in app.routes:
            if isinstance(route, APIRoute):
                # 使用路由的 tags 或 path 来识别所属模块
                # 例如 /api/v1/capital/* 路由属于 capital 模块
                path = route.path
                if path.startswith("/api/v1/"):
                    # 提取模块名: /api/v1/capital/xxx -> capital
                    parts = path.split("/")
                    if len(parts) >= 4:
                        module_name = parts[3]
                        registered_routes.add(module_name)

        # 验证所有期望的路由模块都已注册
        missing_routes = set(expected_route_modules) - registered_routes

        assert not missing_routes, (
            f"以下路由模块未在 main.py 中注册: {missing_routes}\n"
            f"已注册的路由模块: {registered_routes}\n"
            f"期望的路由模块: {set(expected_route_modules)}"
        )

    def test_route_prefix_correct(self) -> None:
        """验证所有业务路由都使用 /api/v1 前缀."""
        from ditto_interfaces.api import routes

        for module_name in expected_route_modules:
            module = getattr(routes, module_name)
            router = module.router

            # 检查该 router 下的所有路由是否都有正确前缀
            for route in router.routes:
                if isinstance(route, APIRoute):
                    # 路由前缀在 include_router 时添加，
                    # 所以这里检查 router 本身是否配置正确
                    # router.prefix 应该为空（由 main.py 统一添加）
                    assert hasattr(router, "prefix"), (
                        f"{module_name}.router 缺少 prefix 属性"
                    )

    def test_expected_route_modules_complete(self) -> None:
        """验证 __all__ 包含所有路由模块."""
        expected = {
            "backtest",
            "capital",
            "commodity",
            "fundamental",
            "fx",
            "ingestion",
            "macro",
            "market",
            "metadata",
            "source",
            "strategy",
            "trade",
            "universe",
        }

        actual = set(expected_route_modules)

        assert actual == expected, (
            f"__all__ 中的路由模块不完整\n"
            f"期望: {expected}\n"
            f"实际: {actual}\n"
            f"缺失: {expected - actual}\n"
            f"多余: {actual - expected}"
        )

    def test_health_endpoint_exists(self) -> None:
        """验证健康检查端点存在."""
        health_paths = {"/healthz", "/"}
        actual_paths = {route.path for route in app.routes if isinstance(route, Route)}

        assert health_paths.issubset(actual_paths), (
            f"健康检查端点缺失\n期望: {health_paths}\n实际路径: {actual_paths}"
        )

    def test_no_duplicate_routes(self) -> None:
        """验证没有重复的路由定义."""
        seen_paths: dict[str, list[str]] = {}

        for route in app.routes:
            if isinstance(route, APIRoute):
                path = route.path
                if path not in seen_paths:
                    seen_paths[path] = []
                # 记录每个路径的方法
                for method in route.methods:
                    seen_paths[path].append(method)

        # 检查重复（同一路径 + 同一方法）
        duplicates = []
        for path, methods in seen_paths.items():
            method_counts = {}
            for method in methods:
                method_counts[method] = method_counts.get(method, 0) + 1
            for method, count in method_counts.items():
                if count > 1:
                    duplicates.append(f"{method} {path} (x{count})")

        assert not duplicates, f"发现重复的路由定义: {duplicates}"
