from typing import Protocol

from ditto_execution.broker.contracts import BrokerGateway


def test_broker_gateway_is_protocol() -> None:
    assert issubclass(BrokerGateway, Protocol)
