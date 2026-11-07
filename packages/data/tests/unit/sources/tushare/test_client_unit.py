"""Tests for TushareClient."""

import httpx
import orjson
import pytest
import pytest_mock
import tenacity
from ditto_data.config import DataSourceSettings
from ditto_data.sources.base import (
    PaginationCorruptionError,
    SourceAuthenticationError,
    SourceConfigurationError,
    SourceFetchError,
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


@pytest.mark.parametrize(
    "message", ["必填参数, trade_date", "参数校验失败, offset", "请指定正确的接口名"]
)
def test_invalid_parameters_are_not_retried(respx_mock, fake_time, message):
    route = respx_mock.post("http://api.tushare.pro").respond(
        200, json={"code": 50101, "msg": message, "data": None}
    )
    client = TushareClient(settings=_settings())
    with pytest.raises(SourceFetchError, match=message):
        client.query("top_list", "ts_code", start_date="20261104")
    assert route.call_count == 1


@pytest.mark.parametrize("failure", ["server_error", "disconnect"])
def test_page_retry_does_not_restart_completed_pages(respx_mock, fake_time, failure):
    offsets = []

    def respond(request):
        params = orjson.loads(request.content)["params"]
        offset = params["offset"]
        offsets.append(offset)
        if offset == 100 and offsets.count(100) == 1:
            if failure == "disconnect":
                raise httpx.RemoteProtocolError(
                    "Server disconnected without sending a response.", request=request
                )
            return httpx.Response(503)
        rows = [[str(i)] for i in range(offset, min(offset + params["limit"], 101))]
        return httpx.Response(
            200, json={"code": 0, "data": {"fields": ["ts_code"], "items": rows}}
        )

    respx_mock.post("http://api.tushare.pro").mock(side_effect=respond)
    client = TushareClient(settings=_settings())
    result = client.query("fina_indicator", "ts_code", ts_code="600519.SH")
    assert result.height == 101
    assert offsets == [0, 100, 100, 101]


def test_disconnected_page_exhaustion_rejects_partial_result(respx_mock, fake_time):
    offsets = []

    def respond(request):
        params = orjson.loads(request.content)["params"]
        offset = params["offset"]
        offsets.append(offset)
        if offset == 100:
            raise httpx.RemoteProtocolError(
                "Server disconnected without sending a response.", request=request
            )
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "fields": ["ts_code"],
                    "items": [[str(i)] for i in range(100)],
                },
            },
        )

    respx_mock.post("http://api.tushare.pro").mock(side_effect=respond)
    with pytest.raises(tenacity.RetryError) as failure:
        TushareClient(settings=_settings()).query(
            "fina_indicator", "ts_code", ts_code="600519.SH"
        )
    assert isinstance(failure.value.last_attempt.exception(), SourceFetchError)
    assert offsets == [0, 100, 100, 100]


@pytest.mark.parametrize(
    "message",
    ["您请求速度过快", "请不要超过10个线程", "ip超限\uff0c请不到在多个ip同时使用"],
)
def test_transport_quota_errors_do_not_use_network_retry(respx_mock, message):
    route = respx_mock.post("http://api.tushare.pro").respond(
        200, json={"code": 50101, "msg": message, "data": None}
    )
    with pytest.raises(SourceRateLimitError, match=message):
        TushareClient(settings=_settings()).query("fund_nav", "ts_code")
    assert route.call_count == 1


