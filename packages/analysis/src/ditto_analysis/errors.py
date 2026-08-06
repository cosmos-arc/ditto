"""Analysis — 研究分析错误定义。"""

from ditto_kernel.exceptions import DittoError

__all__ = [
    "AnalysisError",
    "ExperimentConflictError",
    "ExperimentDatabaseClosedError",
    "ExperimentIdentityError",
    "ExperimentIntegrityError",
    "ExperimentLeaseLostError",
    "ExperimentPersistenceError",
    "ExperimentSchemaError",
    "ExperimentSpecError",
    "ExperimentStateTransitionError",
    "ResearchDatasetError",
]


class AnalysisError(DittoError):
    """分析层基础错误。"""


class ResearchDatasetError(AnalysisError):
    """研究数据集操作错误。"""


class ExperimentIdentityError(AnalysisError):
    """Experiment control-plane identity is absent or malformed."""


class ExperimentSpecError(AnalysisError):
    """An immutable experiment domain specification is invalid."""


class ExperimentStateTransitionError(AnalysisError):
    """An observed experiment status transition is unknown or illegal."""


class ExperimentPersistenceError(AnalysisError):
    """An experiment persistence operation failed without leaking SQLite details."""


class ExperimentIntegrityError(ExperimentPersistenceError):
    """Persisted experiment lineage or immutable payload is inconsistent."""


class ExperimentConflictError(ExperimentPersistenceError):
    """An idempotent replay or optimistic revision conflicts with durable state."""


class ExperimentLeaseLostError(ExperimentConflictError):
    """A scheduler worker no longer owns the supplied fencing token."""


class ExperimentSchemaError(ExperimentPersistenceError):
    """The dedicated research database schema cannot be safely initialized."""


class ExperimentDatabaseClosedError(ExperimentPersistenceError):
    """The dedicated database wrapper has been permanently closed."""
