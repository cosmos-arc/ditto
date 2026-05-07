"""
Checksum module.

Provides general-purpose checksum capabilities for file integrity verification.
"""

from ditto_platform.foundation.checksum.file import compute_checksum

__all__ = [
    "compute_checksum",
]
