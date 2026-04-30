"""DittoError 全局异常继承链测试.

验证 Phase 0.1 异常体系统一：
- DittoError 为全局根
- DataError/DerivedError 继承 DittoError
- 消除双重定义（DataSourceError/SourceFetchError）
- 各包域根存在且继承 DittoError
- 无异常直接继承 Exception（除 DittoError 自身）
"""

import pytest
from ditto_kernel.exceptions import DataError, DittoError


class TestDittoErrorRoot:
    """DittoError 全局根验证."""

    def test_ditto_error_inherits_exception(self) -> None:
        assert issubclass(DittoError, Exception)

    def test_data_error_inherits_ditto_error(self) -> None:
        assert issubclass(DataError, DittoError)

    def test_catch_ditto_error_catches_data_error(self) -> None:
        with pytest.raises(DittoError):
            raise DataError("test")

    def test_ditto_error_catches_identifier_error(self) -> None:
        from ditto_kernel.exceptions import IdentifierError

        with pytest.raises(DittoError):
            raise IdentifierError("test")

    def test_ditto_error_catches_derived_error(self) -> None:
        from ditto_data.errors import DerivedError

        with pytest.raises(DittoError):
            raise DerivedError("test")

    def test_ditto_error_catches_data_source_error(self) -> None:
        from ditto_data.errors import DataSourceError

        with pytest.raises(DittoError):
            raise DataSourceError("test", source="tushare")

    def test_ditto_error_catches_api_error(self) -> None:
        from ditto_apps.api.errors import APIError

        with pytest.raises(DittoError):
            raise APIError("test")


class TestDataErrorHierarchy:
    """DataError 层级验证."""

    def test_validation_error_inherits_data_error(self) -> None:
        from ditto_data.errors import ValidationError

        assert issubclass(ValidationError, DataError)

    def test_calendar_error_inherits_data_error(self) -> None:
        from ditto_data.errors import CalendarError

        assert issubclass(CalendarError, DataError)

    def test_persistence_error_inherits_data_error(self) -> None:
        from ditto_data.errors import PersistenceError

        assert issubclass(PersistenceError, DataError)

    def test_network_error_inherits_data_source_error(self) -> None:
        from ditto_data.errors import NetworkError

        assert issubclass(NetworkError, DataError)

    def test_auth_error_inherits_data_source_error(self) -> None:
        from ditto_data.errors import AuthError

        assert issubclass(AuthError, DataError)

    def test_source_fetch_error_inherits_data_source_error(self) -> None:
        from ditto_data.errors import SourceFetchError

        assert issubclass(SourceFetchError, DataError)

    def test_ingestion_orphans_inherit_data_error(self) -> None:
        from ditto_data.errors import (
            DataChangedError,
            LateArrivalRejectedError,
            NotTradingDayError,
        )

        assert issubclass(NotTradingDayError, DataError)
        assert issubclass(DataChangedError, DataError)
        assert issubclass(LateArrivalRejectedError, DataError)


class TestDerivedErrorHierarchy:
    """DerivedError 层级验证."""

    def test_derived_error_inherits_ditto_error(self) -> None:
        from ditto_data.errors import DerivedError

        assert issubclass(DerivedError, DittoError)

    def test_derived_not_found_inherits_derived_error(self) -> None:
        from ditto_data.errors import DerivedError, DerivedNotFoundError

        assert issubclass(DerivedNotFoundError, DerivedError)

    def test_dead_subclasses_removed(self) -> None:
        import ditto_data.errors as m

        assert not hasattr(m, "DerivedMaterializationError")
        assert not hasattr(m, "DerivedDependencyError")


class TestNoDuplicateDefinitions:
    """消除双重定义验证."""

    def test_data_source_error_single_definition(self) -> None:
        from ditto_data.errors import DataSourceError

        assert DataSourceError.__module__ == "ditto_data.errors"

    def test_source_fetch_error_single_definition(self) -> None:
        from ditto_data.errors import SourceFetchError

        assert SourceFetchError.__module__ == "ditto_data.errors"

    def test_sources_base_no_own_definitions(self) -> None:
        from ditto_data.sources import base

        has_own = hasattr(base, "DataSourceError")
        assert not has_own or base.DataSourceError.__module__ == "ditto_data.errors"

    def test_base_subclasses_merged(self) -> None:
        from ditto_data.errors import (
            DataSourceError,
            SourceAuthenticationError,
            SourceConfigurationError,
            SourceRateLimitError,
            SourceTransformationError,
        )

        assert issubclass(SourceConfigurationError, DataSourceError)
        assert issubclass(SourceAuthenticationError, DataSourceError)
        assert issubclass(SourceRateLimitError, DataSourceError)
        assert issubclass(SourceTransformationError, DataSourceError)


