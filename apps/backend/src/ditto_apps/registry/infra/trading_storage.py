"""Composition binding for the dedicated trading recovery unit."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_data.config.data_store import DataStoreSettings
from ditto_execution.di import ExecutionDatabase, initialize_execution_storage
from ditto_platform.foundation import SQLitePool

__all__ = ["TradingStorageProvider"]


class TradingStorageProvider(Provider):
    """Bind execution-owned adapters to ``trading/trading.sqlite``."""

    scope = Scope.APP

    @provide
    def execution_database(
        self,
        settings: DataStoreSettings,
    ) -> Iterator[ExecutionDatabase]:
        """Own the dedicated trading pool for one application lifetime."""
        override = os.getenv("DITTO_TRADING_SQLITE_PATH")
        database = (
            Path(override).expanduser().resolve(strict=False)
            if override
            else settings.data_root / "trading" / "trading.sqlite"
        )
        database.parent.mkdir(parents=True, exist_ok=True)
        pool = SQLitePool(str(database))
        try:
            initialize_execution_storage(pool)
            yield ExecutionDatabase(pool)
        finally:
            pool.close_all()
