"""Pure symbol/rule assertions for the paper-only execution boundary.

自组合证明拆分（#347 试点）：纯符号/规则断言与真实装配接缝分文件
维护——本文件只断言静态导出与规则形状，不构建容器；真实装配证明见
``test_paper_only_composition_assembly_unit.py``（装配接缝，禁止互替）。
"""

from __future__ import annotations

from ditto_execution.broker.gateways import __all__ as gateway_exports


def test_execution_exports_only_the_paper_gateway() -> None:
    assert gateway_exports == ["PaperBrokerGateway"]
