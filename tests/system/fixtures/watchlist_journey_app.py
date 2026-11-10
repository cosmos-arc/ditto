"""Watchlist journey fixture: seeded instrument catalog over isolated real state.

The production app runs without mocks; only deterministic metadata rows are
seeded so name/code search, exact-identity reopen, and explicit handling of
unknown/delisted objects can be accepted through the real UI and API.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

from ditto_apps.registry.fresh_runtime import create_fresh_runtime
from ditto_data.models.metadata import InstrumentRegistration
from ditto_data.storage.metadata.instrument.instrument_writer import InstrumentWriter
from ditto_platform.foundation import SQLiteClient, SQLitePool

if os.environ.get("DITTO_ENVIRONMENT") != "testing":
    raise RuntimeError("watchlist journey fixture requires testing mode")
_root = Path(os.environ["DITTO_ACCEPTANCE_DATA_ROOT"]).resolve()
if not _root.is_relative_to(Path("/tmp").resolve()):
    raise RuntimeError("watchlist journey fixture requires isolated /tmp state")
_state = _root / "state"
os.environ.update(
    {
        "DITTO_STATE_ROOT": str(_state),
        "SQLITE_PATH": str(_state / "metadata/metadata.sqlite"),
        "ENVIRONMENT": "testing",
    }
)

# 120 只活跃股票：默认目录页（limit ≤ 100）装不下第 115 行，
# 保存后重开必须走 instrument_id 精确身份解析，而不是首页目录成员判断。
STOCK_BASE_ID = 3_000_000
FAR_STOCK_INDEX = 115
FAR_STOCK_ID = STOCK_BASE_ID + FAR_STOCK_INDEX
FAR_STOCK_NAME = "目录样本股115"
ETF_ID = 3_100_001
ETF_NAME = "样本ETF观察"
DELISTED_ID = STOCK_BASE_ID + 121
DELISTED_NAME = "已退市样本"


def _seed(root: Path) -> None:
    create_fresh_runtime(root / "state")
    pool = SQLitePool(str(root / "state/metadata/metadata.sqlite"))
    client = SQLiteClient(pool)
    writer = InstrumentWriter(client=client, cache=None)
    for index in range(1, 121):
        ticker = 600_000 + index
        writer.register(
            STOCK_BASE_ID + index,
            InstrumentRegistration(
                source_ticker=f"{ticker}.SH",
                ticker=str(ticker),
                name=f"目录样本股{index:03d}",
                exchange="SSE",
                asset_class="stock",
                list_date="2001-08-27",
            ),
        )
    writer.register(
        ETF_ID,
        InstrumentRegistration(
            source_ticker="510777.SH",
            ticker="510777",
            name=ETF_NAME,
            exchange="SSE",
            asset_class="etf",
            list_date="2012-05-28",
        ),
    )
    # 退市样本：注册即带退市日期，is_active=False，行保留在目录中。
    writer.register(
        DELISTED_ID,
        InstrumentRegistration(
            source_ticker="600121.SH",
            ticker="600121",
            name=DELISTED_NAME,
            exchange="SSE",
            asset_class="stock",
            list_date="2001-08-27",
            delist_date="2026-06-30",
        ),
    )
    pool.close_all()


_seed(_root)

app = importlib.import_module("ditto_apps.main").app
