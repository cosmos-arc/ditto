"""HTTP 工具函数单元测试."""

import pytest
from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceFetchError,
)
from ditto_datahub.sources.tushare.http_utils import validate_tushare_response


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
