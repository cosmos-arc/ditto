import sys


def test_portfolio_imports_successfully() -> None:
    import ditto_portfolio

    assert ditto_portfolio.__version__ == "0.1.0"


def test_portfolio_does_not_import_forbidden_packages() -> None:
    import ditto_portfolio  # noqa: F401

    loaded = {m for m in sys.modules if m.startswith("ditto_") and m != "ditto_portfolio"}
    forbidden_prefixes = (
        "ditto_strategy",
        "ditto_risk",
        "ditto_execution",
        "ditto_backtest",
        "ditto_analysis",
        "ditto_application",
        "ditto_apps",
    )
    forbidden = {m for m in loaded if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)}
    assert not forbidden, f"Portfolio imported forbidden packages: {sorted(forbidden)}"