def test_corrupt_page_at_retry_floor_stops(respx_mock, fake_time):
    route = respx_mock.post("http://api.tushare.pro").respond(
        200,
        json={
            "code": 0,
            "data": {
                "fields": ["ts_code"],
                "items": [[str(i)] for i in range(500)],
            },
        },
    )
    with pytest.raises(PaginationCorruptionError):
        TushareClient(settings=_settings()).query("fina_indicator", "ts_code")
    assert route.call_count == 5


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
            # 短页续探（#625）：offset=3 再取一行确认取尽
            httpx.Response(
                200,
                json={"code": 0, "msg": None, "data": {"fields": [], "items": []}},
            ),
        ]
        route = respx_mock.post("http://api.tushare.pro").mock(side_effect=pages)

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")

        assert result["cal_date"].to_list() == ["1", "2", "3"]
        assert route.call_count == 3
        second_body = orjson.loads(respx_mock.calls[1].request.content)["params"]
        assert second_body["offset"] == 2
        assert second_body["limit"] == 2
        probe_body = orjson.loads(respx_mock.calls[2].request.content)["params"]
        assert probe_body["offset"] == 3
        assert probe_body["limit"] == 1

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
        # 短页续探（#625）：末短页后 offset=2501 再取一行，空页证明取尽
        assert route.call_count == 3
        requested_limits = [
            orjson.loads(call.request.content)["params"]["limit"]
            for call in respx_mock.calls
        ]
        assert requested_limits == [2000, 2000, 1]

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

    def test_server_cap_below_documented_page_size_self_heals(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """#625 短页截断续探自愈：页宽超服务端上限时不再静默截断。

        「短页=取尽」依赖请求页宽 ≤ 服务端单响应上限。若某端点的实际上限
        低于定档页宽（#196 correctness F4 曾将其固化为已知风险面），首页
        短页会被误判取尽而静默截断。#625 起，短页后续探一行：offset 处
        出现未见过的行即截断实锤，按观测到的服务端上限降页宽续拉，
        完整取回并保持告警可见。
        """
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 9000)
        total_rows = 10202
        server_cap = 8500

        def side_effect(request: httpx.Request) -> httpx.Response:
            params = orjson.loads(request.content)["params"]
            start = min(params["offset"], total_rows)
            limit = min(params["limit"], server_cap)
            page = [[str(i)] for i in range(start, min(start + limit, total_rows))]
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": page},
                },
            )

        route = respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")

        # 截断被检测并自愈：8500 < 10202，降页宽续拉后完整取回
        assert result.height == total_rows
        request_sequence = [
            (
                orjson.loads(call.request.content)["params"]["limit"],
                orjson.loads(call.request.content)["params"]["offset"],
            )
            for call in respx_mock.calls
        ]
        assert request_sequence == [
            (9000, 0),  # 首页：短页 8500（cap < 页宽）
            (1, 8500),  # 续探：未见行 → 截断实锤
            (8500, 8500),  # 降页宽续拉：残段 1702 行短页
            (1, 10202),  # 再续探：空页 → 取尽
        ]
        assert route.call_count == 4

    def test_truncation_probe_seen_row_treated_as_exhausted(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """续探行已见于已见集合（越界回显首页形态）按取尽处理，不误判截断.

        #431 实测形态：服务端对越界 offset 回显首页。续探取回首页首行时
        判定取尽——真截断的续探行不可能与已取回行重复（一致的 offset
        分页无重叠）。回显必须含首页首行才算越界回显证据（#658 批次1
        收窄：已见非首行回显在下一测试 fail-closed）。
        """
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 2)

        def side_effect(request: httpx.Request) -> httpx.Response:
            # 回显首页：忽略 offset/limit，恒返回同两行
            rows = [["a"], ["b"]]
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": rows},
                },
            )

        route = respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")

        assert result["cal_date"].to_list() == ["a", "b"]
        # 主几何（页宽 2）：首页满页 + 回显第二页触发跨页重复守卫；
        # 换档几何（页宽 500）：首页即短页，续探取回首页首行 → 取尽收敛
        probe = orjson.loads(respx_mock.calls[-1].request.content)["params"]
        assert probe["limit"] == 1
        assert route.call_count == 4

    def test_truncation_probe_seen_non_first_row_fails_closed(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
        fake_time,
    ) -> None:
        """续探回显已见行但不含首页首行＝offset 失效，不得判取尽发布 COMPLETE.

        反例（#653/#658 批次1）：探针重复已见行若可以是任意回显位置，
        服务端忽略 offset 截断真数据时会被误判取尽。仅首页首行回显有
        #431 实测证据支撑取尽语义；其余已见行不能直接判取尽。
        #708 换档后整页续探仍连续回显，必须保持 fail-closed。
        """
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 2)

        def side_effect(request: httpx.Request) -> httpx.Response:
            params = orjson.loads(request.content)["params"]
            if params["limit"] == 1:
                # 探针恒回显第二行（已见、非首页首行）
                return httpx.Response(
                    200,
                    json={
                        "code": 0,
                        "msg": None,
                        "data": {"fields": ["cal_date"], "items": [["b"]]},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {
                        "fields": ["cal_date"],
                        "items": [["a"], ["b"]],
                    },
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        client = TushareClient(token="test_token", settings=_settings())
        with pytest.raises(PaginationCorruptionError, match="dedup-merge echo"):
            client.query("trade_cal", "cal_date")

    def test_truncation_probe_transient_failure_recovers(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
        fake_time,
    ) -> None:
        """续探瞬态失败沿既有重试传播：重试后完整取回（#653 反例一）.

        探针失败不按取尽吞掉；只重试失败探针，不重拉已成功首页。
        """
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 2)
        empty_tail = httpx.Response(
            200,
            json={"code": 0, "msg": None, "data": {"fields": [], "items": []}},
        )
        page_one = httpx.Response(
            200,
            json={
                "code": 0,
                "msg": None,
                "data": {"fields": ["cal_date"], "items": [["1"]]},
            },
        )
        respx_mock.post("http://api.tushare.pro").mock(
            side_effect=[
                page_one,
                httpx.Response(500, text="probe blew up"),
                empty_tail,
            ]
        )

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")

        assert result["cal_date"].to_list() == ["1"]

    def test_truncation_probe_persistent_failure_fails_closed(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
        fake_time,
    ) -> None:
        """续探持续失败＝无法证明取尽，最终失败不发布 COMPLETE（#653 反例二）."""
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 2)

        def side_effect(request: httpx.Request) -> httpx.Response:
            params = orjson.loads(request.content)["params"]
            if params["limit"] == 1:
                return httpx.Response(500, text="probe always down")
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [["1"]]},
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        client = TushareClient(token="test_token", settings=_settings())
        with pytest.raises(tenacity.RetryError):
            client.query("trade_cal", "cal_date")

    def test_truncation_below_page_floor_fails_closed(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
        fake_time,
    ) -> None:
        """服务端上限低于页宽下限（500）时截断无法自愈，fail-closed 拒收."""
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 2000)
        total_rows = 800
        server_cap = 499

        def side_effect(request: httpx.Request) -> httpx.Response:
            params = orjson.loads(request.content)["params"]
            start = min(params["offset"], total_rows)
            limit = min(params["limit"], server_cap)
            page = [[str(i)] for i in range(start, min(start + limit, total_rows))]
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": page},
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        client = TushareClient(token="test_token", settings=_settings())
        with pytest.raises(SourceFetchError, match="truncated below floor"):
            client.query("trade_cal", "cal_date")
        assert respx_mock.calls.call_count == 2

    def test_exact_full_page_with_schemaless_empty_tail_completes(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """页宽整除时真实服务端的越界页返回 fields=[]（零列）：必须取尽而非炸 concat."""
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 2)
        pages = [
            {"fields": ["cal_date"], "items": [["1"], ["2"]]},
            {"fields": [], "items": []},
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

    def test_empty_first_page_returns_schemaless_empty_frame(
        self,
        respx_mock,
    ) -> None:
        """首页即空（服务端 fields=[]）：返回零行帧，不发第二次请求."""
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(
                200,
                json={"code": 0, "msg": None, "data": {"fields": [], "items": []}},
            )
        )

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")

        assert result.height == 0

    def test_duplicate_page_raises_instead_of_looping(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
        fake_time,
    ) -> None:
        """服务端忽略 offset（任意几何都重发整页）时 fail-closed，不无限翻页。"""
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 2)

        def side_effect(request: httpx.Request) -> httpx.Response:
            # 恒满页：无论 limit/offset 都返回 limit 行相同内容——真·offset
            # 损坏在主几何与换档几何（2-1000 下限 500）上都触发跨页重复。
            params = orjson.loads(request.content)["params"]
            rows = [["dup"] for _ in range(params["limit"])]
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": rows},
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        client = TushareClient(token="test_token", settings=_settings())
        # 两种几何耗尽即拒绝，不重跑已证实损坏的完整查询。
        with pytest.raises(PaginationCorruptionError, match="duplicate rows"):
            client.query("trade_cal", "cal_date")
        assert respx_mock.calls.call_count == 5

    def test_cross_page_duplicates_retry_with_shifted_page_size(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """排序不稳定在特定边界确定性复发时，换页宽几何重试后完整取回。

        #196 实测形态：balancesheet_vip 2020Q4 期在 offset=9000 恒重 1 行、
        offset=8000 干净（10869 行全量）。换档重试保持守卫语义——第二几何
        若同样损坏仍会拒收。
        """
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 3)
        total_rows = [str(i) for i in range(5)]  # 主几何 3+2 两页，边界行不稳

        def side_effect(request: httpx.Request) -> httpx.Response:
            params = orjson.loads(request.content)["params"]
            limit, offset = params["limit"], params["offset"]
            if limit == 3:
                # 主几何：第二页重复第一页首行（排序不稳定指纹）
                page = (
                    total_rows[:limit]
                    if offset == 0
                    else [total_rows[0], *total_rows[limit : limit + 2]]
                )
            else:
                # 换档几何（3-1000 下限 500）：单页短页干净收尾
                page = total_rows[:limit]
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [[r] for r in page]},
                },
            )

        route = respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")

        assert result["cal_date"].to_list() == total_rows
        requested_limits = [
            orjson.loads(call.request.content)["params"]["limit"]
            for call in respx_mock.calls
        ]
        assert requested_limits == [3, 3, 500, 1]
        assert route.call_count == 4

    def test_small_dataset_with_offset_ignoring_tail_converges_at_shifted_geometry(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """真总量小于页宽 + 越界页回显首页：主几何误报守卫，换档几何收敛。

        服务端真总量 2 行但对越界 offset 回显首页（offset 损坏形态）。
        主几何（页宽 2）第二页收到重复行触发守卫；换档几何（页宽 500）
        首页即短页取尽——返回的正是全量 2 行，无数据损失。换档重试只
        会在「短页=取尽」可证明完整时收敛，仍非绕过守卫的通道（上一
        测试的恒满页形态两几何都拒收）。
        """
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 2)

        def side_effect(request: httpx.Request) -> httpx.Response:
            rows = [["a"], ["b"]]
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": rows},
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")

        assert result["cal_date"].to_list() == ["a", "b"]

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

        # 每次查询末尾的短页续探（#625）取回已见行 → 取尽，limit=1
        requested_limits = [
            orjson.loads(call.request.content)["params"]["limit"]
            for call in respx_mock.calls
        ]
        assert requested_limits == [6000, 1, 2000, 1, 2000, 1]
        assert route.call_count == 6

    def test_resolve_page_size_uses_documented_contract(self) -> None:
        """端点分页契约表与官方专页一致。"""
        assert resolve_page_size("daily") == 6000
        assert resolve_page_size("fund_daily") == 5000
        assert resolve_page_size("fund_adj") == 2000
        assert resolve_page_size("index_global") == 4000
        # 单次上限低于保守默认 2000 的端点（超限会静默截断，#507 G3）
        assert resolve_page_size("pledge_stat") == 1000
        assert resolve_page_size("stock_st") == 1000
        # 独占串行实测稳定（#196：并发/进程重叠下的全败结论已推翻）
        assert resolve_page_size("fina_indicator_vip") == 10000
        # 实测全市场日频端点单日 5000-5400 行一页拉尽（#196 回补提速）
        assert resolve_page_size("adj_factor") == 10000
        assert resolve_page_size("stk_limit") == 10000
        assert resolve_page_size("moneyflow") == 10000
        assert resolve_page_size("cyq_perf") == 10000
        assert resolve_page_size("daily_basic") == 10000
        assert resolve_page_size("bak_basic") == 10000
        # 官方专页核实（#625）：margin_detail 6000 / fund_share 2000
        assert resolve_page_size("margin_detail") == 6000
        assert resolve_page_size("fund_share") == 2000
        assert resolve_page_size("unknown_endpoint") == 2000

    def test_in_page_duplicate_rows_pass_through_with_warning(
        self,
        respx_mock,
    ) -> None:
        """同响应内整行重复放行并告警——事件型数据集存在真实业务冗余行.

        告警走 loguru（不经过 stdlib logging），此处只断言数据放行行为。
        """
        page = {
            "code": 0,
            "msg": None,
            "data": {"fields": ["cal_date"], "items": [["1"], ["1"], ["2"]]},
        }
        respx_mock.post("http://api.tushare.pro").mock(
            return_value=httpx.Response(200, json=page)
        )

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")
        assert result["cal_date"].to_list() == ["1", "1", "2"]

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

        # Assert：主请求 + 短页续探（#625）各过一次限流
        assert wait_spy.call_count == 2

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
        assert call_count == 3  # 网络错误重试成功 + 短页续探（#625）
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
        assert call_count == 3  # 5xx 重试成功 + 短页续探（#625）
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


