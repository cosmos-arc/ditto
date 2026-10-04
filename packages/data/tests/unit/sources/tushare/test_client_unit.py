"""Tests for TushareClient."""

import httpx
import orjson
import pytest
import pytest_mock
import tenacity
from ditto_data.config import DataSourceSettings
from ditto_data.sources.base import (
    SourceAuthenticationError,
    SourceConfigurationError,
    SourceRateLimitError,
)
from ditto_data.sources.tushare.client import TushareClient
from ditto_data.sources.tushare.utils import pagination
from ditto_data.sources.tushare.utils.pagination import resolve_page_size
from ditto_data.sources.tushare.utils.rate_limiter import (
    TushareRateLimitConfig,
    TushareRateLimiter,
)


def _settings(token: str | None = None) -> DataSourceSettings:
    if token is None:
        token = "not_a_secret"
    return DataSourceSettings(tushare_token=token)


class TestTushareClientInit:
    """Tests for TushareClient initialization."""

    def test_init_with_token_from_settings(self) -> None:
        """Test initialization reads token from settings."""
        settings = _settings("test_token_123")
        client = TushareClient(settings=settings)
        assert client._token == "test_token_123"

    def test_init_missing_token_raises_error(self) -> None:
        """Test missing token raises configuration error."""
        with pytest.raises(SourceConfigurationError):
            TushareClient(settings=_settings(""))

    def test_init_custom_rate_limit(self) -> None:
        """Test custom rate limit configuration."""
        config = TushareRateLimitConfig(
            global_rate=100,
            global_window=60,
        )
        client = TushareClient(rate_config=config, settings=_settings())
        assert isinstance(client._limiter, TushareRateLimiter)

    def test_init_custom_retry_config(self) -> None:
        """Test custom retry configuration uses paid tier."""
        client = TushareClient(
            rate_config=TushareRateLimitConfig.paid(),
            settings=_settings(),
        )
        assert isinstance(client._limiter, TushareRateLimiter)

    def test_init_uses_explicit_paid_profile_from_settings(self) -> None:
        """Production paid profile must reach the shared provider limiter."""
        settings = DataSourceSettings(
            tushare_token="not_a_secret",
            rate_limit_profile="paid",
        )

        client = TushareClient(settings=settings)

        assert client._limiter._config == TushareRateLimitConfig.paid()

    def test_init_keeps_free_profile_as_the_default(self) -> None:
        """Development defaults stay conservative unless explicitly overridden."""
        client = TushareClient(settings=_settings())

        assert client._limiter._config == TushareRateLimitConfig.free()

    def test_init_supports_official_account_profiles(self) -> None:
        """官方直连积分档独立于代理 transport 档位（#431）."""
        official_120 = TushareClient(
            settings=DataSourceSettings(
                tushare_token="not_a_secret",
                rate_limit_profile="official_120",
            )
        )
        assert official_120._limiter._config == TushareRateLimitConfig.official_120()

        official_15000 = TushareClient(
            settings=DataSourceSettings(
                tushare_token="not_a_secret",
                rate_limit_profile="official_15000",
            )
        )
        assert (
            official_15000._limiter._config == TushareRateLimitConfig.official_15000()
        )

    def test_init_accepts_proxy_aliases(self) -> None:
        """proxy_free/proxy_paid 显式命名代理 transport 档位，与旧名等价."""
        proxy_paid = TushareClient(
            settings=DataSourceSettings(
                tushare_token="not_a_secret",
                rate_limit_profile="proxy_paid",
            )
        )
        assert proxy_paid._limiter._config == TushareRateLimitConfig.paid()


