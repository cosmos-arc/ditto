"""Facade service for data versioning (freeze) management."""

from __future__ import annotations

from ditto_data.models.storage import FreezeManifest
from ditto_data.runtime.freeze_manager import FreezeManager

__all__ = ["FreezeStore"]


class FreezeStore:
    """
    Data versioning service wrapping FreezeManager.

    Provides a service-layer interface for freeze operations,
    keeping runtime details encapsulated within Data layer.
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
