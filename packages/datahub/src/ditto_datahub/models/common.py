"""Common enumerations and data structures for DataHub."""

from enum import Enum
from typing import Literal, NamedTuple

__all__ = [
    "DQSeverity",
    "Dataset",
    "Domain",
    "InstrumentIdRange",
    "OnDuplicate",
    "Source",
]


# ============ DQ 枚举 ============
class DQSeverity(str, Enum):
    """DQ severity levels (B.5: 统一三级定义)."""

    ERROR = "error"
    WARNING = "warning"
    ALERT = "alert"


# ============ Dataset 枚举 ============
class Dataset(str, Enum):
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

    # 日历类数据集（需要日期范围）
    CALENDAR = "calendar"

    # 行情类数据集（T1 数据，需要 trade_date）
    STOCK_DAILY = "stock_daily"
    ETF_DAILY = "etf_daily"
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

    # Capital 域扩展
    FUTURES = "futures"
    CORPORATE_ACTIONS = "corporate_actions"

    @classmethod
    def is_basic_dataset(cls, dataset: str) -> bool:
        """判断是否为 basic 类数据集（不需要 trade_date）。"""
        return dataset in (cls.STOCK_BASIC.value, cls.ETF_BASIC.value)

    @classmethod
    def is_calendar_dataset(cls, dataset: str) -> bool:
        """判断是否为 calendar 数据集。"""
        return dataset == cls.CALENDAR.value


# ============ Domain 枚举 ============
class Domain(str, Enum):
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
class Source(str, Enum):
    """
    支持的数据源类型。

    数据源枚举，统一管理所有外部数据源。
    """

    TUSHARE = "tushare"
    AKSHARE = "akshare"  # 预留，未来支持


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

    避免未来 instrument_id 冲突，并保持范围一致性。

    Provides bidirectional mapping between asset classes and ID ranges:
    - get_range(asset_class): asset_class → (min_id, max_id)
    - detect_asset_class(ids): ids → asset_class
    """

    min_id: int
    max_id: int

    @classmethod
    def get_range(cls, asset_class: str) -> "InstrumentIdRange":
        """Get ID range for asset class."""
        ranges = {
            "stock": cls(1_000_000, 1_999_999),
            "etf": cls(2_000_000, 2_999_999),
            "index": cls(3_000_000, 3_999_999),
        }

        if asset_class not in ranges:
            raise ValueError(f"Unknown asset class: {asset_class}")

        return ranges[asset_class]

    @classmethod
    def detect_asset_class(cls, ids: list[int]) -> Literal["stock", "etf", "index"]:
        """
        Detect asset class from a list of IDs.

        Args:
            ids: List of instrument IDs.

        Returns:
            Asset class string ("stock", "etf", "index").

        Raises:
            ValueError: If mixed asset classes detected or unrecognized.

        Examples:
            >>> InstrumentIdRange.detect_asset_class([1_000_001, 1_000_002])
            'stock'
            >>> InstrumentIdRange.detect_asset_class([2_500_000])
            'etf'

        """
        stock_range = cls.get_range("stock")
        etf_range = cls.get_range("etf")
        index_range = cls.get_range("index")

        has_stock = any(
            stock_range.min_id <= instrument_id <= stock_range.max_id
            for instrument_id in ids
        )
        has_etf = any(
            etf_range.min_id <= instrument_id <= etf_range.max_id
            for instrument_id in ids
        )
        has_index = any(
            index_range.min_id <= instrument_id <= index_range.max_id
            for instrument_id in ids
        )

        detected: list[Literal["stock", "etf", "index"]] = []
        if has_stock:
            detected.append("stock")
        if has_etf:
            detected.append("etf")
        if has_index:
            detected.append("index")

        if len(detected) > 1:
            display_names = {"stock": "stock", "etf": "ETF", "index": "index"}
            classes = [display_names[c] for c in detected]
            classes_str = ", ".join(classes)
            raise ValueError(
                "检测到混合资产类别查询。ID 包含 "
                + f"{classes_str}。请分别查询每个资产类别。"
            )

        if not detected:
            return "stock"  # 默认

        return detected[0]