class TestInterfacesMerge:
    """Interfaces 层异常清理验证."""

    def test_ditto_exception_removed(self) -> None:
        import ditto_apps.exceptions as m

        assert not hasattr(m, "DittoException")

    def test_dead_subclasses_removed(self) -> None:
        import ditto_apps.exceptions as m

        for name in (
            "DataNotFoundError",
            "InvalidDateError",
            "DatabaseError",
            "ExternalServiceError",
        ):
            assert not hasattr(m, name), f"{name} should be removed"

    def test_route_validation_error_inherits_ditto_error(self) -> None:
        from ditto_apps.exceptions import RouteValidationError

        assert issubclass(RouteValidationError, DittoError)

    def test_api_error_inherits_ditto_error(self) -> None:
        from ditto_apps.api.errors import APIError

        assert issubclass(APIError, DittoError)
        assert not issubclass(APIError, DataError)

    def test_api_subclasses_inherit_ditto_error(self) -> None:
        from ditto_apps.api.errors import (
            BadRequestError,
            ConflictError,
            DateRangeError,
            ForbiddenError,
            NotFoundError,
            RateLimitError,
        )

        for cls in [
            DateRangeError,
            RateLimitError,
            NotFoundError,
            ConflictError,
            ForbiddenError,
            BadRequestError,
        ]:
            assert issubclass(cls, DittoError), (
                f"{cls.__name__} should inherit DittoError"
            )


class TestPerPackageDomainRoots:
    """各包域根验证."""

    def test_engine_error_exists(self) -> None:
        from ditto_engine.exceptions import EngineError

        assert issubclass(EngineError, DittoError)

    def test_analytics_error_exists(self) -> None:
        from ditto_analytics.exceptions import AnalyticsError

        assert issubclass(AnalyticsError, DittoError)

    def test_app_error_exists(self) -> None:
        from ditto_app.exceptions import AppError

        assert issubclass(AppError, DittoError)

    def test_infra_error_exists(self) -> None:
        from ditto_platform.exceptions import InfraError

        assert issubclass(InfraError, DittoError)

    def test_engine_orphan_uses_domain_root(self) -> None:
        from ditto_engine.accounting.order_book import StateTransitionError
        from ditto_engine.exceptions import EngineError

        assert issubclass(StateTransitionError, EngineError)

    def test_analytics_orphans_use_domain_root(self) -> None:
        from ditto_analytics.exceptions import AnalyticsError
        from ditto_analytics.expression.diagnostics import ExpressionCompileError
        from ditto_analytics.research.domain import LateArrivalError

        assert issubclass(ExpressionCompileError, AnalyticsError)
        assert issubclass(LateArrivalError, AnalyticsError)

    def test_app_orphans_use_domain_root(self) -> None:
        from ditto_app.exceptions import AppError
        from ditto_app.process.materialization.cascade_orchestrator import (
            CascadeDepthExceededError,
        )
        from ditto_app.process.materialization.types import MissingDependencyError

        assert issubclass(CascadeDepthExceededError, AppError)
        assert issubclass(MissingDependencyError, AppError)

    def test_infra_orphans_use_domain_root(self) -> None:
        from ditto_platform.exceptions import InfraError
        from ditto_platform.foundation.concurrency.filelock import LockAcquisitionError
        from ditto_platform.foundation.config.errors import ConfigInitError

        assert issubclass(ConfigInitError, InfraError)
        assert issubclass(LockAcquisitionError, InfraError)


class TestNoBareExceptionInheritance:
    """验证无异常直接继承 Exception（除 DittoError 自身）."""

    def test_ditto_error_only_bare_exception_root(self) -> None:
        """DittoError 是唯一允许直接继承 Exception 的类."""
        from ditto_data.errors import DerivedError

        assert DittoError.__bases__ == (Exception,)
        assert DataError.__bases__ == (DittoError,)
        assert DerivedError.__bases__ == (DittoError,)
