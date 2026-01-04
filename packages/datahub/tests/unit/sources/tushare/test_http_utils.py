"""HTTP 工具函数单元测试."""

import httpx
import pytest
from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceFetchError,
    SourceRateLimitError,
)
from ditto_datahub.sources.tushare.http_utils import (
    map_http_error,
    validate_tushare_response,
)


class TestValidateTushareResponse:
    """测试 validate_tushare_response 函数."""

    def test_success_response_returns_data(self):
        """成功响应返回 data 字段."""
        # Arrange
        response_json = {
            "code": 0,
            "msg": None,
            "data": {
                "fields": ["cal_date", "is_open"],
                "items": [["20240101", 0], ["20240102", 1]],
            },
        }

        # Act
        result = validate_tushare_response(response_json)

        # Assert
        assert result == {
            "fields": ["cal_date", "is_open"],
            "items": [["20240101", 0], ["20240102", 1]],
        }

    def test_auth_error_raises_authentication_error(self):
        """code 2002 抛出 SourceAuthenticationError."""
        # Arrange
        response_json = {
            "code": 2002,
            "msg": "没有权限",
        }

        # Act & Assert
        with pytest.raises(SourceAuthenticationError) as exc_info:
            validate_tushare_response(response_json)

        assert "没有权限" in str(exc_info.value)

    def test_business_error_raises_fetch_error(self):
        """其他非零 code 抛出 SourceFetchError."""
        # Arrange
        response_json = {
            "code": 1001,
            "msg": "参数错误",
        }

        # Act & Assert
        with pytest.raises(SourceFetchError) as exc_info:
            validate_tushare_response(response_json)

        assert "参数错误" in str(exc_info.value)

    def test_missing_data_raises_fetch_error(self):
        """缺少 data 字段抛出 SourceFetchError."""
        # Arrange
        response_json = {
            "code": 0,
            "msg": None,
        }

        # Act & Assert
        with pytest.raises(SourceFetchError) as exc_info:
            validate_tushare_response(response_json)

        assert "缺少 data 字段" in str(exc_info.value)

    def test_invalid_data_type_raises_fetch_error(self):
        """data 字段类型错误抛出 SourceFetchError."""
        # Arrange
        response_json = {
            "code": 0,
            "msg": None,
            "data": "not_a_dict",  # 字符串而非 dict
        }

        # Act & Assert
        with pytest.raises(SourceFetchError) as exc_info:
            validate_tushare_response(response_json)

        assert "类型错误" in str(exc_info.value)


class TestMapHttpError:
    """测试 map_http_error 函数."""

    def test_401_raises_authentication_error(self):
        """401 映射到认证错误."""
        # Arrange
        request = httpx.Request("POST", "http://api.tushare.pro")
        response = httpx.Response(401, request=request)
        error = httpx.HTTPStatusError(
            "Unauthorized", request=request, response=response
        )

        # Act & Assert
        with pytest.raises(SourceAuthenticationError) as exc_info:
            map_http_error(error, "trade_cal")

        assert "tushare" in exc_info.value.details.get("source", "")

    def test_403_raises_authentication_error(self):
        """403 映射到认证错误."""
        # Arrange
        request = httpx.Request("POST", "http://api.tushare.pro")
        response = httpx.Response(403, request=request)
        error = httpx.HTTPStatusError("Forbidden", request=request, response=response)

        # Act & Assert
        with pytest.raises(SourceAuthenticationError) as exc_info:
            map_http_error(error, "daily")

        assert "tushare" in exc_info.value.details.get("source", "")

    def test_429_raises_rate_limit_error(self):
        """429 映射到限流错误."""
        # Arrange
        request = httpx.Request("POST", "http://api.tushare.pro")
        response = httpx.Response(429, request=request)
        error = httpx.HTTPStatusError(
            "Too Many Requests", request=request, response=response
        )

        # Act & Assert
        with pytest.raises(SourceRateLimitError) as exc_info:
            map_http_error(error, "stock_basic")

        assert "tushare" in exc_info.value.details.get("source", "")

    def test_5xx_raises_fetch_error(self):
        """5xx 映射到抓取错误."""
        # Arrange
        request = httpx.Request("POST", "http://api.tushare.pro")
        response = httpx.Response(500, request=request)
        error = httpx.HTTPStatusError(
            "Internal Server Error", request=request, response=response
        )

        # Act & Assert
        with pytest.raises(SourceFetchError) as exc_info:
            map_http_error(error, "adj_factor")

        assert "tushare" in exc_info.value.details.get("source", "")
        assert exc_info.value.details.get("original_error") is not None

    def test_network_error_raises_fetch_error(self):
        """网络错误映射到抓取错误."""
        # Arrange
        error = httpx.NetworkError("Connection failed")

        # Act & Assert
        with pytest.raises(SourceFetchError) as exc_info:
            map_http_error(error, "fund_adj")

        assert "tushare" in exc_info.value.details.get("source", "")
        assert exc_info.value.details.get("original_error") is not None

    def test_timeout_raises_fetch_error(self):
        """超时映射到抓取错误."""
        # Arrange
        error = httpx.TimeoutException("Request timeout")

        # Act & Assert
        with pytest.raises(SourceFetchError) as exc_info:
            map_http_error(error, "trade_cal")

        assert "tushare" in exc_info.value.details.get("source", "")
        assert exc_info.value.details.get("original_error") is not None

    def test_unknown_error_raises_fetch_error(self):
        """未知错误映射到抓取错误."""
        # Arrange
        error = Exception("Unknown error")

        # Act & Assert
        with pytest.raises(SourceFetchError) as exc_info:
            map_http_error(error, "daily")

        assert "tushare" in exc_info.value.details.get("source", "")
        assert exc_info.value.details.get("original_error") is not None
