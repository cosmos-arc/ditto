"""fuyao 冗余源单测 — client 信封 fail-closed 与帧转换."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import httpx
import polars as pl
import pytest
import respx
from ditto_data.sources.base import SourceConfigurationError, SourceFetchError
from ditto_data.sources.fuyao.client import (
    FuyaoClient,
    date_to_ms,
    ms_to_date,
)
from ditto_data.sources.fuyao.source import FuyaoSource, _to_thscode

_BASE = "https://fuyao.aicubes.cn"


def _client() -> FuyaoClient:
    return FuyaoClient(base_url=_BASE, api_key="not_a_secret")


@pytest.mark.unit
class TestFuyaoTimeConversions:
    """北京时区毫秒戳换算."""

    def test_roundtrip(self) -> None:
        assert ms_to_date(date_to_ms(date(2025, 8, 18))) == date(2025, 8, 18)

    def test_known_dump_value(self) -> None:
        # 冒烟实测：600519.SH 2025-08-18 的 date_ms
        assert ms_to_date(1755446400000) == date(2025, 8, 18)

    def test_ticker_suffix(self) -> None:
        assert _to_thscode("600519") == "600519.SH"
        assert _to_thscode("000001") == "000001.SZ"
        assert _to_thscode("300750") == "300750.SZ"
        assert _to_thscode("510300") == "510300.SH"
        assert _to_thscode("830799") == "830799.BJ"
        assert _to_thscode("600519.SH") == "600519.SH"

    def test_ticker_suffix_unknown_prefix_rejected(self) -> None:
        """#516：未识别前缀（900/200xxx B 股、空串）显式拒绝，不静默落 .SZ."""
        for bad_ticker in ("900901", "200001", "739001", ""):
            with pytest.raises(SourceFetchError, match="前缀未识别"):
                _to_thscode(bad_ticker)


