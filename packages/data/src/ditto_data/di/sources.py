"""Data 层 - 数据源 Provider。"""

from collections.abc import Iterator

from dishka import Provider, Scope, provide

from ditto_data.config import DataSourceSettings
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.fred.fred_source import FredSource
from ditto_data.sources.protocols import (
    CapitalFetcher,
    FundamentalFetcher,
    MacroFetcher,
    MarketFetcher,
    MetadataFetcher,
)
from ditto_data.sources.registry import SourceRegistry
from ditto_data.sources.source import DataSources
from ditto_data.sources.tdx.source import TdxSource
from ditto_data.sources.tdx.transformer import TdxExchangeTransformer
from ditto_data.sources.tushare.transformer import TushareExchangeTransformer
from ditto_data.sources.tushare.tushare_source import TushareSource

__all__ = ["SourcesProvider"]

_TUSHARE_PROTOCOLS: list[type] = [
    MetadataFetcher,
    MarketFetcher,
    FundamentalFetcher,
    CapitalFetcher,
    MacroFetcher,
]

_FRED_PROTOCOLS: list[type] = [
    MacroFetcher,
]


class SourcesProvider(Provider):
    """外部数据源组件 Provider."""

    scope = Scope.APP

    @provide
    def tushare_source(
        self,
        data_source_settings: DataSourceSettings,
    ) -> Iterator[TushareSource]:
        """
        Tushare 数据源（应用级单例）.

        Token 和配置从 DataSourceSettings 注入.
        使用 yield 语法确保资源正确释放。
        """
        source = TushareSource(
            settings=data_source_settings,
            token=data_source_settings.tushare_token,
        )
        yield source
        source.close()

    @provide
    def fred_source(
        self,
        data_source_settings: DataSourceSettings,
    ) -> FredSource | None:
        """
        FRED 数据源（应用级单例）.

        仅在配置了 fred_api_key 时创建。

        Args:
            data_source_settings: 数据源配置

        Returns:
            FredSource 实例或 None（如果未配置 API key）

        """
        api_key = data_source_settings.fred_api_key
        if not api_key:
            return None
        return FredSource(api_key=api_key)

    @provide
    def data_sources(
        self,
        tushare_source: TushareSource,
        fred_source: FredSource | None,
    ) -> DataSources:
        """
        DataSources 组合器（应用级单例）.

        Args:
            tushare_source: Tushare 数据源实例
            fred_source: FRED 数据源实例（可选）

        """
        return DataSources(tushare=tushare_source, fred=fred_source)

    @provide
    def source_registry(
        self,
        tushare_source: TushareSource,
        fred_source: FredSource | None,
    ) -> SourceRegistry:
        """
        SourceRegistry — 按 Protocol 能力注册和查找数据源.

        每个数据源按其实现的 Fetcher Protocol 注册，消费者通过
        registry.get("tushare", MarketFetcher) 获取类型安全的实例。
        """
        registry = SourceRegistry()
        for proto in _TUSHARE_PROTOCOLS:
            registry.register("tushare", proto, tushare_source)
        if fred_source is not None:
            for proto in _FRED_PROTOCOLS:
                registry.register("fred", proto, fred_source)
        return registry

    @provide
    def tushare_transformer(self) -> TushareExchangeTransformer:
        """Tushare 交易所转换器."""
        return TushareExchangeTransformer()

    @provide
    def tdx_source(self, data_source_settings: DataSourceSettings) -> TdxSource:
        """通达信数据源 — 仅用于质量对账."""
        return TdxSource(data_source_settings=data_source_settings)

    @provide
    def tdx_transformer(self) -> TdxExchangeTransformer:
        """TDX 交易所转换器."""
        return TdxExchangeTransformer()

    @provide
    def exchange_transformers(
        self,
        tushare_transformer: TushareExchangeTransformer,
        tdx_transformer: TdxExchangeTransformer,
    ) -> ExchangeTransformers:
        """
        Exchange transformer 工厂.

        Args:
            tushare_transformer: Tushare 交易所转换器
            tdx_transformer: TDX 交易所转换器

        """
        return ExchangeTransformers(
            tushare=tushare_transformer,
            tdx=tdx_transformer,
        )
