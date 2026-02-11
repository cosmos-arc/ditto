"""
Instrument 相关数据模型.

命名映射：
- Python 代码使用 instrument/source_ticker
- 数据库表/列保持 instrument/source_ticker（避免数据迁移）
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentRegistration:
    """
    证券注册信息配置对象。

    用于封装证券注册所需的所有参数，避免函数参数过多。

    Attributes:
        source_ticker: 源代码（如 "600000.SH"），数据库中存储为 source_ticker
        symbol: 显示符号（如 "600000"）
        name: 证券名称
        exchange: 交易所代码（如 "SSE", "SZSE"）
        asset_class: 资产类别（stock/etf/index）
        list_date: 上市日期（YYYY-MM-DD 格式）
        source: 数据源标识符（默认 "tushare"）
        board: 板块代码（可选）

    """

    source_ticker: str
    symbol: str
    name: str
    exchange: str
    asset_class: str
    list_date: str
    source: str = "tushare"
    board: str | None = None
