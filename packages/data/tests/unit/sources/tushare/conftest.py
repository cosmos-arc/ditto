"""Pytest fixtures for tushare source tests."""

import pytest
from ditto_data.config import DataSourceSettings
from ditto_data.sources.tushare.client import TushareClient
from ditto_data.sources.tushare.tushare_source import TushareSource
from ditto_data.sources.tushare.utils.http_utils import response_to_dataframe


class NoRetryTushareClient(TushareClient):
    """禁用重试的 TushareClient（用于测试加速）."""

    def query(
        self,
        api_name: str,
        fields: str,
        **params: str | int,
    ):
        """直接调用 _query，跳过 @retry 装饰器."""
        # 调用父类的 _query 方法（无 retry）
        data = self._query(api_name, fields, **params)
        # 转换为 DataFrame
        return response_to_dataframe(data)


class NoRetryTushareSource(TushareSource):
    """使用 NoRetryTushareClient 的 TushareSource (组合模式)."""

    def __init__(self, token: str | None = None) -> None:
        """初始化时创建无重试的专门 Adapter 实例."""
        # 导入专门的适配器类
        from ditto_data.sources.tushare.adapters.calendar import (
            CalendarTushareAdapter,
        )
        from ditto_data.sources.tushare.adapters.etf import ETFTushareAdapter
        from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

        # 为每个专门 Adapter 创建无重试的实例
        settings = DataSourceSettings(tushare_token=token or "")
        self._calendar = CalendarTushareAdapter(token=token, settings=settings)
        self._stock = StockTushareAdapter(token=token, settings=settings)
        self._etf = ETFTushareAdapter(token=token, settings=settings)

        # 替换它们的 client 为无重试版本（从现有 client 获取 token）
        self._calendar._client = NoRetryTushareClient(
            token=self._calendar._client._token,
            settings=settings,
        )
        self._stock._client = NoRetryTushareClient(
            token=self._stock._client._token,
            settings=settings,
        )
        self._etf._client = NoRetryTushareClient(
            token=self._etf._client._token,
            settings=settings,
        )


@pytest.fixture
def tushare_source() -> NoRetryTushareSource:
    """提供无重试延迟的 TushareSource 实例（测试加速）.

    使用方式:
        def test_api_error(tushare_source, respx_mock):
            respx_mock.post("http://api.tushare.pro").mock(
                return_value=httpx.Response(500, text="Error")
            )
            with pytest.raises(SourceFetchError):
                tushare_source.fetch_calendar("2024-01-01", "2024-01-03")
    """
    # 设置测试 token
    return NoRetryTushareSource(token="test_token")
