"""Ingestion-specific error types."""

from __future__ import annotations


class SourceFetchError(Exception):
    """Source fetch error used at Port service boundary."""

    def __init__(self, message: str, source: str) -> None:
        super().__init__(message)
        self.source = source
