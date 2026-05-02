"""
SignalDelivery 组件注册 (DI Provider).

将 AlertManager 注入 DeliveryRouter，作为 SignalDeliveryProtocol 实现。
通知通道的具体配置由 NotificationProvider 负责。
"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_application.processes.execution.delivery import DeliveryRouter
from ditto_application.processes.execution.ports import SignalDeliveryProtocol
from ditto_platform.services.notification.manager import AlertManager

__all__ = ["SignalDeliveryProvider"]


class SignalDeliveryProvider(Provider):
    """
    SignalDelivery Provider — 推送路由 + 信号协议.

    依赖链:
      SignalDeliveryProvider → AlertManager
      → DeliveryRouter → SignalDeliveryProtocol
    """

    scope = Scope.APP

    @provide
    def delivery_router(
        self,
        alert_manager: AlertManager,
    ) -> DeliveryRouter:
        """信号推送路由器 — 注入 AlertManager."""
        return DeliveryRouter(alert_manager=alert_manager)

    @provide
    def signal_delivery(
        self,
        router: DeliveryRouter,
    ) -> SignalDeliveryProtocol:
        """DeliveryRouter 实现 SignalDeliveryProtocol — 注入 SignalSnapshotProcess."""
        return router
