"""Tushare HTTP 工具函数."""

from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceFetchError,
)


def validate_tushare_response(response_json: dict[str, object]) -> dict[str, object]:
    """
    验证 Tushare HTTP API 响应格式。

    Args:
        response_json: 原始 JSON 响应

    Returns:
        验证后的 data 字段

    Raises:
        SourceAuthenticationError: code == 2002
        SourceFetchError: code != 0 或缺少 data 字段

    """
    code = response_json.get("code")
    msg = response_json.get("msg")

    # 检查认证错误
    if code == 2002:
        raise SourceAuthenticationError(
            message=(msg if isinstance(msg, str) else None) or "Tushare 认证失败",
            source="tushare",
        )

    # 检查其他业务错误
    if code != 0:
        msg_str = msg if isinstance(msg, str) else None
        error_msg = msg_str or f"Tushare API 返回错误码: {code}"
        raise SourceFetchError(
            message=error_msg,
            source="tushare",
        )

    # 检查 data 字段
    if "data" not in response_json:
        raise SourceFetchError(
            message="响应缺少 data 字段",
            source="tushare",
        )

    data = response_json["data"]
    if not isinstance(data, dict):
        raise SourceFetchError(
            message="响应 data 字段类型错误",
            source="tushare",
        )

    return data