@pytest.mark.unit
class TestFuyaoClientRateLimit:
    """#516 限流治理 — 节流 + 429/4001 退避重试 + fail-closed 保持."""

    @respx.mock
    def test_code_4001_retried_then_succeeds_and_interval_adapts(self) -> None:
        """code=4001 退避后重试成功；节流间隔自适应翻倍（官方：降频重试）."""
        endpoint = respx.get(f"{_BASE}/api/x").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"code": 4001, "message": "rate limit", "data": None},
                ),
                httpx.Response(
                    200, json={"code": 0, "message": "success", "data": {"item": [1]}}
                ),
            ]
        )
        client = FuyaoClient(base_url=_BASE, api_key="k", min_request_interval=0.1)

        assert client.get("/api/x") == {"item": [1]}
        assert endpoint.call_count == 2
        assert client._throttle.min_interval == pytest.approx(0.2)

    @respx.mock
    def test_code_4001_exhaustion_fails_closed(self) -> None:
        """重试耗尽仍 4001 → 按信封错误 fail-closed（隔离语义不变）."""
        endpoint = respx.get(f"{_BASE}/api/x").mock(
            return_value=httpx.Response(
                200, json={"code": 4001, "message": "rate limit", "data": None}
            )
        )

        with pytest.raises(SourceFetchError, match="code=4001"):
            FuyaoClient(base_url=_BASE, api_key="k").get("/api/x")

        assert endpoint.call_count == 4  # 首发 + 3 次退避重试

    @respx.mock
    def test_http_429_retried_like_4001(self) -> None:
        """HTTP 429 与 code=4001 同为限流信号（官方 llms.txt），退避重试."""
        endpoint = respx.get(f"{_BASE}/api/x").mock(
            side_effect=[
                httpx.Response(429, json={"code": 4001, "message": "limit"}),
                httpx.Response(
                    200, json={"code": 0, "message": "success", "data": {"item": []}}
                ),
            ]
        )

        assert _client().get("/api/x") == {"item": []}
        assert endpoint.call_count == 2

    @respx.mock
    def test_http_error_wrapped_without_retry(self) -> None:
        """非限流 HTTP 错误包装为 SourceFetchError（原为裸 httpx 错误）."""
        endpoint = respx.get(f"{_BASE}/api/x").mock(
            return_value=httpx.Response(500, text="internal error")
        )

        with pytest.raises(SourceFetchError, match="http error: 500"):
            _client().get("/api/x")

        assert endpoint.call_count == 1

    @respx.mock
    def test_network_error_wrapped(self) -> None:
        """连接/超时错误包装为 SourceFetchError（对账按标的隔离只捕该类）."""
        respx.get(f"{_BASE}/api/x").mock(side_effect=httpx.ConnectError("refused"))

        with pytest.raises(SourceFetchError, match="network error"):
            _client().get("/api/x")

    @respx.mock
    def test_non_json_body_wrapped(self) -> None:
        """200 非 JSON 响应体 → 包装为 SourceFetchError，不裸抛（#516）."""
        endpoint = respx.get(f"{_BASE}/api/x").mock(
            return_value=httpx.Response(200, text="<html>bad gateway</html>")
        )

        with pytest.raises(SourceFetchError, match="non-JSON"):
            _client().get("/api/x")

        assert endpoint.call_count == 1

    @respx.mock
    def test_non_object_envelope_rejected(self) -> None:
        """200 JSON 但信封不是对象 → 拒绝，不裸抛 AttributeError."""
        respx.get(f"{_BASE}/api/x").mock(
            return_value=httpx.Response(200, json=[1, 2, 3])
        )

        with pytest.raises(SourceFetchError, match="non-object JSON"):
            _client().get("/api/x")

    def test_request_path_is_throttled(
        self, respx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """公开 get 路径两次调用间真实走节流（mock 时钟，删调用即失败）."""
        from ditto_data.sources import throttle as throttle_module

        respx_mock.get(f"{_BASE}/api/x").mock(
            return_value=httpx.Response(
                200, json={"code": 0, "message": "success", "data": {"item": []}}
            )
        )
        client = FuyaoClient(base_url=_BASE, api_key="k", min_request_interval=0.1)
        sleeps: list[float] = []
        clock = {"now": 100.0}

        def _fake_monotonic() -> float:
            return clock["now"]

        def _fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock["now"] += seconds

        monkeypatch.setattr(throttle_module.time, "monotonic", _fake_monotonic)
        monkeypatch.setattr(throttle_module.time, "sleep", _fake_sleep)

        assert client.get("/api/x") == {"item": []}
        assert client.get("/api/x") == {"item": []}

        # 第二次调用距上次起点 0s（mock 时钟不前进）→ 需补满 0.1s
        assert sleeps == [pytest.approx(0.1)]


@pytest.mark.unit
class TestFuyaoClientEnvelope:
    """信封校验 fail-closed."""

    def test_missing_api_key_is_configuration_error(self) -> None:
        with pytest.raises(SourceConfigurationError):
            FuyaoClient(api_key="")

    @respx.mock
    def test_success_returns_data(self) -> None:
        respx_mock = respx.get(f"{_BASE}/api/x").mock(
            return_value=httpx.Response(
                200, json={"code": 0, "message": "success", "data": {"item": []}}
            )
        )
        assert _client().get("/api/x") == {"item": []}
        assert respx_mock.called

    @respx.mock
    def test_business_error_raises(self) -> None:
        respx.get(f"{_BASE}/api/x").mock(
            return_value=httpx.Response(
                200, json={"code": 2001, "message": "invalid key", "data": None}
            )
        )
        with pytest.raises(SourceFetchError, match="code=2001"):
            _client().get("/api/x")

    @respx.mock
    def test_missing_data_payload_raises(self) -> None:
        respx.get(f"{_BASE}/api/x").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "ok"})
        )
        with pytest.raises(SourceFetchError, match="no data payload"):
            _client().get("/api/x")


def _historical_items() -> list[dict[str, object]]:
    return [
        {
            "date_ms": date_to_ms(date(2025, 8, 18)),
            "open_price": 10.0,
            "high_price": 11.0,
            "low_price": 9.5,
            "close_price": 10.5,
            "volume": 100.0,
            "turnover": 1050.0,
        },
        {
            "date_ms": date_to_ms(date(2025, 8, 19)),
            "open_price": 10.5,
            "high_price": 11.5,
            "low_price": 10.0,
            "close_price": 11.0,
            "volume": 200.0,
            "turnover": 2200.0,
        },
    ]


def _bar(date_ms: int, close: float) -> dict[str, object]:
    return {
        "date_ms": date_ms,
        "open_price": close,
        "high_price": close,
        "low_price": close,
        "close_price": close,
        "volume": 100.0,
        "turnover": close * 100.0,
    }


def _adjustment_dump_rows() -> dict[str, list[object]]:
    return {
        "thscode": ["600519.SH", "000001.SZ"],
        "ticker": ["600519", "000001"],
        "currency": ["CNY", "CNY"],
        "ex_date_ms": [
            date_to_ms(date(2025, 6, 25)),
            date_to_ms(date(2025, 7, 10)),
        ],
        "dividend_per_share": [30.0, 0.1],
        "per_share_bonus": [0.0, None],
        "allotment_ratio": [None, None],
        "allotment_price": [None, None],
    }


