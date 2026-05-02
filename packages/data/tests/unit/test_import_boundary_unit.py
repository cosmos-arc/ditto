import sys


def test_data_imports_successfully() -> None:
    import ditto_data

    assert ditto_data is not None


def test_data_does_not_import_forbidden_packages() -> None:
    import ditto_data  # noqa: F401

    loaded = {m for m in sys.modules if m.startswith("ditto_") and m != "ditto_data"}
    forbidden_prefixes = (
        "ditto_strategy",
        "ditto_portfolio",
        "ditto_risk",
        "ditto_execution",
        "ditto_backtest",
        "ditto_analysis",
        "ditto_application",
        "ditto_apps",
    )
    forbidden = {m for m in loaded if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)}
    assert not forbidden, f"Data imported forbidden packages: {sorted(forbidden)}"
