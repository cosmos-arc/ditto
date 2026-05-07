"""Pure functions for partition pruning of year-based parquet files."""

from __future__ import annotations

from datetime import date
from pathlib import Path

__all__ = [
    "prune_parquet_paths",
]


def prune_parquet_paths(
    version_root: Path,
    *,
    start: str | None = None,
    end: str | None = None,
) -> list[Path]:
    """
    Return sorted parquet paths relevant to *[start, end]* date range.

    Strategy:
    - When **both** ``start`` and ``end`` are provided, compute the year span
      and only construct ``<year>.parquet`` candidates — checking each for
      existence.  This avoids a filesystem glob over the entire directory.
    - Otherwise (missing either bound) fall back to ``glob("*.parquet")``
      so no files are accidentally excluded.

    The function deliberately only inspects files named ``<YYYY>.parquet``
    in the root of ``version_root`` — sub-directories like ``_ephemeral/``
    are never visited.
    """
    if start is not None and end is not None:
        start_date = date.fromisoformat(start[:10])
        end_date = date.fromisoformat(end[:10])
        year_start = start_date.year
        year_end = end_date.year

        paths: list[Path] = []
        for year in range(year_start, year_end + 1):
            candidate = version_root / f"{year}.parquet"
            if candidate.is_file():
                paths.append(candidate)
        return sorted(paths)

    # Fallback: glob all parquet files in the directory root.
    # ``glob("*.parquet")`` only matches files — not directories.
    return sorted(version_root.glob("*.parquet"))
