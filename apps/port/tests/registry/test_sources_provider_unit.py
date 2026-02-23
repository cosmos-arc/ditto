"""SourcesProvider 数据源 Provider 测试."""

from dishka import make_container
from ditto_datahub.sources import ExchangeTransformer, ExchangeTransformers
from ditto_datahub.sources.tdx.transformer import TdxExchangeTransformer
from ditto_datahub.sources.tushare.transformer import TushareExchangeTransformer
from ditto_port.registry.datahub.sources import SourcesProvider
from ditto_port.registry.infra import ConfigProvider


class TestSourcesProviderTransformers:
    """SourcesProvider Transformer 相关测试类."""

    def test_tushare_transformer_provider(self, monkeypatch):
        """测试 tushare_transformer provider."""
        # 设置环境
        monkeypatch.setenv("ENVIRONMENT", "testing")

        # 创建容器
        container = make_container(ConfigProvider(), SourcesProvider())

        # 获取 tushare_transformer
        transformer = container.get(TushareExchangeTransformer)

        # 验证
        assert isinstance(transformer, TushareExchangeTransformer)

        # 清理
        container.close()

    def test_tdx_transformer_provider(self, monkeypatch):
        """测试 tdx_transformer provider."""
        # 设置环境
        monkeypatch.setenv("ENVIRONMENT", "testing")

        # 创建容器
        container = make_container(ConfigProvider(), SourcesProvider())

        # 获取 tdx_transformer
        transformer = container.get(TdxExchangeTransformer)

        # 验证
        assert isinstance(transformer, TdxExchangeTransformer)

        # 清理
        container.close()

    def test_exchange_transformers_provider(self, monkeypatch):
        """测试 exchange_transformers provider."""
        # 设置环境
        monkeypatch.setenv("ENVIRONMENT", "testing")

        # 创建容器
        container = make_container(ConfigProvider(), SourcesProvider())

        # 获取 exchange_transformers
        transformers = container.get(ExchangeTransformers)

        # 验证
        assert isinstance(transformers, ExchangeTransformers)
        assert isinstance(transformers.tushare, TushareExchangeTransformer)
        assert isinstance(transformers.tdx, TdxExchangeTransformer)

        # 清理
        container.close()

    def test_transformers_are_singletons(self, monkeypatch):
        """测试 transformer 是单例."""
        # 设置环境
        monkeypatch.setenv("ENVIRONMENT", "testing")

        # 创建容器
        container = make_container(ConfigProvider(), SourcesProvider())

        # 多次获取，验证是同一实例
        tushare1 = container.get(TushareExchangeTransformer)
        tushare2 = container.get(TushareExchangeTransformer)
        assert tushare1 is tushare2

        tdx1 = container.get(TdxExchangeTransformer)
        tdx2 = container.get(TdxExchangeTransformer)
        assert tdx1 is tdx2

        transformers1 = container.get(ExchangeTransformers)
        transformers2 = container.get(ExchangeTransformers)
        assert transformers1 is transformers2

        # 清理
        container.close()

    def test_transformers_functional(self, monkeypatch):
        """测试 transformer 功能正常."""
        # 设置环境
        monkeypatch.setenv("ENVIRONMENT", "testing")

        # 创建容器
        container = make_container(ConfigProvider(), SourcesProvider())

        # 获取 transformer
        tushare = container.get(TushareExchangeTransformer)
        tdx = container.get(TdxExchangeTransformer)

        # 验证功能
        assert tushare.to_standard("000001.SZ") == "000001.XSHE"
        assert tushare.from_standard("000001.XSHE") == "000001.SZ"

        assert tdx.to_standard("000001.SZ") == "000001.XSHE"
        assert tdx.from_standard("000001.XSHE") == "000001.SZ"

        # 清理
        container.close()

    def test_exchange_transformers_get_method(self, monkeypatch):
        """测试 ExchangeTransformers.get() 方法."""
        # 设置环境
        monkeypatch.setenv("ENVIRONMENT", "testing")

        # 创建容器
        container = make_container(ConfigProvider(), SourcesProvider())

        # 获取 ExchangeTransformers
        transformers = container.get(ExchangeTransformers)

        # 测试 get 方法
        tushare = transformers.get("tushare")
        assert isinstance(tushare, ExchangeTransformer)
        assert isinstance(tushare, TushareExchangeTransformer)

        tdx = transformers.get("tdx")
        assert isinstance(tdx, ExchangeTransformer)
        assert isinstance(tdx, TdxExchangeTransformer)

        # 清理
        container.close()

    def test_all_transformers_together(self, monkeypatch):
        """测试所有 transformer 一起获取."""
        # 设置环境
        monkeypatch.setenv("ENVIRONMENT", "testing")

        # 创建容器
        container = make_container(ConfigProvider(), SourcesProvider())

        # 获取所有 transformer
        tushare = container.get(TushareExchangeTransformer)
        tdx = container.get(TdxExchangeTransformer)
        transformers = container.get(ExchangeTransformers)

        # 验证所有 transformer 都正确
        assert isinstance(tushare, TushareExchangeTransformer)
        assert isinstance(tdx, TdxExchangeTransformer)
        assert isinstance(transformers, ExchangeTransformers)

        # 验证 ExchangeTransformers 内部的 transformer 是同一实例
        assert transformers.tushare is tushare
        assert transformers.tdx is tdx

        # 清理
        container.close()
