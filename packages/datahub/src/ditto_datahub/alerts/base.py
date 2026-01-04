"""Alert base classes and interfaces."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class AlertLevel(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    def __lt__(self, other: object) -> bool:
        """Compare alert levels by severity."""
        if not isinstance(other, AlertLevel):
            return NotImplemented
        order = [
            AlertLevel.INFO,
            AlertLevel.WARNING,
            AlertLevel.ERROR,
            AlertLevel.CRITICAL,
        ]
        return order.index(self) < order.index(other)

    def __le__(self, other: object) -> bool:
        """Compare alert levels by severity."""
        if not isinstance(other, AlertLevel):
            return NotImplemented
        return self == other or self < other

    def __gt__(self, other: object) -> bool:
        """Compare alert levels by severity."""
        if not isinstance(other, AlertLevel):
            return NotImplemented
        return not self <= other

    def __ge__(self, other: object) -> bool:
        """Compare alert levels by severity."""
        if not isinstance(other, AlertLevel):
            return NotImplemented
        return self == other or self > other


@dataclass(frozen=True)
class AlertMessage:
    """Alert message data."""

    level: AlertLevel
    title: str
    content: str
    context: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Set default context."""
        if self.context is None:
            object.__setattr__(self, "context", {})

    def format(self) -> str:
        """Format alert message for display."""
        context_str = ""
        if self.context:
            context_str = "\n" + "\n".join(
                f"  {k}: {v}" for k, v in self.context.items()
            )

        return f"[{self.level.value.upper()}] {self.title}\n{self.content}{context_str}"


class AlertSender(ABC):
    """Abstract base class for alert senders."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Get sender name."""
        ...

    @abstractmethod
    def send(self, message: AlertMessage) -> bool:
        """
        Send alert message.

        Args:
            message: Alert message to send.

        Returns:
            True if send was successful, False otherwise.

        """
        ...
