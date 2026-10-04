"""FRED macro data adapter."""

from __future__ import annotations

import datetime

import polars as pl

from ditto_data.sources.fred.adapters.base import BaseFredAdapter
from ditto_data.sources.fred.indicators import get_fred_indicator
from ditto_data.sources.schemas.macro_schemas import MACRO_INDICATOR_SOURCE_SCHEMA

__all__ = ["MacroFredAdapter"]


def _take_latest_vintage_as_of(
    observations: pl.DataFrame,
    as_of: datetime.date,
) -> pl.DataFrame:
    """
    Collapse ALFRED revisions to the latest vintage known by ``as_of``.

    FRED ALFRED returns one row per published revision; each row's
    ``realtime_start`` is the date that vintage became public. For a
    point-in-time query anchored at ``as_of``, the value actually known is
    the vintage with the greatest ``realtime_start`` on or before ``as_of``.

    """
    if observations.height == 0 or "realtime_start" not in observations.columns:
        return observations
    return (
        observations.filter(pl.col("realtime_start") <= as_of)
        .sort("realtime_start")
        .unique(subset=["date"], keep="last")
    )


class MacroFredAdapter(BaseFredAdapter):
    """
    Adapter for fetching macro indicators from FRED API.

    Normalizes FRED data to MACRO_INDICATOR_SOURCE_SCHEMA format.

    PIT semantics:
        FRED/ALFRED ``realtime_start`` is the date on which a specific vintage
        became public. When ``realtime_end`` is supplied, every series uses the
        ALFRED window (uncapped at the start unless the caller narrows it) and
        revisions collapse to the latest vintage actually known by that date.

        knowledge_date 语义（#432）：
        - ALFRED 模式（realtime_end 给定）：所选 vintage 的 ``realtime_start``
          是该修订的公开日，作为 knowledge_date 是事实；
        - 默认模式（无 realtime 参数）：FRED 默认 realtime 窗口为请求当天，
          返回行的 ``realtime_start`` 等于请求日，即**采集时间**而非该值
          首次发布的精确时刻；未知首次发布时刻保持未知，不以观察日或
          裁剪后的 realtime_start 伪装发布时刻（保守 PIT：值不早于采集日
          可见，真实发布可能更早）。

    """

    def fetch_indicators(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        realtime_start: str | None = None,
        realtime_end: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch multiple macro indicators from FRED.

        Args:
            codes: List of unified indicator codes (e.g., ["US_UNRATE", "US_GDP_QOQ"]).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            realtime_start: Optional ALFRED realtime window start (YYYY-MM-DD).
                未提供时不裁剪 realtime 起点（完整 vintage 历史），避免排除
                公开日早于观察窗口起点的修订。
            realtime_end: Optional ALFRED realtime PIT anchor (YYYY-MM-DD).
                When set, the FRED API receives the realtime window, revisions
                collapse to the latest vintage known by this date, and
                ``knowledge_date`` remains the selected vintage's exact
                ``realtime_start``.

        Returns:
            DataFrame with MACRO_INDICATOR_SOURCE_SCHEMA columns.
            Unknown codes are skipped.

        """
        results: list[pl.DataFrame] = []

        for code in codes:
            indicator = get_fred_indicator(code)
            if indicator is None:
                # Skip unknown codes
                continue

            # Bind to a local so the None-check narrows ``realtime_end`` to
            # ``str`` within the branch (a captured bool would not propagate).
            realtime_end_str = realtime_end
            if realtime_end_str is not None:
                as_of = datetime.date.fromisoformat(realtime_end_str)
                # Fetch ALFRED vintage observations known by realtime_end.
                # 未显式给 realtime_start 时不以观察起点裁剪 realtime 窗口：
                # 公开日早于观察窗口起点的修订行同样参与 as-of 折叠，
                # 否则这些行会被整行排除（修订丢失）。
                realtime_params: dict[str, str] = {"realtime_end": realtime_end_str}
                if realtime_start is not None:
                    realtime_params["realtime_start"] = realtime_start
                df = self._client.get_series_observations(
                    series_id=indicator.series_id,
                    observation_start=start_date,
                    observation_end=end_date,
                    **realtime_params,
                )
                # Collapse revisions to the latest vintage known at as_of
                df = _take_latest_vintage_as_of(df, as_of)
            else:
                # The current response still carries the start date of the
                # selected provider vintage. Do not substitute observation date.
                df = self._client.get_series_observations(
                    series_id=indicator.series_id,
                    observation_start=start_date,
                    observation_end=end_date,
                )

            if df.height == 0:
                continue

            # Transform to MACRO_INDICATOR_SOURCE_SCHEMA
            transformed = (
                df.with_columns(
                    pl.lit(code).alias("indicator_code"),
                    pl.lit(indicator.name).alias("indicator_name"),
                    pl.lit(indicator.category).alias("category"),
                    pl.lit(indicator.frequency).alias("frequency"),
                    pl.lit(indicator.need_pit).alias("need_pit"),
                    pl.col("realtime_start").alias("knowledge_date"),
                    pl.lit("fred").alias("source"),
                    pl.lit(indicator.unit).alias("unit"),
                    pl.lit(indicator.description).alias("description"),
                )
                .filter(pl.col("knowledge_date").is_not_null())
                .select(
                    "indicator_code",
                    "indicator_name",
                    "category",
                    "frequency",
                    "need_pit",
                    "date",
                    "value",
                    "knowledge_date",
                    "source",
                    "unit",
                    "description",
                )
            )

            results.append(transformed)

        if not results:
            # Return empty DataFrame with correct schema
            return pl.DataFrame(schema=MACRO_INDICATOR_SOURCE_SCHEMA.schema)

        return pl.concat(results)
