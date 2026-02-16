"""测试 QualityProvider."""

from dishka import make_container
from ditto_core.quality import QualityEngine
from ditto_port.registry.core import QualityProvider
from ditto_port.registry.infra import ConfigProvider


def test_core_provider_provides_dq_engine():
    """测试 QualityProvider 提供 QualityEngine."""
    container = make_container(ConfigProvider(), QualityProvider())

    engine = container.get(QualityEngine)
    assert isinstance(engine, QualityEngine)

    container.close()


def test_core_provider_is_singleton():
    """测试 QualityProvider 组件是单例."""
    container = make_container(ConfigProvider(), QualityProvider())

    engine1 = container.get(QualityEngine)
    engine2 = container.get(QualityEngine)
    assert engine1 is engine2

    container.close()
