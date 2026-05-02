"""Execution storage DI Provider — 审计服务装配."""

from dishka import Provider, Scope, provide
from ditto_platform.foundation import SQLitePool

from ditto_execution.audit import ExecutionAuditService

__all__ = ["ExecutionStorageProvider"]


class ExecutionStorageProvider(Provider):
    """执行存储 Provider — 审计服务初始化."""

    scope = Scope.APP

    @provide
    def execution_audit_service(self, sqlite_pool: SQLitePool) -> ExecutionAuditService:  # noqa: D102
        service = ExecutionAuditService(sqlite_pool)
        service.init_schema()
        return service
