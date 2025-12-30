"""
DQ result models (B.5: Re-export from dq/models.py to eliminate duplication).

This file now re-exports all types from dq/models.py to maintain backward compatibility.
The authoritative definitions are in dq/models.py.
"""

# Re-export all types from models.py
from ditto_datahub.dq.models import (
    DQIssue,
    DQLevel,
    DQResult,
    DQSeverity,
)

__all__ = ["DQIssue", "DQLevel", "DQResult", "DQSeverity"]