@pytest.mark.unit
class TestFuyaoAdjustmentFactorsFrame:
    """#438：复权因子事件流 dump → 事件帧（公司行动原始口径）."""

    def test_event_semantics_kept_without_unit_scaling(self, tmp_path: Path) -> None:
        dump = tmp_path / "adjustment-factors.parquet"
        pl.DataFrame(_adjustment_dump_rows()).write_parquet(dump)

        frame = FuyaoSource.adjustment_factors_frame(dump)

        assert frame.columns == [
            "ticker",
            "trade_date",
            "dividend_per_share",
            "per_share_bonus",
            "allotment_ratio",
            "allotment_price",
        ]
        # 裸码从 thscode 推导，不信任展示列
        assert frame["ticker"].to_list() == ["600519", "000001"]
        assert frame["trade_date"].to_list() == [date(2025, 6, 25), date(2025, 7, 10)]
        # 事件字段原样保留：股/元 → 手/千元换算不适用于公司行动事件
        assert frame["dividend_per_share"].to_list() == [30.0, 0.1]

    def test_currency_contract_violation_rejected(self, tmp_path: Path) -> None:
        rows = _adjustment_dump_rows()
        rows["currency"] = ["CNY", "USD"]
        dump = tmp_path / "adjustment-factors.parquet"
        pl.DataFrame(rows).write_parquet(dump)

        with pytest.raises(SourceFetchError, match="currency"):
            FuyaoSource.adjustment_factors_frame(dump)

    def test_missing_event_column_rejected(self, tmp_path: Path) -> None:
        rows = _adjustment_dump_rows()
        del rows["allotment_price"]
        dump = tmp_path / "adjustment-factors.parquet"
        pl.DataFrame(rows).write_parquet(dump)

        with pytest.raises(SourceFetchError, match="allotment_price"):
            FuyaoSource.adjustment_factors_frame(dump)


@pytest.mark.unit
class TestFuyaoRestWindowSharding:
    """#433：大窗口 REST 分片、覆盖校验与合法空区分."""

    def _source_with_windows(
        self, windows: dict[tuple[date, date], list[dict[str, object]]]
    ) -> tuple[FuyaoSource, MagicMock]:
        client = MagicMock()

        def fake_get(path: str, params: dict[str, object] | None = None):
            assert params is not None
            start = ms_to_date(int(cast("int", params["start"])))
            end = ms_to_date(int(cast("int", params["end"])))
            for (win_start, win_end), items in windows.items():
                if (win_start, win_end) == (start, end):
                    return {"item": items}
            raise AssertionError(f"unexpected window {(start, end)}")

        client.get.side_effect = fake_get
        return FuyaoSource(client=client), client

    def test_multi_year_request_is_sharded_into_safe_windows(self) -> None:
        """10 年请求按 ≤3 年窗口分片（尾部静默截断防护）."""
        w1 = (date(2015, 1, 1), date(2017, 12, 30))
        w2 = (date(2017, 12, 31), date(2020, 12, 29))
        w3 = (date(2020, 12, 30), date(2023, 12, 29))
        w4 = (date(2023, 12, 30), date(2024, 12, 31))
        bars = {
            w1: [_bar(date_to_ms(date(2015, 1, 5)), 10.0)],
            w2: [_bar(date_to_ms(date(2018, 1, 3)), 11.0)],
            w3: [_bar(date_to_ms(date(2021, 1, 4)), 12.0)],
            w4: [_bar(date_to_ms(date(2024, 1, 2)), 13.0)],
        }
        source, client = self._source_with_windows(bars)

        frame = source.fetch_stock_daily(
            source_ticker="600519", start_date="2015-01-01", end_date="2024-12-31"
        )

        assert client.get.call_count == 4
        assert frame["close"].to_list() == [10.0, 11.0, 12.0, 13.0]
        # 分窗边界不丢 pre_close：窗口首条的 pre_close 是上一窗口末根收盘
        assert frame["pre_close"].to_list() == [None, 10.0, 11.0, 12.0]

    def test_out_of_window_bar_raises(self) -> None:
        """响应日期越窗 = 契约违约，fail-closed 而非静默截断."""
        window = (date(2024, 1, 1), date(2024, 12, 31))
        source, _ = self._source_with_windows(
            {window: [_bar(date_to_ms(date(2023, 12, 29)), 10.0)]}
        )

        with pytest.raises(SourceFetchError, match="out-of-window"):
            source.fetch_stock_daily(
                source_ticker="600519", start_date="2024-01-01", end_date="2024-12-31"
            )

    def test_duplicate_trade_date_in_response_raises(self) -> None:
        """同窗响应内重复交易日（不前进/重复键）fail-closed.

        分窗不相交，跨窗重复必然先以越窗形态被拦截；重复键守卫覆盖
        单窗响应内重复与服务端 offset 类异常。
        """
        window = (date(2024, 1, 1), date(2026, 12, 30))
        dup_ms = date_to_ms(date(2025, 6, 3))
        source, _ = self._source_with_windows(
            {window: [_bar(dup_ms, 10.0), _bar(dup_ms, 11.0)]}
        )

        with pytest.raises(SourceFetchError, match="duplicate"):
            source.fetch_stock_daily(
                source_ticker="600519", start_date="2024-01-01", end_date="2027-12-31"
            )

    def test_empty_window_is_legitimate_not_failure(self) -> None:
        """空窗（停牌/上市前/退市后）合法：返回有数据窗口的行，不报错."""
        w1 = (date(2024, 1, 1), date(2026, 12, 30))
        w2 = (date(2026, 12, 31), date(2027, 12, 31))  # 末期退市（合法空窗）
        source, _ = self._source_with_windows(
            {w1: [_bar(date_to_ms(date(2025, 6, 3)), 10.0)], w2: []}
        )

        frame = source.fetch_stock_daily(
            source_ticker="600519", start_date="2024-01-01", end_date="2027-12-31"
        )

        assert frame.height == 1
        assert frame["close"].to_list() == [10.0]

    def test_all_empty_returns_typed_empty_frame(self) -> None:
        """全空（如请求未来区间）返回 schema 一致空帧，不伪造成功."""
        w1 = (date(2024, 1, 1), date(2024, 12, 31))
        source, _ = self._source_with_windows({w1: []})

        frame = source.fetch_stock_daily(
            source_ticker="600519", start_date="2024-01-01", end_date="2024-12-31"
        )

        assert frame.is_empty()
        assert "knowledge_date" in frame.columns


