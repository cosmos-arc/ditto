import sys


def test_backtest_imports_successfully() -> None:
    import ditto_backtest

    assert ditto_backtest.__version__ == "0.1.0"


def test_backtest_does_not_import_forbidden_packages() -> None:
    """Backtest must not depend on analysis, apps, or application."""
    before = set(sys.modules)
    import ditto_backtest  # noqa: F401

    new_modules = set(sys.modules) - before
    forbidden_prefixes = (
        "ditto_analysis",
        "ditto_apps",
        "ditto_application",
    )
    forbidden = {
        m
        for m in new_modules
        if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)
    }
    assert not forbidden, f"Backtest imported forbidden packages: {sorted(forbidden)}"
