"""Security Repository for securities master data access."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import TYPE_CHECKING, Any

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.security_store import SecurityStore

if TYPE_CHECKING:
    from ditto_datahub.runtime.sid_allocator import SidAllocator


def _json_serializable(obj: object) -> object:
    """Convert object to JSON serializable format."""
    if isinstance(obj, date):
        return obj.isoformat()
    to_python_method = getattr(obj, "to_python", None)
    if callable(to_python_method):
        return to_python_method()
    return str(obj)


class SecurityRepository:
    """
    Securities master data repository.

    Provides domain-level interface for security data operations,
    coordinating SecurityStore and SidAllocator.
    """

    def __init__(
        self,
        security_store: SecurityStore,
        sid_allocator: SidAllocator,
    ) -> None:
        """
        Initialize SecurityRepository.

        Args:
            security_store: Security store for data access.
            sid_allocator: SID allocator for new securities.

        """
        self._security_store = security_store
        self._sid_allocator = sid_allocator

    @traced("repository.security.get")
    def get(
        self,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        source: str = "tushare",
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        Query securities data.

        Args:
            sids: Filter by SIDs.
            src_codes: Filter by source codes.
            source: Data source identifier.
            asset_class: Filter by asset class.
            exchange: Filter by exchange.
            is_active: Filter by active status.
            asof: Point-in-time query date.

        Returns:
            Securities data DataFrame.

        """
        logger.debug(
            "Fetching securities",
            event="security_get_start",
            sids_count=len(sids) if sids else None,
            src_codes_count=len(src_codes) if src_codes else None,
            source=source,
            asset_class=asset_class,
        )

        result: pl.DataFrame = self._security_store.find_securities(
            sids=sids,
            src_codes=src_codes,
            source=source,
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
            asof=asof,
        )

        logger.debug(
            "Securities fetched",
            event="security_get_complete",
            row_count=len(result),
        )

        # Record metrics
        M.data_records.add(len(result), {"dataset": "security", "operation": "get"})

        return result

    def get_by_sid(self, sid: int) -> dict[str, Any] | None:
        """
        Get security by SID.

        Args:
            sid: Security ID.

        Returns:
            Security data dict, or None if not found.

        """
        return self._security_store.get_by_sid(sid)

    def resolve_identifier(
        self,
        identifier: str,
        source: str = "tushare",
        asof: str | None = None,
    ) -> int | None:
        """
        Resolve identifier to SID.

        Tries src_code first, then symbol.

        Args:
            identifier: Source code or symbol.
            source: Data source identifier.
            asof: Point-in-time query date.

        Returns:
            SID, or None if not found.

        """
        # Try as src_code first
        sid = self._security_store.resolve_sid(identifier, source, asof)
        if sid:
            return sid

        # Try as symbol
        sids = self._security_store.resolve_by_symbol(identifier, source)
        if sids:
            # Return first match (should be unique for active mappings)
            return sids[0]

        return None

    def resolve_identifiers_batch(
        self,
        identifiers: list[str],
        source: str = "tushare",
        asof: str | None = None,
    ) -> dict[str, int]:
        """
        Batch resolve identifiers to SIDs.

        Args:
            identifiers: List of identifiers.
            source: Data source identifier.
            asof: Point-in-time query date.

        Returns:
            Dictionary mapping identifier to SID (only for found identifiers).

        """
        return self._security_store.resolve_sids_batch(identifiers, source, asof)

    def list_all(
        self,
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool = True,
    ) -> list[int]:
        """
        List all security SIDs.

        Args:
            asset_class: Filter by asset class.
            exchange: Filter by exchange.
            is_active: Filter by active status.

        Returns:
            List of SIDs.

        """
        return self._security_store.list_sids(asset_class, exchange, is_active)

    def get_symbol(self, sid: int) -> str | None:
        """
        Get symbol by SID.

        Args:
            sid: Security ID.

        Returns:
            Symbol, or None if not found.

        """
        return self._security_store.get_symbol(sid)

    def get_src_code(
        self,
        sid: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """
        Get source code by SID.

        Args:
            sid: Security ID.
            source: Data source identifier.
            asof: Point-in-time query date.

        Returns:
            Source code, or None if not found.

        """
        return self._security_store.get_src_code(sid, source, asof)

    @traced("repository.security.register")
    def register(  # noqa: PLR0913
        self,
        src_code: str,
        symbol: str,
        name: str,
        exchange: str,
        asset_class: str,
        list_date: str,
        source: str = "tushare",
        board: str | None = None,
    ) -> int:
        """
        Register a new security and allocate SID.

        Args:
            src_code: Source code.
            symbol: Display symbol.
            name: Security name.
            exchange: Exchange code.
            asset_class: Asset class (stock/etf/index).
            list_date: Listing date.
            source: Data source identifier.
            board: Board code (optional).

        Returns:
            Allocated SID.

        """
        logger.info(
            "Registering new security",
            event="security_register_start",
            symbol=symbol,
            src_code=src_code,
            asset_class=asset_class,
        )

        # Allocate SID
        sid = self._sid_allocator.allocate(asset_class)

        # Register to security store
        registered_sid = self._security_store.register(
            sid=sid,
            source=source,
            src_code=src_code,
            symbol=symbol,
            name=name,
            exchange=exchange,
            asset_class=asset_class,
            list_date=list_date,
            board=board,
        )

        logger.info(
            "Security registered successfully",
            event="security_register_complete",
            sid=registered_sid,
            symbol=symbol,
        )

        # Record metrics
        M.data_records.add(1, {"dataset": "security", "operation": "register"})

        return registered_sid

    def register_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: str,
        src_code_col: str,
    ) -> tuple[str, str]:
        """
        Batch register securities from DataFrame.

        Skips securities that already exist (based on src_code resolution).

        Args:
            df: DataFrame with securities data. Must contain columns:
                - src_code_col: Source code column name
                - symbol: Display symbol
                - name: Security name
                - exchange: Exchange code
                - list_date: Listing date
            source: Data source identifier.
            asset_class: Asset class (stock/etf/index).
            src_code_col: Name of the source code column in df.

        Returns:
            Tuple of (file_path, checksum) for tracking purposes.

        """
        logger.info(
            "Starting batch security registration",
            event="security_batch_register_start",
            source=source,
            asset_class=asset_class,
            row_count=len(df),
        )

        registered_count = 0
        skipped_count = 0

        for row in df.to_dicts():
            src_code = row[src_code_col]

            # Check if already exists
            existing_sid = self._security_store.resolve_sid(src_code, source, None)
            if existing_sid is not None:
                skipped_count += 1
                continue

            # Register new security
            self.register(
                src_code=src_code,
                symbol=row["symbol"],
                name=row["name"],
                exchange=row["exchange"],
                asset_class=asset_class,
                list_date=row["list_date"],
                source=source,
                board=row.get("board"),
            )
            registered_count += 1

        # Calculate checksum from DataFrame content
        data_dict = df.to_dict(as_series=False)
        json_str = json.dumps(data_dict, sort_keys=True, default=_json_serializable)
        checksum = hashlib.md5(
            json_str.encode("utf-8"), usedforsecurity=False
        ).hexdigest()

        # File path for tracking (not a real file for SQLite storage)
        file_path = f"security_store:{asset_class}_basic"

        logger.info(
            "Batch security registration completed",
            event="security_batch_register_complete",
            registered=registered_count,
            skipped=skipped_count,
            checksum=checksum,
        )

        # Record metrics
        M.data_records.add(
            registered_count,
            {"dataset": "security", "operation": "register_batch"},
        )

        return file_path, checksum