@pytest.mark.unit
class TestFuyaoSourceBars:
    """原始日线帧转换与两模式校验."""

    def _source_with_items(
        self, items: list[dict[str, object]]
    ) -> tuple[FuyaoSource, MagicMock]:
        client = MagicMock()
        client.get.return_value = {"item": items}
        return FuyaoSource(client=client), client

    def test_ticker_mode_builds_source_schema_frame(self) -> None:
        source, client = self._source_with_items(_historical_items())

        frame = source.fetch_stock_daily(
            source_ticker="600519", start_date="2025-08-18", end_date="2025-08-19"
        )

        assert frame["source_ticker"].unique().to_list() == ["600519.SH"]
        assert frame["trade_date"].to_list() == [date(2025, 8, 18), date(2025, 8, 19)]
        assert frame["pre_close"].to_list() == [None, 10.5]
        assert frame["knowledge_date"].to_list() == [
            date(2025, 8, 19),
            date(2025, 8, 20),
        ]
        assert frame["pct_change"][1] == pytest.approx(4.761904, abs=1e-4)
        # 原始价：REST 请求显式 adjust=none
        kwargs = client.get.call_args.kwargs
        assert kwargs["params"]["adjust"] == "none"
        assert kwargs["params"]["thscode"] == "600519.SH"

    def test_ticker_mode_empty_items_returns_typed_empty_frame(self) -> None:
        source, _ = self._source_with_items([])

        frame = source.fetch_stock_daily(
            source_ticker="600519", start_date="2025-08-18", end_date="2025-08-18"
        )

        assert frame.is_empty()
        assert "knowledge_date" in frame.columns

    def test_mode_validation(self) -> None:
        source, _ = self._source_with_items([])
        with pytest.raises(ValueError, match="互斥"):
            source.fetch_stock_daily(trade_date="2025-08-18", source_ticker="600519.SH")
        with pytest.raises(ValueError, match="必须指定"):
            source.fetch_stock_daily()
        with pytest.raises(ValueError, match="start_date 和 end_date"):
            source.fetch_stock_daily(source_ticker="600519.SH")

    def test_reconciliation_frame_uses_bare_ticker(self) -> None:
        # 对账单日窗：响应只含请求日 bar（窗外 bar 属契约违约，见分窗测试）
        source, _ = self._source_with_items([_historical_items()[1]])

        frame = source.fetch_stock_daily_bars(["600519"], "2025-08-19")

        assert frame.columns == [
            "ticker",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
        ]
        assert frame["ticker"].to_list() == ["600519"]
        assert frame["trade_date"].to_list() == [date(2025, 8, 19)]
        assert frame["close"].to_list() == [11.0]
        # 单位归一：股→手(÷100)、元→千元(÷1000)
        assert frame["volume"].to_list() == [200.0 / 100]
        assert frame["amount"].to_list() == [2200.0 / 1000]

    def test_market_mode_filters_dump_to_target_date(self, tmp_path: Path) -> None:
        raw = pl.DataFrame(
            {
                "thscode": ["600519.SH", "600519.SH", "000001.SZ"],
                "currency": ["CNY"] * 3,
                "interval": ["1d"] * 3,
                "adjusted": ["none"] * 3,
                "date_ms": [
                    date_to_ms(date(2025, 8, 18)),
                    date_to_ms(date(2025, 8, 19)),
                    date_to_ms(date(2025, 8, 19)),
                ],
                "open_price": [10.0, 10.5, 12.0],
                "high_price": [11.0, 11.5, 13.0],
                "low_price": [9.5, 10.0, 11.5],
                "close_price": [10.5, 11.0, 12.5],
                "volume": [100.0, 200.0, 300.0],
                "turnover": [1050.0, 2200.0, 3750.0],
            }
        )
        dump = tmp_path / "daily-k-10d.parquet"
        raw.write_parquet(dump)

        source = FuyaoSource(client=MagicMock())
        downloaded: list[Path] = []

        def fake_download(kind: str, dest: Path) -> Path:
            downloaded.append(dest)
            raw.write_parquet(dest)
            return dest

        source.download_market_dump = fake_download  # type: ignore[method-assign]

        frame = source.fetch_stock_daily("2025-08-19")

        assert downloaded[0].suffix == ".parquet"
        assert sorted(frame["source_ticker"].to_list()) == [
            "000001.SZ",
            "600519.SH",
        ]
        # dump 窗口内推导 pre_close
        assert frame.filter(pl.col("source_ticker") == "600519.SH")[
            "pre_close"
        ].to_list() == [10.5]
        assert frame.filter(pl.col("source_ticker") == "000001.SZ")[
            "pre_close"
        ].to_list() == [None]


