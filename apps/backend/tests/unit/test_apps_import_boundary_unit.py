import sys


def test_apps_imports_successfully() -> None:
    import ditto_apps

    assert ditto_apps.__name__ == "ditto_apps"


def test_apps_does_not_import_capability_packages_directly() -> None:
    """Apps should access capability packages through application, not directly.

    Apps may depend on: application, platform, kernel (transitively).
    Apps must not directly import: data, features, strategy, portfolio, risk,
    execution, backtest, analysis.
    """
    before = set(sys.modules)
    import ditto_apps  # noqa: F401

    new_modules = set(sys.modules) - before
    forbidden_prefixes = (
        "ditto_strategy",
        "ditto_portfolio",
        "ditto_risk",
        "ditto_execution",
        "ditto_backtest",
        "ditto_analysis",
        "ditto_data",
        "ditto_features",
    )
    forbidden = {
        m
        for m in new_modules
        if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)
    }
    assert not forbidden, (
        f"Apps imported forbidden packages directly: {sorted(forbidden)}"
    )
