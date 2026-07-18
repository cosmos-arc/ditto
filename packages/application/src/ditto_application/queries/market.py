"""Market query facade — 封装 MarketService，隐藏内部查询类型."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_data.catalog.promotion import DatasetMaturityPromotionReader
from ditto_data.models import InstrumentIdRange
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.market_service import AdjType, MarketBarsQuery, MarketService

from ditto_application.catalog_maturity import blocked_catalog_datasets
from ditto_application.exceptions import AppQueryError

__all__ = ["MarketQueryFacade"]

# 支持的复权类型
_VALID_ADJ_TYPES = frozenset({"none", "qfq", "hfq"})
_MARKET_BAR_DATASETS: dict[str, tuple[str, ...]] = {
    "etf": ("etf_daily",),
    "index": ("index_daily",),
    "stock": ("stock_daily",),
    "fx": ("fx_daily",),
    "commodity": ("commodity_daily",),
}


class MarketQueryFacade:
    """
    行情数据查询 facade.

    封装 MarketService，隐藏 MarketBarsQuery / AdjType 等内部类型，
    对外只暴露原始参数和 pl.DataFrame 返回值。
    """

    def __init__(
        self,
        market_service: MarketService,
        capital_store: CapitalStore | None = None,
        maturity_promotion_reader: DatasetMaturityPromotionReader | None = None,
    ) -> None:
        self._service = market_service
        self._capital_store = capital_store
        self._maturity_promotion_reader = maturity_promotion_reader

    def find_bars(
        self,
        *,
        instrument_ids: list[int] | None = None,
        start: str | None = None,
        end: str | None = None,
        adj: str = "none",
        market_wide: bool = False,
        asset_class: str | None = None,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """
        查询 K 线数据（通过 MarketBarsQuery）.

        Args:
            instrument_ids: 标的 ID 列表（market_wide=True 时可为 None）
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            adj: 复权类型 ("none" | "qfq" | "hfq")
            market_wide: 全市场查询模式
                （为 True 且 instrument_ids 为空时获取所有活跃证券）
            asset_class: 资产类别过滤
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            K 线数据 DataFrame

        Raises:
            ValueError: adj 参数不合法

        """
        if adj not in _VALID_ADJ_TYPES:
            msg = f"adj must be one of {_VALID_ADJ_TYPES}, got '{adj}'"
            raise AppQueryError(msg)
        self._assert_market_bars_allowed(
            asset_class,
            instrument_ids=instrument_ids,
            allow_experimental_data=allow_experimental_data,
        )

        query = MarketBarsQuery(
            instrument_ids=instrument_ids,
            start=start,
            end=end,
            adj=AdjType(adj),
            market_wide=market_wide,
            asset_class=asset_class,
        )
        return self._service.find_bars(query)

    def list_bars(
        self,
        *,
        instrument_ids: list[int],
        start: str | None = None,
        end: str | None = None,
        asset_class: str | None = None,
        limit: int | None = None,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """
        查询 K 线数据（直接参数）.

        Args:
            instrument_ids: 标的 ID 列表
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            asset_class: 资产类别过滤
            limit: 返回数量限制
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            K 线数据 DataFrame

        """
        self._assert_market_bars_allowed(
            asset_class,
            instrument_ids=instrument_ids,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.list_bars(
            instrument_ids=instrument_ids,
            start=start,
            end=end,
            asset_class=asset_class,
            limit=limit,
        )

    def get_constituents(
        self,
        index_id: int,
        as_of_date: str | None = None,
    ) -> pl.DataFrame:
        """
        查询指数成分股.

        Args:
            index_id: 指数标的 ID
            as_of_date: 查询日期 (YYYY-MM-DD)

        Returns:
            成分股 DataFrame

        """
        return self._service.get_constituents(index_id, as_of_date)

    def get_index_weights(
        self,
        *,
        index_id: str,
        as_of_date: str,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """Query effective-dated index weights at an explicit PIT cutoff."""
        blocked = blocked_catalog_datasets(
            ("index_weight",),
            allow_experimental_data=allow_experimental_data,
            maturity_promotion_reader=self._maturity_promotion_reader,
        )
        if blocked:
            msg = (
                "index-weight query requires experimental dataset maturity: "
                "index_weight"
            )
            raise AppQueryError(msg)
        if self._capital_store is None:
            raise AppQueryError("index-weight query store is not configured")
        try:
            cutoff = date.fromisoformat(as_of_date)
        except ValueError as error:
            raise AppQueryError(
                f"as_of_date must be ISO YYYY-MM-DD, got '{as_of_date}'"
            ) from error
        return self._capital_store.get_index_composition(index_id, cutoff)

    def get_adj_factors(
        self,
        *,
        start: str,
        end: str,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """Query the persisted market-wide adjustment-factor dataset."""
        blocked = blocked_catalog_datasets(
            ("adj_factor",),
            allow_experimental_data=allow_experimental_data,
            maturity_promotion_reader=self._maturity_promotion_reader,
        )
        if blocked:
            joined = ", ".join(blocked)
            msg = (
                "adjustment-factor query requires experimental dataset maturity: "
                f"{joined}"
            )
            raise AppQueryError(msg)
        return self._service.get_adj_factors(start, end)

    def _assert_market_bars_allowed(
        self,
        asset_class: str | None,
        *,
        instrument_ids: list[int] | None,
        allow_experimental_data: bool,
    ) -> None:
        dataset_ids = _market_bar_dataset_ids(
            asset_class=asset_class,
            instrument_ids=instrument_ids,
        )
        if not dataset_ids:
            return

        blocked = blocked_catalog_datasets(
            dataset_ids,
            allow_experimental_data=allow_experimental_data,
            maturity_promotion_reader=self._maturity_promotion_reader,
        )
        if not blocked:
            return

        joined = ", ".join(blocked)
        msg = (
            "market bars query requires experimental dataset or other "
            f"non-initial-focus dataset maturity: {joined}. "
            "Set allow_experimental_data=True only for explicit research use."
        )
        raise AppQueryError(msg)


def _market_bar_dataset_ids(
    *,
    asset_class: str | None,
    instrument_ids: list[int] | None,
) -> tuple[str, ...]:
    if asset_class is not None:
        normalized_asset_class = asset_class.lower()
        explicit_dataset_ids = _MARKET_BAR_DATASETS.get(normalized_asset_class)
        if explicit_dataset_ids is None:
            msg = (
                f"Unsupported market bars asset_class for maturity gate: {asset_class}"
            )
            raise AppQueryError(msg)
        return explicit_dataset_ids

    inferred_asset_classes = _infer_asset_classes_from_instrument_ids(instrument_ids)
    if not inferred_asset_classes:
        return ()

    dataset_ids: list[str] = []
    seen: set[str] = set()
    for inferred_asset_class in inferred_asset_classes:
        for dataset_id in _MARKET_BAR_DATASETS.get(inferred_asset_class, ()):
            if dataset_id not in seen:
                seen.add(dataset_id)
                dataset_ids.append(dataset_id)
    return tuple(dataset_ids)


def _infer_asset_classes_from_instrument_ids(
    instrument_ids: list[int] | None,
) -> tuple[str, ...]:
    if not instrument_ids:
        return ()

    asset_classes: list[str] = []
    seen: set[str] = set()
    for instrument_id in sorted(set(instrument_ids)):
        try:
            asset_class = InstrumentIdRange.detect_asset_class([instrument_id])
        except ValueError:
            continue
        if asset_class in seen:
            continue
        seen.add(asset_class)
        asset_classes.append(asset_class)
    return tuple(asset_classes)