class TestPaginationDedupMerge:
    """#672：换档重试几何的跨页重叠去重合并与零新行回显硬拦."""

    @pytest.mark.parametrize("tail_only", [False, True])
    def test_seen_tail_probe_continues_until_verified_exhaustion(
        self, respx_mock, fake_time, tail_only: bool
    ) -> None:
        """#708: a repeated single-row probe can precede a page with new rows."""
        total = 48 if tail_only else 3145

        def respond(request: httpx.Request) -> httpx.Response:
            params = orjson.loads(request.content)["params"]
            limit, offset = params["limit"], params["offset"]
            if limit == 1:
                values = (
                    [40 if tail_only else offset - 10]
                    if offset in ({48} if tail_only else {990, 1990})
                    else []
                )
            elif offset == 0:
                values = list(range(min(total, 1990 if limit == 2000 else 990)))
            elif tail_only and offset == 48:
                values = list(range(40, 48))
            elif not tail_only and offset == 990:
                values = list(range(980, 1980))
            elif not tail_only and offset == 1990:
                values = list(range(1970, 2970))
            elif not tail_only and offset == 2990:
                values = list(range(2960, total))
            else:
                values = []
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["nav_date"], "items": [[v] for v in values]},
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=respond)
        with TushareClient(settings=_settings()) as client:
            result = client.query("fund_nav", "nav_date", ts_code="510300.SH")

        assert sorted(result["nav_date"].to_list()) == list(range(total))
        requests = [
            orjson.loads(call.request.content)["params"] for call in respx_mock.calls
        ]
        assert {
            "limit": 1000,
            "offset": 48 if tail_only else 990,
            "ts_code": "510300.SH",
        } in requests
        assert requests[-1]["offset"] == (56 if tail_only else 3175)

    def test_cross_page_overlap_at_both_geometries_dedup_merges(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """主几何与换档几何都边界重叠时,换档几何去重合并完整取回.

        #661 B2 现场/#629 回补形态:etf_nav fund_nav / forecast 端点的
        排序不稳定边界重叠换档后仍复发——修复前 force 通道被完全阻断。
        """
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 3)
        total_rows = [str(i) for i in range(990)]  # 换档几何 500×2 页

        def side_effect(request: httpx.Request) -> httpx.Response:
            params = orjson.loads(request.content)["params"]
            limit, offset = params["limit"], params["offset"]
            if limit == 3:
                # 主几何：第二页重复第一页首行（严格几何 fail-closed 触发换档）
                page = (
                    total_rows[:limit]
                    if offset == 0
                    else [total_rows[0], *total_rows[limit : limit + 2]]
                )
            elif offset == 0:
                page = total_rows[:500]
            elif offset == 500:
                # 换档几何第二页：头部 10 行与第一页尾部重叠（边界抖动）
                page = total_rows[490:990]
            else:
                page = []
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [[r] for r in page]},
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")

        assert sorted(result["cal_date"].to_list()) == sorted(total_rows)
        assert result.height == 990
        requested_limits = [
            orjson.loads(call.request.content)["params"]["limit"]
            for call in respx_mock.calls
        ]
        assert requested_limits == [3, 3, 500, 500, 500]

    def test_zero_new_page_echo_at_shifted_geometry_fails_closed(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
        fake_time,
    ) -> None:
        """换档几何整页零新行连续两次=服务端忽略 offset 的整页回显,硬拦.

        去重合并只自愈边界重叠（页内有新行推进）；整页回显无收敛
        可能,维持 fail-closed 不无限翻页。
        """
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 3)
        echo_rows = [str(i) for i in range(500)]

        def side_effect(request: httpx.Request) -> httpx.Response:
            params = orjson.loads(request.content)["params"]
            limit, offset = params["limit"], params["offset"]
            if limit == 3:
                page = echo_rows[:3] if offset == 0 else [echo_rows[0], *echo_rows[3:5]]
            else:
                # 换档几何：任何 offset 都回显同一整页（真·offset 失效）
                page = echo_rows[:500]
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [[r] for r in page]},
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        client = TushareClient(token="test_token", settings=_settings())
        with pytest.raises(PaginationCorruptionError, match="dedup-merge echo"):
            client.query("trade_cal", "cal_date")

    def test_echo_probes_reset_on_clean_page_between_echoes(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """correctness F1:交替「整页回显/干净推进页」不累加成连续回显.

        回显连续计数在干净页（无跨页重复）上重置——隔页回显是排序
        不稳定的常见形态,不应按连续两次硬拦。
        """
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 3)
        total_rows = [str(i) for i in range(1000)]

        def side_effect(request: httpx.Request) -> httpx.Response:
            params = orjson.loads(request.content)["params"]
            limit, offset = params["limit"], params["offset"]
            if limit == 3:
                page = (
                    total_rows[:3] if offset == 0 else [total_rows[0], *total_rows[3:5]]
                )
            elif offset == 0:
                page = total_rows[:500]
            elif offset == 500:
                page = total_rows[:500]  # 整页回显(零新行)→探测推进
            elif offset == 1000:
                page = total_rows[500:1000]  # 干净推进页(重置回显计数)
            elif offset == 1500:
                page = total_rows[500:1000]  # 再次整页回显(计数=1,不硬拦)
            else:
                page = []
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [[r] for r in page]},
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")

        assert sorted(result["cal_date"].to_list()) == sorted(total_rows)

    def test_zero_new_short_page_returns_deduped_prefix_with_summary(
        self,
        respx_mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """correctness F2 留档:零新行短页按已见前缀返回(接受残差).

        排序不稳定同时跳行是 offset 翻页的固有盲区(旧代码同级不感知);
        去重合并仅在严格几何已 fail 后运行——通道可用性优先于该残差。
        终态 summary 事件走 loguru(caplog 不捕获),此处断言数据行为;
        summary 行为由 tushare_pagination_dedup_merge_summary 事件锁定
        于代码路径,worker.log 可观测。
        """
        monkeypatch.setitem(pagination._DOCUMENTED_PAGE_SIZES, "trade_cal", 3)
        total_rows = [str(i) for i in range(600)]

        def side_effect(request: httpx.Request) -> httpx.Response:
            params = orjson.loads(request.content)["params"]
            limit, offset = params["limit"], params["offset"]
            if limit == 3:
                page = (
                    total_rows[:3] if offset == 0 else [total_rows[0], *total_rows[3:5]]
                )
            elif offset == 0:
                page = total_rows[:500]
            elif offset == 500:
                # 零新行短页:全部已见(服务端跳过了未交付行)
                page = total_rows[400:500]
            else:
                page = []
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": None,
                    "data": {"fields": ["cal_date"], "items": [[r] for r in page]},
                },
            )

        respx_mock.post("http://api.tushare.pro").mock(side_effect=side_effect)

        client = TushareClient(token="test_token", settings=_settings())
        result = client.query("trade_cal", "cal_date")

        # 接受残差:返回已见前缀 500/600,不 raise;worker.log 中应见
        # dedup-merge 与 summary 事件(loguru 不入 caplog,数据行为为准)
        assert result.height == 500
        assert result["cal_date"].to_list() == [str(i) for i in range(500)]
