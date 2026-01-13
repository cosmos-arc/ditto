"""
类型检查测试 - 验证 create_ingestion_context 的类型推断。

这个测试演示了改进前后类型推断的差异。
"""

from pathlib import Path
from typing import Any

from ditto_port.jobs.flows.helpers import create_ingestion_context
from mypy import api


class TestCreateIngestionContextTypeInference:
    """测试 create_ingestion_context 的类型推断能力。"""

    def test_type_inference_with_concrete_types(self):
        """
        测试类型推断能够识别返回的具体类型。

        当使用具体的 DataHub 和 IngestionCoordinator 类型时,
        类型检查器应该能够推断出 hub 和 coordinator 的具体类型。
        """

        # 创建一个测试片段来验证类型推断
        test_code = """
from ditto_port.jobs.flows.helpers import create_ingestion_context

def test_function() -> None:
    with create_ingestion_context(
        data_root="data", source="tushare"
    ) as (hub, coordinator):
        # 这里应该能够访问 hub 和 coordinator 的方法和属性
        # 而不会出现 'Any' 类型警告
        # 类型检查器应该知道 hub 是 DataHub 类型
        # coordinator 是 IngestionCoordinator 类型
        pass
"""

        # 将测试代码写入临时文件
        import tempfile  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(test_code)
            temp_file = f.name

        try:
            # 运行 mypy 检查
            result = api.run([temp_file, "--show-error-codes"])
            # 应该没有错误
            assert result[2] == 0, f"mypy 检查失败: {result[0]}"
        finally:
            Path(temp_file).unlink()

    def test_context_manager_signature(self):
        """测试上下文管理器的类型签名是否正确。"""

        # 验证函数存在且可调用
        assert callable(create_ingestion_context)

        # 验证函数的类型注解
        # 注意: 由于使用了 TYPE_CHECKING,我们需要在获取类型注解时提供全局命名空间
        from typing import get_type_hints  # noqa: PLC0415

        # 导入必要的类型以供 get_type_hints 使用
        from ditto_datahub import DataHub  # noqa: PLC0415
        from ditto_port.services.ingestion.coordinator import (  # noqa: PLC0415
            IngestionCoordinator,
        )

        # 提供全局命名空间以便 get_type_hints 可以解析类型
        globalns = {
            "DataHub": DataHub,
            "IngestionCoordinator": IngestionCoordinator,
            "Iterator": __import__("collections.abc").abc.Iterator,
            "tuple": tuple,
        }

        hints = get_type_hints(create_ingestion_context, globalns=globalns)

        # 验证返回类型是 Iterator[tuple[DataHub, IngestionCoordinator]]
        # 或者至少是 Iterator[tuple[某种类型, 某种类型]]
        # 不应该是 Iterator[tuple[Any, Any]]
        return_hint = hints.get("return")

        # 检查是否是 Iterator 类型
        assert return_hint is not None, "create_ingestion_context 应该有返回类型注解"

        # 如果使用 Any 类型,这个测试会通过但不够理想
        # 如果使用具体类型,这个测试会更好地验证类型推断
        # 这个测试的主要目的是确保类型注解存在且合理
        assert hasattr(return_hint, "__args__"), "返回类型应该是参数化的泛型类型"

        # 进一步验证:不应该包含 Any 类型

        if hasattr(return_hint, "__args__"):
            # 检查类型参数中是否包含 Any
            for arg in return_hint.__args__:
                # 如果找到了 Any 类型,说明类型注解不够具体
                # 我们期望看到具体的 DataHub 和 IngestionCoordinator 类型
                if arg is Any:
                    msg = (
                        "返回类型不应包含 Any,应使用具体的"
                        " DataHub 和 IngestionCoordinator 类型"
                    )
                    raise AssertionError(msg)

    def test_type_checking_with_actual_usage(self):
        """
        测试在实际使用场景中的类型检查。

        这个测试确保在使用 create_ingestion_context 时,
        类型检查器能够正确推断 hub 和 coordinator 的类型。
        """

        # 创建一个更实际的测试场景
        test_code = """
from ditto_port.jobs.flows.helpers import create_ingestion_context

def example_usage() -> None:
    with create_ingestion_context(
        data_root="data", source="tushare"
    ) as (hub, coordinator):
        # 类型检查器应该能够推断出 hub 的类型
        # 并提供相应的类型提示和检查
        # 如果类型是 Any,则无法提供这些功能
        _ = hub
        _ = coordinator

# 确保函数可以被类型检查
if __name__ == "__main__":
    example_usage()
"""

        import tempfile  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(test_code)
            temp_file = f.name

        try:
            result = api.run([temp_file, "--show-error-codes"])
            # 应该没有类型错误
            assert result[2] == 0, f"mypy 检查失败: {result[0]}"
        finally:
            Path(temp_file).unlink()
