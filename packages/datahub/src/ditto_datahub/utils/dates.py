"""
Re-export date normalization utilities from foundation.

This module re-exports DateInput and normalize_date from ditto_foundation.util.dates
for backward compatibility.
"""

# Re-export from foundation for backward compatibility
from ditto_foundation.util.dates import DateInput, normalize_date

__all__ = ["DateInput", "normalize_date"]
