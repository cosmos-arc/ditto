"""
Port application notification module.

Provides business-level alert management on top of Foundation's
notification infrastructure.
"""

from ditto_port.notifications.manager import AlertManager

__all__ = ["AlertManager"]
