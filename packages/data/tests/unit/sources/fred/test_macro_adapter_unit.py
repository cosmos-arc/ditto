"""Tests for MacroFredAdapter."""

from __future__ import annotations

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

    def test_fetch_indicators_sets_knowledge_date_from_observation_date(
        self, respx_mock
    ) -> None:
        """knowledge_date 从观测日期 (date 列) 获取.

        Note: 完整的 PIT 语义需要向 FRED API 传递 realtime_start/realtime_end
        参数，当前未实现，因此使用观测日期作为 knowledge_date。
        """
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

        # Assert - knowledge_date comes from observation date
        import datetime

        assert result["knowledge_date"][0] == datetime.date(2024, 1, 1)

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
