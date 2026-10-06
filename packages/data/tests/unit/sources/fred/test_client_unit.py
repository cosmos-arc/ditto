"""Tests for FredClient."""

from __future__ import annotations

import logging

import httpx
import pytest
import tenacity
from ditto_data.sources.base import (
    SourceAuthenticationError,
    SourceConfigurationError,
    SourceFetchError,
    SourceRateLimitError,
)
from ditto_data.sources.fred import client as fred_client_module
from ditto_data.sources.fred.client import FredClient


class TestFredClientInit:
    """Tests for FredClient initialization."""

    def test_init_with_api_key_parameter(self) -> None:
        """Test initialization with explicit API key."""
        client = FredClient(api_key="test_api_key_123")
        assert client._api_key == "test_api_key_123"

    def test_init_missing_api_key_raises_error(self, monkeypatch) -> None:
        """缺 key 显式报缺，并指向唯一配置入口（#433）."""
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        with pytest.raises(SourceConfigurationError) as exc_info:
            FredClient()
        assert "FRED_API_KEY" in str(exc_info.value)
        assert "DITTO_CONFIG_ROOT" in str(exc_info.value)

    def test_init_does_not_read_environment(self, monkeypatch) -> None:
        """#433：数据层不读环境变量（唯一入口为 DataSourceSettings 注入）."""
        monkeypatch.setenv("FRED_API_KEY", "env_api_key_should_be_ignored")
        with pytest.raises(SourceConfigurationError):
            FredClient()


