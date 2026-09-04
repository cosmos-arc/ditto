"""FRED realtime PIT real-data e2e.

验证 FRED macro realtime PIT 语义在真实 FRED API 生效。

CI 默认跳过（无 key/网络标记）；本地运行：
    pixi run -e dev pytest packages/apps/tests/e2e/test_real_data_pipeline.py -m e2e
"""

from __future__ import annotations

import os
from datetime import date

import pytest


def _fred_api_key() -> str | None:
    """FRED API key：keyring fred/api_key 优先，回退 env。"""
    try:
        import keyring

        key = keyring.get_password("fred", "api_key")
    except Exception:
        key = None
    return key or os.environ.get("FRED_API_KEY")


@pytest.fixture(scope="module")
def fred_source():
    """构建真实 FredSource；无 key 时 skip。"""
    api_key = _fred_api_key()
    if not api_key:
        pytest.skip("FRED API key 未配置 (keyring fred/api_key 或 FRED_API_KEY)")
    from ditto_data.sources.fred.fred_source import FredSource

    return FredSource(api_key=api_key)


@pytest.mark.e2e
@pytest.mark.integration
class TestFredRealtimePitRealFetch:
    """F2-#2 + F2-#3: FRED macro realtime PIT 真实拉取验证。

    验证 ALFRED realtime 参数透传到真实 FRED API，且所有指标都以
    供应商返回的 realtime_start 作为精确 knowledge_date。
    """

    def test_need_pit_indicator_uses_actual_vintage_publication_date(
        self, fred_source
    ) -> None:
        """ALFRED returns the publication date of each selected vintage."""
        df = fred_source.fetch_macro_indicators_range(
            codes=["US_CPI_YOY"],  # need_pit=True
            start_date="2024-01-01",
            end_date="2024-03-31",
            realtime_end="2024-05-01",  # Q1 CPI 已发布
        )
        assert df.height > 0, "FRED CPI 返回空 (检查网络/API key/realtime 窗口)"
        assert all(
            row["date"] <= row["knowledge_date"] <= date(2024, 5, 1)
            for row in df.to_dicts()
        )
        assert any(row["knowledge_date"] > row["date"] for row in df.to_dicts()), (
            "knowledge_date must not be replaced with the observation period"
        )

    def test_non_revising_indicator_still_obeys_publication_cutoff(
        self, fred_source
    ) -> None:
        """A non-revising series is still unavailable before publication."""
        df = fred_source.fetch_macro_indicators_range(
            codes=["US_UNRATE"],  # need_pit=False
            start_date="2024-01-01",
            end_date="2024-03-31",
            realtime_end="2024-05-01",
        )
        if df.height == 0:
            pytest.skip("FRED UNRATE 返回空")
        assert all(
            row["date"] <= row["knowledge_date"] <= date(2024, 5, 1)
            for row in df.to_dicts()
        )
        assert any(row["knowledge_date"] > row["date"] for row in df.to_dicts())

    def test_revising_gdp_preserves_three_real_alfred_vintages(
        self, fred_source
    ) -> None:
        """Each historical as-of sees only the GDP estimate published by then."""
        observations = []
        for cutoff in ("2024-04-29", "2024-05-31", "2024-06-28"):
            frame = fred_source.fetch_macro_indicators_range(
                codes=["US_GDP_QOQ"],
                start_date="2024-01-01",
                end_date="2024-03-31",
                realtime_end=cutoff,
            )
            assert frame.height == 1
            observations.append(
                frame.select("value", "knowledge_date").row(0, named=True)
            )

        assert observations == [
            {"value": 1.6, "knowledge_date": date(2024, 4, 25)},
            {"value": 1.3, "knowledge_date": date(2024, 5, 30)},
            {"value": 1.4, "knowledge_date": date(2024, 6, 27)},
        ]

    def test_gdp_is_empty_before_the_first_real_publication(self, fred_source) -> None:
        """The future sentinel remains invisible one day before first release."""
        frame = fred_source.fetch_macro_indicators_range(
            codes=["US_GDP_QOQ"],
            start_date="2024-01-01",
            end_date="2024-03-31",
            realtime_end="2024-04-24",
        )

        assert frame.is_empty()
