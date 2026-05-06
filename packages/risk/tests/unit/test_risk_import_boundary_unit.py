import sys


def test_risk_imports_successfully() -> None:
    import ditto_risk

    assert ditto_risk.__name__ == "ditto_risk"


def test_risk_does_not_import_forbidden_packages() -> None:
    before = set(sys.modules)
    import ditto_risk  # noqa: F401

    new_modules = set(sys.modules) - before
    forbidden_prefixes = (
        "ditto_analysis",
        "ditto_application",
        "ditto_apps",
        "ditto_backtest",
        "ditto_data",
        "ditto_execution",
        "ditto_features",
        "ditto_strategy",
    )
    forbidden = {
        m
        for m in new_modules
        if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)
    }
    assert not forbidden, f"Risk imported forbidden packages: {sorted(forbidden)}"
