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

    验证 ALFRED realtime 参数透传到真实 FRED API，且 need_pit 指标
    knowledge_date = realtime_end（真正 PIT），非 PIT 指标保持 observation date。
    """

    def test_need_pit_indicator_knowledge_date_is_realtime_end(
        self, fred_source
    ) -> None:
        """need_pit 指标传 realtime_end 时 knowledge_date=realtime_end。"""
        df = fred_source.fetch_macro_indicators_range(
            codes=["US_CPI_YOY"],  # need_pit=True
            start_date="2024-01-01",
            end_date="2024-03-31",
            realtime_end="2024-05-01",  # Q1 CPI 已发布
        )
        assert df.height > 0, "FRED CPI 返回空 (检查网络/API key/realtime 窗口)"
        knowledge_dates = df["knowledge_date"].unique().sort().to_list()
        assert date(2024, 5, 1) in knowledge_dates, (
            f"need_pit 指标 knowledge_date 应为 realtime_end=2024-05-01, "
            f"实际: {knowledge_dates}"
        )

    def test_non_pit_indicator_keeps_observation_date(self, fred_source) -> None:
        """非 PIT 指标即使传 realtime_end 也用 observation date（向后兼容）。"""
        df = fred_source.fetch_macro_indicators_range(
            codes=["US_UNRATE"],  # need_pit=False
            start_date="2024-01-01",
            end_date="2024-03-31",
            realtime_end="2024-05-01",
        )
        if df.height == 0:
            pytest.skip("FRED UNRATE 返回空")
        knowledge_dates = set(df["knowledge_date"].unique().to_list())
        # 非 PIT 指标 knowledge_date 来自各月 observation date，不应统一为 realtime_end
        assert knowledge_dates != {date(2024, 5, 1)}, (
            "非 PIT 指标 knowledge_date 不应全部等于 realtime_end"
        )
