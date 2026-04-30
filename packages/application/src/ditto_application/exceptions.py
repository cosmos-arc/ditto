"""App domain exception root."""

from ditto_kernel.exceptions import DittoError


class AppError(DittoError):
    """应用域基础异常."""


__all__ = ["AppError"]
