import sys


def test_kernel_imports_successfully() -> None:
    import ditto_kernel

    assert ditto_kernel.__name__ == "ditto_kernel"


def test_kernel_does_not_import_other_ditto_packages() -> None:
    before = set(sys.modules)
    import ditto_kernel  # noqa: F401

    new_modules = set(sys.modules) - before
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
    forbidden = {
        m
        for m in new_modules
        if any(m == p or m.startswith(p + ".") for p in forbidden_prefixes)
    }
    assert not forbidden, f"Kernel imported other ditto packages: {sorted(forbidden)}"
