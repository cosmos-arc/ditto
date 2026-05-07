import sys


def test_strategy_imports_successfully() -> None:
    import ditto_strategy

    assert ditto_strategy.__name__ == "ditto_strategy"


def test_strategy_does_not_import_forbidden_packages() -> None:
    before = set(sys.modules)
    import ditto_strategy  # noqa: F401

    new_modules = set(sys.modules) - before
    forbidden_prefixes = (
        "ditto_data",
        "ditto_features",
        "ditto_portfolio",
        "ditto_risk",
        "ditto_application",
        "ditto_apps",
        "ditto_backtest",
        "ditto_analysis",
        "ditto_execution",
    )
    forbidden = {
        m
        for m in new_modules
        if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)
    }
    assert not forbidden, f"Strategy imported forbidden packages: {sorted(forbidden)}"