def _daily_k_rows() -> dict[str, list[object]]:
    return {
        "thscode": ["600519.SH", "600519.SH", "000001.SZ"],
        "currency": ["CNY"] * 3,
        "interval": ["1d"] * 3,
        "adjusted": ["none"] * 3,
        "date_ms": [
            date_to_ms(date(2025, 8, 18)),
            date_to_ms(date(2025, 8, 19)),
            date_to_ms(date(2025, 8, 19)),
        ],
        "open_price": [10.0, 10.5, 12.0],
        "high_price": [11.0, 11.5, 13.0],
        "low_price": [9.5, 10.0, 11.5],
        "close_price": [10.5, 11.0, 12.5],
        "volume": [100.0, 200.0, 300.0],
        "turnover": [1050.0, 2200.0, 3750.0],
    }


def _write_dump(tmp_path: Path, rows: dict[str, list[object]]) -> Path:
    dump = tmp_path / "daily-k.parquet"
    pl.DataFrame(rows).write_parquet(dump)
    return dump


@pytest.mark.unit
class TestDailyKFrameConstantValidation:
    """#439：常量列先验证再删列，不凭注释保证口径."""

    def test_bad_currency_rejected(self, tmp_path: Path) -> None:
        rows = _daily_k_rows()
        rows["currency"] = ["CNY", "USD", "CNY"]
        dump = _write_dump(tmp_path, rows)

        with pytest.raises(SourceFetchError, match="currency"):
            FuyaoSource.daily_k_frame(dump)

    def test_forward_adjusted_rejected(self, tmp_path: Path) -> None:
        # ETF 红线同源：复权口径 dump 不进原始价管道
        rows = _daily_k_rows()
        rows["adjusted"] = ["forward"] * 3
        dump = _write_dump(tmp_path, rows)

        with pytest.raises(SourceFetchError, match="adjusted"):
            FuyaoSource.daily_k_frame(dump)

    def test_missing_constant_column_rejected(self, tmp_path: Path) -> None:
        rows = _daily_k_rows()
        del rows["interval"]
        dump = _write_dump(tmp_path, rows)

        with pytest.raises(SourceFetchError, match="interval"):
            FuyaoSource.daily_k_frame(dump)


