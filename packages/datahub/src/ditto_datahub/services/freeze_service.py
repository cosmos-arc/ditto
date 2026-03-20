"""Facade service for data versioning (freeze) management."""

from __future__ import annotations

from ditto_datahub.models.storage import FreezeManifest
from ditto_datahub.runtime.freeze_manager import FreezeManager

__all__ = ["FreezeService"]


class FreezeService:
    """
    Data versioning service wrapping FreezeManager.

    Provides a service-layer interface for freeze operations,
    keeping runtime details encapsulated within DataHub.
    """

    def __init__(self, freeze_manager: FreezeManager) -> None:
        self._manager = freeze_manager

    def create_freeze(
        self,
        freeze_id: str,
        description: str,
        datasets: list[str],
    ) -> FreezeManifest:
        """Create a freeze manifest recording dataset checksums."""
        return self._manager.create(freeze_id, description, datasets)

    def verify_freeze(
        self,
        freeze_id: str,
        raise_on_error: bool = False,
    ) -> tuple[bool, list[str]]:
        """Verify freeze checksums match current data."""
        return self._manager.verify(freeze_id, raise_on_error)

    def list_freezes(self) -> list[FreezeManifest]:
        """List all freeze manifests."""
        return self._manager.list_freezes()
