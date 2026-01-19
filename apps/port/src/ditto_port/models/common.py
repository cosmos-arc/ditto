"""Common models for API responses."""

from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    """
    Standard error response model for API errors.

    Used for external API responses, so using Pydantic BaseModel (not frozen dataclass).
    """

    status_code: int
    error: str
    detail: str | None = None
    error_code: str | None = None
    request_id: str | None = None
    timestamp: float | None = None

    model_config = ConfigDict(
        # API 响应模型：必须 strict=True 防止类型强制转换
        strict=True,
        # 忽略额外字段，确保向后兼容
        extra="ignore",
    )
