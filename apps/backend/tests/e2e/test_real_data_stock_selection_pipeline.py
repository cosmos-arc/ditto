"""Tushare catalog-backed stock-selection real-data e2e.

验证 A 股股票真实 Tushare 数据可完成：
1. market + capital 数据摄取并写入 catalog。
2. stock_selection 策略经官方 EOD 入口通过 freshness/DQ 门禁并发布信号包。

CI 默认在网络访问前跳过（未显式启用）；本地真实演练：
    DITTO_RUN_REAL_DATA_ACCEPTANCE=1 pixi run -e dev pytest \
        apps/backend/tests/e2e/test_real_data_stock_selection_pipeline.py \
        -m e2e --no-cov -q
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import orjson
import pytest
from ditto_application.commands.account import (
    ImportAccountBaselineCommand,
    ImportAccountBaselineHandler,
)
from ditto_application.queries.daily_decision import DailyDecisionQueryFacade
from ditto_application.queries.ingestion_status import IngestionStatusQueryFacade
from ditto_apps.registry.container import make_app_container
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.storage.sqlite.trade.service import TradeService
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
TRADE_DATE = "2024-03-29"
INTENDED_TRADE_DATE = "2024-04-01"
SOURCE = "tushare"
REAL_ACCEPTANCE_STRATEGY_ID = "seed_stock_selection_rotation"
REAL_ACCEPTANCE_UNIVERSE_ID = "csi_a_share"
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
    token: str = field(repr=False)
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


def _bounded_redacted(text: str, token: str, *, limit: int = 10_000) -> str:
    redacted = _redact_token(text, token)
    if len(redacted) <= limit:
        return redacted
    return f"<truncated {len(redacted) - limit} chars>\n{redacted[-limit:]}"


def _failure_stdout_diagnostics(stdout: str, token: str) -> str:
    """Keep actionable EOD facts without dumping every dataset row or secret."""
    try:
        payload = orjson.loads(stdout)
    except orjson.JSONDecodeError:
        return _bounded_redacted(stdout, token)
    if not isinstance(payload, dict):
        return _bounded_redacted(stdout, token)

    ingestion = payload.get("ingestion")
    ingestion_summary = (
        ingestion.get("summary") if isinstance(ingestion, dict) else None
    )
    strategies: list[dict[str, object]] = []
    raw_strategies = payload.get("strategies")
    if isinstance(raw_strategies, list):
        evidence_keys = (
            "strategy_id",
            "strategy_version",
            "status",
            "reason",
            "batch_key",
            "artifact_id",
            "checksum",
        )
        strategies = [
            {key: strategy.get(key) for key in evidence_keys if key in strategy}
            for strategy in raw_strategies
            if isinstance(strategy, dict)
        ]
    summary = {
        "date": payload.get("date"),
        "overall_status": payload.get("overall_status"),
        "ingestion_summary": ingestion_summary,
        "strategies": strategies,
    }
    return _bounded_redacted(
        orjson.dumps(summary, option=orjson.OPT_INDENT_2).decode(),
        token,
    )


def test_cli_failure_diagnostics_are_bounded_structured_and_redacted() -> None:
    token = "unit-test-secret-token"
    stdout = orjson.dumps(
        {
            "date": TRADE_DATE,
            "overall_status": "partial",
            "ingestion": {
                "summary": {"failed_count": 3},
                "t1_results": {"noise": "x" * 50_000},
            },
            "strategies": [
                {
                    "strategy_id": "stock-selection",
                    "status": "failed",
                    "reason": f"secret={token}",
                }
            ],
        }
    ).decode()

    diagnostics = _failure_stdout_diagnostics(stdout, token)

    assert '"failed_count": 3' in diagnostics
    assert '"status": "failed"' in diagnostics
    assert token not in diagnostics
    assert "<redacted-tushare-token>" in diagnostics
    assert "x" * 1_000 not in diagnostics
    assert len(diagnostics) < 12_000


def _cli_env(data_root: Path, token: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "DITTO_STATE_ROOT": data_root.as_posix(),
            "SQLITE_PATH": (data_root / "metadata" / "metadata.sqlite").as_posix(),
            "DUCKDB_PATH": (data_root / "db" / "ditto.duckdb").as_posix(),
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
    __tracebackhide__ = True
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
                    _failure_stdout_diagnostics(completed.stdout, token),
                    "stderr:",
                    _bounded_redacted(completed.stderr, token),
                ]
            )
        )
    return completed


def test_tushare_context_repr_never_contains_token(tmp_path: Path) -> None:
    """即使 pytest 展示失败局部变量，也不能泄露真实数据凭据。"""
    token = "unit-test-secret-token"
    context = TushareStockSelectionContext(
        data_root=tmp_path,
        token=token,
        trade_date=TRADE_DATE,
    )

    assert token not in repr(context)


def test_real_acceptance_designates_the_builtin_published_seed() -> None:
    seed = SEED_STRATEGY_SPECS[REAL_ACCEPTANCE_STRATEGY_ID]

    assert seed.strategy_id == REAL_ACCEPTANCE_STRATEGY_ID
    assert seed.universe == REAL_ACCEPTANCE_UNIVERSE_ID
    assert seed.template == "stock_selection"


@contextmanager
def _app_env(data_root: Path, token: str) -> Iterator[None]:
    keys = (
        "DITTO_STATE_ROOT",
        "SQLITE_PATH",
        "DUCKDB_PATH",
        "ENVIRONMENT",
        "TUSHARE_TOKEN",
    )
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
    """Prepare isolated live evidence only after an explicit operator opt-in."""
    if os.environ.get("DITTO_RUN_REAL_DATA_ACCEPTANCE") != "1":
        pytest.skip("real-data acceptance requires DITTO_RUN_REAL_DATA_ACCEPTANCE=1")
    token = _tushare_token()
    if not token:
        pytest.skip("Tushare token 未配置 (TUSHARE_TOKEN 或 keyring)")

    data_root = tmp_path_factory.mktemp("tushare-stock-selection")
    for args in (
        ["ingest", "metadata", "calendar", TRADE_DATE],
        ["ingest", "metadata", "calendar", INTENDED_TRADE_DATE],
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
    expected_tickers: set[str] = set(SAMPLE_SOURCE_TICKERS)
    missing = sorted(expected_tickers - set(resolved))
    assert not missing, f"样本股票未解析到 instrument_id: {missing}"
    return resolved


def _prepare_designated_seed_universe(ctx: TushareStockSelectionContext) -> None:
    with _app_env(ctx.data_root, ctx.token):
        container = make_app_container()
        try:
            metadata = container.get(MetadataService)
            resolved = _resolve_sample_instruments(metadata, asof=ctx.trade_date)
            metadata.universe.create_universe(
                universe_id=REAL_ACCEPTANCE_UNIVERSE_ID,
                name="E2E Real Stock Selection Universe",
                description="Tushare real-data E2E universe",
                universe_type="custom",
                source_ref=SOURCE,
            )
            metadata.universe.replace_constituents(
                REAL_ACCEPTANCE_UNIVERSE_ID,
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
        finally:
            container.close()


def _bootstrap_designated_seed(ctx: TushareStockSelectionContext) -> int:
    completed = _run_cli(
        ctx.data_root,
        ctx.token,
        ["strategy", "bootstrap-seeds"],
    )
    payload = orjson.loads(completed.stdout)
    result = next(
        item
        for item in payload["results"]
        if item["strategy_id"] == REAL_ACCEPTANCE_STRATEGY_ID
    )
    assert result["status"] == "published"
    assert result["created"] is True
    version = result["version"]
    assert isinstance(version, int)
    return version


def _import_designated_seed_baseline(
    ctx: TushareStockSelectionContext,
    *,
    published_version: int,
) -> None:
    with _app_env(ctx.data_root, ctx.token):
        container = make_app_container()
        try:
            published = container.get(StrategyCatalogService).get_active_published(
                REAL_ACCEPTANCE_STRATEGY_ID
            )
            assert published is not None
            assert published.version == published_version
            assert published.spec_json["universe"] == REAL_ACCEPTANCE_UNIVERSE_ID
            assert published.spec_json["template"] == "stock_selection"
            container.get(ImportAccountBaselineHandler).handle(
                ImportAccountBaselineCommand(
                    account_id="real-paper",
                    strategy_id=REAL_ACCEPTANCE_STRATEGY_ID,
                    snapshot_date=ctx.trade_date,
                    cash_available=1_000_000.0,
                    cash_settled=1_000_000.0,
                    cash_frozen=0.0,
                    total_value=1_000_000.0,
                    nav=1.0,
                )
            )
        finally:
            container.close()


def _assert_live_strategy_evidence(
    payload: dict[str, object],
    *,
    published_version: int,
) -> dict[str, object]:
    assert payload["date"] == TRADE_DATE
    assert payload["overall_status"] in {"success", "partial"}
    strategies = payload["strategies"]
    assert isinstance(strategies, list)
    assert len(strategies) == 1
    strategy = strategies[0]
    assert isinstance(strategy, dict)
    assert strategy["strategy_id"] == REAL_ACCEPTANCE_STRATEGY_ID
    assert strategy["strategy_version"] == str(published_version)
    assert strategy["status"] == "completed"
    assert strategy["artifact_id"]
    checksum = strategy["checksum"]
    assert isinstance(checksum, str)
    assert checksum.startswith("sha256:")
    required_rows = strategy["required_dataset_states"]
    assert isinstance(required_rows, list)
    required_states = {row["dataset"]: row for row in required_rows}
    assert set(required_states) == set(
        SEED_STRATEGY_SPECS[REAL_ACCEPTANCE_STRATEGY_ID].required_datasets
    )
    assert all(
        state["status"] == "ready" and state["snapshot_id"]
        for state in required_states.values()
    )
    return strategy


def _persisted_strategy_evidence_ids(
    ctx: TushareStockSelectionContext,
    *,
    strategy_id: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Read durable artifact/intent identities without mutating recovery evidence."""
    with _app_env(ctx.data_root, ctx.token):
        container = make_app_container()
        try:
            artifact_ids = tuple(
                sorted(
                    artifact.artifact_id
                    for artifact in container.get(
                        StrategyArtifactService
                    ).list_by_strategy(strategy_id)
                )
            )
            intent_ids = tuple(
                sorted(
                    intent.intent_id
                    for intent in container.get(TradeService).list_intents(
                        strategy_id,
                        signal_date=ctx.trade_date,
                    )
                )
            )
        finally:
            container.close()
    return artifact_ids, intent_ids


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

    def test_tushare_catalog_backed_stock_selection_to_signal_package_via_eod(
        self,
        tushare_stock_selection_context: TushareStockSelectionContext,
    ) -> None:
        """The designated built-in published seed must drive live EOD evidence."""
        ctx = tushare_stock_selection_context
        strategy_id = REAL_ACCEPTANCE_STRATEGY_ID
        _prepare_designated_seed_universe(ctx)
        published_version = _bootstrap_designated_seed(ctx)
        _import_designated_seed_baseline(
            ctx,
            published_version=published_version,
        )

        cli_args = [
            "ops",
            "run-eod",
            "--signal-date",
            ctx.trade_date,
            "--strategy-id",
            strategy_id,
            "--account-id",
            "real-paper",
            "--allow-experimental-data",
        ]
        completed = _run_cli(ctx.data_root, ctx.token, cli_args, timeout=600)

        payload = orjson.loads(completed.stdout)
        assert isinstance(payload, dict)
        strategy = _assert_live_strategy_evidence(
            payload,
            published_version=published_version,
        )
        artifact_ids_before, intent_ids_before = _persisted_strategy_evidence_ids(
            ctx,
            strategy_id=strategy_id,
        )

        rerun = _run_cli(ctx.data_root, ctx.token, cli_args, timeout=600)
        rerun_payload = orjson.loads(rerun.stdout)
        assert isinstance(rerun_payload, dict)
        rerun_strategy = _assert_live_strategy_evidence(
            rerun_payload,
            published_version=published_version,
        )
        artifact_ids_after, intent_ids_after = _persisted_strategy_evidence_ids(
            ctx,
            strategy_id=strategy_id,
        )

        assert rerun_strategy["status"] == "completed"
        assert rerun_strategy["artifact_id"] == strategy["artifact_id"]
        assert rerun_strategy["checksum"] == strategy["checksum"]
        assert artifact_ids_after == artifact_ids_before
        assert intent_ids_after == intent_ids_before

        with _app_env(ctx.data_root, ctx.token):
            container = make_app_container()
            try:
                decision = container.get(DailyDecisionQueryFacade).get_report_v2(
                    strategy_id=strategy_id,
                    trade_date=ctx.trade_date,
                    account_id="real-paper",
                )
            finally:
                container.close()

        assert decision.identity["signal_date"] == ctx.trade_date
        assert decision.identity["intended_trade_date"] == INTENDED_TRADE_DATE
        assert decision.readiness["status"] in {"ready", "review"}
        assert decision.data["freshness"] == "ready"
        assert decision.data["dq_state"] == "passed"
        assert decision.run_package["artifact_id"] == strategy["artifact_id"]
        assert decision.run_package["checksum"] == strategy["checksum"]
        assert decision.run_package["checksum_valid"] is True
