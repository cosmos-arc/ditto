"""Data 数据源配置."""

from pydantic import BaseModel, ConfigDict, Field


class DataSourceSettings(BaseModel):
    """数据源配置."""

    model_config = ConfigDict(extra="ignore")

    # HTTP 配置
    http_base_url: str = Field(default="http://api.tushare.pro")
    http_timeout: float = Field(default=30.0, ge=1.0, le=300.0)

    # 重试配置
    retry_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_multiplier: float = Field(default=1.0, ge=0.1)
    retry_min_wait: float = Field(default=1.0, ge=0.1)
    retry_max_wait: float = Field(default=10.0, ge=1.0)

    # 限流配置
    rate_limit_profile: str = Field(default="free")
    rate_limit_global_rate: int | None = Field(default=None)
    rate_limit_daily_rate: int | None = Field(default=None)
    # 日配额覆盖（次/天，官方直连档位默认 100000；None = 沿用档位默认）
    rate_limit_daily_quota: int | None = Field(default=None)

    # Token
    tushare_token: str = Field(default="")

    # FRED API key (美国宏观数据)
    fred_api_key: str = Field(default="")

    # fuyao（同花顺开源金融数据，冗余源）
    fuyao_api_key: str = Field(default="")
    fuyao_base_url: str = Field(default="https://fuyao.aicubes.cn")

    # 新浪外盘期货（免费公开无 key，#436）：显式启用而非按缺 key 跳过；
    # 无 SLA，源故障由复合源合同显式报错。
    sina_enabled: bool = Field(default=True)
    sina_base_url: str = Field(default="https://stock2.finance.sina.com.cn")


__all__ = ["DataSourceSettings"]
