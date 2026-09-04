"""Tests for MacroFredAdapter."""

from __future__ import annotations

import datetime

import httpx
from ditto_data.sources.fred.adapters.macro import MacroFredAdapter
from ditto_data.sources.schemas.macro_schemas import MACRO_INDICATOR_SOURCE_SCHEMA


class TestMacroFredAdapter:
    """Tests for MacroFredAdapter."""

    def test_fetch_indicators_returns_correct_schema(self, respx_mock) -> None:
        """返回符合 MACRO_INDICATOR_SOURCE_SCHEMA 的 DataFrame."""
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
        adapter = MacroFredAdapter(api_key="test_key")
        result = adapter.fetch_indicators(
            codes=["US_UNRATE"],
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        # Assert - check schema columns
        expected_columns = set(MACRO_INDICATOR_SOURCE_SCHEMA.schema.keys())
        assert set(result.columns) == expected_columns

    def test_fetch_indicators_uses_provider_vintage_start_as_knowledge_date(
        self, respx_mock
    ) -> None:
        """Current-vintage fetches cannot predate the provider vintage start."""
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
                            "realtime_start": "2024-02-02",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-01",
                            "value": "3.7",
                        },
                    ],
                },
            )
        )

        # Act
        adapter = MacroFredAdapter(api_key="test_key")
        result = adapter.fetch_indicators(
            codes=["US_UNRATE"],
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        # The January observation was not public until February 2.
        import datetime

        assert result["knowledge_date"][0] == datetime.date(2024, 2, 2)

    def test_fetch_indicators_unknown_code_skipped(self, respx_mock) -> None:
        """未知指标代码被跳过."""
        # Arrange - no mock needed as it should skip

        # Act
        adapter = MacroFredAdapter(api_key="test_key")
        result = adapter.fetch_indicators(
            codes=["UNKNOWN_CODE"],
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        # Assert - empty dataframe with correct schema
        assert result.height == 0
        assert set(result.columns) == set(MACRO_INDICATOR_SOURCE_SCHEMA.schema.keys())

    def test_fetch_multiple_indicators(self, respx_mock) -> None:
        """获取多个指标."""
        # Arrange
        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            series_id = dict(request.url.params).get("series_id", "UNKNOWN")
            return httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": series_id,
                    "observations": [
                        {
                            "realtime_start": "2024-02-01",
                            "realtime_end": "2024-12-31",
                            "date": "2024-01-01",
                            "value": "100",
                        },
                    ],
                },
            )

        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            side_effect=side_effect
        )

        # Act
        adapter = MacroFredAdapter(api_key="test_key")
        result = adapter.fetch_indicators(
            codes=["US_UNRATE", "US_PAYEMS"],
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        # Assert
        assert call_count == 2
        assert result.height == 2

    def test_fetch_indicators_empty_response(self, respx_mock) -> None:
        """空响应返回空 DataFrame."""
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
        adapter = MacroFredAdapter(api_key="test_key")
        result = adapter.fetch_indicators(
            codes=["US_UNRATE"],
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        # Assert
        assert result.height == 0


class TestMacroFredAdapterRealtimePit:
    """F2-#2: ALFRED realtime PIT 语义（仅 need_pit 指标启用真正 PIT）。"""

    def test_need_pit_indicator_passes_realtime_and_uses_vintage_start(
        self, respx_mock
    ) -> None:
        """ALFRED provides the exact date on which the selected vintage appeared."""
        import datetime

        captured: dict[str, str] = {}

        def side_effect(request: httpx.Request) -> httpx.Response:
            captured.update(dict(request.url.params))
            return httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-04-01",
                    "series_id": "CPIAUCSL",
                    "observations": [
                        {
                            "realtime_start": "2024-02-15",
                            "realtime_end": "9999-12-31",
                            "date": "2024-01-01",
                            "value": "3.1",
                        },
                    ],
                },
            )

        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            side_effect=side_effect
        )

        adapter = MacroFredAdapter(api_key="test_key")
        result = adapter.fetch_indicators(
            codes=["US_CPI_YOY"],  # need_pit=True
            start_date="2024-01-01",
            end_date="2024-03-31",
            realtime_end="2024-04-01",
        )

        # realtime_end 透传给 FRED API
        assert captured.get("realtime_end") == "2024-04-01"
        assert result["knowledge_date"][0] == datetime.date(2024, 2, 15)

    def test_non_revising_indicator_still_respects_publication_time(
        self, respx_mock
    ) -> None:
        """Revision policy never permits visibility before first publication."""
        import datetime

        captured: dict[str, str] = {}

        def side_effect(request: httpx.Request) -> httpx.Response:
            captured.update(dict(request.url.params))
            return httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "UNRATE",
                    "observations": [
                        {
                            "realtime_start": "2024-02-02",
                            "realtime_end": "9999-12-31",
                            "date": "2024-01-01",
                            "value": "3.7",
                        },
                    ],
                },
            )

        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            side_effect=side_effect
        )

        adapter = MacroFredAdapter(api_key="test_key")
        result = adapter.fetch_indicators(
            codes=["US_UNRATE"],  # need_pit=False
            start_date="2024-01-01",
            end_date="2024-03-31",
            realtime_end="2024-04-01",
        )

        assert captured.get("realtime_end") == "2024-04-01"
        assert result["knowledge_date"][0] == datetime.date(2024, 2, 2)

    def test_need_pit_dedupes_revisions_takes_latest_as_of(self, respx_mock) -> None:
        """realtime 模式下同一 date 多版本（修订）取 realtime_start<=T 最新版本."""
        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-04-01",
                    "series_id": "CPIAUCSL",
                    "observations": [
                        {  # 初值
                            "realtime_start": "2024-02-15",
                            "realtime_end": "2024-03-15",
                            "date": "2024-01-01",
                            "value": "3.1",
                        },
                        {  # 修订值
                            "realtime_start": "2024-03-15",
                            "realtime_end": "9999-12-31",
                            "date": "2024-01-01",
                            "value": "3.2",
                        },
                    ],
                },
            )
        )

        adapter = MacroFredAdapter(api_key="test_key")
        result = adapter.fetch_indicators(
            codes=["US_CPI_YOY"],  # need_pit=True
            start_date="2024-01-01",
            end_date="2024-03-31",
            realtime_end="2024-04-01",
        )

        # 去重为一行，取修订后最新值及其实际公开日
        assert result.height == 1
        assert result["value"][0] == 3.2
        assert result["knowledge_date"][0] == datetime.date(2024, 3, 15)

    def test_need_pit_without_realtime_uses_current_vintage_start(
        self, respx_mock
    ) -> None:
        """Current-vintage fallback remains fail-closed for historical queries."""
        import datetime

        captured: dict[str, str] = {}

        def side_effect(request: httpx.Request) -> httpx.Response:
            captured.update(dict(request.url.params))
            return httpx.Response(
                200,
                json={
                    "realtime_start": "2024-01-01",
                    "realtime_end": "2024-12-31",
                    "series_id": "CPIAUCSL",
                    "observations": [
                        {
                            "realtime_start": "2024-02-15",
                            "realtime_end": "9999-12-31",
                            "date": "2024-01-01",
                            "value": "3.1",
                        },
                    ],
                },
            )

        respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            side_effect=side_effect
        )

        adapter = MacroFredAdapter(api_key="test_key")
        result = adapter.fetch_indicators(
            codes=["US_CPI_YOY"],  # need_pit=True 但不传 realtime
            start_date="2024-01-01",
            end_date="2024-03-31",
        )

        assert "realtime_end" not in captured
        assert result["knowledge_date"][0] == datetime.date(2024, 2, 15)
