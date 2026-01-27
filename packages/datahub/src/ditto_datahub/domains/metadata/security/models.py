"""Security 相关数据模型."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SecurityRegistration:
    """
    证券注册信息配置对象。

    用于封装证券注册所需的所有参数，避免函数参数过多。
    """

    src_code: str
    symbol: str
    name: str
    exchange: str
    asset_class: str
    list_date: str
    source: str = "tushare"
    board: str | None = None
