"""验证 DI 容器无重复 Path provider。"""

import ast
from pathlib import Path


class TestDINoDuplicatePathProvider:
    """验证 DI 容器无重复 Path provider。"""

    def _get_source_file(self) -> Path:
        """获取 runtime.py 源文件路径。"""
        import ditto_data.di.runtime as mod

        return Path(mod.__file__)

    def _get_method_params(self, source: str, method_name: str) -> list[str]:
        """解析源代码获取方法参数列表。"""
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "RuntimeProvider":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return [arg.arg for arg in item.args.args]

        return []

    def _has_method(self, source: str, method_name: str) -> bool:
        """检查类是否有指定方法。"""
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "RuntimeProvider":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return True

        return False

    def test_data_root_not_in_runtime_provider(self) -> None:
        """RuntimeProvider 不应直接提供 data_root (Path 类型)。"""
        source_file = self._get_source_file()
        source = source_file.read_text()

        # 检查是否有名为 data_root 的方法
        has_data_root = self._has_method(source, "data_root")

        assert not has_data_root, (
            "RuntimeProvider should not have data_root method - "
            "it's already provided by ConfigProvider"
        )

    def test_freeze_manager_uses_settings(self) -> None:
        """freeze_manager 应该使用 DataStoreSettings 而不是 Path。"""
        source_file = self._get_source_file()
        source = source_file.read_text()

        params = self._get_method_params(source, "freeze_manager")

        # 应该包含 settings 参数（self 之外）
        non_self_params = [p for p in params if p != "self"]
        assert "settings" in non_self_params, (
            f"freeze_manager should have 'settings' parameter, got: {non_self_params}"
        )

    def test_file_lock_uses_settings(self) -> None:
        """file_lock 应该使用 DataStoreSettings 而不是 Path。"""
        source_file = self._get_source_file()
        source = source_file.read_text()

        params = self._get_method_params(source, "file_lock")

        # 应该包含 settings 参数（self 之外）
        non_self_params = [p for p in params if p != "self"]
        assert "settings" in non_self_params, (
            f"file_lock should have 'settings' parameter, got: {non_self_params}"
        )

    def test_sql_engine_uses_settings(self) -> None:
        """sql_engine 应该使用 DataStoreSettings 而不是 Path。"""
        source_file = self._get_source_file()
        source = source_file.read_text()

        params = self._get_method_params(source, "sql_engine")

        # 应该包含 settings 参数（self 之外）
        non_self_params = [p for p in params if p != "self"]
        assert "settings" in non_self_params, (
            f"sql_engine should have 'settings' parameter, got: {non_self_params}"
        )
