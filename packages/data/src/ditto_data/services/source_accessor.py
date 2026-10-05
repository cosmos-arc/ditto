"""
SourceAccessor - 外部数据源访问服务.

封装 DataSources，为 Port 层提供统一的外部数据源访问接口.
"""

from __future__ import annotations

from ditto_data.models.common import Source
from ditto_data.sources.fred.fred_source import FredSource
from ditto_data.sources.reference_config import EtfReferenceConfigSource
from ditto_data.sources.sina.source import SinaSource
from ditto_data.sources.source import DataSources
from ditto_data.sources.tushare.tushare_source import TushareSource


class SourceAccessor:
    """
    外部数据源访问服务.

    封装 DataSources，为 Port 层提供统一的外部数据源访问接口.

    职责：
    - 提供数据源的统一访问入口
    - 支持依赖注入和测试替换
    - 管理不同数据源的获取
    """

    def __init__(
        self,
        sources: DataSources,
        sina_source: SinaSource | None = None,
        etf_reference_config: EtfReferenceConfigSource | None = None,
    ) -> None:
        """
        初始化 SourceAccessor.

        Args:
            sources: DataSources accessor 实例
            sina_source: 新浪外盘连续期货源（#436，免费公开无 key，
                默认启用；sina_enabled=False 时为 None）
            etf_reference_config: 维护者确认的 ETF 参考事实声明源（#408，
                composition root 按配置根解析注入；缺文件时为 None）

        """
        self._sources = sources
        self._sina_source = sina_source
        self._etf_reference_config = etf_reference_config

    def get_source(self, name: str | Source) -> TushareSource | FredSource:
        """
        获取数据源实例.

        Args:
            name: 数据源名称（枚举或字符串，如 "tushare"、Source.TUSHARE）

        Returns:
            TushareSource 或 FredSource 实例

        Raises:
            ValueError: 数据源名称未知

        """
        return self._sources.get(name)

    @property
    def tushare(self) -> TushareSource:
        """
        获取 Tushare 数据源.

        Returns:
            TushareSource 实例

        """
        return self._sources.tushare

    @property
    def fred(self) -> FredSource | None:
        """
        获取 FRED 数据源.

        Returns:
            FredSource 实例或 None

        """
        return self._sources.fred

    @property
    def sina(self) -> SinaSource | None:
        """
        获取新浪外盘连续期货源（#436）.

        Returns:
            SinaSource 实例或 None（sina_enabled=False 时）

        """
        return self._sina_source

    @property
    def etf_reference_config(self) -> EtfReferenceConfigSource | None:
        """
        获取维护者确认的 ETF 参考事实声明源（#408）.

        Returns:
            EtfReferenceConfigSource 实例或 None（声明文件未解析时）

        """
        return self._etf_reference_config
