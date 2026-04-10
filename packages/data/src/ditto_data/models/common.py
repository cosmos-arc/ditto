"""Common enumerations and data structures for Data."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum, StrEnum
from typing import Literal, NamedTuple, cast

from ditto_kernel.enums import AssetClass

# 资产类别类型别名
type AssetClassType = Literal[
    "stock", "etf", "index", "fx", "commodity", "bond", "futures", "option"
]

__all__ = [
    "AssetClassType",
    "Dataset",
    "DateScheduleType",
    "Domain",
    "InstrumentIdRange",
    "OnDuplicate",
    "Source",
]


# ============ 日期调度类型枚举 ============
class DateScheduleType(Enum):
    """
    数据集日期调度类型.

    用于确定数据摄取时的日期序列生成策略。

    Attributes:
        TRADING_DAYS: A 股交易日驱动（stock_daily, etf_daily 等）
        NATURAL_DAYS: 自然日驱动（fx_daily 等）
        SOURCE_DEFINED: 由数据源决定（commodity_daily, macro_indicators）

    """

    TRADING_DAYS = "trading_days"
    NATURAL_DAYS = "natural_days"
    SOURCE_DEFINED = "source_defined"


# ============ Dataset 枚举 ============
class Dataset(StrEnum):
    """
    支持的数据集类型。

    数据集分类：
    - 基础类（basic）：不需要 trade_date 参数（stock_basic, etf_basic）
    - 日历类（calendar）：需要日期范围参数（calendar）
    - 行情类（daily）：需要 trade_date 参数（stock_daily, etf_daily, stock_status）
    - 参考类（reference）：需要 trade_date 参数（adj_factor, fund_adj）
    """

    # 基础类数据集（T0 数据，不需要 trade_date）
    STOCK_BASIC = "stock_basic"
    ETF_BASIC = "etf_basic"
    INDEX_BASIC = "index_basic"

    # 日历类数据集（需要日期范围）
    CALENDAR = "calendar"

    # 行情类数据集（T1 数据，需要 trade_date）
    STOCK_DAILY = "stock_daily"
    ETF_DAILY = "etf_daily"
    INDEX_DAILY = "index_daily"
    STOCK_STATUS = "stock_status"

    # 参考类数据集（需要 trade_date）
    ADJ_FACTOR = "adj_factor"
    FUND_ADJ = "fund_adj"

    # Fundamental 域（财务/公司行为）
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOW = "cash_flow"
    DIVIDEND = "dividend"

    # Capital 域（估值/融资融券/质押）
    VALUATION_METRICS = "valuation_metrics"
    MARGIN_TRADING = "margin_trading"
    PLEDGE_RATIO = "pledge_ratio"

    # Macro 域（宏观指标）
    MACRO_INDICATORS = "macro_indicators"

    # Market 域扩展（汇率/商品）
    FX_DAILY = "fx_daily"
    COMMODITY_DAILY = "commodity_daily"

    # Capital 域扩展
    CORPORATE_ACTIONS = "corporate_actions"

    @property
    def asset_class(self) -> AssetClass | None:
        """
        获取数据集对应的资产类型。

        Returns:
            资产类型枚举，如果数据集不关联特定资产类型则返回 None。

        """
        # Stock 数据集
        if self in (
            Dataset.STOCK_DAILY,
            Dataset.ADJ_FACTOR,
            Dataset.STOCK_STATUS,
            Dataset.VALUATION_METRICS,
            Dataset.BALANCE_SHEET,
            Dataset.INCOME_STATEMENT,
            Dataset.CASH_FLOW,
            Dataset.DIVIDEND,
            Dataset.MARGIN_TRADING,
            Dataset.PLEDGE_RATIO,
        ):
            return AssetClass.STOCK
        # ETF 数据集
        if self in (Dataset.ETF_DAILY, Dataset.FUND_ADJ):
            return AssetClass.ETF
        # Index 数据集
        if self == Dataset.INDEX_DAILY:
            return AssetClass.INDEX
        return None

    @property
    def date_schedule(self) -> DateScheduleType:
        """
        获取数据集的日期调度类型.

        Returns:
            日期调度类型枚举。

        """
        # A 股交易日驱动
        if self in (
            Dataset.STOCK_DAILY,
            Dataset.ETF_DAILY,
            Dataset.INDEX_DAILY,
            Dataset.STOCK_STATUS,
            Dataset.ADJ_FACTOR,
            Dataset.FUND_ADJ,
            Dataset.VALUATION_METRICS,
            Dataset.BALANCE_SHEET,
            Dataset.INCOME_STATEMENT,
            Dataset.CASH_FLOW,
            Dataset.DIVIDEND,
            Dataset.MARGIN_TRADING,
            Dataset.PLEDGE_RATIO,
            Dataset.CORPORATE_ACTIONS,
        ):
            return DateScheduleType.TRADING_DAYS

        # 自然日驱动
        if self == Dataset.FX_DAILY:
            return DateScheduleType.NATURAL_DAYS

        # 数据源决定
        if self in (Dataset.COMMODITY_DAILY, Dataset.MACRO_INDICATORS):
            return DateScheduleType.SOURCE_DEFINED

        # 默认：交易日驱动
        return DateScheduleType.TRADING_DAYS

    def supports_instrument_ingestion(self) -> bool:
        """
        判断数据集是否支持按标的（instrument）进行数据摄取。

        Returns:
            如果支持按标的摄取返回 True，否则返回 False。

        """
        return self.asset_class is not None

    @classmethod
    def is_basic_dataset(cls, dataset: str) -> bool:
        """判断是否为 basic 类数据集（不需要 trade_date）。"""
        return dataset in (
            cls.STOCK_BASIC.value,
            cls.ETF_BASIC.value,
            cls.INDEX_BASIC.value,
        )

    @classmethod
    def is_calendar_dataset(cls, dataset: str) -> bool:
        """判断是否为 calendar 数据集。"""
        return dataset == cls.CALENDAR.value

    @classmethod
    def get_asset_class(
        cls, dataset: Dataset | str
    ) -> Literal["stock", "etf", "index", "other"]:
        """
        获取数据集对应的资产类别。

        Args:
            dataset: 数据集枚举或字符串

        Returns:
            资产类别: "stock" | "etf" | "index" | "other"

        Note:
            此方法为兼容性方法，推荐使用 ``dataset.asset_class`` 属性。

        """
        # 转换为 Dataset 枚举
        dataset_enum = dataset if isinstance(dataset, Dataset) else cls(dataset)

        # 使用 asset_class 属性获取类型
        asset_class = dataset_enum.asset_class

        # 转换为字符串字面量（保持向后兼容）
        if asset_class is None:
            return "other"
        # asset_class 只会是 STOCK, ETF, INDEX 之一，因为 asset_class 属性只返回这些
        if asset_class == AssetClass.STOCK:
            return "stock"
        if asset_class == AssetClass.ETF:
            return "etf"
        return "index"


# ============ Domain 枚举 ============
class Domain(StrEnum):
    """
    支持的数据域类型。

    数据域枚举，用于 Port 层 IngestionCoordinator 路由和域级别数据管理。
    """

    METADATA = "metadata"
    MARKET = "market"
    CAPITAL = "capital"
    FUNDAMENTAL = "fundamental"
    MACRO = "macro"


# ============ Source 枚举 ============
class Source(StrEnum):
    """
    支持的数据源类型。

    数据源枚举，统一管理所有外部数据源。
    """

    TUSHARE = "tushare"
    AKSHARE = "akshare"  # 预留，未来支持
    FRED = "fred"  # Federal Reserve Economic Data (美国宏观数据)


# ============ Store 枚举 ============
class OnDuplicate(Enum):
    """策略：处理写入时的重复数据."""

    ERROR = "error"  # 遇到重复时报错（默认，最安全）
    KEEP_FIRST = "keep_first"  # 保留现有数据，忽略新数据
    KEEP_LAST = "keep_last"  # 使用新数据覆盖现有数据（Last-Write-Wins）


class InstrumentIdRange(NamedTuple):
    """
    Instrument ID range definition.

    统一使用百万级范围:
    - stock: 1M (1,000,000 - 1,999,999)
    - etf: 2M (2,000,000 - 2,999,999)
    - index: 3M (3,000,000 - 3,999,999)
    - fx: 4M (4,000,000 - 4,999,999)
    - commodity: 5M (5,000,000 - 5,999,999)
    - bond: 6M (6,000,000 - 6,999,999)
    - futures: 7M (7,000,000 - 7,999,999)
    - option: 8M (8,000,000 - 8,999,999)

    避免未来 instrument_id 冲突，并保持范围一致性。

    Provides bidirectional mapping between asset classes and ID ranges:
    - get_range(asset_class): asset_class → (min_id, max_id)
    - detect_asset_class(ids): ids → asset_class
    """

    min_id: int
    max_id: int

    @classmethod
    def get_range(cls, asset_class: str) -> InstrumentIdRange:
        """Get ID range for asset class."""
        ranges = {
            "stock": cls(1_000_000, 1_999_999),
            "etf": cls(2_000_000, 2_999_999),
            "index": cls(3_000_000, 3_999_999),
            "fx": cls(4_000_000, 4_999_999),
            "commodity": cls(5_000_000, 5_999_999),
            "bond": cls(6_000_000, 6_999_999),
            "futures": cls(7_000_000, 7_999_999),
            "option": cls(8_000_000, 8_999_999),
        }

        if asset_class not in ranges:
            raise ValueError(f"Unknown asset class: {asset_class}")

        return ranges[asset_class]

    @classmethod
    def detect_asset_class(cls, ids: list[int]) -> AssetClassType:
        """
        Detect asset class from a list of IDs.

        Args:
            ids: List of instrument IDs.

        Returns:
            Asset class string.

        Raises:
            ValueError: If mixed asset classes detected, empty list,
                or unrecognized IDs.

        Examples:
            >>> InstrumentIdRange.detect_asset_class([1_000_001, 1_000_002])
            'stock'
            >>> InstrumentIdRange.detect_asset_class([4_000_001])
            'fx'

        """
        if not ids:
            raise ValueError("无法推断空 instrument_id 列表的资产类别")

        # 定义所有资产类别范围（与 AssetClassType 保持一致）
        asset_classes: list[AssetClassType] = [
            "stock",
            "etf",
            "index",
            "fx",
            "commodity",
            "bond",
            "futures",
            "option",
        ]
        ranges: list[tuple[AssetClassType, int, int]] = [
            ("stock", 1_000_000, 1_999_999),
            ("etf", 2_000_000, 2_999_999),
            ("index", 3_000_000, 3_999_999),
            ("fx", 4_000_000, 4_999_999),
            ("commodity", 5_000_000, 5_999_999),
            ("bond", 6_000_000, 6_999_999),
            ("futures", 7_000_000, 7_999_999),
            ("option", 8_000_000, 8_999_999),
        ]

        # 统计各范围命中次数
        hits: dict[AssetClassType, int] = dict.fromkeys(asset_classes, 0)
        unknown_ids: list[int] = []

        for instrument_id in ids:
            matched = False
            for ac, lo, hi in ranges:
                if lo <= instrument_id <= hi:
                    hits[ac] += 1
                    matched = True
                    break
            if not matched:
                unknown_ids.append(instrument_id)

        # 存在未知范围 ID，抛异常
        _MAX_SAMPLE = 5  # 最多显示 5 个未知 ID
        if unknown_ids:
            sample = unknown_ids[:_MAX_SAMPLE]
            suffix = "..." if len(unknown_ids) > _MAX_SAMPLE else ""
            raise ValueError(f"instrument_id {sample}{suffix} 不在任何已定义范围内")

        # 检测命中的资产类别
        detected: list[AssetClassType] = [ac for ac, count in hits.items() if count > 0]

        if len(detected) > 1:
            display_names = {
                "stock": "stock",
                "etf": "ETF",
                "index": "index",
                "fx": "FX",
                "commodity": "commodity",
                "bond": "bond",
                "futures": "futures",
                "option": "option",
            }
            classes = [display_names[c] for c in detected]
            classes_str = ", ".join(classes)
            raise ValueError(
                "检测到混合资产类别查询。ID 包含 "
                + f"{classes_str}。请分别查询每个资产类别。"
            )

        if not detected:
            # 理论上不会到这里，因为 unknown_ids 已经处理了
            raise ValueError("无法确定资产类别")

        return detected[0]


# ---------------------------------------------------------------------------
# JSON type aliases (shared across models)
# ---------------------------------------------------------------------------

type JsonPrimitive = None | bool | int | float | str
type JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
type JsonDict = dict[str, JsonValue]


# ---------------------------------------------------------------------------
# JSON record field validators
# ---------------------------------------------------------------------------


def require_str(data: Mapping[str, JsonValue], key: str) -> str:
    """Extract a required string field from JSON payload."""
    value = data[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def require_int(data: Mapping[str, JsonValue], key: str) -> int:
    """Extract a required int field from JSON payload."""
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an int")
    return value


def require_bool(data: Mapping[str, JsonValue], key: str) -> bool:
    """Extract a required bool field from JSON payload."""
    value = data[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a bool")
    return value


def require_payload(data: Mapping[str, JsonValue], key: str) -> JsonDict:
    """Extract a required JSON object field from payload."""
    value = data[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be a JSON object")
    return cast(JsonDict, value)
