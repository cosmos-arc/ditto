"""One bounded #711 real-storage run; no source requests or account writes."""

import argparse
import json
import os
import resource
import shutil
import subprocess
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

import orjson
import polars as pl
from ditto_application.queries.account_catalog import ListPaperAccountsQuery
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.capital import CapitalQueryFacade
from ditto_application.queries.capital_profile import (
    CapitalProfileQueryFacade,
    CapitalProfileRequest,
)
from ditto_application.queries.market_chart import (
    MarketChartQueryFacade,
    MarketChartRequest,
)
from ditto_apps.operations.workstation_performance import (
    PerformanceBudgetError,
    PerformanceCase,
    benchmark_workstation,
)
from ditto_apps.registry.container import make_app_container
from loguru import logger

logger.remove()
EXPECTED_BARS = 22
MIN_MARGIN_ROWS = 10
ROOT = Path.cwd()
STATE = Path(os.environ["DITTO_STATE_ROOT"])
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
OUT = args.output.parent
OUT.mkdir(parents=True, exist_ok=True)
CONFIG = Path(os.environ["DITTO_CONFIG_ROOT"])


def footprint():
    def size(root):
        return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())

    wal = STATE / "metadata/metadata.sqlite-wal"
    return {
        "at": datetime.now(UTC).isoformat(),
        "free_bytes": shutil.disk_usage(STATE).free,
        "state_bytes": size(STATE),
        "app_logs_bytes": size(STATE / "logs"),
        "worker_logs_bytes": size(CONFIG / ".cache/prefect-worker"),
        "temp_bytes": size(STATE / "temp"),
        "wal_bytes": wal.stat().st_size if wal.exists() else 0,
        "acceptance_bytes": size(OUT),
    }


def encode(value):
    if isinstance(value, pl.DataFrame):
        return value.to_dicts()
    return str(value)


out = {
    "started_at": datetime.now(UTC).isoformat(),
    "code_sha": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip(),
    "state_root": str(STATE),
    "config_root": str(CONFIG),
    "cache_root": os.environ["DITTO_CACHE_ROOT"],
    "config_hashes": {
        str(p.relative_to(CONFIG)): sha256(p.read_bytes()).hexdigest()
        for p in (CONFIG / "config").rglob("*")
        if p.is_file()
    },
    "before": footprint(),
    "cases": {},
}
assert out["before"]["free_bytes"] >= 20 * 1024**3
clock = datetime.now(UTC)
out["query_clock"] = clock.isoformat()
with closing(make_app_container()) as c:
    chart = c.get(MarketChartQueryFacade)
    profile = c.get(CapitalProfileQueryFacade)
    capital = c.get(CapitalQueryFacade)
    accounts = c.get(ListPaperAccountsQuery).list()
    assert accounts, "no existing Paper portfolio read model"
    ledger = c.get(AccountLedgerQuery)
    account = accounts[0]
    out["portfolio_account_id"] = account.account_id
    for name, op, budget, purpose in [
        (
            "stock_chart",
            lambda: chart.get_chart(
                MarketChartRequest(
                    1000001,
                    "stock",
                    date(2026, 10, 1),
                    date(2026, 11, 6),
                    "daily",
                    "none",
                    True,
                    clock,
                    exchange="SZSE",
                )
            ),
            None,
            "22 daily candles; source-bound chart has no assigned SLO",
        ),
        (
            "etf_adjusted_chart",
            lambda: chart.get_chart(
                MarketChartRequest(
                    2001562,
                    "etf",
                    date(2026, 10, 1),
                    date(2026, 11, 6),
                    "daily",
                    "qfq",
                    True,
                    clock,
                )
            ),
            None,
            "22 daily candles; source-bound adjusted chart has no assigned SLO",
        ),
        (
            "capital_profile",
            lambda: profile.get_profile(
                CapitalProfileRequest(
                    1000001,
                    date(2026, 10, 19),
                    date(2026, 11, 6),
                    True,
                    date(2026, 11, 7),
                )
            ),
            None,
            "Latest multi-dataset composition; no materialized-model SLO",
        ),
        (
            "historical_cutoff",
            lambda: capital.get_margin_trading_range(
                1000001,
                "2024-09-30",
                "2024-09-30",
                date(2024, 10, 8),
                allow_experimental_data=True,
            ),
            None,
            "strict cutoff read only, not historical strategy eligibility",
        ),
        (
            "portfolio_ledger",
            lambda: ledger.get_paper(account_id=account.account_id, as_of="2026-11-06"),
            None,
            "Ledger-derived portfolio; no materialized-model or comparison SLO",
        ),
    ]:
        record = {
            "started_at": datetime.now(UTC).isoformat(),
            "purpose": purpose,
            "result_hashes": [],
            "rss_before_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }

        def checked(name=name, op=op, record=record):
            value = op()
            if name in ("stock_chart", "etf_adjusted_chart"):
                assert len(value.bars) == EXPECTED_BARS
                record["source_snapshot_ids"] = value.source_snapshot_ids
                record["rows"] = len(value.bars)
                record["missing_sessions"] = value.missing_sessions
            elif name == "historical_cutoff":
                assert value.height == 1
                record["rows"] = value.height
            elif name == "capital_profile":
                record["rows"] = {
                    k: getattr(value, k).rows.height
                    for k in ("moneyflow", "top_list", "top_inst", "margin_trading")
                }
                assert value.moneyflow.rows.height > 0
                assert value.margin_trading.rows.height >= MIN_MARGIN_ROWS
                assert all(getattr(value, k).read_error is None for k in record["rows"])
            else:
                record["event_count"] = value.ledger_revision.event_count
                record["ledger_hash"] = value.ledger_revision.ledger_hash
                assert value.ledger_revision.event_count > 0
            digest = sha256(
                orjson.dumps(value, default=encode, option=orjson.OPT_SORT_KEYS)
            ).hexdigest()
            record["result_hashes"].append(digest)
            assert len(set(record["result_hashes"])) == 1, (
                name + " result changed during measurement"
            )
            return value

        try:
            report = benchmark_workstation(
                (PerformanceCase(name, checked, budget),), warmup=5, iterations=40
            )
        except PerformanceBudgetError as failure:
            report = failure.report
        record["performance"] = asdict(report)
        record["rss_peak_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        record["finished_at"] = datetime.now(UTC).isoformat()
        record["result_sha256"] = record["result_hashes"][0]
        record["consistent_calls"] = len(record.pop("result_hashes"))
        out["cases"][name] = record
        args.output.write_text(json.dumps(out, default=str, indent=2))
        print(name, report.cases[0], flush=True)
    rejected = capital.get_margin_trading_range(
        1000001,
        "2024-09-30",
        "2024-09-30",
        date(2024, 10, 7),
        allow_experimental_data=True,
    )
    assert rejected.height == 0
    out["historical_rejection"] = {
        "business_day": "2024-09-30",
        "cutoff": "2024-10-07",
        "rows": 0,
        "allowed_cutoff": "2024-10-08",
        "allowed_rows": 1,
    }
out["after"] = footprint()
out["capacity_passed"] = out["after"]["free_bytes"] >= 20 * 1024**3
out["finished_at"] = datetime.now(UTC).isoformat()
args.output.write_text(json.dumps(out, default=str, indent=2))
assert out["capacity_passed"]