@pytest.mark.unit
class TestFuyaoDailyKDumpFetcher:
    """#439：daily-k 本地 dump 回填 fetcher."""

    def test_fetch_filters_date_and_reports_coverage(self, tmp_path: Path) -> None:
        from ditto_data.sources.fuyao.source import FuyaoDailyKDumpFetcher

        fetcher = FuyaoDailyKDumpFetcher(_write_dump(tmp_path, _daily_k_rows()))

        assert fetcher.coverage == (date(2025, 8, 18), date(2025, 8, 19))
        day = fetcher.fetch_stock_daily(trade_date="2025-08-19")
        assert sorted(day["source_ticker"].to_list()) == [
            "000001.SZ",
            "600519.SH",
        ]

    def test_beijing_exchange_ticker_roundtrip(self, tmp_path: Path) -> None:
        """北交所代码（8/4 前缀）在 dump 取数与身份后缀推导同构."""
        from ditto_data.sources.fuyao.source import FuyaoDailyKDumpFetcher

        rows = _daily_k_rows()
        rows["thscode"] = rows["thscode"] + ["830799.BJ"]
        for key in ("currency", "interval", "adjusted"):
            rows[key] = rows[key] + [rows[key][0]]
        rows["date_ms"] = rows["date_ms"] + [date_to_ms(date(2025, 8, 19))]
        for key in (
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
            "turnover",
        ):
            rows[key] = rows[key] + [rows[key][0]]
        fetcher = FuyaoDailyKDumpFetcher(_write_dump(tmp_path, rows))

        day = fetcher.fetch_stock_daily(trade_date="2025-08-19")

        assert "830799.BJ" in day["source_ticker"].to_list()
        assert _to_thscode("830799") == "830799.BJ"

    def test_fetch_out_of_coverage_returns_typed_empty(self, tmp_path: Path) -> None:
        from ditto_data.sources.fuyao.source import FuyaoDailyKDumpFetcher

        fetcher = FuyaoDailyKDumpFetcher(_write_dump(tmp_path, _daily_k_rows()))

        empty = fetcher.fetch_stock_daily(trade_date="2030-01-01")

        assert empty.is_empty()
        assert "knowledge_date" in empty.columns

    def test_duplicate_primary_keys_reject_backfill(self, tmp_path: Path) -> None:
        from ditto_data.sources.fuyao.source import FuyaoDailyKDumpFetcher

        rows = _daily_k_rows()
        dup_ms = date_to_ms(date(2025, 8, 19))
        for key in rows:
            rows[key] = rows[key] + [rows[key][1]]  # 复制 600519 8-19 行
        rows["date_ms"][-1] = dup_ms
        dump = _write_dump(tmp_path, rows)

        with pytest.raises(SourceFetchError, match="重复"):
            FuyaoDailyKDumpFetcher(dump)

    def test_non_date_mode_rejected(self, tmp_path: Path) -> None:
        from ditto_data.sources.fuyao.source import FuyaoDailyKDumpFetcher

        fetcher = FuyaoDailyKDumpFetcher(_write_dump(tmp_path, _daily_k_rows()))

        with pytest.raises(SourceFetchError, match="单日"):
            fetcher.fetch_stock_daily(
                source_ticker="600519", start_date="2025-08-18", end_date="2025-08-19"
            )


def _index_item(d: date, close: float = 3842.19) -> dict[str, object]:
    return {
        "date_ms": date_to_ms(d),
        "open_price": close - 3.0,
        "high_price": close + 9.0,
        "low_price": close - 9.0,
        "close_price": close,
        "volume": 41_456_025_000.0,
        "turnover": 679_398_990_000.0,
    }


def _source_by_thscode(
    responses: dict[str, object],
) -> FuyaoSource:
    """按 thscode 路由 mock 响应（dict=正常 data；Exception=抛错）。"""
    client = MagicMock()

    def fake_get(path: str, params: dict[str, object] | None = None):
        assert params is not None
        key = str(params.get("thscode", ""))
        if key not in responses:
            raise AssertionError(f"unexpected thscode {key} on {path}")
        value = responses[key]
        if isinstance(value, Exception):
            raise value
        return value

    client.get.side_effect = fake_get
    return FuyaoSource(client=client)


