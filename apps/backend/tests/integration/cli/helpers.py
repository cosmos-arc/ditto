"""CLI 测试辅助函数。"""

from typing import Any


def assert_cli_result(
    result: Any,
    *,
    allowed_exit_codes: tuple[int, ...] = (0,),
    allowed_error_patterns: tuple[str, ...] = (),
) -> None:
    """验证 CLI 执行结果，使用显式白名单避免假绿。

    Args:
        result: CliRunner.invoke() 返回的结果对象
        allowed_exit_codes: 允许的退出码（默认只允许 0）
        allowed_error_patterns: 允许的错误消息模式（子字符串匹配）

    Raises:
        AssertionError: 如果结果不符合预期且不在白名单中

    Example:
        >>> assert_cli_result(
        ...     result,
        ...     allowed_exit_codes=(0, 1),
        ...     allowed_error_patterns=("unable to open database file", "Tushare"),
        ... )
    """
    if result.exit_code in allowed_exit_codes:
        return

    # 非零退出码时，检查异常是否匹配白名单
    if result.exception:
        error_msg = str(result.exception)
        for pattern in allowed_error_patterns:
            if pattern in error_msg:
                return
        # 不匹配白名单则失败
        raise AssertionError(
            f"CLI failed with unexpected error:\n"
            f"  exit_code: {result.exit_code}\n"
            f"  exception: {result.exception!r}\n"
            f"  allowed_patterns: {allowed_error_patterns}"
        )

    raise AssertionError(
        f"CLI failed with exit_code={result.exit_code}\n  stdout: {result.stdout}"
    )
