import sys


def test_execution_imports_successfully() -> None:
    import ditto_execution

    assert ditto_execution.__version__ == "0.1.0"


def test_execution_does_not_import_forbidden_packages() -> None:
    import ditto_execution  # noqa: F401

    loaded = {m for m in sys.modules if m.startswith("ditto_") and m != "ditto_execution"}
    forbidden_prefixes = (
        "ditto_strategy",
        "ditto_portfolio",
        "ditto_risk",
        "ditto_backtest",
        "ditto_analysis",
        "ditto_application",
        "ditto_apps",
    )
    forbidden = {m for m in loaded if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)}
    assert not forbidden, f"Execution imported forbidden packages: {sorted(forbidden)}"
