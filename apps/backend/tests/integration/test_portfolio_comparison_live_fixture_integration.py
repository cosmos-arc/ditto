"""CMP-07 isolated live-fixture acceptance evidence."""

from __future__ import annotations

import runpy
import tempfile
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import cast


def test_portfolio_comparison_live_fixture_uses_production_read_paths() -> None:
    repository_root = Path(__file__).parents[4]
    namespace = runpy.run_path(
        str(repository_root / "scripts/evidence/portfolio_comparison_live_fixture.py"),
        run_name="portfolio_comparison_live_fixture_evidence",
    )
    seed = cast("Callable[[Path], dict[str, object]]", namespace["seed"])

    with tempfile.TemporaryDirectory(
        prefix="ditto-cmp-live-",
        dir="/private/tmp",
    ) as temporary_directory:
        evidence = seed(Path(temporary_directory))

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
