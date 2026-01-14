"""Tushare HTTP 工具函数."""

from typing import Any, NoReturn, cast

import httpx
import polars as pl

from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceFetchError,
    SourceRateLimitError,
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
    # 2002: 权限不足/无权限
    # 40101: 用户Token格式错误或无效
    if code in (2002, 40101):
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

    data_value = response_json.get("data")
    if data_value is None:
        raise SourceFetchError(
            message="响应缺少 data 字段",
            source="tushare",
        )

    data = cast(dict[str, Any], data_value)
    return data


def map_http_error(error: Exception, api_name: str) -> NoReturn:
    """
    映射 httpx 异常到 DataSource 错误体系。

    Args:
        error: httpx 异常
        api_name: API 名称(用于日志)

    Raises:
        SourceAuthenticationError: HTTP 401/403
        SourceRateLimitError: HTTP 429
        SourceFetchError: 其他网络错误

    """
    # 处理 HTTP 状态码错误
    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code

        if status_code in (401, 403):
            raise SourceAuthenticationError(
                message=f"Tushare API 认证失败 (API: {api_name})",
                source="tushare",
            )

        if status_code == 429:
            raise SourceRateLimitError(
                message=f"Tushare API 限流 (API: {api_name})",
                source="tushare",
            )

        # 5xx 服务器错误
        if status_code >= 500:
            raise SourceFetchError(
                message=f"Tushare API 服务器错误 (API: {api_name})",
                source="tushare",
                original_error=str(error),
            )

        # 其他 4xx 错误
        raise SourceFetchError(
            message=f"Tushare API 请求失败 (API: {api_name})",
            source="tushare",
            original_error=str(error),
        )

    # 处理网络错误
    if isinstance(error, httpx.NetworkError):
        raise SourceFetchError(
            message=f"Tushare API 网络错误 (API: {api_name})",
            source="tushare",
            original_error=str(error),
        )

    # 处理超时错误
    if isinstance(error, httpx.TimeoutException):
        raise SourceFetchError(
            message=f"Tushare API 请求超时 (API: {api_name})",
            source="tushare",
            original_error=str(error),
        )

    # 未知错误
    raise SourceFetchError(
        message=f"Tushare API 未知错误 (API: {api_name})",
        source="tushare",
        original_error=str(error),
    )


def response_to_dataframe(response_data: dict[str, object]) -> pl.DataFrame:
    """
    将 Tushare API 响应转换为 polars DataFrame。

    Args:
        response_data: API 响应的 data 字段

    Returns:
        polars DataFrame

    """
    fields = cast(list[str], response_data["fields"])
    items = cast(list[list[object]], response_data["items"])

    # items 是按行组织的列表，转换为按列组织的字典
    if not items:
        return pl.DataFrame(schema=fields)

    # 转置数据：从行式转为列式
    data = {col: [row[i] for row in items] for i, col in enumerate(fields)}
    return pl.DataFrame(data)
