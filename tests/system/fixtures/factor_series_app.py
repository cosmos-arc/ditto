"""Real evaluation-stack factor chart fixture over a seeded isolated store.

Charts under test are computed at read time by the production query path:
derived factor artifact (seeded through the production catalog/persistence
services) + ETF bars (seeded parquet) feed ``FactorEvaluator.evaluate_series``
over ``ForwardReturnService``. Prices are engineered so the factor rank
predicts forward returns (positive IC with quantile monotonicity).
"""

from __future__ import annotations

import importlib
import os
from datetime import date, timedelta
from pathlib import Path

import polars as pl
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.fresh_runtime import create_fresh_runtime
from ditto_data.models.metadata import InstrumentRegistration
from ditto_data.storage.metadata.instrument.instrument_writer import InstrumentWriter
from ditto_features.models.derived import (
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_features.services.derived.artifact_persistence_service import (
    ArtifactPersistenceService,
)
from ditto_features.services.derived_catalog_service import DerivedCatalogService
from ditto_platform.foundation import (
    OnDuplicate,
    ParquetStore,
    SQLiteClient,
    SQLitePool,
)

if os.environ.get("DITTO_ENVIRONMENT") != "testing":
    raise RuntimeError("factor series fixture requires testing mode")
_root = Path(os.environ["DITTO_ACCEPTANCE_DATA_ROOT"]).resolve()
if not _root.is_relative_to(Path("/tmp").resolve()):
    raise RuntimeError("factor series fixture requires isolated /tmp state")
_state = _root / "state"
os.environ.update(
    {
        "DITTO_STATE_ROOT": str(_state),
        "SQLITE_PATH": str(_state / "metadata/metadata.sqlite"),
        "ENVIRONMENT": "testing",
    }
)

FACTOR_ID = "fx-momentum-20"
START_DATE = "2026-01-05"
END_DATE = "2026-04-24"

# 20 只 ETF × 80 个交易日：横截面广度支撑 5 分位与秩相关。
N_INSTRUMENTS = 20
INSTRUMENT_IDS = [2_010_000 + index for index in range(N_INSTRUMENTS)]
TRADING_DAYS: list[date] = []
_cursor = date(2026, 1, 5)
while len(TRADING_DAYS) < 80:
    if _cursor.weekday() < 5:
        TRADING_DAYS.append(_cursor)
    _cursor += timedelta(days=1)


def _close_path(instrument_index: int) -> list[float]:
    """确定性价格路径：日收益与因子秩同向（因子有预测力），叠加小幅确定性噪声."""
    closes: list[float] = []
    base = 3.0 + instrument_index * 0.25
    for day_index in range(len(TRADING_DAYS)):
        noise = 0.0004 * ((day_index * 7 + instrument_index * 3) % 5 - 2)
        drift = 0.0012 * (instrument_index - N_INSTRUMENTS / 2) / 10 + noise
        previous = closes[-1] if closes else base
        closes.append(round(previous * (1 + drift), 4))
    return closes


def _ticker(instrument_index: int, *, with_suffix: bool) -> str:
    digits = f"51{instrument_index % 10:02d}{(instrument_index * 7) % 90 + 10:02d}"
    return f"{digits}.SH" if with_suffix else digits


def _bars_frame(instrument_index: int, instrument_id: int) -> pl.DataFrame:
    closes = _close_path(instrument_index)
    rows = []
    previous_close = closes[0]
    for day, close in zip(TRADING_DAYS, closes, strict=True):
        rows.append(
            {
                "instrument_id": instrument_id,
                "trade_date": day.isoformat(),
                "open": round(previous_close, 4),
                "high": round(max(previous_close, close) * 1.004, 4),
                "low": round(min(previous_close, close) * 0.996, 4),
                "close": close,
                "pre_close": previous_close,
                "volume": 500_000 + instrument_index * 1_000,
                "amount": round(close * 500_000, 2),
                "turnover_rate": 0.4,
            },
        )
        previous_close = close
    return pl.DataFrame(rows)


def _factor_frame() -> pl.DataFrame:
    """因子值 = 标的秩（-1..1 归一），与次日收益严格同向 → IC 显著为正."""
    rows = []
    for instrument_index, instrument_id in enumerate(INSTRUMENT_IDS):
        value = (instrument_index - (N_INSTRUMENTS - 1) / 2) / ((N_INSTRUMENTS - 1) / 2)
        for day in TRADING_DAYS:
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "trade_date": day.isoformat(),
                    "value": round(value, 6),
                },
            )
    return pl.DataFrame(rows).sort(["instrument_id", "trade_date"])


def _seed() -> None:
    create_fresh_runtime(_state)
    pool = SQLitePool(str(_state / "metadata/metadata.sqlite"))
    client = SQLiteClient(pool)
    writer = InstrumentWriter(client=client, cache=None)
    for instrument_index, instrument_id in enumerate(INSTRUMENT_IDS):
        writer.register(
            instrument_id,
            InstrumentRegistration(
                source_ticker=_ticker(instrument_index, with_suffix=True),
                ticker=_ticker(instrument_index, with_suffix=False),
                name=f"ETF-因子验收-{instrument_index}",
                exchange="SSE",
                asset_class="etf",
                list_date="2019-01-01",
            ),
        )
    store = ParquetStore(
        _state,
        key_columns=("instrument_id", "trade_date"),
        date_column="trade_date",
        instrument_column="instrument_id",
    )
    store.write(
        "market/etf/bars",
        pl.concat(
            [
                _bars_frame(index, instrument_id)
                for index, instrument_id in enumerate(INSTRUMENT_IDS)
            ],
        ),
        OnDuplicate.ERROR.value,
        year=2026,
    )

    # 衍生因子 artifact：catalog 记录 + 持久分区走生产写入器（路径合同一致）。
    container = make_app_container()
    try:
        catalog = container.get(DerivedCatalogService)
    finally:
        container.close()
    spec = DerivedSpecRecord(
        derived_id=FACTOR_ID,
        version=1,
        role="factor",
        materialization_profile="series",
        spec_hash="f" * 64,
        spec_json={
            "factor_id": FACTOR_ID,
            "description": "fixture momentum-like rank factor",
        },
        created_at="2026-04-25T00:00:00Z",
    )
    catalog.save_spec(spec)
    catalog.save_version(
        DerivedVersionRecord(
            derived_id=FACTOR_ID,
            version=1,
            status="published",
            engine_version="fixture-v1",
            is_online=False,
            is_primary=True,
            created_at="2026-04-25T00:00:00Z",
            updated_at=None,
        ),
    )
    factor_frame = _factor_frame()
    catalog.save_state(
        DerivedStateRecord(
            derived_id=FACTOR_ID,
            active_version=1,
            coverage_start=START_DATE,
            coverage_end=END_DATE,
            watermark=END_DATE,
            latest_run_id="fx-seed-run-1",
            latest_run_status="succeeded",
            total_rows=factor_frame.height,
            updated_at="2026-04-25T00:00:00Z",
        ),
    )
    persistence = ArtifactPersistenceService(artifact_root=_state)
    persistence.write_durable_partitions(
        spec=spec,
        time_key="trade_date",
        run_id="fx-seed-run-1",
        frame=factor_frame,
        request_start=START_DATE,
        request_end=END_DATE,
        source_snapshot_id=None,
    )


_seed()

app = importlib.import_module("ditto_apps.main").app
