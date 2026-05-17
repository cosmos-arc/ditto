"""Network, authentication, and data source error classes."""

from ditto_kernel.exceptions import DataError as _DataError


class DataSourceError(_DataError):
    """
    数据源错误基类。

    所有与外部数据源交互相关的异常基类。

    Attributes:
        source: 数据源名称（如 "tushare", "fred"）.

    """

    def __init__(
        self,
        message: str,
        source: str,
        details: dict[str, object] | None = None,
    ) -> None:
        _details: dict[str, object] = {"source": source}
        if details:
            _details.update(details)
        super().__init__(message, _details)
        self.source = source


class NetworkError(DataSourceError):
    """
    网络错误。

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
        details: dict[str, object] | None = None,
    ) -> None:
        _details: dict[str, object] = {"timeout": timeout}
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
    ) -> "NetworkError":
        """
        从 httpx 异常创建 NetworkError。

        Args:
            error: httpx 异常实例.
            source: 数据源名称.
            context: 额外上下文信息（如数据集名称）.

        Returns:
            NetworkError 实例.

        """
        import httpx  # noqa: PLC0415 — 仅错误处理时使用

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
    认证错误。

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
        details: dict[str, object] | None = None,
    ) -> None:
        _details: dict[str, object] = {"auth_type": auth_type}
        if details:
            _details.update(details)
        super().__init__(message, source, _details)
        self.auth_type = auth_type


class DataValidationError(DataSourceError):
    """
    数据校验错误。

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
        details: dict[str, object] | None = None,
    ) -> None:
        _details: dict[str, object] = {}
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
    数据获取错误。

    当从数据源获取数据失败时抛出（非网络、非认证原因）。
    """

    def __init__(
        self,
        message: str,
        source: str,
        *,
        cause: Exception | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, source, details)
        self.__cause__ = cause


class SourceConfigurationError(DataSourceError):
    """数据源配置错误（缺少环境变量、无效配置）。"""

    def __init__(
        self,
        message: str = "Source configuration error",
        *,
        env_var: str | None = None,
        config_key: str | None = None,
    ) -> None:
        details: dict[str, object] = {}
        if env_var:
            details["env_var"] = env_var
        if config_key:
            details["config_key"] = config_key
        super().__init__(message, "unknown", details if details else None)


class SourceAuthenticationError(DataSourceError):
    """数据源认证失败（无效 token、凭证）。"""

    def __init__(
        self,
        message: str = "Authentication failed",
        *,
        source: str | None = None,
    ) -> None:
        super().__init__(message, source=source or "unknown")


class SourceRateLimitError(DataSourceError):
    """数据源限流错误。"""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        source: str | None = None,
        limit: int | None = None,
        window: int | None = None,
    ) -> None:
        details: dict[str, object] = {}
        if limit:
            details["limit"] = limit
        if window:
            details["window"] = window
        super().__init__(message, source or "unknown", details if details else None)


class SourceTransformationError(DataSourceError):
    """数据转换错误（schema 不匹配、转换失败）。"""

    def __init__(
        self,
        message: str = "Data transformation failed",
        *,
        source: str | None = None,
        dataset: str | None = None,
        expected_columns: list[str] | None = None,
        actual_columns: list[str] | None = None,
    ) -> None:
        details: dict[str, object] = {}
        if dataset:
            details["dataset"] = dataset
        if expected_columns:
            details["expected_columns"] = expected_columns
        if actual_columns:
            details["actual_columns"] = actual_columns
        super().__init__(message, source or "unknown", details if details else None)


def convert_httpx_to_network_error(
    error: Exception,
    source: str,
    context: str | None = None,
) -> NetworkError:
    """
    将 httpx 异常转换为 NetworkError。

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
    import httpx  # noqa: PLC0415 — 仅错误处理时使用

    if not isinstance(error, (httpx.NetworkError, httpx.TimeoutException)):
        raise ValueError(
            "Expected httpx.NetworkError or httpx.TimeoutException, "
            + f"got {type(error).__name__}"
        )

    return NetworkError.from_httpx(error, source, context)
