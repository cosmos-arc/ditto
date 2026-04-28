"""Infra domain exception root."""

from ditto_kernel.exceptions import DittoError


class InfraError(DittoError):
    """基础设施域基础异常."""


__all__ = ["InfraError"]
