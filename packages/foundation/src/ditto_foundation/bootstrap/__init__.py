"""
Application bootstrap module.

Provides application initialization and lifecycle management capabilities.
"""

from ditto_foundation.bootstrap.initializer import (
    AppInitializer,
    get_initializer,
    initialize_app,
    reset_for_testing,
)

__all__ = [
    "AppInitializer",
    "get_initializer",
    "initialize_app",
    "reset_for_testing",
]