class TestFredClientGetSeriesObservations:
    """Tests for FredClient.get_series_observations method."""

    def test_api_key_is_redacted_from_httpx_logs(
        self,
        respx_mock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Provider credentials must never enter observable HTTP client logs."""
        secret = "unit-test-fred-secret"
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={"observations": []},
            )
        )

        with caplog.at_level(logging.INFO, logger="httpx"):
            FredClient(api_key=secret).get_series_observations(
                series_id="UNRATE",
                observation_start="2024-01-01",
                observation_end="2024-01-31",
            )

        rendered = "\n".join(record.getMessage() for record in caplog.records)
        assert secret not in rendered
        assert "api_key=%3Credacted%3E" in rendered

    def test_successful_fetch_returns_dataframe(self, respx_mock) -> None:
        """成功获取返回 polars DataFrame."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "UNRATE",
                    "observations": [
                        {
                            "realtime_start": "2024-02-01",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-01",
                            "value": "3.7",
                        },
                        {
                            "realtime_start": "2024-03-01",
                            "realtime_end": "2024-12-31",
                            "date": "2024-02-01",
                            "value": "3.9",
                        },
                    ],
                },
            )
        )

        # Act
        client = FredClient(api_key="test_key")
        result = client.get_series_observations(
            series_id="UNRATE",
            observation_start="2024-01-01",
            observation_end="2024-12-31",
        )

        # Assert
        assert result.height == 2
        assert "date" in result.columns
        assert "value" in result.columns
        assert "realtime_start" in result.columns

    def test_empty_response_returns_empty_dataframe(self, respx_mock) -> None:
        """空响应返回空 DataFrame，带正确 schema."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "UNRATE",
                    "observations": [],
                },
            )
        )

        # Act
        client = FredClient(api_key="test_key")
        result = client.get_series_observations(
            series_id="UNRATE",
            observation_start="2024-01-01",
            observation_end="2024-12-31",
        )

        # Assert
        assert result.height == 0
        assert "date" in result.columns
        assert "value" in result.columns

    def test_auth_error_raises_authentication_error(self, respx_mock) -> None:
        """401 错误抛出 SourceAuthenticationError."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )

        # Act & Assert
        client = FredClient(api_key="invalid_key")
        with pytest.raises(SourceAuthenticationError):
            client.get_series_observations(
                series_id="UNRATE",
                observation_start="2024-01-01",
                observation_end="2024-12-31",
            )

    def test_network_error_raises_fetch_error(self, respx_mock) -> None:
        """网络错误最终抛出异常."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            side_effect=httpx.NetworkError("Connection failed")
        )

        # Act & Assert
        client = FredClient(api_key="test_key")
        # Tenacity wraps the exception in RetryError after retries
        import tenacity

        with pytest.raises(tenacity.RetryError) as exc_info:
            client.get_series_observations(
                series_id="UNRATE",
                observation_start="2024-01-01",
                observation_end="2024-12-31",
            )

        # Verify the original exception is SourceFetchError
        assert isinstance(exc_info.value.__cause__, SourceFetchError)

    def test_pit_parameters_included_in_request(self, respx_mock) -> None:
        """PIT 参数 (realtime_start/end) 包含在请求中."""
        # Arrange
        request_capture = None

        def capture_request(request: httpx.Request) -> httpx.Response:
            nonlocal request_capture
            request_capture = request
            return httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "GDP",
                    "observations": [],
                },
            )

        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            side_effect=capture_request
        )

        # Act
        client = FredClient(api_key="test_key")
        client.get_series_observations(
            series_id="GDP",
            observation_start="2020-01-01",
            observation_end="2024-12-31",
            realtime_start="2024-01-01",
            realtime_end="2024-12-31",
        )

        # Assert
        assert request_capture is not None
        params = dict(request_capture.url.params)
        assert params.get("realtime_start") == "2024-01-01"
        assert params.get("realtime_end") == "2024-12-31"

    def test_value_column_parsed_as_float(self, respx_mock) -> None:
        """value 列解析为 Float64."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "UNRATE",
                    "observations": [
                        {
                            "realtime_start": "2024-02-01",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-01",
                            "value": "3.7",
                        },
                    ],
                },
            )
        )

        # Act
        client = FredClient(api_key="test_key")
        result = client.get_series_observations(
            series_id="UNRATE",
            observation_start="2024-01-01",
            observation_end="2024-12-31",
        )

        # Assert

        assert str(result["value"].dtype) == "Float64"

    def test_date_columns_parsed_as_date(self, respx_mock) -> None:
        """日期列解析为 Date 类型."""
        # Arrange
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "UNRATE",
                    "observations": [
                        {
                            "realtime_start": "2024-02-01",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-01",
                            "value": "3.7",
                        },
                    ],
                },
            )
        )

        # Act
        client = FredClient(api_key="test_key")
        result = client.get_series_observations(
            series_id="UNRATE",
            observation_start="2024-01-01",
            observation_end="2024-12-31",
        )

        # Assert
        assert str(result["date"].dtype) == "Date"
        assert str(result["realtime_start"].dtype) == "Date"


class TestFredClientResourceManagement:
    """Tests for FredClient resource management."""

    def test_close_method(self) -> None:
        """Test close method properly closes HTTP client."""
        client = FredClient(api_key="test_key")

        # Verify _client exists and is not closed
        assert client._client is not None
        assert not client._client.is_closed

        # Call close
        client.close()

        # Verify _client is closed
        assert client._client.is_closed

    def test_context_manager(self) -> None:
        """Test FredClient supports context manager protocol."""
        with FredClient(api_key="test_key") as client:
            assert client is not None
            assert isinstance(client, FredClient)
            # Verify client is not closed inside the with block
            assert not client._client.is_closed

        # After with block, client should be closed
        assert client._client.is_closed


