"""The NAV reconciliation CLI compares the latest retained disclosure."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
import yaml
from ditto_application.commands.quality_reconciliation import ReconcileSourcesHandler
from ditto_application.queries.market import MarketQueryFacade
from ditto_apps.cli.main import app
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.di.market import MarketProvider
from ditto_data.observability.metrics import register_metrics
from ditto_data.quality.engine import QualityEngine
from ditto_data.quality.spec import DatasetRules, DQSpec
from ditto_data.services.deps import MarketReaders
from ditto_data.services.market_service import MarketService
from ditto_platform.foundation import FileLockManager
from pytest_mock import MockerFixture
from typer.testing import CliRunner


@pytest.mark.parametrize("secondary_nav", [2.2, 3.2])
def test_cli_nav_reconciliation_uses_latest_disclosure(
    tmp_path: Path, mocker: MockerFixture, secondary_nav: float
) -> None:
    register_metrics()
    provider = MarketProvider()
    settings = DataStoreSettings(data_root=tmp_path)
    readers = provider.market_readers(settings, MagicMock())
    writer = provider.market_writers(
        settings, FileLockManager(tmp_path / "locks")
    ).etf_nav
    assert writer is not None
    writer.write(
        pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 10, 30)] * 2,
                "knowledge_date": [date(2026, 10, 31), date(2026, 11, 2)],
                "unit_nav": [2.1365, 2.2],
            }
        ),
        2026,
    )
    root = next(
        p
        for p in Path(__file__).resolve().parents
        if (p / "config/default/dq_rules").is_dir()
    )
    rules = yaml.safe_load((root / "config/default/dq_rules/etf_nav.yml").read_text())
    engine = QualityEngine(DQSpec(datasets={"etf_nav": DatasetRules(**rules)}))
    instruments = MagicMock()
    instruments.enrich_with_ticker.side_effect = lambda frame: frame.with_columns(
        ticker=pl.lit("510300")
    )
    resolver = MagicMock()
    resolver.resolve_secondary_ids.return_value = {"510300.SH": 1}
    secondary = MagicMock()
    secondary.fetch_fund_nav.return_value = pl.DataFrame(
        {
            "ticker": ["510300.SH"],
            "trade_date": [date(2026, 10, 30)],
            "unit_nav": [secondary_nav],
        }
    )
    handler = ReconcileSourcesHandler(
        engine=engine,
        secondary_source=MagicMock(),
        comparison_store=MagicMock(),
        instrument_store=instruments,
        secondary_identity_resolver=resolver,
        secondary_fund_nav_source=secondary,
    )
    container = MagicMock()
    container.get.side_effect = {
        ReconcileSourcesHandler: handler,
        MarketReaders: readers,
        MarketQueryFacade: MarketQueryFacade(MarketService(readers)),
        Path: tmp_path,
    }.__getitem__
    mocker.patch(
        "ditto_apps.cli.commands.ops.make_app_container", return_value=container
    )
    result = CliRunner().invoke(
        app, ["ops", "reconcile", "2026-10-30", "--dataset", "etf_nav"]
    )
    assert result.exit_code == 0, result.output
    assert "主源行数: 1" in result.output
    assert "主侧重复键=0" in result.output
    assert f"差异数={int(secondary_nav != 2.2)}" in result.output
    assert f"issues={int(secondary_nav != 2.2)}" in result.output
    assert readers.etf_nav is not None
    assert readers.etf_nav.read().height == 2
