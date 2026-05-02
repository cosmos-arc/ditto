import sys


def test_platform_imports_successfully() -> None:
    import ditto_platform

    assert ditto_platform is not None


def test_platform_does_not_import_business_packages() -> None:
    """Platform may depend on kernel, but must not import business packages."""
    import ditto_platform  # noqa: F401

    loaded = {m for m in sys.modules if m.startswith("ditto_") and m != "ditto_platform"}
    forbidden_prefixes = (
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
    assert not forbidden, f"Platform imported business packages: {sorted(forbidden)}"
