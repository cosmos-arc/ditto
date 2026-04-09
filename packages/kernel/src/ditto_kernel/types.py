"""
共享值对象 — 跨层使用的纯数据类.

提供 frozen dataclass 值对象，不含业务行为。

准入依据:
- InstrumentIngestParams 被 interfaces 和 app 层同时使用
- 零外部依赖，纯值语义
- 稳定性高，不随子域迭代变更
"""

from dataclasses import dataclass

__all__ = ["InstrumentIngestParams"]


@dataclass(frozen=True)
class InstrumentIngestParams:
    """
    按标的摄取的参数。

    标识符三选一，优先级: instrument_id > standard_ticker > ticker
    """

    # 标识符（三选一）
    instrument_id: int | None = None
    standard_ticker: str | None = None  # Ditto 标准格式，如 "000001.XSHE"
    ticker: str | None = None  # 裸代码，如 "000001"

    # 时间范围
    start_date: str = ""  # YYYY-MM-DD
    end_date: str = ""  # YYYY-MM-DD
