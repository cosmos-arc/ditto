"""Persistence and validation-related error classes."""

from ditto_kernel.exceptions import DataError as _DataError


class DataChangedError(_DataError):
    """数据已变更异常（checksum 变更，force=False 时抛出）。"""

    def __init__(
        self,
        trade_date: str,
        old_checksum: str,
        new_checksum: str,
    ) -> None:
        self.trade_date = trade_date
        self.old_checksum = old_checksum
        self.new_checksum = new_checksum
        super().__init__(
            f"Data changed for {trade_date}: checksum {old_checksum} → {new_checksum}. "
            + "Use force=True to overwrite."
        )


class LateArrivalRejectedError(_DataError):
    """延迟到达数据被拒绝异常。"""

    def __init__(
        self,
        delay_days: int,
        max_delay_days: int,
        trade_date: str,
        knowledge_date: str,
    ) -> None:
        self.delay_days = delay_days
        self.max_delay_days = max_delay_days
        self.trade_date = trade_date
        self.knowledge_date = knowledge_date
        super().__init__(
            f"数据延迟到达被拒绝: trade_date={trade_date}, "
            + f"knowledge_date={knowledge_date}, "
            + f"延迟 {delay_days} 天超过阈值 {max_delay_days} 天"
        )


class ValidationError(_DataError):
    """DataFrame schema validation failed."""

    pass


class DatasetNotFoundError(_DataError):
    """Dataset directory or files do not exist."""

    def __init__(
        self,
        message: str = "Dataset not found",
        dataset: str | None = None,
    ) -> None:
        """
        Initialize DatasetNotFoundError.

        Args:
            message: Error message.
            dataset: The dataset name that was not found.

        """
        details: dict[str, object] = {}
        if dataset:
            details["dataset"] = dataset
        super().__init__(message, details if details else None)


class PartitionNotFoundError(_DataError):
    """Year partition file does not exist."""

    def __init__(
        self,
        message: str = "Partition not found",
        dataset: str | None = None,
        year: int | None = None,
    ) -> None:
        """
        Initialize PartitionNotFoundError.

        Args:
            message: Error message.
            dataset: The dataset name.
            year: The year partition that was not found.

        """
        details: dict[str, object] = {}
        if dataset:
            details["dataset"] = dataset
        if year:
            details["year"] = year
        super().__init__(message, details if details else None)


class SchemaValidationError(ValidationError):
    """SourceSchema validation failed."""

    pass


class PersistenceError(_DataError):
    """
    持久化错误基类。

    所有与数据持久化相关的异常基类。

    Attributes:
        dataset: 数据集名称（可选）.

    """

    def __init__(
        self,
        message: str,
        *,
        dataset: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        _details: dict[str, object] = {}
        if dataset:
            _details["dataset"] = dataset
        if details:
            _details.update(details)
        super().__init__(message, _details)
        self.dataset = dataset


class WriteError(PersistenceError):
    """
    写入错误。

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
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, dataset=dataset, details=details)
        self.__cause__ = cause

    @classmethod
    def from_exception(
        cls,
        error: Exception,
        dataset: str | None = None,
        context: str | None = None,
    ) -> "WriteError":
        """
        从异常创建 WriteError。

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
