"""DataHub 层 - 数据源 Provider。"""

from collections.abc import Iterator

from dishka import Provider, Scope, provide
from ditto_datahub.config import DataSourceSettings
from ditto_datahub.sources import ExchangeTransformers
from ditto_datahub.sources.fred.fred_source import FredSource
from ditto_datahub.sources.source import DataSources
from ditto_datahub.sources.tdx.transformer import TdxExchangeTransformer
from ditto_datahub.sources.tushare.transformer import TushareExchangeTransformer
from ditto_datahub.sources.tushare.tushare_source import TushareSource

__all__ = ["SourcesProvider"]


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
    def tushare_transformer(self) -> TushareExchangeTransformer:
        """Tushare 交易所转换器."""
        return TushareExchangeTransformer()

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
