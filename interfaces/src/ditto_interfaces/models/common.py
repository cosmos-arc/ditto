"""API 响应通用模型."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, computed_field

T = TypeVar("T")


class PaginationRequest(BaseModel):
    """
    分页请求模型.

    Attributes:
        limit: 每页数量, 默认 100, 范围 1-1000.
        offset: 偏移量, 默认 0, 非负整数.

    """

    limit: int = Field(default=100, ge=1, le=1000, description="每页数量, 范围 1-1000")
    offset: int = Field(default=0, ge=0, description="偏移量, 非负整数")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class PaginationResponse(BaseModel):
    """
    分页响应模型.

    Attributes:
        total: 总记录数.
        limit: 每页数量.
        offset: 当前偏移量.
        has_more: 是否有更多数据(计算字段).

    """

    total: int = Field(ge=0, description="总记录数")
    limit: int = Field(ge=1, description="每页数量")
    offset: int = Field(ge=0, description="当前偏移量")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )

    @computed_field
    @property
    def has_more(self) -> bool:
        """判断是否还有更多数据."""
        return self.offset + self.limit < self.total


class APIResponse(BaseModel, Generic[T]):  # noqa: UP046  # Pydantic requires Generic[T]
    """
    统一 API 响应模型.

    泛型模型, 用于包装任意类型的数据响应.

    Attributes:
        data: 响应数据.
        pagination: 分页信息(可选).

    """

    data: T = Field(description="响应数据")
    pagination: PaginationResponse | None = Field(
        default=None, description="分页信息(可选)"
    )

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


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
        # API 响应模型: 必须 strict=True 防止类型强制转换
        strict=True,
        # 忽略额外字段, 确保向后兼容
        extra="ignore",
    )
