"""Market 域 - 市场数据存储."""

from enum import StrEnum


class AdjType(StrEnum):
    """复权类型."""

    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


__all__ = ["AdjType"]
