"""Real assembly seam: Ditto cannot resolve a real broker gateway.

自组合证明拆分（#347 试点）：这是真实装配接缝测试——构建 composition
root 的实际 DI 容器并证明 BrokerGateway 不可解析（禁止真实券商路径）。
纯符号/规则断言见 ``test_paper_only_symbol_rules_unit.py``；两者语义
不同层，符号断言不得替代本装配证明。
"""

from __future__ import annotations

import pytest
from dishka.exceptions import NoFactoryError
from ditto_apps.registry.container import make_app_container
from ditto_execution.broker.contracts import BrokerGateway


def test_composition_root_has_no_broker_gateway_provider() -> None:
    container = make_app_container()
    try:
        with pytest.raises(NoFactoryError):
            container.get(BrokerGateway)
    finally:
        container.close()
