from __future__ import annotations

from typing import Protocol


class BrokerGateway(Protocol):
    """
    Boundary for real and simulated broker implementations.

    TODO: 在对接真实券商时 flesh out 方法签名
    （submit_order, cancel_order, query_fills 等）。
    当前为占位 Protocol，等 execution 包订单模型稳定后再设计完整接口。
    """
