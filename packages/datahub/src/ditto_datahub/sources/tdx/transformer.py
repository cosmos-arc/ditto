"""TDX (通达信) 交易所转换器实现."""

from __future__ import annotations

# TDX exchange 到 Ditto exchange 的映射
# TDX 使用: SZ (深圳), SH (上海), BJ (北京)
# Ditto 使用 ISO 10383 MIC 简化版: XSHE, XSHG, XBSE
_TDX_TO_DITTO: dict[str, str] = {
    "SZ": "XSHE",
    "SH": "XSHG",
    "BJ": "XBSE",
}

_DITTO_TO_TDX: dict[str, str] = {v: k for k, v in _TDX_TO_DITTO.items()}


class TdxExchangeTransformer:
    """
    TDX (通达信) 数据源交易所转换器.

    实现 ExchangeTransformer 协议，提供 TDX 代码与标准格式之间的双向转换.
    标准格式使用 ISO 10383 MIC 简化版（如 XSHE, XSHG, XBSE）.

    TDX 与 Tushare 使用相同的交易所代码格式（.SZ, .SH, .BJ）.

    Example:
        >>> transformer = TdxExchangeTransformer()
        >>> transformer.to_standard("000001.SZ")
        '000001.XSHE'
        >>> transformer.from_standard("000001.XSHE")
        '000001.SZ'

    """

    def to_standard(self, source_ticker: str) -> str:
        """
        将 TDX 代码转换为标准格式.

        Args:
            source_ticker: TDX 代码 (e.g., "000001.SZ")

        Returns:
            标准格式代码 (e.g., "000001.XSHE")

        Example:
            >>> transformer = TdxExchangeTransformer()
            >>> transformer.to_standard("000001.SZ")
            '000001.XSHE'
            >>> transformer.to_standard("600000.SH")
            '600000.XSHG'
            >>> transformer.to_standard("000001")  # 无后缀
            '000001'

        """
        if "." not in source_ticker:
            return source_ticker
        ticker, exchange = source_ticker.split(".", 1)
        ditto_exchange = _TDX_TO_DITTO.get(exchange, exchange)
        return f"{ticker}.{ditto_exchange}"

    def from_standard(self, standard_ticker: str) -> str:
        """
        将标准格式转换为 TDX 代码.

        Args:
            standard_ticker: 标准格式代码 (e.g., "000001.XSHE")

        Returns:
            TDX 代码 (e.g., "000001.SZ")

        Example:
            >>> transformer = TdxExchangeTransformer()
            >>> transformer.from_standard("000001.XSHE")
            '000001.SZ'
            >>> transformer.from_standard("600000.XSHG")
            '600000.SH'
            >>> transformer.from_standard("000001")  # 无后缀
            '000001'

        """
        if "." not in standard_ticker:
            return standard_ticker
        ticker, exchange = standard_ticker.split(".", 1)
        tdx_exchange = _DITTO_TO_TDX.get(exchange, exchange)
        return f"{ticker}.{tdx_exchange}"


__all__ = ["TdxExchangeTransformer"]
