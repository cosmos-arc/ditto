"""Composition proof that Ditto cannot resolve a real broker gateway."""

from __future__ import annotations

import pytest
from dishka.exceptions import NoFactoryError
from ditto_apps.registry.container import make_app_container
from ditto_execution.broker.contracts import BrokerGateway
from ditto_execution.broker.gateways import __all__ as gateway_exports


def test_composition_root_has_no_broker_gateway_provider() -> None:
    with make_app_container() as container:
        with pytest.raises(NoFactoryError):
            container.get(BrokerGateway)


def test_execution_exports_only_the_paper_gateway() -> None:
    assert gateway_exports == ["PaperBrokerGateway"]
