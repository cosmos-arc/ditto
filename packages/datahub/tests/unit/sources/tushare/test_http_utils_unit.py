"""HTTP 工具函数单元测试."""

import httpx
import polars as pl
import pytest
from ditto_datahub.sources.provider import (
    ProviderAuthenticationError,
    ProviderFetchError,
    ProviderRateLimitError,
)
from ditto_datahub.sources.tushare.http_utils import (
    map_http_error,
    response_to_dataframe,
    validate_tushare_response,
)
from polars.testing import assert_frame_equal


class TestValidateTushareResponse:
    """测试 validate_tushare_response 函数."""

    def test_success_response_returns_data(self):
        """成功响应返回 data 字段."""
        # Arrange
        response_json: dict[str, object] = {
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
        """code 2002 抛出 ProviderAuthenticationError."""
        # Arrange
        response_json: dict[str, object] = {
            "code": 2002,
            "msg": "没有权限",
        }

        # Act & Assert
        with pytest.raises(ProviderAuthenticationError) as exc_info:
            validate_tushare_response(response_json)

        assert "没有权限" in str(exc_info.value)

    def test_business_error_raises_fetch_error(self):
        """其他非零 code 抛出 ProviderFetchError."""
        # Arrange
        response_json: dict[str, object] = {
            "code": 1001,
            "msg": "参数错误",
        }

        # Act & Assert
        with pytest.raises(ProviderFetchError) as exc_info:
            validate_tushare_response(response_json)

        assert "参数错误" in str(exc_info.value)

    def test_missing_data_raises_fetch_error(self):
        """缺少 data 字段抛出 ProviderFetchError."""
        # Arrange
        response_json: dict[str, object] = {
            "code": 0,
            "msg": None,
        }

        # Act & Assert
        with pytest.raises(ProviderFetchError) as exc_info:
            validate_tushare_response(response_json)

        assert "缺少 data 字段" in str(exc_info.value)

    def test_invalid_data_type_raises_fetch_error(self):
        """data 字段类型错误抛出 ProviderFetchError."""
        # Arrange
        response_json: dict[str, object] = {
            "code": 0,
            "msg": None,
            "data": "not_a_dict",  # 字符串而非 dict
        }

        # Act & Assert
        with pytest.raises(ProviderFetchError) as exc_info:
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
        with pytest.raises(ProviderAuthenticationError) as exc_info:
            map_http_error(error, "trade_cal")

        assert exc_info.value.details.get("source") == "tushare"

    def test_403_raises_authentication_error(self):
        """403 映射到认证错误."""
        # Arrange
        request = httpx.Request("POST", "http://api.tushare.pro")
        response = httpx.Response(403, request=request)
        error = httpx.HTTPStatusError("Forbidden", request=request, response=response)

        # Act & Assert
        with pytest.raises(ProviderAuthenticationError) as exc_info:
            map_http_error(error, "daily")

        assert exc_info.value.details.get("source") == "tushare"

    def test_429_raises_rate_limit_error(self):
        """429 映射到限流错误."""
        # Arrange
        request = httpx.Request("POST", "http://api.tushare.pro")
        response = httpx.Response(429, request=request)
        error = httpx.HTTPStatusError(
            "Too Many Requests", request=request, response=response
        )

        # Act & Assert
        with pytest.raises(ProviderRateLimitError) as exc_info:
            map_http_error(error, "stock_basic")

        assert exc_info.value.details.get("source") == "tushare"

    def test_5xx_raises_fetch_error_with_retry(self):
        """5xx 映射到抓取错误并支持重试."""
        # Arrange
        request = httpx.Request("POST", "http://api.tushare.pro")
        response = httpx.Response(500, request=request)
        error = httpx.HTTPStatusError(
            "Internal Server Error", request=request, response=response
        )

        # Act & Assert
        with pytest.raises(ProviderFetchError) as exc_info:
            map_http_error(error, "adj_factor")

        assert exc_info.value.details.get("source") == "tushare"
        assert exc_info.value.details.get("original_error") is not None

    def test_network_error_raises_fetch_error(self):
        """网络错误映射到抓取错误."""
        # Arrange
        error = httpx.NetworkError("Connection failed")

        # Act & Assert
        with pytest.raises(ProviderFetchError) as exc_info:
            map_http_error(error, "fund_adj")

        assert exc_info.value.details.get("source") == "tushare"
        assert exc_info.value.details.get("original_error") is not None

    def test_timeout_raises_fetch_error(self):
        """超时映射到抓取错误."""
        # Arrange
        error = httpx.TimeoutException("Request timeout")

        # Act & Assert
        with pytest.raises(ProviderFetchError) as exc_info:
            map_http_error(error, "trade_cal")

        assert exc_info.value.details.get("source") == "tushare"
        assert exc_info.value.details.get("original_error") is not None

    def test_unknown_error_raises_fetch_error(self):
        """未知错误映射到抓取错误."""
        # Arrange
        error = Exception("Unknown error")

        # Act & Assert
        with pytest.raises(ProviderFetchError) as exc_info:
            map_http_error(error, "daily")

        assert exc_info.value.details.get("source") == "tushare"
        assert exc_info.value.details.get("original_error") is not None


class TestResponseToDataFrame:
    """测试 response_to_dataframe 函数."""

    def test_converts_response_to_dataframe(self):
        """正常响应转换成功."""
        # Arrange
        response_data = {
            "fields": ["cal_date", "is_open"],
            "items": [["20240101", 0], ["20240102", 1]],
        }

        # Act
        result = response_to_dataframe(response_data)

        # Assert
        expected = pl.DataFrame(
            {
                "cal_date": ["20240101", "20240102"],
                "is_open": [0, 1],
            }
        )
        assert_frame_equal(result, expected)

    def test_empty_response_returns_empty_dataframe(self):
        """空响应返回空 DataFrame."""
        # Arrange
        response_data: dict[str, object] = {
            "fields": ["cal_date", "is_open"],
            "items": [],
        }

        # Act
        result = response_to_dataframe(response_data)

        # Assert
        # 空数据时 Polars 会推断为 Null 类型,这是正常行为
        assert result.height == 0
        assert result.columns == ["cal_date", "is_open"]

    def test_preserve_column_names(self):
        """字段名正确映射."""
        # Arrange
        response_data = {
            "fields": ["ts_code", "trade_date", "close"],
            "items": [["000001.SZ", "20240102", 10.5]],
        }

        # Act
        result = response_to_dataframe(response_data)

        # Assert
        assert result.columns == ["ts_code", "trade_date", "close"]
        assert result.height == 1