class TestTushareClientQuery:
    """Tests for TushareClient.query method."""

    def test_successful_query_returns_dataframe(self, respx_mock) -> None:
        """成功查询返回 polars DataFrame."""
        # Arrange
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["cal_date", "is_open"],
                        "items": [["20240101", 0], ["20240102", 1]],
                    },
                },
            )
        )

        # Act
        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date,is_open", exchange="SSE")

        # Assert
        assert result.height == 2
        assert result.columns == ["cal_date", "is_open"]
        assert result.to_dict(as_series=False) == {
            "cal_date": ["20240101", "20240102"],
            "is_open": [0, 1],
        }

    def test_full_page_follows_offset_pagination(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """单页达到上限时自动携带 offset 翻页，避免静默截断。"""
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 2)
        pages = [
            httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [["1"], ["2"]]},
                },
            ),
            httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [["3"]]},
                },
            ),
        ]
        route = respx_mock.post("http://api.tushare.pro").mock(side_effect=pages)

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")

        assert result["cal_date"].to_list() == ["1", "2", "3"]
        assert route.call_count == 2
        second_body = orjson.loads(respx_mock.calls[1].request.content)["params"]
        assert second_body["offset"] == 2
        assert second_body["limit"] == 2

    def test_caller_managed_limit_stays_single_page(
        self,
        respx_mock,
    ) -> None:
        """调用方自带 limit/offset 时保持单页语义，不自动翻页。"""
        full_page = {
            "code": 0,
            "msg": None,
            "data": {"fields": ["cal_date"], "items": [["1"], ["2"]]},
        }
        route = respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(200, json=full_page)
        )

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date", limit=2, offset=0)

        assert result.height == 2
        assert route.call_count == 1

    def test_server_cap_below_old_page_size_still_paginates(
        self,
        respx_mock,
    ) -> None:
        """#431 回归：请求页宽必须等于端点契约上限，而非统一 9000.

        离线复现的原始缺陷：2501 行源、服务端 cap 2000、旧实现请求
        limit=9000 并以短页为结束条件 → 只取回 2000。修复后按保守默认
        页宽 2000 请求，满页继续翻页，完整取回 2501。
        """
        rows = [{"cal_date": str(i)} for i in range(2501)]

        def side_effect(request: httpx.Request) -> httpx.Response:
            params = orjson.loads(request.content)["params"]
            page = rows[params["offset"] : params["offset"] + 2000]  # cap=2000
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["cal_date"],
                        "items": [[r["cal_date"]] for r in page],
                    },
                },
            )

        route = respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")

        assert result.height == 2501
        assert route.call_count == 2
        requested_limits = {
            orjson.loads(call.request.content)["params"]["limit"]
            for call in respx_mock.calls
        }
        assert requested_limits == {2000}

    def test_exact_full_page_with_empty_tail_completes(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """恰好在页宽边界结束：短尾页（含空尾页）是合法取尽条件。"""
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 2)
        pages = [
            {"fields": ["cal_date"], "items": [["1"], ["2"]]},
            {"fields": ["cal_date"], "items": []},
        ]
        route = respx_mock.post("http://api.tushare.pro").mock(
            side_effect=[
                httpx.Response(200, json={"code": 0, "msg": None, "data": page})
                for page in pages
            ]
        )

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")

        assert result["cal_date"].to_list() == ["1", "2"]
        assert route.call_count == 2

    def test_duplicate_page_raises_instead_of_looping(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
        fake_time,
    ) -> None:
        """服务端忽略 offset（重复页/不前进）时 fail-closed，不无限翻页。"""
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 2)
        page = {
            "code": 0,
            "msg": None,
            "data": {"fields": ["cal_date"], "items": [["1"], ["2"]]},
        }
        route = respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(200, json=page)
        )

        client = TushareClient(token="test_token", settings=_settings())
        # 重复页错误按 SourceFetchError 参与现有重试语义，耗尽后以 RetryError 冒泡
        with pytest.raises(tenacity.RetryError) as exc_info:
            client.query("trade_cal", "cal_date")

        assert "duplicate rows" in str(exc_info.value.last_attempt.exception())
        # 每次尝试在第二页（offset=2 收到重复页）即拦截，不会无限翻页
        assert route.call_count == 2 * 3

    def test_documented_endpoint_uses_exact_page_size(self, respx_mock) -> None:
        """已核实上限的端点按精确页宽请求；未知端点用保守默认 2000。"""
        single_page = {
            "code": 0,
            "msg": None,
            "data": {"fields": ["ts_code"], "items": [["000001.SZ"]]},
        }
        route = respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(200, json=single_page)
        )

        client = TushareClient(token="test_token", settings=_settings())
        client.query("daily", "ts_code")
        client.query("fund_adj", "ts_code")
        client.query("not_documented", "ts_code")

        requested_limits = [
            orjson.loads(call.request.content)["params"]["limit"]
            for call in respx_mock.calls
        ]
        assert requested_limits == [6000, 2000, 2000]
        assert route.call_count == 3

    def test_resolve_page_size_uses_documented_contract(self) -> None:
        """端点分页契约表与官方专页一致。"""
        assert resolve_page_size("daily") == 6000
        assert resolve_page_size("fund_daily") == 5000
        assert resolve_page_size("fund_adj") == 2000
        assert resolve_page_size("index_global") == 4000
        assert resolve_page_size("unknown_endpoint") == 2000

    def test_in_page_duplicate_rows_raise(
        self,
        respx_mock,
    ) -> None:
        """同响应内整行重复（主键重复）fail-closed，不得静默入库."""
        page = {
            "code": 0,
            "msg": None,
            "data": {"fields": ["cal_date"], "items": [["1"], ["1"]]},
        }
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(200, json=page)
        )

        client = TushareClient(token="test_token", settings=_settings())
        # 重复行错误参与现有 SourceFetchError 重试语义，耗尽后以 RetryError 冒泡
        with pytest.raises(tenacity.RetryError) as exc_info:
            client.query("trade_cal", "cal_date")
        assert "in-page=1" in str(exc_info.value.last_attempt.exception())

    def test_rate_limit_message_classified_as_rate_limit_error(
        self, respx_mock
    ) -> None:
        """频次超限消息归为 SourceRateLimitError，不得转为空成功或普通失败."""
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": -1,
                    # 标记特征：官方频次超限消息含"每分钟最多访问"（全角标点从略）
                    "msg": "抱歉 您每分钟最多访问该接口2次",
                },
            )
        )

        client = TushareClient(token="test_token", settings=_settings())
        with pytest.raises(SourceRateLimitError):
            client.query("trade_cal", "cal_date")

    def test_rate_limit_before_request(
        self, respx_mock, mocker: pytest_mock.MockFixture
    ) -> None:
        """请求前调用限流器."""
        # Arrange
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [["20240101"]]},
                },
            )
        )

        client = TushareClient(token="test_token", settings=_settings())
        wait_spy = mocker.spy(client._limiter, "wait_if_needed")

        # Act
        client.query("trade_cal", "cal_date", exchange="SSE")

        # Assert
        wait_spy.assert_called_once()

    def test_retry_on_network_error(self, respx_mock, fake_time) -> None:
        """网络错误自动重试."""
        # Arrange
        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.NetworkError("Connection failed")
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [["20240101"]]},
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        # Act
        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date", exchange="SSE")

        # Assert
        assert call_count == 2  # [REVIEW],第二次成功
        assert result.height == 1

    def test_no_retry_on_auth_error(self, respx_mock) -> None:
        """认证错误不重试,直接抛出."""
        # Arrange
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={"code": 2002, "msg": "没有权限"},
            )
        )

        # Act & Assert
        client = TushareClient(token="invalid_token", settings=_settings())
        with pytest.raises(SourceAuthenticationError):
            client.query("trade_cal", "cal_date", exchange="SSE")

    def test_retry_on_5xx_status(self, respx_mock, fake_time) -> None:
        """5xx 状态码自动重试."""
        # Arrange
        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(500, text="Internal Server Error")
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [["20240101"]]},
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        # Act
        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date", exchange="SSE")

        # Assert
        assert call_count == 2
        assert result.height == 1


class TestTushareClientResourceManagement:
    """Tests for TushareClient resource management."""

    def test_close_method(self) -> None:
        """Test close method properly closes HTTP client."""
        client = TushareClient(settings=_settings())

        # Verify _client exists and is not closed
        assert client._client is not None
        assert not client._client.is_closed

        # Call close
        client.close()

        # Verify _client is closed
        assert client._client.is_closed

    def test_context_manager(self) -> None:
        """Test TushareClient supports context manager protocol."""
        with TushareClient(settings=_settings()) as client:
            assert client is not None
            assert isinstance(client, TushareClient)
            # Verify client is not closed inside the with block
            assert not client._client.is_closed

        # After with block, client should be closed
        assert client._client.is_closed
