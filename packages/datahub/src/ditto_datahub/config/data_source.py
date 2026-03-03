"""DataHub 数据源配置."""

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

    # Token
    tushare_token: str = Field(default="")

    # FRED API key (美国宏观数据)
    fred_api_key: str = Field(default="")

    # 通达信数据源配置（用于质量对账）
    tdx_path: str = Field(default="D:\\new_tdx\\vipdoc")


__all__ = ["DataSourceSettings"]
