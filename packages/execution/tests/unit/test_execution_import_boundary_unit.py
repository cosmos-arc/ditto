import sys


def test_execution_imports_successfully() -> None:
    import ditto_execution

    assert ditto_execution.__name__ == "ditto_execution"


def test_execution_does_not_import_forbidden_packages() -> None:
    before = set(sys.modules)
    import ditto_execution  # noqa: F401

    new_modules = set(sys.modules) - before
    forbidden_prefixes = (
        "ditto_data",
        "ditto_features",
        "ditto_strategy",
        "ditto_portfolio",
        "ditto_risk",
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
    assert not forbidden, f"Execution imported forbidden packages: {sorted(forbidden)}"
