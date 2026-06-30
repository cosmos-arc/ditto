"""Tushare catalog-backed stock-selection real-data e2e.

验证 A 股股票真实 Tushare 数据可完成：
1. market + capital 数据摄取并写入 catalog。
2. stock_selection 策略基于 catalog 数据发布人工交易信号包。

CI 默认跳过（无 token/网络标记）；本地运行：
    pixi run -e dev pytest \
        packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py \
        -m e2e --no-cov -q
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest
from ditto_application.queries.ingestion_status import IngestionStatusQueryFacade
from ditto_apps.registry.container import make_app_container
from ditto_data.services.metadata_service import MetadataService
from ditto_strategy.alpha.specs import ExecutionSpec, StrategySpec
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
TRADE_DATE = "2024-03-29"
SOURCE = "tushare"
SAMPLE_SOURCE_TICKERS = (
    "000001.SZ",
    "000002.SZ",
    "600000.SH",
    "600519.SH",
    "000858.SZ",
)


@dataclass(frozen=True)
class TushareStockSelectionContext:
    """真实 Tushare 股票筛选 E2E 上下文。"""

    data_root: Path
    token: str
    trade_date: str


def _tushare_token() -> str | None:
    """Tushare token: env 优先，回退 keyring。"""
    env_token = os.environ.get("TUSHARE_TOKEN")
    if env_token:
        return env_token

    try:
        import keyring

        return keyring.get_password("tushare", "token") or keyring.get_password(
            "ditto", "tushare"
        )
    except Exception:
        return None


def _redact_token(text: str, token: str) -> str:
    return text.replace(token, "<redacted-tushare-token>") if token else text


def _cli_env(data_root: Path, token: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "DITTO_DATA_ROOT": data_root.as_posix(),
            "ENVIRONMENT": "testing",
            "PYTHONUNBUFFERED": "1",
            "TUSHARE_TOKEN": token,
        }
    )
    return env


def _run_cli(
    data_root: Path,
    token: str,
    args: list[str],
    *,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(  # noqa: S603 - controlled pytest CLI invocation.
        [sys.executable, "-m", "ditto_apps.cli.main", *args],
        cwd=REPO_ROOT,
        env=_cli_env(data_root, token),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        pytest.fail(
            "\n".join(
                [
                    f"CLI command failed: {' '.join(args)}",
                    f"exit_code={completed.returncode}",
                    "stdout:",
                    _redact_token(completed.stdout, token),
                    "stderr:",
                    _redact_token(completed.stderr, token),
                ]
            )
        )
    return completed


@contextmanager
def _app_env(data_root: Path, token: str) -> Iterator[None]:
    keys = ("DITTO_DATA_ROOT", "ENVIRONMENT", "TUSHARE_TOKEN")
    old_values = {key: os.environ.get(key) for key in keys}
    os.environ.update(_cli_env(data_root, token))
    try:
        yield
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="module")
def tushare_stock_selection_context(
    tmp_path_factory: pytest.TempPathFactory,
) -> TushareStockSelectionContext:
    """准备独立真实数据根；无 Tushare token 时 skip。"""
    token = _tushare_token()
    if not token:
        pytest.skip("Tushare token 未配置 (TUSHARE_TOKEN 或 keyring)")

    data_root = tmp_path_factory.mktemp("tushare-stock-selection")
    for args in (
        ["ingest", "metadata", "calendar", TRADE_DATE],
        ["ingest", "metadata", "basic", "stock"],
        ["ingest", "market", "stock", TRADE_DATE],
        ["ingest", "capital", "valuation", TRADE_DATE],
    ):
        _run_cli(data_root, token, args)

    return TushareStockSelectionContext(
        data_root=data_root,
        token=token,
        trade_date=TRADE_DATE,
    )


def _resolve_sample_instruments(
    metadata: MetadataService,
    *,
    asof: str,
) -> dict[str, int]:
    resolved = metadata.instrument.resolve_instrument_ids_batch(
        list(SAMPLE_SOURCE_TICKERS),
        SOURCE,
        asof,
    )
    missing = sorted(set(SAMPLE_SOURCE_TICKERS) - set(resolved))
    assert not missing, f"样本股票未解析到 instrument_id: {missing}"
    return resolved


def _publish_stock_selection_spec(
    catalog: StrategyCatalogService,
    *,
    strategy_id: str,
    universe_id: str,
) -> None:
    spec = StrategySpec(
        strategy_id=strategy_id,
        name="E2E Real Stock Selection Signal",
        template="stock_selection",
        universe=universe_id,
        asset_class="stock",
        execution=ExecutionSpec(frequency="D", method="calendar"),
        benchmark=None,
        params={
            "top_k": 2,
            "signal_factors": ("signal_value",),
            "signal_weights": (1.0,),
            "allocation_method": "equal_weight",
            "cash_target": 0.0,
            "max_weight": 0.6,
            "trend_threshold": 0.0,
            "rebalance_freq": "daily",
        },
        tags=("e2e", "real-data", "stock-selection"),
    )
    catalog.save_spec(
        StrategySpecRecord(
            strategy_id=spec.strategy_id,
            name=spec.name,
            spec_json=asdict(spec),
            version=1,
            tags=spec.tags,
        )
    )
    catalog.publish_spec(spec.strategy_id, 1)


@pytest.mark.e2e
@pytest.mark.integration
class TestTushareCatalogBackedStockSelectionRealFetch:
    """Phase 2: Tushare catalog-backed stock_selection 真实数据验证。"""

    def test_tushare_catalog_backed_market_and_fundamental_fetch(
        self,
        tushare_stock_selection_context: TushareStockSelectionContext,
    ) -> None:
        """真实 market + capital 摄取结果应可通过 catalog 状态查询层读取。"""
        ctx = tushare_stock_selection_context
        with _app_env(ctx.data_root, ctx.token):
            container = make_app_container()
            try:
                facade = container.get(IngestionStatusQueryFacade)
                statuses = {
                    status.dataset: status
                    for status in facade.get_status(
                        ["stock_daily", "valuation_metrics"]
                    )
                }
            finally:
                container.close()

        for dataset in ("stock_daily", "valuation_metrics"):
            status = statuses[dataset]
            assert status.latest_status == "success"
            assert status.latest_date == ctx.trade_date
            assert status.catalog_storage_uri
            assert status.catalog_schema_hash
            assert status.catalog_row_count is not None
            assert status.catalog_row_count > 1_000

    def test_tushare_catalog_backed_stock_selection_to_signal_package(
        self,
        tushare_stock_selection_context: TushareStockSelectionContext,
    ) -> None:
        """真实 catalog 股票行情可驱动 stock_selection 并发布信号包。"""
        ctx = tushare_stock_selection_context
        strategy_id = "e2e_real_stock_selection_signal"
        universe_id = "e2e_real_stock_selection_universe"

        with _app_env(ctx.data_root, ctx.token):
            container = make_app_container()
            try:
                metadata = container.get(MetadataService)
                resolved = _resolve_sample_instruments(
                    metadata,
                    asof=ctx.trade_date,
                )
                metadata.universe.create_universe(
                    universe_id=universe_id,
                    name="E2E Real Stock Selection Universe",
                    description="Tushare real-data E2E universe",
                    universe_type="custom",
                    source_ref=SOURCE,
                )
                metadata.universe.replace_constituents(
                    universe_id,
                    [
                        {
                            "instrument_id": instrument_id,
                            "effective_from": ctx.trade_date,
                            "source": SOURCE,
                            "source_ticker": source_ticker,
                        }
                        for source_ticker, instrument_id in resolved.items()
                    ],
                    ctx.trade_date,
                )
                _publish_stock_selection_spec(
                    container.get(StrategyCatalogService),
                    strategy_id=strategy_id,
                    universe_id=universe_id,
                )
            finally:
                container.close()

        completed = _run_cli(
            ctx.data_root,
            ctx.token,
            [
                "strategy",
                "publish-signals",
                strategy_id,
                ctx.trade_date,
                "--version",
                "1",
                "--allow-experimental-data",
                "--dataset-snapshot",
                "stock_daily=real",
                "--dataset-snapshot",
                "valuation_metrics=real",
                "--factor",
                "signal_value",
                "--threshold",
                "0.0",
            ],
        )

        output = completed.stdout.strip()
        assert f"strategy_id={strategy_id}" in output
        assert f"signal_date={ctx.trade_date}" in output
        assert "run_id=" in output
        assert "checksum=sha256:" in output
        assert (match := re.search(r"\bintents=(\d+)\b", output)) is not None
        assert int(match.group(1)) > 0
