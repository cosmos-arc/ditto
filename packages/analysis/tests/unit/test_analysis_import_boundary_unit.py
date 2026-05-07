import sys


def test_analysis_imports_successfully() -> None:
    import ditto_analysis

    assert ditto_analysis.__name__ == "ditto_analysis"


def test_analysis_does_not_import_forbidden_packages() -> None:
    before = set(sys.modules)
    import ditto_analysis  # noqa: F401

    new_modules = set(sys.modules) - before
    forbidden_prefixes = (
        "ditto_application",
        "ditto_apps",
        "ditto_backtest",
        "ditto_data",
        "ditto_execution",
        "ditto_features",
        "ditto_portfolio",
        "ditto_risk",
        "ditto_strategy",
    )
    forbidden = {
        m
        for m in new_modules
        if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)
    }
    assert not forbidden, f"Analysis imported forbidden packages: {sorted(forbidden)}"
