"""
Gateways — 券商网关实现。

提供与具体券商（如 QMT、XTP）的适配器实现。
每个网关实现 BrokerGateway Protocol，
由 apps 层 composition root 按环境注入。
"""

from ditto_execution.broker.gateways.paper import PaperBrokerGateway

__all__ = ["PaperBrokerGateway"]
