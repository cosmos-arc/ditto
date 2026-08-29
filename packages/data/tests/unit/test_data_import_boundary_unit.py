import sys


def test_data_imports_successfully() -> None:
    import ditto_data

    assert ditto_data is not None


def test_data_does_not_import_forbidden_packages() -> None:
    before = set(sys.modules)
    import ditto_data  # noqa: F401

    new_modules = set(sys.modules) - before
    forbidden_prefixes = (
        "ditto_agent",
        "ditto_strategy",
        "ditto_portfolio",
        "ditto_risk",
        "ditto_execution",
        "ditto_backtest",
        "ditto_analysis",
        "ditto_application",
        "ditto_apps",
    )
    forbidden = {
        m
        for m in new_modules
        if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)
    }
    assert not forbidden, f"Data imported forbidden packages: {sorted(forbidden)}"