class TestFredClientRobustness:
    """#516 健壮性收口 — 限流退避 / 确定性 4xx / 响应体防护 / 缺失值."""

    def test_missing_value_dot_becomes_null(self, respx_mock) -> None:
        """官方缺失值 '.' → null（Float64 非严格 cast），行为锁定（#508）."""
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "observations": [
                        {
                            "realtime_start": "2024-02-01",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-01",
                            "value": ".",
                        },
                        {
                            "realtime_start": "2024-02-01",
                            "realtime_end": "2024-12-31",
                            "date": "2024-02-01",
                            "value": "3.9",
                        },
                    ],
                },
            )
        )

        result = FredClient(api_key="test_key").get_series_observations(
            series_id="UNRATE",
            observation_start="2024-01-01",
            observation_end="2024-12-31",
        )

        assert result.height == 2
        assert result["value"][0] is None
        assert result["value"][1] == 3.9
        assert str(result["value"].dtype) == "Float64"

    def test_rate_limit_429_retries_then_succeeds(self, respx_mock) -> None:
        """429 → SourceRateLimitError 专用退避后重试成功，不中断（#516）."""
        endpoint = respx_mock.get("https://api.stlouisfed.org/fred/series/observations")
        endpoint.side_effect = [
            httpx.Response(429, json={"error_code": 429, "error_message": "limit"}),
            httpx.Response(200, json={"observations": []}),
        ]

        result = FredClient(api_key="test_key").get_series_observations(
            series_id="UNRATE",
            observation_start="2024-01-01",
            observation_end="2024-12-31",
        )

        assert result.height == 0
        assert endpoint.call_count == 2

    def test_rate_limit_retry_after_header_parsed(self) -> None:
        """Retry-After 秒数头被解析进 details，供退避优先遵从."""
        response = httpx.Response(429, headers={"Retry-After": "30"})
        request = httpx.Request("GET", "https://api.stlouisfed.org/fred/x")
        error = FredClient._rate_limit_error(
            httpx.HTTPStatusError("429", request=request, response=response)
        )
        assert isinstance(error, SourceRateLimitError)
        assert error.details["retry_after_seconds"] == 30

    def test_permanent_4xx_not_retried(self, respx_mock) -> None:
        """404 等确定性 4xx 立即失败，不做无意义重试（#508 缺陷）."""
        endpoint = respx_mock.get("https://api.stlouisfed.org/fred/series/observations")
        endpoint.mock(return_value=httpx.Response(404, text="Not Found"))

        with pytest.raises(SourceFetchError, match="404"):
            FredClient(api_key="test_key").get_series_observations(
                series_id="BAD_SERIES",
                observation_start="2024-01-01",
                observation_end="2024-12-31",
            )

        assert endpoint.call_count == 1

    def test_non_json_200_raises_permanent_fetch_error(self, respx_mock) -> None:
        """200 但非 JSON 响应体 → 包装为确定性失败，不裸抛（#516）."""
        endpoint = respx_mock.get("https://api.stlouisfed.org/fred/series/observations")
        endpoint.mock(return_value=httpx.Response(200, text="<html>gateway</html>"))

        with pytest.raises(SourceFetchError, match="non-JSON"):
            FredClient(api_key="test_key").get_series_observations(
                series_id="UNRATE",
                observation_start="2024-01-01",
                observation_end="2024-12-31",
            )

        assert endpoint.call_count == 1

    def test_non_observations_json_body_rejected(self, respx_mock) -> None:
        """200 JSON 但不是 observations 文档（如数组）→ 确定性失败，不裸抛."""
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(200, json=[1, 2, 3])
        )

        with pytest.raises(SourceFetchError, match="observations document"):
            FredClient(api_key="test_key").get_series_observations(
                series_id="UNRATE",
                observation_start="2024-01-01",
                observation_end="2024-12-31",
            )

    def test_transient_503_retried_then_wrapped(self, respx_mock) -> None:
        """5xx 瞬态错误照旧走 3 次重试，耗尽后 RetryError 包 SourceFetchError."""
        endpoint = respx_mock.get("https://api.stlouisfed.org/fred/series/observations")
        endpoint.mock(return_value=httpx.Response(503, text="Service Unavailable"))

        with pytest.raises(tenacity.RetryError) as exc_info:
            FredClient(api_key="test_key").get_series_observations(
                series_id="UNRATE",
                observation_start="2024-01-01",
                observation_end="2024-12-31",
            )

        assert isinstance(exc_info.value.__cause__, SourceFetchError)
        assert endpoint.call_count == 3

    def test_rate_limit_429_exhaustion_wrapped(self, respx_mock) -> None:
        """持续 429 → 3 次尝试耗尽后 RetryError 包 SourceRateLimitError."""
        endpoint = respx_mock.get("https://api.stlouisfed.org/fred/series/observations")
        endpoint.mock(
            return_value=httpx.Response(429, json={"error_code": 429, "message": "l"})
        )

        with pytest.raises(tenacity.RetryError) as exc_info:
            FredClient(api_key="test_key").get_series_observations(
                series_id="UNRATE",
                observation_start="2024-01-01",
                observation_end="2024-12-31",
            )

        assert isinstance(exc_info.value.__cause__, SourceRateLimitError)
        assert endpoint.call_count == 3

    def test_scalar_observations_elements_rejected(self, respx_mock) -> None:
        """observations 元素非对象（如 [1,2,3]）→ 确定性失败，不裸抛 polars 错."""
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(200, json={"observations": [1, 2, 3]})
        )

        with pytest.raises(SourceFetchError, match="non-object elements"):
            FredClient(api_key="test_key").get_series_observations(
                series_id="UNRATE",
                observation_start="2024-01-01",
                observation_end="2024-12-31",
            )

    def test_malformed_observation_rows_wrapped(self, respx_mock) -> None:
        """缺键行在帧构造处包装为确定性失败，不留 polars 裸抛（#516 评审 F4）."""
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200, json={"observations": [{"date": "2024-01-01"}]}
            )
        )

        with pytest.raises(SourceFetchError, match="malformed element shape"):
            FredClient(api_key="test_key").get_series_observations(
                series_id="UNRATE",
                observation_start="2024-01-01",
                observation_end="2024-12-31",
            )

    def test_request_path_is_throttled(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """公开取数路径两次调用间真实走节流（mock 时钟，删调用即失败）."""
        from ditto_data.sources import throttle as throttle_module

        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(200, json={"observations": []})
        )
        client = FredClient(api_key="test_key", min_request_interval=0.5)
        sleeps: list[float] = []
        clock = {"now": 100.0}

        def _fake_monotonic() -> float:
            return clock["now"]

        def _fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock["now"] += seconds

        monkeypatch.setattr(throttle_module.time, "monotonic", _fake_monotonic)
        monkeypatch.setattr(throttle_module.time, "sleep", _fake_sleep)

        client.get_series_observations(
            series_id="UNRATE",
            observation_start="2024-01-01",
            observation_end="2024-12-31",
        )
        client.get_series_observations(
            series_id="UNRATE",
            observation_start="2024-01-01",
            observation_end="2024-12-31",
        )

        # 第二次调用距上次起点 0s（mock 时钟不前进）→ 需补满 0.5s
        assert sleeps == [pytest.approx(0.5)]

    def test_rate_limit_wait_uses_dedicated_backoff(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """429 走专用指数退避并尊重 Retry-After；其他错误沿用通用退避."""
        monkeypatch.setattr(fred_client_module, "_RATE_LIMIT_BACKOFF_BASE_SECONDS", 5.0)
        wait_fn = fred_client_module._rate_limit_aware_wait

        def _state_with(error: BaseException, attempt: int) -> object:
            state = fred_client_module.RetryCallState(None, None, (), {})
            state.attempt_number = attempt
            state.set_exception((type(error), error, None))
            return state

        rate_limited = SourceRateLimitError(message="x", source="fred")
        assert wait_fn(_state_with(rate_limited, 1)) == 5.0
        assert wait_fn(_state_with(rate_limited, 2)) == 10.0
        assert wait_fn(_state_with(rate_limited, 9)) == 5.0 * 2**8  # 纯函数无封顶

        with_retry_after = SourceRateLimitError(message="x", source="fred")
        with_retry_after.details["retry_after_seconds"] = 7
        assert wait_fn(_state_with(with_retry_after, 1)) == 7.0

        transient = SourceFetchError(message="x", source="fred")
        assert wait_fn(_state_with(transient, 1)) == 2.0  # min=2
