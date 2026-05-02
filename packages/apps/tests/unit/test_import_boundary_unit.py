import sys


def test_apps_imports_successfully() -> None:
    import ditto_apps

    assert ditto_apps.__version__ == "0.1.0"


def test_apps_does_not_import_capability_packages_directly() -> None:
    """Apps should access capability packages through application, not directly.

    Apps may depend on: application, platform, kernel (transitively).
    Apps must not directly import: data, features, strategy, portfolio, risk,
    execution, backtest, analysis.
    """
    import ditto_apps  # noqa: F401

    loaded = {m for m in sys.modules if m.startswith("ditto_") and m != "ditto_apps"}
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
    forbidden = {m for m in loaded if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)}
    assert not forbidden, f"Apps imported forbidden packages directly: {sorted(forbidden)}"
