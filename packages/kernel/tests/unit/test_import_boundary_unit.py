import sys


def test_kernel_imports_successfully() -> None:
    import ditto_kernel

    assert ditto_kernel.__version__ == "0.2.0"


def test_kernel_does_not_import_other_ditto_packages() -> None:
    import ditto_kernel  # noqa: F401

    loaded = {m for m in sys.modules if m.startswith("ditto_") and m != "ditto_kernel"}
    forbidden_prefixes = (
        "ditto_platform",
        "ditto_data",
        "ditto_features",
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
    assert not forbidden, f"Kernel imported other ditto packages: {sorted(forbidden)}"
