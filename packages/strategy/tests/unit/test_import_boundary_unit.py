import sys


def test_strategy_imports_successfully() -> None:
    import ditto_strategy

    assert ditto_strategy.__version__ == "0.1.0"


def test_strategy_does_not_import_forbidden_packages() -> None:
    import ditto_strategy  # noqa: F401

    loaded = {m for m in sys.modules if m.startswith("ditto_") and m != "ditto_strategy"}
    forbidden_prefixes = (
        "ditto_application",
        "ditto_apps",
        "ditto_backtest",
        "ditto_analysis",
        "ditto_execution",
    )
    forbidden = {m for m in loaded if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)}
    assert not forbidden, f"Strategy imported forbidden packages: {sorted(forbidden)}"
