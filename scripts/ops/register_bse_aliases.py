"""#592 一次性运维：登记北交所新旧代码别名映射.

从 tushare bse_mapping 官方端点拉全量对照（~248 行，冻结历史），
按当前注册表解析 920 新码 → instrument_id，为旧码（43/83/87）登记
instrument_mapping 别名行。幂等：重复执行不重复写。

用法（dev 根示例）:
    DITTO_CONFIG_ROOT=<repo> DITTO_STATE_ROOT=<data root> \
    DITTO_CACHE_ROOT=<cache> uv run --no-sync python \
    scripts/ops/register_bse_aliases.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import typer  # noqa: E402
from ditto_apps.registry.container import make_app_container  # noqa: E402
from ditto_data.services.metadata_service import MetadataService  # noqa: E402
from ditto_data.sources.tushare.tushare_source import TushareSource  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="仅拉取对照表并打印(不登记)"
    )
    args = parser.parse_args()

    container = make_app_container()
    try:
        source = container.get(TushareSource)
        mappings = source.fetch_bse_code_mapping()
        typer.echo(f"bse_mapping rows={mappings.height}")
        if mappings.height == 0:
            typer.echo("empty mapping table; nothing to do")
            return
        if args.dry_run:
            typer.echo(mappings.head(5))
            return
        service = container.get(MetadataService).instrument
        observed_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        summary = service.register_bse_code_aliases(mappings, observed_at=observed_at)
        typer.echo(f"summary={summary}")
        if summary["unresolved_n_code"] or summary["conflict"]:
            raise SystemExit(1)
    finally:
        container.close()


if __name__ == "__main__":
    main()
