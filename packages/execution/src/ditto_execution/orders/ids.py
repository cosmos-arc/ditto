"""Order ID 值对象 — ClientOrderId + BrokerOrderId。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

__all__ = ["BrokerOrderId", "ClientOrderId"]


@dataclass(frozen=True)
class ClientOrderId:
    """客户端订单 ID — 由 OMS 生成，'ditto-' 前缀 UUID。"""

    value: str

    @classmethod
    def generate(cls) -> ClientOrderId:
        """生成 'ditto-' 前缀的 UUID 订单 ID。"""
        return cls(value=f"ditto-{uuid4().hex}")


@dataclass(frozen=True)
class BrokerOrderId:
    """券商订单 ID — 由外部券商返回。"""

    value: str
