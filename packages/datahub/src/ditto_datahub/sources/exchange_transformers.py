"""Exchange transformer protocol and factory."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["ExchangeTransformer", "ExchangeTransformers"]


@runtime_checkable
class ExchangeTransformer(Protocol):
    """
    数据源交易所转换器协议.

    定义了数据源代码与标准格式之间的双向转换接口.
    标准格式使用 ISO 10383 MIC 简化版（如 XSHE, XSHG, XBSE）.

    Example:
        >>> transformer = TushareExchangeTransformer()
        >>> transformer.to_standard("000001.SZ")
        '000001.XSHE'
        >>> transformer.from_standard("000001.XSHE")
        '000001.SZ'

    """

    def to_standard(self, source_ticker: str) -> str:
        """
        将数据源代码转换为标准格式.

        Args:
            source_ticker: 数据源代码 (e.g., "000001.SZ")

        Returns:
            标准格式代码 (e.g., "000001.XSHE")

        """
        ...

    def from_standard(self, standard_ticker: str) -> str:
        """
        将标准格式转换为数据源代码.

        Args:
            standard_ticker: 标准格式代码 (e.g., "000001.XSHE")

        Returns:
            数据源代码 (e.g., "000001.SZ")

        """
        ...


class ExchangeTransformers:
    """
    Exchange transformer 工厂（通过 DI 注入）.

    管理所有数据源的交易所转换器实例，提供统一的访问入口.
    所有转换器实例通过构造函数注入，支持依赖倒置和测试替换.

    Example:
        >>> from ditto_datahub.sources.exchange_transformers import (
        ...     ExchangeTransformers,
        ... )
        >>> from ditto_datahub.sources.tushare.transformer import (
        ...     TushareExchangeTransformer,
        ... )
        >>> from ditto_datahub.sources.tdx.transformer import (
        ...     TdxExchangeTransformer,
        ... )
        >>> transformers = ExchangeTransformers(
        ...     tushare=TushareExchangeTransformer(),
        ...     tdx=TdxExchangeTransformer(),
        ... )
        >>> tushare_tf = transformers.get("tushare")
        >>> tushare_tf.to_standard("000001.SZ")
        '000001.XSHE'

    """

    def __init__(
        self,
        tushare: ExchangeTransformer,
        tdx: ExchangeTransformer,
    ) -> None:
        """
        初始化 ExchangeTransformers.

        Args:
            tushare: Tushare 数据源交易所转换器实例.
            tdx: TDX 数据源交易所转换器实例.

        """
        self._tushare = tushare
        self._tdx = tdx

    @property
    def tushare(self) -> ExchangeTransformer:
        """Get Tushare exchange transformer."""
        return self._tushare

    @property
    def tdx(self) -> ExchangeTransformer:
        """Get TDX exchange transformer."""
        return self._tdx

    def get(self, name: str) -> ExchangeTransformer:
        """
        按名称获取转换器.

        Args:
            name: 数据源名称 (e.g., "tushare", "tdx").

        Returns:
            对应的 ExchangeTransformer 实例.

        Raises:
            ValueError: 如果数据源名称未知.

        """
        normalized_name = name.lower().strip()
        if normalized_name == "tushare":
            return self._tushare
        if normalized_name == "tdx":
            return self._tdx
        raise ValueError(
            f"Unknown source: '{name}'. Supported sources: ['tushare', 'tdx']"
        )
