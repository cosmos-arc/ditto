"""Application-owned scheduler control values."""

from __future__ import annotations

from enum import StrEnum

from ditto_application.exceptions import AppProcessError


class ExperimentExecutionControlChanged(AppProcessError):
    """A durable PAUSE/CANCEL request won the race before attempt start."""


class ResearchExecutionDirective(StrEnum):
    """Normal durable control observed by an executing research child."""

    RUN = "run"
    PAUSE = "pause"
    CANCEL = "cancel"
