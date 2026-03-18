"""Research artifact file I/O service."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

import orjson
import polars as pl

__all__ = ["ResearchArtifactService"]


class ResearchArtifactService:
    """Encapsulates research artifact file I/O for the DataHub layer."""

    def __init__(self, *, artifact_root: Path) -> None:
        self._root = Path(artifact_root)

    # -- Parquet --

    def read_parquet(self, relative_path: str) -> pl.DataFrame:
        """Read a parquet file by its relative path from artifact_root."""
        path = self._root / relative_path
        if not path.exists():
            raise FileNotFoundError(f"research parquet not found: {relative_path}")
        return pl.read_parquet(path)

    def write_parquet(
        self,
        relative_path: str,
        frame: pl.DataFrame,
    ) -> None:
        """Write a parquet file, creating parent directories as needed."""
        path = self._root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(path)

    # -- JSON --

    def read_json(self, relative_path: str) -> dict[str, object]:
        """Read a JSON file by its relative path from artifact_root."""
        path = self._root / relative_path
        if not path.exists():
            raise FileNotFoundError(f"research JSON not found: {relative_path}")
        payload = orjson.loads(path.read_bytes())
        if not isinstance(payload, dict):
            raise ValueError(f"expected JSON object at {relative_path}")
        return cast(dict[str, object], payload)

    def write_json(
        self,
        relative_path: str,
        data: Mapping[str, object],
    ) -> None:
        """Write a JSON file with sorted keys, creating parent directories."""
        path = self._root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            orjson.dumps(
                data,
                option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
            )
        )

    # -- Artifact resolution --

    def resolve_artifact_relative_path(
        self,
        derived_id: str,
        version: int,
    ) -> str | None:
        """Resolve artifact relative path for a derived/version pair."""
        artifact_root = self._root / "derived" / "artifacts"
        matches = sorted(artifact_root.glob(f"*/{derived_id}/v{version}"))
        if matches:
            return str(matches[0].relative_to(self._root))
        return None

    def read_source_snapshot_ids(
        self,
        artifact_relative_path: str,
    ) -> tuple[str, ...]:
        """Read source snapshot IDs from the latest artifact metadata."""
        version_root = self._root / artifact_relative_path
        runs_root = version_root / "_runs"
        if not runs_root.exists():
            return ()
        metadata_paths = tuple(runs_root.glob("*/artifact_metadata.json"))
        if not metadata_paths:
            return ()
        latest_metadata = max(
            metadata_paths,
            key=lambda p: p.stat().st_mtime_ns,
        )
        payload = orjson.loads(latest_metadata.read_bytes())
        raw_snapshots = payload.get("input_snapshots", [])
        if not isinstance(raw_snapshots, list):
            return ()
        ids: list[str] = []
        for item in cast(list[object], raw_snapshots):
            if isinstance(item, str) and item:
                ids.append(item)
        return tuple(sorted(set(ids)))
