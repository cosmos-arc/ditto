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
        # Python 3.12+ 规范：使用 strict=True
        strict=True,
        # API 响应不需要 frozen，因为 Pydantic BaseModel 默认可变
        # 如果需要不可变性，可以添加 frozen=True
    )
