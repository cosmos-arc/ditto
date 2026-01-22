"""DataHub 数据源配置."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DataSourceSettings(BaseSettings):
    """数据源配置."""

    model_config = SettingsConfigDict(
        env_prefix="DATASOURCE_",
        extra="ignore",
    )

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


__all__ = ["DataSourceSettings"]