@pytest.mark.unit
class TestFuyaoIndexBarsReconciliationFrame:
    """#474 指数对账帧：单位归一 + 越窗/重复键/未知代码按标的隔离失败."""

    def test_normalizes_units_and_keeps_full_thscode(self) -> None:
        d = date(2026, 9, 30)
        source = _source_by_thscode({"000001.SH": {"item": [_index_item(d)]}})

        frame = source.fetch_index_daily_bars(["000001.SH"], "2026-09-30")

        assert frame.height == 1
        assert frame["ticker"].to_list() == ["000001.SH"]
        assert frame["trade_date"].to_list() == [d]
        # 股→手(÷100)、元→千元(÷1000)，与 Tushare index_daily 口径对齐
        assert frame["close"].to_list() == [3842.19]
        assert frame["volume"].to_list() == [414_560_250.0]
        assert frame["amount"].to_list() == [679_398_990.0]

    def test_unknown_thscode_skipped_not_fatal(self) -> None:
        """申万 .SI 等未收录代码（code=1002）按标的跳过，其余标的继续."""
        d = date(2026, 9, 30)
        source = _source_by_thscode(
            {
                "801951.SI": SourceFetchError(
                    source="fuyao", message="code=1002 Unknown thscode"
                ),
                "000300.SH": {"item": [_index_item(d, close=4357.62)]},
            }
        )

        frame = source.fetch_index_daily_bars(["801951.SI", "000300.SH"], "2026-09-30")

        assert frame["ticker"].to_list() == ["000300.SH"]

    def test_out_of_window_bar_skipped(self) -> None:
        """最新边缘返回窗口外最近一根（实测行为）→ 拒收该标的，不缩窗伪造."""
        source = _source_by_thscode(
            {"000001.SH": {"item": [_index_item(date(2026, 9, 30))]}}
        )

        frame = source.fetch_index_daily_bars(["000001.SH"], "2026-10-03")

        assert frame.height == 0

    def test_duplicate_trade_date_skipped(self) -> None:
        d = date(2026, 9, 30)
        source = _source_by_thscode(
            {"000001.SH": {"item": [_index_item(d), _index_item(d)]}}
        )

        frame = source.fetch_index_daily_bars(["000001.SH"], "2026-09-30")

        assert frame.height == 0

    def test_empty_items_returns_typed_empty_frame(self) -> None:
        """空返回（覆盖不足）= 有类型空帧，零交集由上层判 not_comparable."""
        source = _source_by_thscode({"000001.SH": {"item": []}})

        frame = source.fetch_index_daily_bars(["000001.SH"], "2018-06-01")

        assert frame.height == 0
        assert frame["ticker"].dtype == pl.String
        assert frame["trade_date"].dtype == pl.Date


def _income_item(
    period_end: date, report_date: date, **overrides: object
) -> dict[str, object]:
    item: dict[str, object] = {
        "thscode": "600519.SH",
        "ticker": "600519",
        "period": "quarterly",
        "fiscal_year": period_end.year,
        "fiscal_period": "Q2",
        "report_date_ms": date_to_ms(report_date),
        "period_end_ms": date_to_ms(period_end),
        "currency": "CNY",
        "operating_income": 90_703_260_964.48,
        "operating_costs": 9_473_762_565.88,
        "operating_expenses": 30_946_044_878.08,
        "sales_fee": 3_206_308_341.53,
        "manage_fee": 3_635_355_263.82,
        "research_and_development_expenses": 114_926_219.6,
        "operating_profit": 61_411_291_686.27,
        "interest_expenses": 76_587_662.57,
        "profit_total": 61_438_419_177.29,
        "income_tax_expense": 15_405_088_610.51,
        "net_profit": 46_033_330_566.78,
        "parent_holder_net_profit": 44_516_880_421.86,
        "basic_eps": 35.57,
    }
    item.update(overrides)
    return item


@pytest.mark.unit
class TestFuyaoFinancialStatementsFrame:
    """#473 财务三表对账帧：字段映射、披露日、契约违约按标的隔离."""

    def test_renames_fields_and_derives_dates_from_bare_ticker(self) -> None:
        source = _source_by_thscode(
            {
                "600519.SH": {
                    "item": [_income_item(date(2026, 6, 30), date(2026, 8, 14))]
                }
            }
        )

        frame = source.fetch_financial_statements(
            "income_statement",
            ["600519"],  # 裸码 → 前缀规则补后缀
        )

        assert frame.height == 1
        row = frame.row(0, named=True)
        assert row["ticker"] == "600519.SH"
        assert row["report_date"] == date(2026, 6, 30)
        assert row["disclosure_date"] == date(2026, 8, 14)
        assert row["fiscal_period"] == "Q2"
        # fuyao 字段 → 内部列名（营业收入映射 operating_revenue 同科目；
        # 金额保持元，无单位换算）
        assert row["operating_revenue"] == pytest.approx(90_703_260_964.48)
        assert row["net_profit"] == pytest.approx(46_033_330_566.78)
        assert row["eps"] == pytest.approx(35.57)
        assert row["total_profit"] == pytest.approx(61_438_419_177.29)

    def test_non_cny_currency_skips_ticker(self) -> None:
        source = _source_by_thscode(
            {
                "600519.SH": {
                    "item": [_income_item(date(2026, 6, 30), date(2026, 8, 14))]
                },
                "600036.SH": {
                    "item": [
                        _income_item(
                            date(2026, 6, 30), date(2026, 8, 14), currency="USD"
                        )
                    ]
                },
            }
        )

        frame = source.fetch_financial_statements(
            "income_statement", ["600519", "600036"]
        )

        assert frame["ticker"].to_list() == ["600519.SH"]

    def test_missing_mapped_column_skips_ticker(self) -> None:
        item = _income_item(date(2026, 6, 30), date(2026, 8, 14))
        del item["basic_eps"]
        source = _source_by_thscode({"600519.SH": {"item": [item]}})

        frame = source.fetch_financial_statements("income_statement", ["600519"])

        assert frame.height == 0

    def test_business_error_skips_ticker(self) -> None:
        source = _source_by_thscode(
            {
                "600519.SH": SourceFetchError(
                    source="fuyao", message="code=1002 Unknown thscode"
                )
            }
        )

        frame = source.fetch_financial_statements("income_statement", ["600519"])

        assert frame.height == 0
        assert frame["report_date"].dtype == pl.Date


