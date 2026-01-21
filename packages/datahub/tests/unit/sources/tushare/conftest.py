"""Pytest fixtures for tushare source tests."""

import pytest
from ditto_datahub.sources.tushare.client import TushareClient
from ditto_datahub.sources.tushare.http_utils import response_to_dataframe
from ditto_datahub.sources.tushare.tushare_source import TushareSource


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
    """使用 NoRetryTushareClient 的 TushareSource."""

    def __init__(self, token: str | None = None) -> None:
        """初始化时创建 NoRetryTushareClient."""
        # 复用父类的 token 获取逻辑
        from ditto_datahub.sources.tushare.client import _get_tushare_token

        # 优先使用测试 token
        self._token = token or _get_tushare_token(token)
        # 创建无重试的 client
        self._client = NoRetryTushareClient(token=self._token)


@pytest.fixture
def tushare_source(monkeypatch: pytest.MonkeyPatch) -> NoRetryTushareSource:
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
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token")
    return NoRetryTushareSource(token="test_token")
