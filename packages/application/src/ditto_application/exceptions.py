"""App domain exception root."""

from ditto_kernel.exceptions import DittoError


class AppError(DittoError):
    """应用域基础异常."""


class AppConfigurationError(AppError):
    """应用配置异常."""


class AppCommandError(AppError):
    """应用命令异常."""


class AppNotFoundError(AppCommandError):
    """命令目标不存在。"""


class AppConflictError(AppCommandError):
    """命令幂等键或当前资源状态发生冲突。"""


class AppQueryError(AppError):
    """应用查询异常."""


class AppProcessError(AppError):
    """应用流程编排异常."""


class AppBuilderError(AppError):
    """应用运行时装配异常."""


__all__ = [
    "AppBuilderError",
    "AppCommandError",
    "AppConfigurationError",
    "AppConflictError",
    "AppError",
    "AppNotFoundError",
    "AppProcessError",
    "AppQueryError",
]
