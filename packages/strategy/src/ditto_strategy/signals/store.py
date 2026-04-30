from __future__ import annotations

from typing import Protocol


class SignalStore(Protocol):
    """Persist and load strategy signal batches."""
