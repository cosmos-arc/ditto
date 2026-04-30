"""验证 ObservabilityProvider 使用注入的 runtime_flags。"""

import ast
from pathlib import Path


class TestObservabilityUsesInjectedFlags:
    """验证 ObservabilityProvider 使用注入的 runtime_flags。"""

    def _get_source_file(self) -> Path:
        """获取 observability.py 源文件路径。"""
        import ditto_apps.registry.infra.observability as mod

        return Path(mod.__file__)

    def _get_method_params(self, source: str, method_name: str) -> list[str]:
        """解析源代码获取方法参数列表。"""
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ObservabilityProvider":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return [arg.arg for arg in item.args.args]

        return []

    def test_observability_config_uses_runtime_flags(self) -> None:
        """observability_config 应使用注入的 runtime_flags。"""
        source_file = self._get_source_file()
        source = source_file.read_text()

        params = self._get_method_params(source, "observability_config")

        # 应该包含 runtime_flags 参数
        non_self_params = [p for p in params if p != "self"]
        assert "runtime_flags" in non_self_params, (
            f"observability_config should have 'runtime_flags' parameter, "
            f"got: {non_self_params}"
        )

    def test_no_direct_pytest_detection(self) -> None:
        """observability_config 不应直接检测 PYTEST_CURRENT_TEST。"""
        source_file = self._get_source_file()
        source = source_file.read_text()

        # 检查源代码中不应该有 PYTEST_CURRENT_TEST 的直接引用
        # （应该使用注入的 runtime_flags）
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ObservabilityProvider":
                for item in node.body:
                    is_target = (
                        isinstance(item, ast.FunctionDef)
                        and item.name == "observability_config"
                    )
                    if is_target:
                        # 检查函数体中是否有 PYTEST_CURRENT_TEST 字符串
                        source_segment = ast.get_source_segment(source, item)
                        if source_segment:
                            assert "PYTEST_CURRENT_TEST" not in source_segment, (
                                "observability_config should not directly "
                                "check PYTEST_CURRENT_TEST; "
                                "use injected runtime_flags instead"
                            )
