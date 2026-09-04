"""Exact persisted IndustryRotation reads for UI and API consumers."""

from __future__ import annotations

from ditto_strategy.industry_rotation.store import IndustryRotationReader

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.selection_views import (
    IndustryRotationView,
    to_industry_rotation_view,
)

__all__ = ["IndustryRotationQueryService"]


class IndustryRotationQueryService:
    """Read a content-addressed rotation snapshot without latest-state fallback."""

    def __init__(self, reader: IndustryRotationReader) -> None:
        self._reader = reader

    def get(self, snapshot_id: str) -> IndustryRotationView:
        """Return one exact persisted snapshot or fail closed."""
        if not snapshot_id.strip():
            raise AppQueryError(
                "industry rotation snapshot_id must be non-empty",
                details={"reason": "invalid_industry_rotation_snapshot_id"},
            )
        value = self._reader.get_rotation(snapshot_id)
        if value is None:
            raise AppQueryError(
                f"industry rotation not found: {snapshot_id}",
                details={
                    "reason": "industry_rotation_not_found",
                    "snapshot_id": snapshot_id,
                },
            )
        return to_industry_rotation_view(value)
