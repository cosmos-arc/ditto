"""CLI compatibility wrapper for the registry-composed live snapshot builder."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Literal, cast

import orjson

from ditto_apps.registry.live.r3_live_snapshot_builder import (
    LiveDatasetSnapshotBinding,
    LiveResearchSnapshotBuild,
    build_composed_live_research_snapshot,
    build_live_research_snapshot,
)

type LiveLane = Literal["stock", "etf"]

__all__ = [
    "LiveDatasetSnapshotBinding",
    "LiveResearchSnapshotBuild",
    "build_live_research_snapshot",
]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", required=True, choices=("stock", "etf"))
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--etf-ticker",
        action="append",
        dest="etf_tickers",
        help="Narrow the ETF lane to exact SelectionRun ticker(s).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Build one live snapshot using the configured production composition root."""
    args = _parser().parse_args(argv)
    root = args.data_root.expanduser().resolve(strict=True)
    output = args.output.expanduser().resolve(strict=False)
    configured_root = os.environ.get("DITTO_DATA_ROOT")
    if configured_root is None or Path(configured_root).expanduser().resolve() != root:
        raise SystemExit(
            "DITTO_DATA_ROOT must exactly match --data-root before composition"
        )
    result = build_composed_live_research_snapshot(
        lane=cast("LiveLane", args.lane),
        data_root=root,
        etf_tickers=None if args.etf_tickers is None else tuple(args.etf_tickers),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        orjson.dumps(asdict(result), option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
        + b"\n"
    )
    sys.stdout.write(
        orjson.dumps(
            {
                "lane": result.lane,
                "manifest_hash": result.manifest_hash,
                "row_count": result.row_count,
                "snapshot_id": result.snapshot_id,
            },
            option=orjson.OPT_SORT_KEYS,
        ).decode()
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