@pytest.mark.unit
class TestFuyaoFundNavFrame:
    """#475 ETF 单位净值对账帧：只取 unit、目标日落窗跳过."""

    def test_filters_target_date_and_requests_unit_only(self) -> None:
        client = MagicMock()
        client.get.return_value = {
            "item": [
                {"nav_date": date_to_ms(date(2026, 9, 29)), "unit_nav": 4.4181},
                {"nav_date": date_to_ms(date(2026, 9, 30)), "unit_nav": 4.4312},
            ]
        }
        source = FuyaoSource(client=client)

        frame = source.fetch_fund_nav(["510300"], "2026-09-30")

        assert frame.height == 1
        assert frame.row(0, named=True) == {
            "ticker": "510300.SH",
            "trade_date": date(2026, 9, 30),
            "unit_nav": 4.4312,
        }
        # 红线：只请求单位净值（adj_nav 复权净值不参与比较）
        params = client.get.call_args.kwargs["params"]
        assert params["nav_type"] == "unit"

    def test_target_out_of_range_window_skips_ticker(self) -> None:
        client = MagicMock()
        client.get.return_value = {
            "item": [{"nav_date": date_to_ms(date(2026, 9, 30)), "unit_nav": 4.4312}]
        }
        source = FuyaoSource(client=client)

        frame = source.fetch_fund_nav(["510300"], "2025-06-30")

        assert frame.height == 0

    def test_business_error_returns_typed_empty(self) -> None:
        source = _source_by_thscode(
            {
                "513100.SH": SourceFetchError(
                    source="fuyao", message="code=3002 no snapshot"
                )
            }
        )

        frame = source.fetch_fund_nav(["513100"], "2026-09-30")

        assert frame.height == 0
        assert frame["unit_nav"].dtype == pl.Float64


@pytest.mark.unit
class TestFuyaoPerTickerIsolation:
    """#516 评审 F1/F2 — 未识别前缀按标的隔离，单标的身份错误不中断整批."""

    def test_financial_statements_unknown_prefix_skips_ticker(self) -> None:
        """混入 900xxx B 股裸码：该标的跳过留痕，有效标的结果不受影响."""
        source = _source_by_thscode(
            {
                "600519.SH": {
                    "item": [_income_item(date(2026, 6, 30), date(2026, 8, 14))]
                }
            }
        )

        frame = source.fetch_financial_statements(
            "income_statement", ["600519", "900901"]
        )

        assert frame.height == 1
        assert frame["ticker"].to_list() == ["600519.SH"]

    def test_fund_nav_unknown_prefix_skips_ticker(self) -> None:
        target_ms = date_to_ms(date(2026, 9, 30))
        source = _source_by_thscode(
            {"510300.SH": {"item": [{"nav_date": target_ms, "unit_nav": 4.4312}]}}
        )

        frame = source.fetch_fund_nav(["510300", "900901"], "2026-09-30")

        assert frame.height == 1
        assert frame["ticker"].to_list() == ["510300.SH"]

    def test_stock_daily_bars_unknown_prefix_skips_ticker(self) -> None:
        """bars 篮子（宽基对账最大篮）同样按标的隔离，不再整批中断."""
        source = _source_by_thscode(
            {"600519.SH": {"item": [_bar(date_to_ms(date(2026, 9, 30)), 10.5)]}}
        )

        frame = source.fetch_stock_daily_bars(["600519", "900901"], "2026-09-30")

        assert frame.height == 1
        assert frame["ticker"].to_list() == ["600519"]

    def test_stock_daily_bars_contract_violation_skips_ticker(self) -> None:
        """越窗 bar（契约违约）按标的跳过留痕，其余标的照常返回."""
        good_ms = date_to_ms(date(2026, 9, 30))
        bad_ms = date_to_ms(date(2026, 10, 15))
        source = _source_by_thscode(
            {
                "600519.SH": {"item": [_bar(good_ms, 10.5)]},
                "000001.SZ": {"item": [_bar(bad_ms, 12.0)]},
            }
        )

        frame = source.fetch_stock_daily_bars(["600519", "000001"], "2026-09-30")

        assert frame.height == 1
        assert frame["ticker"].to_list() == ["600519"]
