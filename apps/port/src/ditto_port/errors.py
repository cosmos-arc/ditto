"""
Port 层异常层次定义.

提供清晰的异常层次结构，用于区分不同类型的错误场景：
- DataSourceError: 数据源相关（网络、认证、数据校验）
- PersistenceError: 持久化相关（写入失败）

设计原则：
- 使用具体异常类型，不使用通用 Exception
- 包含上下文信息（source, cause 等）
- 使用 raise ... from e 链式异常保留调试信息
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class DittoPortError(Exception):
    """
    Port 层基础异常类.

    所有 Port 层异常的基类，提供统一的错误处理接口。

    Attributes:
        message: 错误消息.
        details: 额外的错误详情字典.

    """

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        初始化 DittoPortError.

        Args:
            message: 错误消息.
            details: 额外的错误详情字典.

        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        """返回错误消息."""
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


# ============================================================================
# 数据源相关异常
# ============================================================================


class DataSourceError(DittoPortError):
    """
    数据源错误基类.

    所有与外部数据源交互相关的异常基类。

    Attributes:
        source: 数据源名称（如 "tushare", "fred"）.

    """

    def __init__(
        self,
        message: str,
        source: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        初始化 DataSourceError.

        Args:
            message: 错误消息.
            source: 数据源名称.
            details: 额外的错误详情字典.

        """
        _details = {"source": source}
        if details:
            _details.update(details)
        super().__init__(message, _details)
        self.source = source


class NetworkError(DataSourceError):
    """
    网络错误.

    当网络超时、连接失败或传输错误时抛出。

    Attributes:
        timeout: 是否为超时错误.
        cause: 原始异常（用于链式异常追踪）.

    """

    def __init__(
        self,
        message: str,
        source: str,
        *,
        timeout: bool = False,
        cause: Exception | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        初始化 NetworkError.

        Args:
            message: 错误消息.
            source: 数据源名称.
            timeout: 是否为超时错误.
            cause: 原始异常.
            details: 额外的错误详情字典.

        """
        _details = {"timeout": timeout}
        if details:
            _details.update(details)
        super().__init__(message, source, _details)
        self.timeout = timeout
        self.__cause__ = cause

    @classmethod
    def from_httpx(
        cls,
        error: Exception,
        source: str,
        context: str | None = None,
    ) -> NetworkError:
        """
        从 httpx 异常创建 NetworkError.

        Args:
            error: httpx 异常实例.
            source: 数据源名称.
            context: 额外上下文信息（如数据集名称）.

        Returns:
            NetworkError 实例.

        """
        import httpx  # noqa: PLC0415

        is_timeout = isinstance(error, httpx.TimeoutException)
        error_type = type(error).__name__
        msg = f"Network error ({error_type})"
        if context:
            msg = f"{msg} during {context}"
        msg = f"{msg}: {error}"

        return cls(
            message=msg,
            source=source,
            timeout=is_timeout,
            cause=error,
        )


class AuthError(DataSourceError):
    """
    认证错误.

    当数据源认证失败（如 API Key 无效、过期）时抛出。

    Attributes:
        auth_type: 认证类型（如 "api_key", "oauth"）.

    """

    def __init__(
        self,
        message: str,
        source: str,
        *,
        auth_type: str = "api_key",
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        初始化 AuthError.

        Args:
            message: 错误消息.
            source: 数据源名称.
            auth_type: 认证类型.
            details: 额外的错误详情字典.

        """
        _details = {"auth_type": auth_type}
        if details:
            _details.update(details)
        super().__init__(message, source, _details)
        self.auth_type = auth_type


class DataValidationError(DataSourceError):
    """
    数据校验错误.

    当从数据源获取的数据不符合预期格式或约束时抛出。

    Attributes:
        dataset: 数据集名称.
        field: 校验失败的字段名（可选）.

    """

    def __init__(
        self,
        message: str,
        source: str,
        *,
        dataset: str | None = None,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        初始化 DataValidationError.

        Args:
            message: 错误消息.
            source: 数据源名称.
            dataset: 数据集名称.
            field: 校验失败的字段名.
            details: 额外的错误详情字典.

        """
        _details: dict[str, Any] = {}
        if dataset:
            _details["dataset"] = dataset
        if field:
            _details["field"] = field
        if details:
            _details.update(details)
        super().__init__(message, source, _details)
        self.dataset = dataset
        self.field = field


class SourceFetchError(DataSourceError):
    """
    数据获取错误.

    当从数据源获取数据失败时抛出（非网络、非认证原因）。

    用于包装数据源特定的获取错误，提供统一的错误处理接口。

    """

    def __init__(
        self,
        message: str,
        source: str,
        *,
        cause: Exception | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        初始化 SourceFetchError.

        Args:
            message: 错误消息.
            source: 数据源名称.
            cause: 原始异常.
            details: 额外的错误详情字典.

        """
        super().__init__(message, source, details)
        self.__cause__ = cause


# ============================================================================
# 持久化相关异常
# ============================================================================


class PersistenceError(DittoPortError):
    """
    持久化错误基类.

    所有与数据持久化相关的异常基类。

    Attributes:
        dataset: 数据集名称（可选）.

    """

    def __init__(
        self,
        message: str,
        *,
        dataset: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        初始化 PersistenceError.

        Args:
            message: 错误消息.
            dataset: 数据集名称.
            details: 额外的错误详情字典.

        """
        _details: dict[str, Any] = {}
        if dataset:
            _details["dataset"] = dataset
        if details:
            _details.update(details)
        super().__init__(message, _details)
        self.dataset = dataset


class WriteError(PersistenceError):
    """
    写入错误.

    当数据写入失败时抛出。

    Attributes:
        cause: 原始异常（用于链式异常追踪）.

    """

    def __init__(
        self,
        message: str,
        *,
        dataset: str | None = None,
        cause: Exception | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        初始化 WriteError.

        Args:
            message: 错误消息.
            dataset: 数据集名称.
            cause: 原始异常.
            details: 额外的错误详情字典.

        """
        super().__init__(message, dataset=dataset, details=details)
        self.__cause__ = cause

    @classmethod
    def from_exception(
        cls,
        error: Exception,
        dataset: str | None = None,
        context: str | None = None,
    ) -> WriteError:
        """
        从异常创建 WriteError.

        Args:
            error: 原始异常.
            dataset: 数据集名称.
            context: 额外上下文信息.

        Returns:
            WriteError 实例.

        """
        error_type = type(error).__name__
        msg = f"Write error ({error_type})"
        if context:
            msg = f"{msg} during {context}"
        msg = f"{msg}: {error}"

        return cls(
            message=msg,
            dataset=dataset,
            cause=error,
        )


# ============================================================================
# 异常转换工具函数
# ============================================================================


def convert_httpx_to_network_error(
    error: Exception,
    source: str,
    context: str | None = None,
) -> NetworkError:
    """
    将 httpx 异常转换为 NetworkError.

    用于在边界层统一处理 httpx 异常，避免外部异常类型外泄。

    Args:
        error: 原始异常（期望是 httpx 异常）.
        source: 数据源名称.
        context: 额外上下文信息.

    Returns:
        NetworkError 实例.

    Raises:
        ValueError: 如果 error 不是 httpx 异常.

    """
    import httpx  # noqa: PLC0415

    if not isinstance(error, (httpx.NetworkError, httpx.TimeoutException)):
        raise ValueError(
            "Expected httpx.NetworkError or httpx.TimeoutException, "
            + f"got {type(error).__name__}"
        )

    return NetworkError.from_httpx(error, source, context)
