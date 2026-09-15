"""CMP-07 isolated live-fixture acceptance evidence."""

from __future__ import annotations

import runpy
import tempfile
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest
from ditto_application.queries.portfolio_comparison import (
    GetPortfolioComparisonQuery,
    PortfolioComparisonRequest,
)
from ditto_apps.registry.container import make_app_container


def test_portfolio_comparison_live_fixture_uses_production_read_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = Path(__file__).parents[4]
    namespace = runpy.run_path(
        str(repository_root / "scripts/evidence/portfolio_comparison_live_fixture.py"),
        run_name="portfolio_comparison_live_fixture_evidence",
    )
    seed = cast("Callable[[Path], dict[str, object]]", namespace["seed"])

    with tempfile.TemporaryDirectory(prefix="ditto-cmp-live-") as temporary_directory:
        root = Path(temporary_directory)
        evidence = seed(root)
        for name, path in {
            "DITTO_STATE_ROOT": root,
            "DITTO_CONFIG_ROOT": root / "config",
            "DITTO_CACHE_ROOT": root / "cache",
            "DITTO_LOG_DIR": root / "logs",
            "SQLITE_PATH": root / "metadata/metadata.sqlite",
            "DITTO_TRADING_SQLITE_PATH": root / "trading/trading.sqlite",
        }.items():
            monkeypatch.setenv(name, str(path))
        monkeypatch.setenv("ENVIRONMENT", "testing")
        params = parse_qs(urlsplit(str(evidence["frontend_path"])).query)
        container = make_app_container()
        try:
            comparison = container.get(GetPortfolioComparisonQuery).get(
                PortfolioComparisonRequest(
                    strategy_id=params["strategy_id"][0],
                    model_portfolio_id=params["model_portfolio_id"][0],
                    paper_account_id=params["paper_account_id"][0],
                    manual_account_id=params["manual_account_id"][0],
                    paper_session_id=params["paper_session_id"][0],
                    as_of=params["as_of"][0],
                    knowledge_cutoff=datetime.fromisoformat(
                        params["knowledge_cutoff"][0]
                    ),
                    publication_cutoff=datetime.fromisoformat(
                        params["publication_cutoff"][0]
                    ),
                    source_snapshot_ids=tuple(params["source_snapshot_ids"]),
                )
            )
            assert comparison.valuation_snapshot_id == evidence["valuation_snapshot_id"]
            assert comparison.model_vs_paper.attribution.fee_amount == Decimal("15.51")
        finally:
            container.close()

    assert evidence["artifact_checksum"] == (
        "sha256:a7ddd52a672dc03e303a537e6a8dec9294fedbbb56b9c2900173e034d1f1d93f"
    )
    assert Decimal(cast("str", evidence["paper_unfilled_bps"])) == Decimal("3000")
    assert Decimal(cast("str", evidence["paper_fee_amount"])) == Decimal("15.51")
    assert Decimal(cast("str", evidence["manual_user_choice_bps"])) == Decimal(
        "2277.48"
    )
    assert evidence["scenario_turnover"] == 0.23328831
    assert "mode=comparison" in cast("str", evidence["frontend_path"])
    assert "valuation_snapshot_id=" in cast("str", evidence["frontend_path"])
